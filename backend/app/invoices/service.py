"""FD-041: invoice calculations - line totals, subtotal, tax/discount,
grand total. Pure computation only, no routes/schemas yet - the
authorization-gated CRUD/editing surface that actually calls these
functions is FD-042's job (it depends on FD-041 *and* FD-015's RBAC
together; this task depends on neither).

Server-authoritative (Epic E06's own acceptance criterion: "client-
submitted totals are never authoritative"): every function here
*recomputes* a value from its real inputs (quantity/unit_price,
`tax_rate`, `discount_type`/`discount_value`) rather than accepting
one. Whichever future route creates or edits an `Invoice`/
`InvoiceLineItem` must call these instead of trusting anything the
client sent for `line_total`/`subtotal`/`tax_total`/`discount_total`/
`total`.

Rounding policy, resolved with the user (Section 35 open decision #6)
rather than guessed:
- `line_total` = `quantity * unit_price`, rounded to the column's own
  2-decimal precision with `ROUND_HALF_UP` - not itself a disputed
  policy, just how a product gets stored in a `Numeric(12, 2)` column.
- Per-line tax amounts are summed at full decimal precision *before*
  rounding - `tax_total` is only rounded once, at the end, not
  line-by-line-then-summed (the user's explicit choice over the
  per-line-rounding alternative).
- `discount_total` is either `discount_value` directly (`flat`) or
  `round(subtotal * discount_value / 100)` (`percentage`) - the user's
  explicit choice to support both, where FD-040's schema only had the
  computed `discount_total` output with no input to compute it from.
- `total` is rejected (never silently clamped) if discounting would
  drive it negative - a financial record should error loudly on a bad
  input, not quietly rewrite it.
"""

import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import func
from sqlalchemy.exc import IntegrityError

from app.activity.service import log_activity
from app.errors import APIError
from app.extensions import db
from app.models import Customer, CustomerStatus, DiscountType, Invoice, InvoiceLineItem, InvoiceStatus, Payment

_CENT = Decimal("0.01")


def _round_money(value: Decimal) -> Decimal:
    return value.quantize(_CENT, rounding=ROUND_HALF_UP)


def compute_line_total(quantity: Decimal, unit_price: Decimal) -> Decimal:
    """The one place a line item's own total is computed - whichever
    future endpoint creates/edits an `InvoiceLineItem` must call this
    rather than accepting a client-submitted `line_total`."""
    return _round_money(quantity * unit_price)


def recalculate_invoice(invoice: Invoice) -> None:
    """Recomputes `subtotal`/`tax_total`/`discount_total`/`total` on
    `invoice` from its current `line_items` and discount input,
    in place. Does not commit - the caller (a future FD-042 endpoint)
    controls the transaction, same convention every other service
    function in this codebase follows.

    Does not itself recompute each line's own `line_total` - that's
    `compute_line_total`'s job, called whenever a line item is
    created/edited; this function only aggregates whatever
    `line_total`/`tax_rate` values the line items already carry.
    """
    if invoice.discount_value < Decimal("0.00"):
        raise APIError(
            "Discount value must not be negative.",
            status_code=422,
            code="INVALID_DISCOUNT",
            details={"discount_value": "must not be negative"},
        )
    # FD-042 addition: a percentage above 100 isn't caught by the
    # negative-total check below, since a large enough tax_rate can
    # offset it into a still-positive total (e.g. subtotal 100, tax 60,
    # discount_value 150% -> discount_total 150, total 10 - positive,
    # but a "150% discount" is nonsensical regardless). Enforced here
    # too, not just at the schema layer (CreateInvoiceRequest/
    # UpdateInvoiceRequest), so this invariant holds for every caller
    # of this function, not only ones that went through the API schema.
    if invoice.discount_type == DiscountType.PERCENTAGE and invoice.discount_value > Decimal("100.00"):
        raise APIError(
            "A percentage discount must not exceed 100.",
            status_code=422,
            code="INVALID_DISCOUNT",
            details={"discount_value": "must not exceed 100 when discount_type is percentage"},
        )

    subtotal = Decimal("0.00")
    tax_total_unrounded = Decimal("0")
    for item in invoice.line_items:
        subtotal += item.line_total
        if item.tax_rate is not None:
            tax_total_unrounded += item.line_total * item.tax_rate / Decimal("100")
    tax_total = _round_money(tax_total_unrounded)

    if invoice.discount_type == DiscountType.PERCENTAGE:
        discount_total = _round_money(subtotal * invoice.discount_value / Decimal("100"))
    else:
        discount_total = invoice.discount_value

    total = subtotal + tax_total - discount_total
    if total < Decimal("0.00"):
        # Not necessarily the discount's fault - e.g. a negative line
        # quantity (unvalidated by this task) could also drive this -
        # so the message/code stay generic rather than naming discount_value.
        raise APIError(
            "This invoice's total cannot be negative.",
            status_code=422,
            code="NEGATIVE_TOTAL",
            details={"total": "discount must not exceed subtotal plus tax"},
        )

    invoice.subtotal = subtotal
    invoice.tax_total = tax_total
    invoice.discount_total = discount_total
    invoice.total = total


