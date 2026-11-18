"""FD-026: task creation and retrieval (list + single).

Scope-based access is simpler here than the employee directory's
(FD-022): TASK_VIEW_UPDATE only ever grants `full` or `assigned` (see
app/authz/permissions.py) - never `limited` - so every caller who can
see a task sees *all* its fields; the only thing a granted scope
restricts is *which* tasks are visible at all, never which columns.
`assigned` is this codebase's first scope that needs translating into
a list-query row filter rather than a field-visibility filter.
"""

import enum
import uuid
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.activity.service import log_activity
from app.authz.permissions import PermissionScope
from app.authz.service import check_scope_allows
from app.errors import APIError
from app.extensions import db
from app.notifications.service import create_notification
from app.models import (
    Department,
    DepartmentStatus,
    Membership,
    MembershipStatus,
    Task,
    TaskComment,
    TaskHistory,
    TaskPriority,
    TaskStatus,
)

# FD-033 (FR-016): "Completed" and "Cancelled" are the two terminal
# statuses _STATUS_TRANSITIONS already treats as dead ends (no outgoing
# edges) - a task that reached either one is simply finished, never
# "overdue", no matter how far past its due date it is.
TERMINAL_TASK_STATUSES = {TaskStatus.COMPLETED, TaskStatus.CANCELLED}


def _validate_department(organization_id: uuid.UUID, department_id: uuid.UUID | None) -> None:
    """department_id, if given, must resolve to a real, *active*
    Department in this organization - mirrors
    app.employees.service._validate_department's pattern (same
    deferred-to-the-service-layer gap Task.department_id's own
    docstring names, FD-025)."""
    if department_id is None:
        return

    department = db.session.query(Department).filter_by(id=department_id, organization_id=organization_id).first()
    if department is None or department.status != DepartmentStatus.ACTIVE:
        raise APIError(
            "department_id must reference an active department in this organization.",
            status_code=422,
            code="INVALID_DEPARTMENT",
            details={"department_id": "must reference an active department in this organization"},
        )


def _set_title(task: Task, title: str) -> None:
    # Task.title's own @validates (strips and rejects a blank result,
    # e.g. whitespace-only, which passes pydantic's min_length=1 but
    # not this) - converted to a 422 here rather than letting the bare
    # ValueError escape as an unhandled 500, same pattern
    # app.departments.service._set_name already established.
    try:
        task.title = title
    except ValueError as exc:
        raise APIError(str(exc), status_code=422, code="VALIDATION_ERROR", details={"title": str(exc)})


def create_task(
    organization_id: uuid.UUID,
    creator_membership_id: uuid.UUID,
    *,
    title: str,
    description: str | None,
    priority: TaskPriority | None,
    department_id: uuid.UUID | None,
    start_date: date | None,
    due_date: date | None,
    estimated_hours,
) -> Task:
    _validate_department(organization_id, department_id)

    task = Task(
        organization_id=organization_id,
        creator_membership_id=creator_membership_id,
        description=description,
        department_id=department_id,
        start_date=start_date,
        due_date=due_date,
        estimated_hours=estimated_hours,
    )
    _set_title(task, title)
    if priority is not None:
        task.priority = priority

    db.session.add(task)
    db.session.flush()
    log_activity(organization_id, creator_membership_id, "task_created", "task", task.id, metadata={"title": task.title})
    db.session.commit()
    return task


