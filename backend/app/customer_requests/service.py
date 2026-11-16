"""FD-037: customer request creation/retrieval, assignment, and the
status workflow (New -> Assigned -> In Progress -> Waiting for
Customer -> Resolved -> Closed). Bundled into one task because the
backlog has no separate "request creation/retrieval" entry the way
Task had FD-026 before FD-027/FD-028 split assignment and status out -
nothing else creates a CustomerRequest row.

`Permission.CUSTOMER_REQUEST_MANAGE` (FD-015) is a single permission
covering the whole module (unlike Task's two-permission
TASK_CREATE_ASSIGN/TASK_VIEW_UPDATE split): `full` for Owner/Manager/
CustomerSupport, `assigned` for Employee, `none` for Accountant. Since
`require_permission` only rejects `none`, create/assign explicitly
check for `full` themselves (FR-020: "Managers/authorized Support
staff assign requests" - Employees aren't listed as assigners, and
realistically can't create one either since nothing in FR-019's flow
has an Employee originating a request). Status changes apply the same
object-level `assigned` reach as Task's TASK_VIEW_UPDATE, with a
Task-style subset of transitions an assignee may trigger themselves.
"""

import uuid
from datetime import date

from app.authz.permissions import PermissionScope
from app.authz.service import check_scope_allows
from app.errors import APIError
from app.extensions import db
from app.models import (
    Customer,
    CustomerRequest,
    CustomerStatus,
    Membership,
    MembershipStatus,
    RequestHistory,
    RequestPriority,
    RequestStatus,
)


def _require_full_scope(scope: PermissionScope) -> None:
    if scope != PermissionScope.FULL:
        raise APIError("You do not have permission to do this.", status_code=403, code="FORBIDDEN")


def _validate_customer(organization_id: uuid.UUID, customer_id: uuid.UUID) -> None:
    """customer_id must resolve to a real, *active* Customer in this
    organization - mirrors app.departments.service._validate_manager_membership's
    pattern. Requiring `active` (not just "exists in this org") blocks
    logging a *new* request against an archived customer, though an
    existing request already tied to one stays fully visible/manageable
    regardless of later archiving (Section 26's own acceptance
    criterion is about the past, not about accepting new work against a
    customer no longer active)."""
    customer = db.session.query(Customer).filter_by(id=customer_id, organization_id=organization_id).first()
    if customer is None or customer.status != CustomerStatus.ACTIVE:
        raise APIError(
            "customer_id must reference an active customer in this organization.",
            status_code=422,
            code="INVALID_CUSTOMER",
            details={"customer_id": "must reference an active customer in this organization"},
        )


def _set_title(request: CustomerRequest, title: str) -> None:
    try:
        request.title = title
    except ValueError as exc:
        raise APIError(str(exc), status_code=422, code="VALIDATION_ERROR", details={"title": str(exc)})


def create_request(
    organization_id: uuid.UUID,
    creator_membership_id: uuid.UUID,
    *,
    scope: PermissionScope,
    customer_id: uuid.UUID,
    title: str,
    description: str | None,
    category: str | None,
    priority: RequestPriority | None,
    due_date: date | None,
) -> CustomerRequest:
    _require_full_scope(scope)
    _validate_customer(organization_id, customer_id)

    request = CustomerRequest(
        organization_id=organization_id,
        customer_id=customer_id,
        creator_membership_id=creator_membership_id,
        description=description,
        category=category,
        due_date=due_date,
    )
    _set_title(request, title)
    if priority is not None:
        request.priority = priority

    db.session.add(request)
    db.session.commit()
    return request


def _apply_filters(
    query,
    *,
    customer_id: uuid.UUID | None,
    category: str | None,
    priority: RequestPriority | None,
    status: RequestStatus | None,
    due_date_from: date | None,
    due_date_to: date | None,
):
    if customer_id is not None:
        query = query.filter(CustomerRequest.customer_id == customer_id)
    if category is not None:
        query = query.filter(CustomerRequest.category == category)
    if priority is not None:
        query = query.filter(CustomerRequest.priority == priority)
    if status is not None:
        query = query.filter(CustomerRequest.status == status)
    if due_date_from is not None:
        query = query.filter(CustomerRequest.due_date >= due_date_from)
    if due_date_to is not None:
        query = query.filter(CustomerRequest.due_date <= due_date_to)
    return query