def build_line_item(
    organization_id,
    invoice_id,
    *,
    description: str,
    quantity: Decimal,
    unit_price: Decimal,
    tax_rate: Decimal | None,
) -> InvoiceLineItem:
    """Constructs a line item with a server-computed `line_total` -
    never accepts one from a caller. Doesn't add it to the session or
    recalculate the parent invoice; the caller (FD-042) is responsible
    for both, the same "service functions don't own the transaction"
    convention every other function here follows."""
    return InvoiceLineItem(
        organization_id=organization_id,
        invoice_id=invoice_id,
        description=description,
        quantity=quantity,
        unit_price=unit_price,
        tax_rate=tax_rate,
        line_total=compute_line_total(quantity, unit_price),
    )


# ---------------------------------------------------------------------------
# FD-042: invoice lifecycle (create/retrieve, controlled Draft-only editing,
# issue, cancel) and the overdue-status refresh. Section 35 open decision #7
# ("void-only vs. credit-note corrections") was resolved with the user in
# favor of credit-note-style corrections for *issued* invoices - but that
# needs a new entity beyond FD-040's schema, which is new scope outside this
# task's own "lifecycle + controlled editing" title and isn't in the
# original backlog. This task implements the *locking* half only (once
# issued, financial details are immutable here); the correction mechanism
# itself is necessary follow-up work for a future task, not built now.
#
# `Permission.INVOICE_PAYMENT_MANAGE` (FD-015) is `full` for Owner/
# Accountant and `none` for every other role - no scope nuance to apply
# beyond `require_permission`'s own gate, the same simple shape as
# `CUSTOMER_MANAGE`/`DEPARTMENT_MANAGE`.
# ---------------------------------------------------------------------------


def _set_currency(invoice: Invoice, currency: str) -> None:
    # Invoice.currency's own @validates (FD-042 addition) normalizes
    # case and checks length - converted to a 422 here rather than
    # letting the bare ValueError escape as an unhandled 500, same
    # pattern as every other _set_<field> helper in this codebase.
    try:
        invoice.currency = currency
    except ValueError as exc:
        raise APIError(str(exc), status_code=422, code="VALIDATION_ERROR", details={"currency": str(exc)})


def _validate_customer(organization_id: uuid.UUID, customer_id: uuid.UUID) -> None:
    """Mirrors app.customer_requests.service._validate_customer exactly:
    customer_id must reference an *active* Customer in this organization.
    A new invoice can't be created against (or edited onto) an archived
    customer, though an existing invoice stays fully usable if its
    customer is archived later."""
    customer = db.session.query(Customer).filter_by(id=customer_id, organization_id=organization_id).first()
    if customer is None or customer.status != CustomerStatus.ACTIVE:
        raise APIError(
            "customer_id must reference an active customer in this organization.",
            status_code=422,
            code="INVALID_CUSTOMER",
            details={"customer_id": "must reference an active customer in this organization"},
        )


