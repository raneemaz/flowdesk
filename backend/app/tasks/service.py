"""FD-026: task creation and retrieval (list + single).

Scope-based access is simpler here than the employee directory's
(FD-022): TASK_VIEW_UPDATE only ever grants `full` or `assigned` (see
app/authz/permissions.py) - never `limited` - so every caller who can
see a task sees *all* its fields; the only thing a granted scope
restricts is *which* tasks are visible at all, never which columns.
`assigned` is this codebase's first scope that needs translating into
a list-query row filter rather than a field-visibility filter.
"""

import uuid
from datetime import date, datetime, time, timedelta, timezone

from app.authz.permissions import PermissionScope
from app.authz.service import check_scope_allows
from app.errors import APIError
from app.extensions import db
from app.models import Department, DepartmentStatus, Task, TaskPriority, TaskStatus


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
