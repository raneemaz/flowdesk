"""FD-043: payment recording - partial payments, transactional balance
update, idempotent.

Idempotency (Section 13's mandatory "duplicate payment request -> no
duplicate transaction created" scenario) is implemented via a
client-supplied `idempotency_key`, at the user's explicit direction
over a server-side duplicate-detection heuristic (e.g. matching on
amount/method/reference within a time window) - see `Payment.idempotency_key`'s
own model docstring (FD-043) for why.

Overpayment is rejected, at the user's explicit direction over
allowing it: the sum of a payable invoice's recorded payments can
never exceed `invoice.total` (Epic E06's own acceptance criterion).
This is a check-then-act validation (read the current balance, then
insert), which two concurrent requests using two different,
individually-valid idempotency keys could otherwise both pass before
either commits - the idempotency unique constraint alone only catches
a *repeated* key, never two legitimately-different ones. Closed by
locking the invoice row (`get_invoice_or_404(..., for_update=True)`)
for the duration of the balance check and insert, so a second,
concurrent request against the same invoice blocks until the first
commits, then re-reads the now-current balance.

Uses `Permission.INVOICE_PAYMENT_MANAGE` (FD-015) - the same
permission `app.invoices.service` uses; there is no separate "payment"
permission in the matrix, and the permission's own name already covers
both.
"""

import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy.exc import IntegrityError

from app.errors import APIError
from app.extensions import db
from app.invoices.service import get_invoice_or_404
from app.models import Invoice, InvoiceStatus, Payment

# A payment may only be recorded against an invoice that's actually
# been billed and isn't already fully settled or voided - draft
# (never issued) and cancelled (voided) are never payable; paid is
# excluded by construction (its balance_due is already 0, so any
# positive amount would be rejected as an overpayment below anyway,
# but listing it explicitly here gives a clearer error than relying on
# that side effect).
_PAYABLE_STATUSES = (InvoiceStatus.SENT, InvoiceStatus.PARTIALLY_PAID, InvoiceStatus.OVERDUE)


def get_invoice_balance(invoice: Invoice) -> tuple[Decimal, Decimal]:
    """Returns `(amount_paid, balance_due)` for `invoice`, computed
    from its actually-recorded `payments` every time - never a stored
    column, so it can never drift out of sync with the real rows (the
    same "derive, don't duplicate" reasoning as FD-033's `is_overdue`)."""
    amount_paid = sum((payment.amount for payment in invoice.payments), Decimal("0.00"))
    balance_due = invoice.total - amount_paid
    return amount_paid, balance_due


def _set_method(payment: Payment, method: str) -> None:
    # Payment.method's own @validates (FD-040) strips and rejects a
    # blank result - converted to a 422 here rather than letting the
    # bare ValueError escape as an unhandled 500, same pattern as every
    # other _set_<field> helper in this codebase.
    try:
        payment.method = method
    except ValueError as exc:
        raise APIError(str(exc), status_code=422, code="VALIDATION_ERROR", details={"method": str(exc)})


def _find_existing_payment(organization_id: uuid.UUID, idempotency_key: str) -> Payment | None:
    return db.session.query(Payment).filter_by(organization_id=organization_id, idempotency_key=idempotency_key).first()


def _ensure_replay_matches(
    existing: Payment,
    *,
    invoice_id: uuid.UUID,
    amount: Decimal,
    payment_date: date,
    method: str,
    reference: str | None,
    notes: str | None,
) -> None:
    """A replayed `idempotency_key` must carry the *same* operation -
    same invoice and same payment details - or it's a client bug
    (reusing a key for a materially different request), not a genuine
    retry. Rejected as a conflict rather than silently returning
    mismatched data or silently accepting the new values over the
    original."""
    if (
        existing.invoice_id != invoice_id
        or existing.amount != amount
        or existing.payment_date != payment_date
        or existing.method != method.strip()
        or existing.reference != reference
        or existing.notes != notes
    ):
        raise APIError(
            "This idempotency_key was already used for a different payment.",
            status_code=409,
            code="IDEMPOTENCY_KEY_CONFLICT",
            details={"idempotency_key": "already used for a different payment"},
        )


