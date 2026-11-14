import uuid

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models import EmployeeStatus, MembershipRole


class ListEmployeesQuery(BaseModel):
    """Query-string params for GET /organizations/{id}/employees.
    extra="forbid" rejects an unknown param (e.g. a typo) with a clear
    422 rather than silently ignoring it, same defense-in-depth as the
    JSON-body schemas elsewhere in this project."""

    model_config = ConfigDict(extra="forbid")

    # Name only, never email - see app/employees/service.py's module
    # docstring for why.
    search: str | None = Field(default=None, max_length=255)
    department_id: uuid.UUID | None = None
    role: MembershipRole | None = None
    status: EmployeeStatus | None = None
    page: int = Field(default=1, ge=1)
    per_page: int = Field(default=20, ge=1, le=100)


class UpdateEmployeeProfileRequest(BaseModel):
    """FD-023: body for PATCH /organizations/{id}/employees/{membership_id}.
    Partial update (and implicit create - nothing else creates an
    EmployeeProfile row yet, see app/employees/service.py), so the route
    must use `model_dump(exclude_unset=True)`, never a plain
    `model_dump()` - job_title/department_id/manager_membership_id
    legitimately accept an explicit `null` to clear them (an employee
    can have no job title, no department, no manager), but `status`
    doesn't - it's a required three-value enum on the model, never a
    "clearable" concept."""

    model_config = ConfigDict(extra="forbid")

    job_title: str | None = Field(default=None, max_length=255)
    department_id: uuid.UUID | None = None
    manager_membership_id: uuid.UUID | None = None
    status: EmployeeStatus | None = None

    @model_validator(mode="after")
    def _status_cannot_be_explicitly_null(self):
        if "status" in self.model_fields_set and self.status is None:
            raise ValueError("status must not be null")
        return self