def _build_line_items(organization_id: uuid.UUID, invoice_id: uuid.UUID, line_items: list[dict]) -> list[InvoiceLineItem]:
    """`line_items` is a list of plain dicts (description/quantity/
    unit_price/tax_rate) - the shape both CreateInvoiceRequest's and
    UpdateInvoiceRequest's own `line_items` take once the route layer
    calls `.model_dump()` on them, so both callers can pass the same
    shape through without one needing real pydantic objects and the
    other plain dicts."""
    return [
        build_line_item(
            organization_id,
            invoice_id,
            description=item["description"],
            quantity=item["quantity"],
            unit_price=item["unit_price"],
            tax_rate=item.get("tax_rate"),
        )
        for item in line_items
    ]


_MAX_INVOICE_NUMBER_ATTEMPTS = 5


def _generate_invoice_number(organization_id: uuid.UUID, attempt: int) -> str:
    """Sequential per organization ("INV-0001", "INV-0002", ...) -
    server-generated, never client-supplied (neither CreateInvoiceRequest
    nor UpdateInvoiceRequest accepts invoice_number), consistent with
    every other server-computed invoice field. Simpler than the
    "INV-2026-0001" year-based example in FD-040's own model docstring -
    nothing requires year-based numbering, and a flat counter is the
    more predictable choice for V1. Counts *every* invoice ever created
    in the organization, cancelled ones included, so a number is never
    reused. `attempt` disambiguates a uniqueness race (two concurrent
    creates computing the same count before either commits) by
    offsetting the candidate sequence - simpler than
    app.organizations.service._generate_unique_slug's random-suffix
    retry, since invoice numbers are meant to look sequential."""
    count = db.session.query(func.count(Invoice.id)).filter(Invoice.organization_id == organization_id).scalar()
    sequence = count + 1 + attempt
    return f"INV-{sequence:04d}"


def create_invoice(
    organization_id: uuid.UUID,
    creator_membership_id: uuid.UUID,
    *,
    customer_id: uuid.UUID,
    currency: str,
    issue_date: date | None,
    due_date: date | None,
    notes: str | None,
    payment_terms: str | None,
    discount_type: DiscountType,
    discount_value: Decimal,
    line_items: list[dict],
) -> Invoice:
    """FD-042. Always starts Draft (the model's own default) - `status`
    isn't accepted here, same convention as CustomerRequest/Task's own
    create functions. A Draft may legitimately have zero line items
    (FD-040's own docstring) - `issue_invoice` is what requires at
    least one. `created_by` is always the caller's own membership,
    never accepted from the request body."""
    _validate_customer(organization_id, customer_id)

    last_error = None
    for attempt in range(_MAX_INVOICE_NUMBER_ATTEMPTS):
        invoice = Invoice(
            organization_id=organization_id,
            customer_id=customer_id,
            invoice_number=_generate_invoice_number(organization_id, attempt),
            issue_date=issue_date,
            due_date=due_date,
            notes=notes,
            payment_terms=payment_terms,
            discount_type=discount_type,
            discount_value=discount_value,
            created_by=creator_membership_id,
        )
        _set_currency(invoice, currency)
        db.session.add(invoice)
        try:
            db.session.flush()
        except IntegrityError:
            db.session.rollback()
            last_error = "invoice_number collision"
            continue
        break
    else:
        raise RuntimeError(
            f"Could not generate a unique invoice_number after {_MAX_INVOICE_NUMBER_ATTEMPTS} attempts: {last_error}"
        )

    invoice.line_items = _build_line_items(organization_id, invoice.id, line_items)

    try:
        recalculate_invoice(invoice)
    except APIError:
        db.session.rollback()
        raise

    log_activity(
        organization_id,
        creator_membership_id,
        "invoice_created",
        "invoice",
        invoice.id,
        metadata={"invoice_number": invoice.invoice_number, "total": str(invoice.total)},
    )
    db.session.commit()
    return invoice


