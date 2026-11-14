import uuid

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models import DepartmentStatus


class CreateDepartmentRequest(BaseModel):
    # extra="forbid": no smuggling organization_id/status/id through the
    # body - same defense-in-depth as CreateOrganizationRequest/
    # CreateInvitationRequest. status isn't accepted here at all - a new
    # department always starts active (the model's own default).
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=255)
    description: str | None = None
    manager_membership_id: uuid.UUID | None = None


class UpdateDepartmentRequest(BaseModel):
    """Partial update - every field is optional-to-provide. Route/service
    code must use `model_dump(exclude_unset=True)`, never a plain
    `model_dump()`, so a field the caller simply didn't mention isn't
    mistaken for "clear it" (relevant for description and
    manager_membership_id, which legitimately accept an explicit `null`
    to clear them)."""

    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    manager_membership_id: uuid.UUID | None = None
    status: DepartmentStatus | None = None

    @model_validator(mode="after")
    def _name_and_status_cannot_be_explicitly_null(self):
        # Unlike description/manager_membership_id, name (never nullable
        # at the model level) and status (a two-value enum, not a
        # clearable field) only make sense as "omitted" or "a real
        # value" - an explicit `null` for either is a validation error,
        # not a valid "clear this field" request.
        if "name" in self.model_fields_set and self.name is None:
            raise ValueError("name must not be null")
        if "status" in self.model_fields_set and self.status is None:
            raise ValueError("status must not be null")
        return self