def _apply_filters(
    query,
    *,
    department_id: uuid.UUID | None,
    priority: TaskPriority | None,
    status: TaskStatus | None,
    due_date_from: date | None,
    due_date_to: date | None,
    created_from: date | None,
    created_to: date | None,
):
    if department_id is not None:
        query = query.filter(Task.department_id == department_id)
    if priority is not None:
        query = query.filter(Task.priority == priority)
    if status is not None:
        query = query.filter(Task.status == status)
    if due_date_from is not None:
        query = query.filter(Task.due_date >= due_date_from)
    if due_date_to is not None:
        query = query.filter(Task.due_date <= due_date_to)
    # created_at is a timestamptz, not a date - an inclusive day-level
    # range means "from the start of created_from" through "before the
    # start of the day after created_to".
    if created_from is not None:
        query = query.filter(Task.created_at >= datetime.combine(created_from, time.min, tzinfo=timezone.utc))
    if created_to is not None:
        query = query.filter(
            Task.created_at < datetime.combine(created_to, time.min, tzinfo=timezone.utc) + timedelta(days=1)
        )
    return query


def list_tasks(
    organization_id: uuid.UUID,
    *,
    scope: PermissionScope,
    caller_membership_id: uuid.UUID,
    assignee_membership_id: uuid.UUID | None,
    department_id: uuid.UUID | None,
    priority: TaskPriority | None,
    status: TaskStatus | None,
    due_date_from: date | None,
    due_date_to: date | None,
    created_from: date | None,
    created_to: date | None,
    page: int,
    per_page: int,
) -> tuple[list[Task], int]:
    query = db.session.query(Task).filter(Task.organization_id == organization_id)

    # `assigned` scope (Employee/Accountant/CustomerSupport): always
    # forced to the caller's own tasks, regardless of any
    # assignee_membership_id they supplied - silently overriding
    # rather than rejecting avoids an oracle for whether a *different*
    # assignee_membership_id even has tasks in this org, and keeps
    # TASK_VIEW_UPDATE's "never a flat 403 on list" property (every
    # caller still gets *some* useful result, just their own).
    if scope == PermissionScope.ASSIGNED:
        query = query.filter(Task.assignee_membership_id == caller_membership_id)
    elif assignee_membership_id is not None:
        query = query.filter(Task.assignee_membership_id == assignee_membership_id)

    query = _apply_filters(
        query,
        department_id=department_id,
        priority=priority,
        status=status,
        due_date_from=due_date_from,
        due_date_to=due_date_to,
        created_from=created_from,
        created_to=created_to,
    )

    total = query.count()
    tasks = query.order_by(Task.created_at.desc()).offset((page - 1) * per_page).limit(per_page).all()
    return tasks, total


def get_task_or_404(organization_id: uuid.UUID, task_id: uuid.UUID) -> Task:
    task = db.session.query(Task).filter_by(id=task_id, organization_id=organization_id).first()
    if task is None:
        raise APIError("Not found.", status_code=404, code="NOT_FOUND")
    return task


def get_task(
    organization_id: uuid.UUID, task_id: uuid.UUID, *, scope: PermissionScope, caller_membership_id: uuid.UUID
) -> Task:
    """`get_task_or_404` already rejects missing/cross-organization
    tasks with 404 (never confirming existence). This is the
    object-level check on top of that - a task that genuinely exists
    in the caller's own organization but that their `assigned` scope
    doesn't reach (not assigned to them) is a 403, not a 404, same
    `can_assign_role`-style distinction FD-016's invitation
    cancellation already established: "authenticated member, record
    exists in your org, you just don't have reach over it" is 403;
    "doesn't exist or isn't yours to even know about" is 404.
    """
    task = get_task_or_404(organization_id, task_id)
    if not check_scope_allows(scope, caller_id=caller_membership_id, assignee_id=task.assignee_membership_id):
        raise APIError("You do not have permission to do this.", status_code=403, code="FORBIDDEN")
    return task


def _validate_assignee(organization_id: uuid.UUID, assignee_membership_id: uuid.UUID | None) -> None:
    """assignee_membership_id, if given, must resolve to a real, active
    Membership in this organization - mirrors
    app.employees.service._validate_manager_membership's pattern (same
    deferred-to-the-service-layer gap Task.assignee_membership_id's own
    docstring names, FD-025). Unlike that one, there's no self-
    reference to reject here - assigning a task to yourself is normal
    (e.g. a Manager assigning themselves work)."""
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


