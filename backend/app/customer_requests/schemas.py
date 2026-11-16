import uuid
from datetime import date

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models import RequestPriority, RequestStatus


class CreateCustomerRequestRequest(BaseModel):
    """FD-037: body for POST /organizations/{id}/customer-requests.

    Deliberately does NOT accept assignee_membership_id - FR-020 treats
    "assign" as its own action ("Managers/authorized Support staff
    assign requests"), separate from creation, same split FD-027
    established for Task. Nor `status` (a new request always starts
    `new`, the model's own default)."""

    model_config = ConfigDict(extra="forbid")

    customer_id: uuid.UUID
    title: str = Field(min_length=1, max_length=255)
    description: str | None = None
    category: str | None = Field(default=None, max_length=255)
    priority: RequestPriority | None = None
    due_date: date | None = None


class ListCustomerRequestsQuery(BaseModel):
    """Query-string params for GET /organizations/{id}/customer-requests."""

    model_config = ConfigDict(extra="forbid")

    customer_id: uuid.UUID | None = None
    assignee_membership_id: uuid.UUID | None = None
    category: str | None = Field(default=None, max_length=255)
    priority: RequestPriority | None = None
    status: RequestStatus | None = None
    due_date_from: date | None = None
    due_date_to: date | None = None
    page: int = Field(default=1, ge=1)
    per_page: int = Field(default=20, ge=1, le=100)

    @model_validator(mode="after")
    def _due_date_range_is_not_inverted(self):
        if self.due_date_from is not None and self.due_date_to is not None and self.due_date_from > self.due_date_to:
            raise ValueError("due_date_from must not be after due_date_to")
        return self


class AssignCustomerRequestRequest(BaseModel):
    """FD-037: body for PATCH /organizations/{id}/customer-requests/{request_id}/assign.
    `assignee_membership_id` is required (not optional-to-omit) - same
    reasoning as Task's own AssignTaskRequest (FD-027): this endpoint
    does exactly one thing, so the caller always states the intended
    assignee; `null` unassigns."""

    model_config = ConfigDict(extra="forbid")

    assignee_membership_id: uuid.UUID | None


class UpdateCustomerRequestStatusRequest(BaseModel):
    """FD-037: body for PATCH /organizations/{id}/customer-requests/{request_id}/status.
    `resolution_notes` is optional and accepted alongside any
    transition - there's no separate general-editing endpoint for
    requests in this backlog (unlike Task's FD-029), and FR-021's own
    "resolution details" naturally gets recorded at the point a request
    is actually resolved/closed."""

    model_config = ConfigDict(extra="forbid")

    status: RequestStatus
    resolution_notes: str | None = None


class CreateRequestCommentRequest(BaseModel):
    """FD-038: body for POST /organizations/{id}/customer-requests/{request_id}/comments.
    No max_length cap - RequestComment.body is an unbounded Text
    column (FD-036), same treatment as TaskComment.body."""

    model_config = ConfigDict(extra="forbid")

    body: str = Field(min_length=1)


class ListRequestCommentsQuery(BaseModel):
    """Query-string params for GET /organizations/{id}/customer-requests/{request_id}/comments."""

    model_config = ConfigDict(extra="forbid")

    page: int = Field(default=1, ge=1)
    per_page: int = Field(default=20, ge=1, le=100)


class ListRequestHistoryQuery(BaseModel):
    """FD-038: query-string params for GET /organizations/{id}/customer-requests/{request_id}/history.
    No filters - same "chronological, append-only" retrieval scope as
    Task's own ListTaskHistoryQuery (FD-031)."""

    model_config = ConfigDict(extra="forbid")

    page: int = Field(default=1, ge=1)
    per_page: int = Field(default=20, ge=1, le=100)