def _today_in_timezone(organization_timezone: str, *, now: datetime | None = None) -> date:
    """Identical in intent to app.tasks.service._today_in_timezone
    (FD-033) - "today" is always the calling organization's own local
    calendar date, never the server's. Duplicated here rather than
    imported since there's no shared utility module in this codebase
    for it yet; see that function's own docstring for the full
    reasoning (unrecognized zone names fall back to UTC rather than
    raising, `now` is injectable for deterministic boundary tests)."""
    try:
        tz = ZoneInfo(organization_timezone)
    except (ZoneInfoNotFoundError, ValueError, TypeError):
        tz = timezone.utc
    reference = now if now is not None else datetime.now(timezone.utc)
    return reference.astimezone(tz).date()


# FR-025's `overdue` is a real stored InvoiceStatus value (FD-040) -
# unlike Task's own overdue detection (FD-033), which layers a
# *computed*, read-only `is_overdue` flag on top of a status with no
# such value. So this actually transitions and persists `status`,
# applied as a bulk UPDATE across the whole organization before every
# get/list read (not a per-row Python loop) - that way a `?status=overdue`
# filter sees accurate rows too, not just whichever single invoice a
# caller happens to fetch. This substitutes for the "scheduled daily"
# background job spec Section 14 names, until that scheduler actually
# exists - same bootstrapping rationale FD-033 already established.
# `partially_paid` is included for forward compatibility with FD-043
# (payments), even though nothing in this task's own tests can reach
# that status yet.
_OVERDUE_ELIGIBLE_STATUSES = (InvoiceStatus.SENT, InvoiceStatus.PARTIALLY_PAID)


def _refresh_overdue_invoices(organization_id: uuid.UUID, organization_timezone: str, *, now: datetime | None = None) -> None:
    today = _today_in_timezone(organization_timezone, now=now)
    db.session.query(Invoice).filter(
        Invoice.organization_id == organization_id,
        Invoice.status.in_(_OVERDUE_ELIGIBLE_STATUSES),
        Invoice.due_date.isnot(None),
        Invoice.due_date < today,
    ).update({Invoice.status: InvoiceStatus.OVERDUE}, synchronize_session="fetch")
    db.session.commit()


def get_invoice_or_404(organization_id: uuid.UUID, invoice_id: uuid.UUID, *, for_update: bool = False) -> Invoice:
    """`for_update=True` (FD-043) issues `SELECT ... FOR UPDATE`,
    locking the row for the rest of the caller's transaction - used by
    `app.payments.service.record_payment` immediately before its
    check-then-act balance validation, so two concurrent payment
    requests against the same invoice (with two different, individually
    valid `idempotency_key`s - the idempotency unique constraint alone
    only catches a *repeated* key) serialize on this row instead of
    both reading the same pre-payment balance and both passing the
    overpayment check. Every plain read (GET/list) leaves this `False`
    - there's no reason to lock a row nothing is about to mutate."""
    query = db.session.query(Invoice).filter_by(id=invoice_id, organization_id=organization_id)
    if for_update:
        query = query.with_for_update()
    invoice = query.first()
    if invoice is None:
        raise APIError("Not found.", status_code=404, code="NOT_FOUND")
    return invoice


def get_invoice(
    organization_id: uuid.UUID, invoice_id: uuid.UUID, organization_timezone: str, *, now: datetime | None = None
) -> Invoice:
    _refresh_overdue_invoices(organization_id, organization_timezone, now=now)
    return get_invoice_or_404(organization_id, invoice_id)


def list_invoices(
    organization_id: uuid.UUID,
    *,
    organization_timezone: str,
    customer_id: uuid.UUID | None,
    status: InvoiceStatus | None,
    due_date_from: date | None,
    due_date_to: date | None,
    page: int,
    per_page: int,
    now: datetime | None = None,
) -> tuple[list[Invoice], int]:
    _refresh_overdue_invoices(organization_id, organization_timezone, now=now)

    query = db.session.query(Invoice).filter(Invoice.organization_id == organization_id)
    if customer_id is not None:
        query = query.filter(Invoice.customer_id == customer_id)
    if status is not None:
        query = query.filter(Invoice.status == status)
    if due_date_from is not None:
        query = query.filter(Invoice.due_date >= due_date_from)
    if due_date_to is not None:
        query = query.filter(Invoice.due_date <= due_date_to)

    total = query.count()
    invoices = query.order_by(Invoice.created_at.desc()).offset((page - 1) * per_page).limit(per_page).all()
    return invoices, total


