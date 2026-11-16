from pydantic import BaseModel, ConfigDict, EmailStr, Field, model_validator

from app.models import CustomerStatus


class CreateCustomerRequest(BaseModel):
    """FD-035: body for POST /organizations/{id}/customers.
    extra="forbid": no smuggling organization_id/status/id through the
    body, same defense-in-depth as CreateDepartmentRequest. `status`
    isn't accepted here - a new customer always starts `active` (the
    model's own default)."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=255)
    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=50)
    company: str | None = Field(default=None, max_length=255)
    address: str | None = None
    notes: str | None = None


class ListCustomersQuery(BaseModel):
    """Query-string params for GET /organizations/{id}/customers.
    `search` matches name/email/phone/company (see
    app/customers/service.py) - the fields FD-034's own model docstring
    indexed specifically for this."""

    model_config = ConfigDict(extra="forbid")

    search: str | None = Field(default=None, max_length=255)
    status: CustomerStatus | None = None
    page: int = Field(default=1, ge=1)
    per_page: int = Field(default=20, ge=1, le=100)


class UpdateCustomerRequest(BaseModel):
    """FD-035: body for PATCH /organizations/{id}/customers/{customer_id}.
    Partial update - only fields actually present are applied
    (`model_dump(exclude_unset=True)`, see app/customers/service.py).
    email/phone/company/address/notes accept an explicit `null` to
    clear them (all nullable on the model - FD-034's own judgment
    call); `name` and `status` don't, same reasoning as
    UpdateDepartmentRequest."""

    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=255)
    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=50)
    company: str | None = Field(default=None, max_length=255)
    address: str | None = None
    notes: str | None = None
    status: CustomerStatus | None = None

    @model_validator(mode="after")
    def _name_and_status_cannot_be_explicitly_null(self):
        if "name" in self.model_fields_set and self.name is None:
            raise ValueError("name must not be null")
        if "status" in self.model_fields_set and self.status is None:
            raise ValueError("status must not be null")
        return self
