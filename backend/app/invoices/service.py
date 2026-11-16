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

from decimal import ROUND_HALF_UP, Decimal

from app.errors import APIError
from app.models import DiscountType, Invoice, InvoiceLineItem

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