def assign_task(
    organization_id: uuid.UUID,
    task_id: uuid.UUID,
    *,
    actor_membership_id: uuid.UUID,
    assignee_membership_id: uuid.UUID | None,
) -> Task:
    """FD-027. No object-level reach check beyond TASK_CREATE_ASSIGN's
    own full/none scope (unlike EMPLOYEE_MANAGE's Manager-vs-Owner
    restriction) - the baseline matrix's "Create/assign tasks" row has
    no reach nuance to implement, so any Owner/Manager may assign/
    reassign any task in their organization.

    Idempotent: reassigning to the assignee a task already has is a
    no-op, same convention Department's deactivate endpoint already
    established - no spurious TaskHistory row for a change that didn't
    actually happen. A real change records one, with FR-012's "every
    change records actor + timestamp" generalized to this field too
    (the acceptance criterion this task's own title names: "validated
    assignee, history").
    """
    task = get_task_or_404(organization_id, task_id)
    _validate_assignee(organization_id, assignee_membership_id)

    previous_assignee_membership_id = task.assignee_membership_id
    if previous_assignee_membership_id == assignee_membership_id:
        return task

    task.assignee_membership_id = assignee_membership_id
    db.session.add(
        TaskHistory(
            organization_id=organization_id,
            task_id=task.id,
            actor_membership_id=actor_membership_id,
            event_type="assignee_changed",
            previous_value=str(previous_assignee_membership_id) if previous_assignee_membership_id else None,
            new_value=str(assignee_membership_id) if assignee_membership_id else None,
        )
    )
    if assignee_membership_id is not None:
        log_activity(
            organization_id,
            actor_membership_id,
            "task_assigned",
            "task",
            task.id,
            metadata={"assignee_membership_id": str(assignee_membership_id)},
        )
        if assignee_membership_id != actor_membership_id:
            create_notification(
                organization_id,
                assignee_membership_id,
                "task_assigned",
                "You were assigned a task",
                f'You were assigned the task "{task.title}".',
                "task",
                task.id,
            )
    db.session.commit()
    return task


# FD-028's status workflow (FR-012): "To Do -> In Progress -> Under
# Review -> Completed, with Cancelled as a terminal state... managers
# can return tasks for revision; unauthorized transitions are
# blocked." The spec states the happy path and two explicit rules
# (managers may return under_review -> in_progress; cancelled is
# terminal) but not the full graph or who may trigger each edge - the
# rest is a judgment call, grounded directly in spec Section 7.2's own
# "View/update own assigned task" baseline-matrix row (Owner/Manager
# Full, Employee/Accountant/CustomerSupport "If assigned") and
# app/authz/permissions.py's own comment that TASK_VIEW_UPDATE is how
# an employee "act[s] on tasks already assigned to them".
#
# `completed` is treated as terminal too, even though the spec only
# says this explicitly for `cancelled` - the more conservative
# default for an undefined "reopen" concept; easy to revisit later
# since nothing below is migration-dependent.
_STATUS_TRANSITIONS: dict[TaskStatus, set[TaskStatus]] = {
    TaskStatus.TODO: {TaskStatus.IN_PROGRESS, TaskStatus.CANCELLED},
    TaskStatus.IN_PROGRESS: {TaskStatus.UNDER_REVIEW, TaskStatus.CANCELLED},
    TaskStatus.UNDER_REVIEW: {TaskStatus.COMPLETED, TaskStatus.IN_PROGRESS, TaskStatus.CANCELLED},
    TaskStatus.COMPLETED: set(),
    TaskStatus.CANCELLED: set(),
}

