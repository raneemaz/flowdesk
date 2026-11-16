from datetime import date
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class CreatePaymentRequest(BaseModel):
    """FD-043: body for POST .../invoices/{invoice_id}/payments.
    `idempotency_key` is required, not optional - an idempotency
    scheme only works if every caller actually participates in it (see
    Payment.idempotency_key's own model docstring). `amount` must be
    strictly positive - a zero or negative "payment" isn't one."""

    model_config = ConfigDict(extra="forbid")

    amount: Decimal = Field(gt=0)
    payment_date: date
    method: str = Field(min_length=1, max_length=50)
    reference: str | None = Field(default=None, max_length=255)
    notes: str | None = None
    idempotency_key: str = Field(min_length=1, max_length=255)


class ListPaymentsQuery(BaseModel):
    """Query-string params for GET .../invoices/{invoice_id}/payments."""

    model_config = ConfigDict(extra="forbid")

    page: int = Field(default=1, ge=1)
    per_page: int = Field(default=20, ge=1, le=100)