def list_requests(
    organization_id: uuid.UUID,
    *,
    scope: PermissionScope,
    caller_membership_id: uuid.UUID,
    customer_id: uuid.UUID | None,
    assignee_membership_id: uuid.UUID | None,
    category: str | None,
    priority: RequestPriority | None,
    status: RequestStatus | None,
    due_date_from: date | None,
    due_date_to: date | None,
    page: int,
    per_page: int,
) -> tuple[list[CustomerRequest], int]:
    query = db.session.query(CustomerRequest).filter(CustomerRequest.organization_id == organization_id)

    # `assigned` scope (Employee): always forced to the caller's own
    # requests, regardless of any assignee_membership_id they supplied -
    # same silent-override convention app.tasks.service.list_tasks
    # already established, for the same oracle-prevention reason.
    if scope == PermissionScope.ASSIGNED:
        query = query.filter(CustomerRequest.assignee_membership_id == caller_membership_id)
    elif assignee_membership_id is not None:
        query = query.filter(CustomerRequest.assignee_membership_id == assignee_membership_id)

    query = _apply_filters(
        query,
        customer_id=customer_id,
        category=category,
        priority=priority,
        status=status,
        due_date_from=due_date_from,
        due_date_to=due_date_to,
    )

    total = query.count()
    requests = query.order_by(CustomerRequest.created_at.desc()).offset((page - 1) * per_page).limit(per_page).all()
    return requests, total


def get_request_or_404(organization_id: uuid.UUID, request_id: uuid.UUID) -> CustomerRequest:
    request = db.session.query(CustomerRequest).filter_by(id=request_id, organization_id=organization_id).first()
    if request is None:
        raise APIError("Not found.", status_code=404, code="NOT_FOUND")
    return request


def get_request(
    organization_id: uuid.UUID, request_id: uuid.UUID, *, scope: PermissionScope, caller_membership_id: uuid.UUID
) -> CustomerRequest:
    """Same `assigned`-scope object-level reach check as Task's
    get_task: a request that exists in the caller's own organization
    but isn't assigned to them is 403, not 404."""
    request = get_request_or_404(organization_id, request_id)
    if not check_scope_allows(scope, caller_id=caller_membership_id, assignee_id=request.assignee_membership_id):
        raise APIError("You do not have permission to do this.", status_code=403, code="FORBIDDEN")
    return request


def _validate_assignee(organization_id: uuid.UUID, assignee_membership_id: uuid.UUID | None) -> None:
    if assignee_membership_id is None:
        return

    membership = (
        db.session.query(Membership).filter_by(id=assignee_membership_id, organization_id=organization_id).first()
    )
    if membership is None or membership.status != MembershipStatus.ACTIVE:
        raise APIError(
            "assignee_membership_id must reference an active membership in this organization.",
            status_code=422,
            code="INVALID_ASSIGNEE",
            details={"assignee_membership_id": "must reference an active membership in this organization"},
        )


def assign_request(
    organization_id: uuid.UUID,
    request_id: uuid.UUID,
    *,
    scope: PermissionScope,
    actor_membership_id: uuid.UUID,
    assignee_membership_id: uuid.UUID | None,
) -> CustomerRequest:
    """FD-037 (FR-020). `full` scope only - mirrors Task's
    TASK_CREATE_ASSIGN being Owner/Manager-only, here enforced inline
    since CUSTOMER_REQUEST_MANAGE has no separate create/assign
    permission to gate on. Idempotent: reassigning to the assignee a
    request already has is a no-op, same convention
    app.tasks.service.assign_task already established.

    Judgment call: `assigned` is itself one of `RequestStatus`'s values
    (FR-019), unlike Task where assignment and status are independent -
    the first time a request gets a real assignee while still `new`,
    status auto-advances to `assigned` too, recorded as its own history
    entry. Reassigning a request that has already moved past `new`
    never regresses its status; it's just an assignee swap.
    """
    _require_full_scope(scope)
    request = get_request_or_404(organization_id, request_id)
    _validate_assignee(organization_id, assignee_membership_id)

    previous_assignee_membership_id = request.assignee_membership_id
    if previous_assignee_membership_id == assignee_membership_id:
        return request

    history_entries = [
        RequestHistory(
            organization_id=organization_id,
            request_id=request.id,
            actor_membership_id=actor_membership_id,
            event_type="assignee_changed",
            previous_value=str(previous_assignee_membership_id) if previous_assignee_membership_id else None,
            new_value=str(assignee_membership_id) if assignee_membership_id else None,
        )
    ]
    request.assignee_membership_id = assignee_membership_id

    if request.status == RequestStatus.NEW and assignee_membership_id is not None:
        previous_status = request.status
        request.status = RequestStatus.ASSIGNED
        history_entries.append(
            RequestHistory(
                organization_id=organization_id,
                request_id=request.id,
                actor_membership_id=actor_membership_id,
                event_type="status_changed",
                previous_value=previous_status.value,
                new_value=RequestStatus.ASSIGNED.value,
            )
        )

    db.session.add_all(history_entries)
    db.session.commit()
    return request


