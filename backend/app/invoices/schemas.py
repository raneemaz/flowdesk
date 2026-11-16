import uuid
from datetime import date
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models import DiscountType, InvoiceStatus


class LineItemInput(BaseModel):
    """FD-042: one line item inside a Create/Update invoice body.
    `line_total` is never accepted - app.invoices.service.compute_line_total
    (FD-041) is the only place it's computed. `quantity` must be
    strictly positive and `unit_price`/`tax_rate` non-negative - closes
    the financial-integrity-reviewer's FD-041 forward-looking note about
    an unvalidated negative quantity misattributing recalculate_invoice's
    negative-total error to the discount."""

    model_config = ConfigDict(extra="forbid")

    description: str = Field(min_length=1, max_length=500)
    quantity: Decimal = Field(gt=0)
    unit_price: Decimal = Field(ge=0)
    tax_rate: Decimal | None = Field(default=None, ge=0, le=100)


class CreateInvoiceRequest(BaseModel):
    """FD-042: body for POST /organizations/{id}/invoices. Always
    starts Draft - `status` isn't accepted (the model's own default).
    `invoice_number` isn't accepted either - server-generated, see
    app.invoices.service._generate_invoice_number."""

    model_config = ConfigDict(extra="forbid")

    customer_id: uuid.UUID
    currency: str = Field(min_length=3, max_length=3)
    issue_date: date | None = None
    due_date: date | None = None
    notes: str | None = None
    payment_terms: str | None = Field(default=None, max_length=255)
    discount_type: DiscountType = DiscountType.FLAT
    discount_value: Decimal = Field(default=Decimal("0.00"), ge=0)
    line_items: list[LineItemInput] = Field(default_factory=list)

    @model_validator(mode="after")
    def _percentage_discount_must_not_exceed_100(self):
        if self.discount_type == DiscountType.PERCENTAGE and self.discount_value > Decimal("100"):
            raise ValueError("discount_value must not exceed 100 when discount_type is percentage")
        return self


class ListInvoicesQuery(BaseModel):
    """Query-string params for GET /organizations/{id}/invoices."""

    model_config = ConfigDict(extra="forbid")

    customer_id: uuid.UUID | None = None
    status: InvoiceStatus | None = None
    due_date_from: date | None = None
    due_date_to: date | None = None
    page: int = Field(default=1, ge=1)
    per_page: int = Field(default=20, ge=1, le=100)

    @model_validator(mode="after")
    def _due_date_range_is_not_inverted(self):
        if self.due_date_from is not None and self.due_date_to is not None and self.due_date_from > self.due_date_to:
            raise ValueError("due_date_from must not be after due_date_to")
        return self


class UpdateInvoiceRequest(BaseModel):
    """FD-042: body for PATCH /organizations/{id}/invoices/{invoice_id}.
    Draft-only - app.invoices.service.update_invoice rejects any other
    status with 422 INVOICE_LOCKED regardless of what's sent here.
    Partial update (`model_dump(exclude_unset=True)`) - only fields
    actually present are applied. `invoice_number` and `status` are
    never accepted - status changes go through the dedicated
    issue/cancel actions instead. `line_items`, if present, replaces
    the entire set (see update_invoice's own docstring)."""

    model_config = ConfigDict(extra="forbid")

    customer_id: uuid.UUID | None = None
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    issue_date: date | None = None
    due_date: date | None = None
    notes: str | None = None
    payment_terms: str | None = Field(default=None, max_length=255)
    discount_type: DiscountType | None = None
    discount_value: Decimal | None = Field(default=None, ge=0)
    line_items: list[LineItemInput] | None = None

    @model_validator(mode="after")
    def _non_nullable_fields_cannot_be_explicitly_null(self):
        # customer_id/currency/discount_type/discount_value/line_items
        # are all NOT NULL on the model - explicit null for any of them
        # is a 422, same convention UpdateCustomerRequest/UpdateDepartmentRequest
        # already established for their own non-nullable fields.
        for field_name in ("customer_id", "currency", "discount_type", "discount_value", "line_items"):
            if field_name in self.model_fields_set and getattr(self, field_name) is None:
                raise ValueError(f"{field_name} must not be null")
        return self

    @model_validator(mode="after")
    def _percentage_discount_must_not_exceed_100(self):
        # Only a best-effort check for the combination given in *this*
        # request - a PATCH sending only discount_value against an
        # invoice whose discount_type is already `percentage` can't be
        # caught here (this schema has no access to the invoice's
        # current state), which is exactly why
        # app.invoices.service.recalculate_invoice re-checks the same
        # invariant against the invoice's actual post-update state -
        # that's the authoritative guard, this is just earlier feedback.
        if (
            "discount_type" in self.model_fields_set
            and "discount_value" in self.model_fields_set
            and self.discount_type == DiscountType.PERCENTAGE
            and self.discount_value is not None
            and self.discount_value > Decimal("100")
        ):
            raise ValueError("discount_value must not exceed 100 when discount_type is percentage")
        return self


class FinancialSummaryQuery(BaseModel):
    """FD-044: query-string params for GET .../invoices/financial-summary.
    `period_start`/`period_end` (only the monthly_revenue_collected
    metric's own window - see app.invoices.service.get_financial_summary's
    own docstring) must be given together or not at all; omitted
    entirely, they default to the current calendar month in the
    organization's own timezone."""

    model_config = ConfigDict(extra="forbid")

    period_start: date | None = None
    period_end: date | None = None

    @model_validator(mode="after")
    def _period_bounds_are_given_together_and_not_inverted(self):
        if (self.period_start is None) != (self.period_end is None):
            raise ValueError("period_start and period_end must be given together")
        if self.period_start is not None and self.period_end is not None and self.period_start > self.period_end:
            raise ValueError("period_start must not be after period_end")
        return self