_EDITABLE_INVOICE_FIELDS = ("issue_date", "due_date", "notes", "payment_terms", "discount_type", "discount_value")


def update_invoice(organization_id: uuid.UUID, invoice_id: uuid.UUID, fields: dict) -> Invoice:
    """FD-042: PATCH, Draft-only - any other status is `422
    INVOICE_LOCKED` (the "Important invoice rule": once issued,
    financial details are never silently overwritten; controlled
    corrections to an issued invoice are a future credit-note task, not
    this endpoint). `fields` is the caller's own
    `UpdateInvoiceRequest.model_dump(exclude_unset=True)` - only keys
    actually present are applied, same convention
    app.customers.service.update_customer established. `line_items`,
    if present, replaces the entire set (delete-orphan cascade handles
    the old rows) rather than exposing separate add/remove/edit-one-line
    sub-endpoints - the simplest shape that still lets a Draft be fully
    reworked before issuing. `invoice_number`/`status` are never
    accepted (not in `_EDITABLE_INVOICE_FIELDS` or handled below) -
    status changes go through `issue_invoice`/`cancel_invoice` only.
    Totals are unconditionally recalculated, even if only an unrelated
    field like `notes` changed - cheap, and removes any risk of a
    missed case leaving stale totals."""
    invoice = get_invoice_or_404(organization_id, invoice_id)
    if invoice.status != InvoiceStatus.DRAFT:
        raise APIError(
            "Cannot edit an invoice once it has been issued.",
            status_code=422,
            code="INVOICE_LOCKED",
            details={"status": "only a draft invoice can be edited"},
        )

    if "customer_id" in fields:
        _validate_customer(organization_id, fields["customer_id"])
        invoice.customer_id = fields["customer_id"]
    if "currency" in fields:
        _set_currency(invoice, fields["currency"])
    if "line_items" in fields:
        invoice.line_items = _build_line_items(organization_id, invoice.id, fields["line_items"])

    for field in _EDITABLE_INVOICE_FIELDS:
        if field in fields:
            setattr(invoice, field, fields[field])

    try:
        recalculate_invoice(invoice)
    except APIError:
        db.session.rollback()
        raise

    db.session.commit()
    return invoice


_CANCELLABLE_STATUSES = (InvoiceStatus.DRAFT, InvoiceStatus.SENT, InvoiceStatus.OVERDUE)


def issue_invoice(organization_id: uuid.UUID, invoice_id: uuid.UUID) -> Invoice:
    """FD-042: draft -> sent, the action that locks financial details
    going forward. Not idempotent (unlike cancel) - issuing is a
    meaningful one-time action, so re-issuing an already-sent invoice
    is `422 INVALID_STATUS_TRANSITION`, not a silent no-op. Requires at
    least one line item - issuing an invoice that bills nothing doesn't
    make sense, even though a bare Draft may otherwise have zero
    (FD-040's own docstring)."""
    invoice = get_invoice_or_404(organization_id, invoice_id)
    if invoice.status != InvoiceStatus.DRAFT:
        raise APIError(
            f"Cannot issue an invoice from status '{invoice.status.value}'.",
            status_code=422,
            code="INVALID_STATUS_TRANSITION",
            details={"status": "only a draft invoice can be issued"},
        )
    if not invoice.line_items:
        raise APIError(
            "Cannot issue an invoice with no line items.",
            status_code=422,
            code="EMPTY_INVOICE",
            details={"line_items": "at least one line item is required to issue an invoice"},
        )

    invoice.status = InvoiceStatus.SENT
    db.session.commit()
    return invoice


