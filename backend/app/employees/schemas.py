import uuid

from pydantic import BaseModel, ConfigDict, Field

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
