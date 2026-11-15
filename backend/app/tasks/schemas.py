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


class AssignTaskRequest(BaseModel):
    """FD-027: body for PATCH /organizations/{id}/tasks/{task_id}/assign.
    `assignee_membership_id` is required (not optional-to-omit, unlike
    the partial-update schemas elsewhere in this project) - this
    endpoint does exactly one thing, so the caller always states the
    intended assignee; `null` is how a task gets unassigned."""

    model_config = ConfigDict(extra="forbid")

    assignee_membership_id: uuid.UUID | None


class UpdateTaskStatusRequest(BaseModel):
    """FD-028: body for PATCH /organizations/{id}/tasks/{task_id}/status.
    `status` is required, not nullable - unlike assignment, "no status"
    isn't a real task state (every task always has exactly one, the
    model's own NOT NULL column)."""

    model_config = ConfigDict(extra="forbid")

    status: TaskStatus


class UpdateTaskRequest(BaseModel):
    """FD-029: body for PATCH /organizations/{id}/tasks/{task_id}.

    General field editing - NOT assignee_membership_id (FD-027's
    dedicated /assign endpoint) or status (FD-028's dedicated /status
    endpoint); both are rejected here via extra="forbid" so a caller
    is steered to the right endpoint rather than silently ignored.

    Gated by TASK_CREATE_ASSIGN (Owner/Manager only), not
    TASK_VIEW_UPDATE's `assigned` scope - FR-011 bundles "set deadline/
    priority/instructions" together with assignment itself
    ("Assignment: assign/reassign, set deadline/priority/instructions"),
    framing task editing as the same administrative capability as
    assigning it, not something the assignee does to their own task
    (that's FD-028's status-progression scope instead).

    Partial update - only fields actually present in the body are
    applied (model_dump(exclude_unset=True), see app/tasks/service.py's
    update_task). description/department_id/start_date/due_date/
    estimated_hours/actual_hours accept an explicit null to clear
    them; title/priority don't (neither is a "clearable" concept).
    """

    model_config = ConfigDict(extra="forbid")

    title: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    priority: TaskPriority | None = None
    department_id: uuid.UUID | None = None
    start_date: date | None = None
    due_date: date | None = None
    estimated_hours: Decimal | None = Field(default=None, ge=0, le=Decimal("9999.99"))
    actual_hours: Decimal | None = Field(default=None, ge=0, le=Decimal("9999.99"))

    @model_validator(mode="after")
    def _non_clearable_fields_are_not_null(self):
        if "title" in self.model_fields_set and self.title is None:
            raise ValueError("title must not be null")
        if "priority" in self.model_fields_set and self.priority is None:
            raise ValueError("priority must not be null")
        return self

    @model_validator(mode="after")
    def _due_date_not_before_start_date_within_this_request(self):
        # Only catches the case where both dates are given together in
        # this same request and are inconsistent with each other - the
        # service layer still has to re-check against whichever date
        # *isn't* included in this request (the task's existing,
        # unchanged value), since this schema has no visibility into
        # that merged state.
        if "start_date" in self.model_fields_set and "due_date" in self.model_fields_set:
            if self.start_date is not None and self.due_date is not None and self.due_date < self.start_date:
                raise ValueError("due_date must not be before start_date")
        return self
