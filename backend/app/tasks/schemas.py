import uuid
from datetime import date
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models import TaskPriority, TaskStatus


class CreateTaskRequest(BaseModel):
    """FD-026: body for POST /organizations/{id}/tasks.

    Deliberately does NOT accept assignee_membership_id - FR-011 treats
    "assign" as its own action, separate from creation (a task can
    exist unassigned), and FD-027 ("task assignment/reassignment") is
    the task that implements it, including the validated-assignee and
    history-recording concerns that come with it. Nor does it accept
    status (a new task always starts `to_do`, the model's own default -
    same convention CreateDepartmentRequest already uses for `status`)
    or actual_hours (that accrues as work happens, not something you'd
    set at creation).
    """

    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=255)
    description: str | None = None
    priority: TaskPriority | None = None
    department_id: uuid.UUID | None = None
    start_date: date | None = None
    due_date: date | None = None
    estimated_hours: Decimal | None = Field(default=None, ge=0, le=Decimal("9999.99"))

    @model_validator(mode="after")
    def _due_date_not_before_start_date(self):
        # A basic sanity check, not FD-029's job: FD-029 ("task editing
        # & deadlines, date validation") is about validating a *change*
        # to an existing task's dates (and recording history for it) -
        # a different concern from rejecting obviously-nonsensical
        # input at creation time.
        if self.start_date is not None and self.due_date is not None and self.due_date < self.start_date:
            raise ValueError("due_date must not be before start_date")
        return self


class ListTasksQuery(BaseModel):
    """Query-string params for GET /organizations/{id}/tasks.
    extra="forbid" rejects an unknown param with a clear 422, same
    defense-in-depth as every other list endpoint in this project."""

    model_config = ConfigDict(extra="forbid")

    assignee_membership_id: uuid.UUID | None = None
    department_id: uuid.UUID | None = None
    priority: TaskPriority | None = None
    status: TaskStatus | None = None
    due_date_from: date | None = None
    due_date_to: date | None = None
    created_from: date | None = None
    created_to: date | None = None
    page: int = Field(default=1, ge=1)
    per_page: int = Field(default=20, ge=1, le=100)

    @model_validator(mode="after")
    def _ranges_are_not_inverted(self):
        if self.due_date_from is not None and self.due_date_to is not None and self.due_date_from > self.due_date_to:
            raise ValueError("due_date_from must not be after due_date_to")
        if self.created_from is not None and self.created_to is not None and self.created_from > self.created_to:
            raise ValueError("created_from must not be after created_to")
        return self