# FD-037 (FR-019): "New -> Assigned -> In Progress -> Waiting for
# Customer -> Resolved -> Closed", a single stated chain with no
# branch or skip mentioned anywhere - unlike Task's workflow (FR-012),
# which explicitly names one backward loop ("managers can return tasks
# for revision") and an any-state escape hatch (Cancelled). Neither
# exists in FR-019's wording, and `RequestStatus` itself (FD-036) has
# no analogous "cancelled" value, so no such edges are invented here -
# strict, linear, no skipping a stage. This mirrors how Task's own
# FD-028 already treated an identically-phrased single-arrow spec
# sentence (no skip from in_progress straight to completed there
# either).
_REQUEST_TRANSITIONS: dict[RequestStatus, set[RequestStatus]] = {
    RequestStatus.NEW: {RequestStatus.ASSIGNED},
    RequestStatus.ASSIGNED: {RequestStatus.IN_PROGRESS},
    RequestStatus.IN_PROGRESS: {RequestStatus.WAITING_FOR_CUSTOMER},
    RequestStatus.WAITING_FOR_CUSTOMER: {RequestStatus.RESOLVED},
    RequestStatus.RESOLVED: {RequestStatus.CLOSED},
    RequestStatus.CLOSED: set(),
}

# The subset of _REQUEST_TRANSITIONS an `assigned`-scope caller (the
# request's own assignee) may trigger themselves - the two "forward
# progress" moves they naturally drive, same shape as Task's own
# _ASSIGNEE_ALLOWED_TRANSITIONS. Resolving and closing are Owner/
# Manager/CustomerSupport-only - Section 26's own acceptance criterion
# ("unauthorized users can't close requests"), generalized here to
# resolving too (the step immediately before closing), mirroring how
# Task reserved its own last forward step (-> completed) to full scope.
_ASSIGNEE_ALLOWED_TRANSITIONS: set[tuple[RequestStatus, RequestStatus]] = {
    (RequestStatus.ASSIGNED, RequestStatus.IN_PROGRESS),
    (RequestStatus.IN_PROGRESS, RequestStatus.WAITING_FOR_CUSTOMER),
}


def update_request_status(
    organization_id: uuid.UUID,
    request_id: uuid.UUID,
    *,
    scope: PermissionScope,
    caller_membership_id: uuid.UUID,
    actor_membership_id: uuid.UUID,
    new_status: RequestStatus,
    resolution_notes: str | None,
) -> CustomerRequest:
    """FD-037. Checked in this order, mirroring
    app.tasks.service.update_task_status exactly:
    1. Object-level reach (same as get_request) - before anything else,
       including before the idempotency check, so a non-assignee can't
       use a same-status request as a free oracle for a request's
       current status.
    2. `resolution_notes`, if given, is applied regardless of whether
       status itself changes - FR-021's "resolution details" is its own
       fact, not gated behind a specific transition (there's no
       separate general-editing endpoint for requests to carry it
       instead, unlike Task's FD-029).
    3. Idempotent no-op on status - requesting the status a request
       already has writes no status-change history row (resolution_notes
       may still have been applied above).
    4. Transition-graph validity (422 INVALID_STATUS_TRANSITION) -
       checked for every caller, Owner/Manager/CustomerSupport included.
    5. Role reach for *this specific* transition (403) - only
       `assigned`-scope callers are restricted further.
    """
    request = get_request_or_404(organization_id, request_id)
    if not check_scope_allows(scope, caller_id=caller_membership_id, assignee_id=request.assignee_membership_id):
        raise APIError("You do not have permission to do this.", status_code=403, code="FORBIDDEN")

    history_entries = []

    if resolution_notes is not None and resolution_notes != request.resolution_notes:
        history_entries.append(
            RequestHistory(
                organization_id=organization_id,
                request_id=request.id,
                actor_membership_id=actor_membership_id,
                event_type="resolution_notes_changed",
                previous_value=request.resolution_notes,
                new_value=resolution_notes,
            )
        )
        request.resolution_notes = resolution_notes

    previous_status = request.status
    if new_status != previous_status:
        if new_status not in _REQUEST_TRANSITIONS.get(previous_status, set()):
            raise APIError(
                f"Cannot transition a request from '{previous_status.value}' to '{new_status.value}'.",
                status_code=422,
                code="INVALID_STATUS_TRANSITION",
                details={"status": f"no such transition from {previous_status.value}"},
            )

        if scope == PermissionScope.ASSIGNED and (previous_status, new_status) not in _ASSIGNEE_ALLOWED_TRANSITIONS:
            raise APIError("You do not have permission to do this.", status_code=403, code="FORBIDDEN")

        # Data integrity: `assigned` status implies a real assignee -
        # normally set together by assign_request's own auto-advance,
        # but this endpoint is a separate path that could otherwise
        # leave status=assigned with assignee_membership_id still None.
        if new_status == RequestStatus.ASSIGNED and request.assignee_membership_id is None:
            raise APIError(
                "Cannot mark a request as assigned without an assignee.",
                status_code=422,
                code="INVALID_STATUS_TRANSITION",
                details={"status": "assigned requires assignee_membership_id to already be set"},
            )

        request.status = new_status
        history_entries.append(
            RequestHistory(
                organization_id=organization_id,
                request_id=request.id,
                actor_membership_id=actor_membership_id,
                event_type="status_changed",
                previous_value=previous_status.value,
                new_value=new_status.value,
            )
        )

    if history_entries:
        db.session.add_all(history_entries)
    db.session.commit()
    return request