# The subset of _STATUS_TRANSITIONS an `assigned`-scope caller (the
# task's own assignee) may trigger themselves, without Owner/Manager
# involvement - only the two "forward progress" moves an assignee
# naturally drives. Approving (-> completed), returning for revision
# (-> in_progress from under_review - FR-012 reserves this to
# managers explicitly), and cancelling are all Owner/Manager-only.
_ASSIGNEE_ALLOWED_TRANSITIONS: set[tuple[TaskStatus, TaskStatus]] = {
    (TaskStatus.TODO, TaskStatus.IN_PROGRESS),
    (TaskStatus.IN_PROGRESS, TaskStatus.UNDER_REVIEW),
}


def update_task_status(
    organization_id: uuid.UUID,
    task_id: uuid.UUID,
    *,
    scope: PermissionScope,
    caller_membership_id: uuid.UUID,
    actor_membership_id: uuid.UUID,
    new_status: TaskStatus,
) -> Task:
    """FD-028. Checked in this order:
    1. Object-level reach (same as get_task) - an `assigned`-scope
       caller acting on a task that isn't theirs is 403, before
       anything else runs. This must come before the idempotency
       no-op check below, or a non-assignee could use a same-status
       request as a free oracle for the task's current status.
    2. Idempotent no-op - requesting the status a task already has
       changes nothing and writes no TaskHistory row, same convention
       assign_task already established.
    3. Graph validity (422 INVALID_STATUS_TRANSITION) - checked for
       *every* caller, Owner/Manager included: a transition that
       doesn't exist in the workflow at all is rejected regardless of
       who's asking.
    4. Role reach for *this specific* transition (403) - only
       `assigned`-scope callers are restricted further, to
       _ASSIGNEE_ALLOWED_TRANSITIONS; `full` scope (Owner/Manager) may
       make any graph-legal transition.
    """
    task = get_task_or_404(organization_id, task_id)
    if not check_scope_allows(scope, caller_id=caller_membership_id, assignee_id=task.assignee_membership_id):
        raise APIError("You do not have permission to do this.", status_code=403, code="FORBIDDEN")

    previous_status = task.status
    if new_status == previous_status:
        return task

    if new_status not in _STATUS_TRANSITIONS.get(previous_status, set()):
        raise APIError(
            f"Cannot transition a task from '{previous_status.value}' to '{new_status.value}'.",
            status_code=422,
            code="INVALID_STATUS_TRANSITION",
            details={"status": f"no such transition from {previous_status.value}"},
        )

    if scope == PermissionScope.ASSIGNED and (previous_status, new_status) not in _ASSIGNEE_ALLOWED_TRANSITIONS:
        raise APIError("You do not have permission to do this.", status_code=403, code="FORBIDDEN")

    task.status = new_status
    db.session.add(
        TaskHistory(
            organization_id=organization_id,
            task_id=task.id,
            actor_membership_id=actor_membership_id,
            event_type="status_changed",
            previous_value=previous_status.value,
            new_value=new_status.value,
        )
    )
    if new_status == TaskStatus.COMPLETED:
        log_activity(
            organization_id, actor_membership_id, "task_completed", "task", task.id, metadata={"title": task.title}
        )
    db.session.commit()
    return task


# FD-029. Order matters: title is listed first so a blank-title
# rejection (the one field whose model-level @validates can raise)
# happens before any other field in the same request gets mutated -
# nothing else in this tuple can fail once _validate_department and
# the merged-date check below have already passed.
_EDITABLE_FIELDS = (
    "title",
    "description",
    "priority",
    "department_id",
    "start_date",
    "due_date",
    "estimated_hours",
    "actual_hours",
)


def _history_str(value) -> str | None:
    if value is None:
        return None
    if isinstance(value, enum.Enum):
        return value.value
    return str(value)