def record_payment(
    organization_id: uuid.UUID,
    invoice_id: uuid.UUID,
    recorder_membership_id: uuid.UUID,
    *,
    amount: Decimal,
    payment_date: date,
    method: str,
    reference: str | None,
    notes: str | None,
    idempotency_key: str,
) -> tuple[Payment, bool]:
    """FD-043 (FR-026). Returns `(payment, created)` - `created` is
    `False` for an idempotent replay (the route uses it to choose `200`
    vs `201`), `True` for a genuinely new payment.

    NFR-006 ("financial operations use database transactions"): the
    payment insert and the invoice's status transition commit together
    in the one `db.session.commit()` below - never two separate
    commits that could leave one without the other if the process
    died in between.

    `new_balance_due` is computed arithmetically
    (`balance_due - amount`) rather than by re-querying
    `invoice.payments` after adding the new row - the relationship
    collection, if already loaded earlier in this same function, would
    not reflect an unflushed add made via a raw `invoice_id` column
    rather than the relationship itself, and a second query is
    unnecessary when simple subtraction gives the same answer.
    """
    invoice = get_invoice_or_404(organization_id, invoice_id)

    existing = _find_existing_payment(organization_id, idempotency_key)
    if existing is not None:
        _ensure_replay_matches(
            existing,
            invoice_id=invoice_id,
            amount=amount,
            payment_date=payment_date,
            method=method,
            reference=reference,
            notes=notes,
        )
        return existing, False

    # Re-fetch with a row lock before the check-then-act balance
    # validation below. Without this, two concurrent requests against
    # the same invoice using two different (individually valid)
    # idempotency_keys could both read the same pre-payment balance_due
    # before either commits, both pass the overpayment check, and
    # together record more than invoice.total - the idempotency_key
    # unique constraint alone only catches a *repeated* key, never two
    # legitimately-different ones. Held only from here through the
    # commit/rollback below, not during the unlocked fetch/idempotency
    # check above (those don't mutate anything).
    invoice = get_invoice_or_404(organization_id, invoice_id, for_update=True)

    # Everything from here on holds that row lock on an open
    # transaction - every exit path, success or failure, must either
    # commit or roll back explicitly before returning/raising. A bare
    # `raise` here (unlike every other service function's plain
    # business-rule checks) would otherwise leave the lock held for
    # the rest of this request - Flask's own APIError handler never
    # touches the session - and a later request/test that needs the
    # same row (e.g. a cleanup DELETE sweeping the whole table) would
    # block on it indefinitely.
    try:
        if invoice.status not in _PAYABLE_STATUSES:
            raise APIError(
                f"Cannot record a payment against an invoice with status '{invoice.status.value}'.",
                status_code=422,
                code="INVOICE_NOT_PAYABLE",
                details={"status": "invoice must be sent, overdue, or partially paid"},
            )

        _, balance_due = get_invoice_balance(invoice)
        if amount > balance_due:
            raise APIError(
                "Payment amount exceeds the invoice's outstanding balance.",
                status_code=422,
                code="OVERPAYMENT",
                details={"amount": f"must not exceed the outstanding balance of {balance_due}"},
            )

        payment = Payment(
            organization_id=organization_id,
            invoice_id=invoice_id,
            amount=amount,
            payment_date=payment_date,
            reference=reference,
            notes=notes,
            recorded_by=recorder_membership_id,
            idempotency_key=idempotency_key,
        )
        _set_method(payment, method)
        db.session.add(payment)

        new_balance_due = balance_due - amount
        invoice.status = InvoiceStatus.PAID if new_balance_due <= Decimal("0.00") else InvoiceStatus.PARTIALLY_PAID

        db.session.commit()
    except APIError:
        db.session.rollback()
        raise
    except IntegrityError:
        # Lost a race: another request inserted the same
        # (organization_id, idempotency_key) between this function's
        # own lookup above and this commit. Roll back this attempt
        # (discarding its own invoice.status mutation too - it was
        # never actually recorded) and return the winner's row as a
        # replay, same resolution as if the lookup had found it to
        # begin with.
        db.session.rollback()
        existing = _find_existing_payment(organization_id, idempotency_key)
        if existing is None:
            raise
        _ensure_replay_matches(
            existing,
            invoice_id=invoice_id,
            amount=amount,
            payment_date=payment_date,
            method=method,
            reference=reference,
            notes=notes,
        )
        return existing, False

    return payment, True


def list_payments(
    organization_id: uuid.UUID, invoice_id: uuid.UUID, *, page: int, per_page: int
) -> tuple[list[Payment], int]:
    """Chronological, oldest first (a running ledger) - same convention
    as comments/history lists elsewhere in this codebase. Confirms the
    invoice itself exists in this organization first (404 otherwise),
    same reach check every other invoice-scoped read uses."""
    get_invoice_or_404(organization_id, invoice_id)

    query = db.session.query(Payment).filter_by(organization_id=organization_id, invoice_id=invoice_id)
    total = query.count()
    payments = query.order_by(Payment.created_at.asc()).offset((page - 1) * per_page).limit(per_page).all()
    return payments, total