def cancel_invoice(organization_id: uuid.UUID, invoice_id: uuid.UUID) -> Invoice:
    """FD-042: -> cancelled. Idempotent on an already-cancelled invoice
    (`200` no-op, same convention app.customers.service.archive_customer
    already established) - unlike issue_invoice, "cancel" is naturally
    idempotent (it's a terminal state, not a one-time trigger). Blocked
    once money has moved (partially_paid/paid) - the Important Invoice
    Rule, and this task's own resolved Section 35 #7 answer: a
    correction to an issued, paid-against invoice goes through a
    future credit-note mechanism, never a cancellation of this one."""
    invoice = get_invoice_or_404(organization_id, invoice_id)
    if invoice.status == InvoiceStatus.CANCELLED:
        return invoice
    if invoice.status not in _CANCELLABLE_STATUSES:
        raise APIError(
            f"Cannot cancel an invoice from status '{invoice.status.value}'.",
            status_code=422,
            code="INVALID_STATUS_TRANSITION",
            details={"status": "cannot cancel once a payment has been recorded"},
        )

    invoice.status = InvoiceStatus.CANCELLED
    db.session.commit()
    return invoice


# ---------------------------------------------------------------------------
# FD-044: financial API & reports (FR-028/FR-029). Gated by
# `Permission.FINANCIAL_REPORTS_VIEW` - deliberately NOT the same
# permission as the rest of this module (`INVOICE_PAYMENT_MANAGE`),
# even though both happen to be `full` for Owner/Accountant and `none`
# for everyone else in today's matrix. FR-029 ("only Owner and
# authorized financial roles see sensitive financial data") names
# *financial reports* as its own restriction target, distinct from
# day-to-day invoice/payment management - using the semantically
# correct permission here means a future role change to either one
# doesn't silently affect the other.
#
# Scope judgment calls (not Section 35 items, not money-integrity
# ambiguities - ordinary reporting-definition choices, documented
# rather than asked about):
# - `total_invoiced` counts every invoice that was ever actually
#   issued and not voided (`sent`/`partially_paid`/`overdue`/`paid`) -
#   a `draft` was never billed to anyone, and a `cancelled` invoice
#   represents withdrawn billing, not real revenue.
# - `total_collected`/`outstanding_balance` are all-time cumulative
#   totals; `monthly_revenue_collected` is the one period-scoped
#   metric, exactly matching FR-028's own wording ("total invoiced,
#   total collected, outstanding balance, overdue invoices, *monthly*
#   revenue collected, recent payments").
# - The full FR-034 date-filter taxonomy (last 7/30/90 days, custom
#   range, etc.) is deliberately NOT built here - that's FD-052's
#   (Analytics API) job. This endpoint only accepts an optional
#   `period_start`/`period_end` override for the one period-scoped
#   metric, defaulting to the current calendar month in the
#   organization's own timezone.
# - `recent_payments` is a fixed-size list (not a paginated/filterable
#   endpoint of its own) - a dashboard widget, not a payments browser;
#   a caller wanting more belongs at the per-invoice
#   `GET .../invoices/{id}/payments` endpoint (FD-043) instead.
# ---------------------------------------------------------------------------

# Mirrors _OVERDUE_ELIGIBLE_STATUSES's own reasoning but for the
# reporting question "was this invoice ever actually billed" rather
# than "could this invoice still become overdue" - `paid` belongs here
# (it was billed and fully collected) but not in the overdue set
# (it can never become overdue again).
_EVER_INVOICED_STATUSES = (InvoiceStatus.SENT, InvoiceStatus.PARTIALLY_PAID, InvoiceStatus.OVERDUE, InvoiceStatus.PAID)

_RECENT_PAYMENTS_LIMIT = 10


def _sum_decimal(query) -> Decimal:
    result = query.scalar()
    return result if result is not None else Decimal("0.00")


def _current_month_bounds(organization_timezone: str, *, now: datetime | None = None) -> tuple[date, date]:
    today = _today_in_timezone(organization_timezone, now=now)
    period_start = today.replace(day=1)
    if today.month == 12:
        next_month_start = today.replace(year=today.year + 1, month=1, day=1)
    else:
        next_month_start = today.replace(month=today.month + 1, day=1)
    period_end = next_month_start - timedelta(days=1)
    return period_start, period_end