def update_task(organization_id: uuid.UUID, task_id: uuid.UUID, fields: dict, *, actor_membership_id: uuid.UUID) -> Task:
    """`fields` is the caller's `UpdateTaskRequest.model_dump(exclude_unset=True)`
    - only keys actually present in the request body are applied.

    Writes one TaskHistory row per field whose *stored* value actually
    ends up changing - not one per key in `fields` - compared after
    mutation (not before), so a value that only differs from the
    current one by whitespace/representation (e.g. title's own
    @validates strips it, or a Decimal sent with different trailing
    zeros) correctly doesn't produce a spurious no-op history entry.
    A request that changes nothing writes no history, same idempotent
    convention assign_task/update_task_status already established.
    """
    task = get_task_or_404(organization_id, task_id)

    if "department_id" in fields:
        _validate_department(organization_id, fields["department_id"])

    # Date validation against the *merged* state: a field this request
    # doesn't touch keeps the task's current value, so changing only
    # one of start_date/due_date is still checked against whichever
    # one wasn't included here (CreateTaskRequest's equivalent check
    # only ever had to compare two values *within* the same request,
    # since there was no existing task yet).
    resulting_start_date = fields["start_date"] if "start_date" in fields else task.start_date
    resulting_due_date = fields["due_date"] if "due_date" in fields else task.due_date
    if resulting_start_date is not None and resulting_due_date is not None and resulting_due_date < resulting_start_date:
        raise APIError(
            "due_date must not be before start_date.",
            status_code=422,
            code="INVALID_DATE_RANGE",
            details={"due_date": "must not be before start_date"},
        )

    history_entries = []
    for field in _EDITABLE_FIELDS:
        if field not in fields:
            continue
        previous_value = getattr(task, field)
        if field == "title":
            _set_title(task, fields[field])
        else:
            setattr(task, field, fields[field])
        new_value = getattr(task, field)
        if new_value == previous_value:
            continue
        history_entries.append(
            TaskHistory(
                organization_id=organization_id,
                task_id=task.id,
                actor_membership_id=actor_membership_id,
                event_type=f"{field}_changed",
                previous_value=_history_str(previous_value),
                new_value=_history_str(new_value),
            )
        )

    if history_entries:
        db.session.add_all(history_entries)
    db.session.commit()
    return task


def _set_comment_body(comment: TaskComment, body: str) -> None:
    # TaskComment.body's own @validates (strips and rejects a blank
    # result, e.g. whitespace-only, which passes pydantic's
    # min_length=1 but not this) - converted to a 422 here rather than
    # letting the bare ValueError escape as an unhandled 500, same
    # pattern _set_title already established.
    try:
        comment.body = body
    except ValueError as exc:
        raise APIError(str(exc), status_code=422, code="VALIDATION_ERROR", details={"body": str(exc)})


def create_task_comment(
    organization_id: uuid.UUID,
    task_id: uuid.UUID,
    *,
    scope: PermissionScope,
    caller_membership_id: uuid.UUID,
    author_membership_id: uuid.UUID,
    body: str,
) -> TaskComment:
    """FD-030. Reuses get_task's own reach check (404 for missing/
    cross-organization, 403 for an `assigned`-scope caller whose task
    isn't theirs) as the "access-restricted" gate this task's own
    title names - posting a comment requires the same access as
    viewing the task, nothing more. `author_membership_id` is always
    the caller's own membership (set by the route from
    g.current_membership.id), never accepted from the request body.
    """
    task = get_task(organization_id, task_id, scope=scope, caller_membership_id=caller_membership_id)

    comment = TaskComment(organization_id=organization_id, task_id=task.id, author_membership_id=author_membership_id)
    _set_comment_body(comment, body)

    db.session.add(comment)
    if task.assignee_membership_id is not None and task.assignee_membership_id != author_membership_id:
        create_notification(
            organization_id,
            task.assignee_membership_id,
            "task_comment_added",
            "New comment on your task",
            f'A new comment was added to "{task.title}".',
            "task",
            task.id,
        )
    db.session.commit()
    return comment