def get_financial_summary(
    organization_id: uuid.UUID,
    organization_timezone: str,
    *,
    period_start: date | None = None,
    period_end: date | None = None,
    now: datetime | None = None,
) -> dict:
    """FD-044 (FR-028). Refreshes overdue statuses first (FD-042) so
    `overdue_invoice_count` reflects reality even if nothing has
    `GET`/listed this organization's invoices recently. `period_start`/
    `period_end` must be given together or not at all - defaulting to
    the current calendar month when omitted (see module-level comment
    above for why this isn't the full FD-052 date-filter taxonomy)."""
    _refresh_overdue_invoices(organization_id, organization_timezone, now=now)

    if period_start is None and period_end is None:
        period_start, period_end = _current_month_bounds(organization_timezone, now=now)

    total_invoiced = _sum_decimal(
        db.session.query(func.sum(Invoice.total)).filter(
            Invoice.organization_id == organization_id, Invoice.status.in_(_EVER_INVOICED_STATUSES)
        )
    )
    total_collected = _sum_decimal(
        db.session.query(func.sum(Payment.amount)).filter(Payment.organization_id == organization_id)
    )
    # Always correct, not just approximately so: every Payment in this
    # organization was necessarily recorded against an invoice that
    # was, at the time, in a payable status (app.payments.service's
    # own _PAYABLE_STATUSES - sent/partially_paid/overdue), and every
    # one of those statuses - plus the paid status a full payment
    # advances it to - is already in _EVER_INVOICED_STATUSES above. So
    # total_collected is always a subset of total_invoiced's own
    # underlying invoices, and this subtraction is exact, never an
    # approximation that could drift from summing each invoice's own
    # (total - amount_paid) individually.
    outstanding_balance = total_invoiced - total_collected

    overdue_invoice_count = (
        db.session.query(func.count(Invoice.id))
        .filter(Invoice.organization_id == organization_id, Invoice.status == InvoiceStatus.OVERDUE)
        .scalar()
    )

    monthly_revenue_collected = _sum_decimal(
        db.session.query(func.sum(Payment.amount)).filter(
            Payment.organization_id == organization_id,
            Payment.payment_date >= period_start,
            Payment.payment_date <= period_end,
        )
    )

    recent_payments = (
        db.session.query(Payment)
        .filter(Payment.organization_id == organization_id)
        .order_by(Payment.created_at.desc())
        .limit(_RECENT_PAYMENTS_LIMIT)
        .all()
    )

    return {
        "total_invoiced": total_invoiced,
        "total_collected": total_collected,
        "outstanding_balance": outstanding_balance,
        "overdue_invoice_count": overdue_invoice_count,
        "period_start": period_start,
        "period_end": period_end,
        "monthly_revenue_collected": monthly_revenue_collected,
        "recent_payments": recent_payments,
    }


def list_invoice_line_items(organization_id: uuid.UUID, invoice_id: uuid.UUID) -> list[InvoiceLineItem]:
    """FD-046: read-only - line items are only ever written as a side
    effect of `create_invoice`/`update_invoice`, never through a
    direct endpoint of their own, same "no separate create path"
    convention `list_request_history` already established. Added
    because no endpoint anywhere returned individual line items
    before this - `Invoice.to_public_dict()` only ever exposed the
    computed aggregates (`subtotal`/`tax_total`/...), which is enough
    for a list/summary view but not for an *editor*, this task's own
    job, to show a caller what they'd previously entered. A separate
    endpoint (mirroring comments/history) rather than embedding the
    list in `Invoice.to_public_dict()` itself avoids an N+1 query on
    every row of `GET .../invoices` (list), which never needs this.
    Ordered by `created_at` - insertion order, not any business
    ranking - same as the relationship's own default ordering."""
    get_invoice_or_404(organization_id, invoice_id)

    return (
        db.session.query(InvoiceLineItem)
        .filter_by(organization_id=organization_id, invoice_id=invoice_id)
        .order_by(InvoiceLineItem.created_at.asc())
        .all()
    )