def list_task_comments(
    organization_id: uuid.UUID,
    task_id: uuid.UUID,
    *,
    scope: PermissionScope,
    caller_membership_id: uuid.UUID,
    page: int,
    per_page: int,
) -> tuple[list[TaskComment], int]:
    """Same reach check as create_task_comment - a caller who can't
    view the task can't see its comments either. Chronological, oldest
    first (a conversation thread), unlike the tasks list's own
    newest-first default."""
    task = get_task(organization_id, task_id, scope=scope, caller_membership_id=caller_membership_id)

    query = db.session.query(TaskComment).filter_by(organization_id=organization_id, task_id=task.id)
    total = query.count()
    comments = query.order_by(TaskComment.created_at.asc()).offset((page - 1) * per_page).limit(per_page).all()
    return comments, total


def list_task_history(
    organization_id: uuid.UUID,
    task_id: uuid.UUID,
    *,
    scope: PermissionScope,
    caller_membership_id: uuid.UUID,
    page: int,
    per_page: int,
) -> tuple[list[TaskHistory], int]:
    """FD-031. No create function exists for TaskHistory, by design -
    "append-only" here means every row is written as a side effect of
    assign_task/update_task_status/update_task (FD-027/028/029), never
    directly through an API call; this is purely the read side. Same
    reach check as list_task_comments - a caller who can't view the
    task can't see its history either. Chronological, oldest first,
    same convention as the comments list and Task.history's own
    order_by (FD-025)."""
    task = get_task(organization_id, task_id, scope=scope, caller_membership_id=caller_membership_id)

    query = db.session.query(TaskHistory).filter_by(organization_id=organization_id, task_id=task.id)
    total = query.count()
    entries = query.order_by(TaskHistory.created_at.asc()).offset((page - 1) * per_page).limit(per_page).all()
    return entries, total


def _today_in_timezone(organization_timezone: str, *, now: datetime | None = None) -> date:
    """FD-033: "today", for overdue purposes, is always the calling
    organization's own local calendar date - never the server's (which
    may run in any timezone) nor derived from `due_date` itself (a
    plain `Date` with no zone of its own). `organization_timezone` is
    `Organization.timezone` (FD-013, an IANA zone name defaulting to
    "UTC") - validated as non-empty at the model level but never
    checked against the real IANA database, so an unrecognized name
    falls back to UTC rather than raising: this runs on every task
    response and must never 500 a request over a stale/bad zone name it
    can't fix here - `TypeError` is caught alongside `ZoneInfoNotFoundError`/
    `ValueError` for the same reason, covering a non-string value
    (e.g. `None`), even though the column itself is non-nullable today.
    `now` is accepted explicitly (rather than always reading the wall
    clock) purely so tests can pin the instant and exercise the
    rollover boundary deterministically.
    """
    try:
        tz = ZoneInfo(organization_timezone)
    except (ZoneInfoNotFoundError, ValueError, TypeError):
        tz = timezone.utc
    reference = now if now is not None else datetime.now(timezone.utc)
    return reference.astimezone(tz).date()


def is_task_overdue(task: Task, organization_timezone: str, *, now: datetime | None = None) -> bool:
    """FD-033 (FR-016): "due date passed and not Completed/Cancelled."
    `due_date` is inclusive through its own day - a task due *today* in
    the organization's timezone isn't overdue until tomorrow arrives."""
    if task.due_date is None or task.status in TERMINAL_TASK_STATUSES:
        return False
    return task.due_date < _today_in_timezone(organization_timezone, now=now)


def serialize_task(task: Task, organization_timezone: str, *, now: datetime | None = None) -> dict:
    """Wraps `Task.to_public_dict()` with the one computed field FD-033
    adds - kept out of the model itself (unlike every other field there,
    which are plain columns) since it's a business rule, not stored
    data, and depends on information (the organization's timezone) the
    model has no business reaching for on its own."""
    return {**task.to_public_dict(), "is_overdue": is_task_overdue(task, organization_timezone, now=now)}
