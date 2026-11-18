"""FD-051: the analytics service - deterministic metrics, explicit
periods, org-scoped (this task's own title names all three required
properties). Service layer only: no routes/schemas here. FD-052
("analytics API... date filters") is the separate future task that
exposes these functions over HTTP and resolves the named date-filter
taxonomy (last 7/30/90 days, current/previous month, custom range,
FR-034) into the `period_start`/`period_end` dates every function here
takes as **required, already-resolved** arguments - "explicit periods"
means this module never infers or defaults a period itself, unlike
`app.invoices.service.get_financial_summary` (FD-044), which predates
this requirement and still defaults to the current calendar month when
omitted. That leniency is left alone; every call into it from here
always passes explicit dates.

Design principle #5 (spec Section 4.2): "Explainable analytics -
calculations are deterministic and traceable to stored data." Every
number below is a plain aggregate (`COUNT`/`SUM`/`AVG`) over real rows,
never estimated, interpolated, or carried over from a cache. Principle
#6 ("AI as an interpreter, not an accountant") is why there is no
AI-facing summarization here - a later epic (AIReport, FD-055+)
*consumes* this service's output as its own `metrics_snapshot`, never
the reverse.

**Four categories, matching FD-052's own title ("overview/employee/
department/finance") and FR-030/031/032/033** - the FRs, not the
`Permission.ANALYTICS_VIEW` comments, are what actually define the
category boundaries used here:
- `get_overview_metrics` (FR-030) - FULL scope only (Owner/Manager;
  Section 12.3 only ever lists an org-wide overview on their own
  dashboards).
- `get_employee_performance` (FR-031) - FULL sees any/every employee;
  OWN (Employee) is silently forced to the caller's own membership
  regardless of what was asked, same oracle-prevention convention
  `app.tasks.service.list_tasks` already established for `assigned`
  scope.
- `get_department_analytics` (FR-032) - FULL scope only (Section
  12.3's "department-level activity" is named only on the Manager
  dashboard).
- `get_financial_analytics` (FR-033) - FULL, **or** LIMITED when the
  caller's role is Accountant (`ANALYTICS_VIEW`'s own LIMITED comment:
  "the financial analytics subset... not operational/task/employee
  analytics") - same scope+role disambiguation pattern
  `app.activity.service.list_activity` already established for a
  LIMITED value with more than one meaning.

**CustomerSupport's own LIMITED grant ("the customer/request analytics
subset (volume, resolution time)") has no matching function here** -
a deliberate, documented gap, not an oversight: FR-030 through FR-033
name exactly four categories, none of them a customer/request-specific
one, and Section 12.3's own CustomerSupport dashboard ("open/waiting
requests, assignments, response workload") is already fully served by
the real-time `GET .../customer-requests` list endpoint FD-037 already
built, with its own filters - there is no FR asking for a *historical/
aggregate* customer-analytics view for this role. Revisiting this is a
decision for whichever future task (if any) actually names that
requirement, not something to invent here.

**Department-level request volume is derived, not stored** -
`CustomerRequest` has no `department_id` of its own (its own model
docstring: "unlike Task, FR-018 never lists a department"), so
`get_department_analytics` attributes a request to a department via
its assignee's own `EmployeeProfile.department_id` (a join). A request
with no assignee, or whose assignee has no `EmployeeProfile` row yet,
contributes to no department's count - never silently folded into an
arbitrary bucket.

**A cross-organization `target_membership_id`/`department_id` yields
an empty result, never an error** - `get_employee_performance`/
`get_department_analytics` filter the given id by `organization_id`
and simply produce nothing for one that doesn't resolve, the same
"indistinguishable from legitimate empty data, no existence oracle"
shape every other cross-tenant case in this codebase uses. This means
neither function can tell a future route layer "that id isn't yours";
FD-052's own route must do its own membership/department
existence-and-ownership lookup first if it wants to return `404`
rather than `200` with an empty list/array for a bad id.

**No separate "trend" computation** - FR-032's "completion trends" and
the Epic's own caution ("no fabricated trends when comparison data is
missing") are deliberately not built as a dedicated time-series field
here. Every count below is already period-scoped; a caller wanting a
trend calls this twice (once per period) and compares the two real,
independently-computed results - inventing an interpolated/synthetic
single-call "trend" field risks exactly the fabrication the Epic
criterion warns against, for a shape no FR actually specifies.
"""

import uuid
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import func

from app.authz.permissions import PermissionScope
from app.errors import APIError
from app.extensions import db
from app.invoices.service import get_financial_summary
from app.models import (
    CustomerRequest,
    Department,
    EmployeeProfile,
    Invoice,
    InvoiceStatus,
    Membership,
    MembershipRole,
    MembershipStatus,
    Payment,
    RequestStatus,
    Task,
    TaskHistory,
    TaskStatus,
    User,
)

_TERMINAL_TASK_STATUSES = (TaskStatus.COMPLETED, TaskStatus.CANCELLED)
_OPEN_REQUEST_STATUSES_EXCLUDED = (RequestStatus.RESOLVED, RequestStatus.CLOSED)
# Duplicated from app.invoices.service's own (private) constant of the
# same name/values - same "don't cross-import a private per-module
# helper" convention `_today_in_timezone` below already follows.
_EVER_INVOICED_STATUSES = (InvoiceStatus.SENT, InvoiceStatus.PARTIALLY_PAID, InvoiceStatus.OVERDUE, InvoiceStatus.PAID)


def _require_full_scope(scope: PermissionScope) -> None:
    if scope != PermissionScope.FULL:
        raise APIError("You do not have permission to do this.", status_code=403, code="FORBIDDEN")


def _validate_period(period_start: date, period_end: date) -> None:
    if period_end < period_start:
        raise APIError(
            "period_end must not be before period_start.",
            status_code=422,
            code="INVALID_PERIOD",
            details={"period_end": "must not be before period_start"},
        )


def _today_in_timezone(organization_timezone: str, *, now: datetime | None = None) -> date:
    """Identical in intent to `app.tasks.service._today_in_timezone`/
    `app.invoices.service._today_in_timezone` (FD-033/FD-042) -
    duplicated rather than imported, same "no shared utility module for
    this yet" precedent those two already established."""
    try:
        tz = ZoneInfo(organization_timezone)
    except (ZoneInfoNotFoundError, ValueError, TypeError):
        tz = timezone.utc
    reference = now if now is not None else datetime.now(timezone.utc)
    return reference.astimezone(tz).date()


def _datetime_range(period_start: date, period_end: date) -> tuple[datetime, datetime]:
    """An inclusive day-level `[start, end)` range for comparing a
    `date` period against a `timestamptz` column - same UTC-anchored
    simplification `app.tasks.service.list_tasks`'s own
    `created_from`/`created_to` filters already established (not
    org-timezone-aware; a deliberate, already-precedented
    simplification for day-level range filtering, not a new one
    introduced here)."""
    start = datetime.combine(period_start, time.min, tzinfo=timezone.utc)
    end = datetime.combine(period_end, time.min, tzinfo=timezone.utc) + timedelta(days=1)
    return start, end


def _sum_decimal(query) -> Decimal:
    result = query.scalar()
    return result if result is not None else Decimal("0.00")


def get_overview_metrics(
    organization_id: uuid.UUID,
    organization_timezone: str,
    scope: PermissionScope,
    *,
    period_start: date,
    period_end: date,
    now: datetime | None = None,
) -> dict:
    """FR-030. FULL scope only. `employee_count`/`active_tasks`/
    `overdue_tasks`/`open_requests` are current-state snapshots (not
    period-scoped - "how many right now", same convention
    `app.invoices.service._refresh_overdue_invoices`'s own
    `overdue_invoice_count` already uses); `completed_tasks` and the
    two money fields are the ones this period actually bounds.
    `monthly_collected` reuses `get_financial_summary`'s own
    `monthly_revenue_collected` computation exactly (and gets its
    overdue-invoice refresh as a side effect) rather than duplicating
    it; `monthly_invoiced` is this module's own query, since
    `get_financial_summary`'s own `total_invoiced` is deliberately
    all-time, not period-scoped (FD-044)."""
    _require_full_scope(scope)
    _validate_period(period_start, period_end)
    today = _today_in_timezone(organization_timezone, now=now)

    employee_count = (
        db.session.query(func.count(Membership.id))
        .filter(Membership.organization_id == organization_id, Membership.status == MembershipStatus.ACTIVE)
        .scalar()
    )

    active_tasks = (
        db.session.query(func.count(Task.id))
        .filter(Task.organization_id == organization_id, Task.status.notin_(_TERMINAL_TASK_STATUSES))
        .scalar()
    )

    history_start, history_end = _datetime_range(period_start, period_end)
    completed_tasks = (
        db.session.query(func.count(TaskHistory.id))
        .filter(
            TaskHistory.organization_id == organization_id,
            TaskHistory.event_type == "status_changed",
            TaskHistory.new_value == TaskStatus.COMPLETED.value,
            TaskHistory.created_at >= history_start,
            TaskHistory.created_at < history_end,
        )
        .scalar()
    )

    overdue_tasks = (
        db.session.query(func.count(Task.id))
        .filter(
            Task.organization_id == organization_id,
            Task.due_date.isnot(None),
            Task.due_date < today,
            Task.status.notin_(_TERMINAL_TASK_STATUSES),
        )
        .scalar()
    )

    open_requests = (
        db.session.query(func.count(CustomerRequest.id))
        .filter(
            CustomerRequest.organization_id == organization_id,
            CustomerRequest.status.notin_(_OPEN_REQUEST_STATUSES_EXCLUDED),
        )
        .scalar()
    )

    monthly_invoiced = _sum_decimal(
        db.session.query(func.sum(Invoice.total)).filter(
            Invoice.organization_id == organization_id,
            Invoice.status.in_(_EVER_INVOICED_STATUSES),
            Invoice.issue_date.isnot(None),
            Invoice.issue_date >= period_start,
            Invoice.issue_date <= period_end,
        )
    )
    monthly_collected = get_financial_summary(
        organization_id, organization_timezone, period_start=period_start, period_end=period_end, now=now
    )["monthly_revenue_collected"]

    return {
        "period_start": period_start,
        "period_end": period_end,
        "employee_count": employee_count,
        "active_tasks": active_tasks,
        "completed_tasks": completed_tasks,
        "overdue_tasks": overdue_tasks,
        "open_requests": open_requests,
        "monthly_invoiced": monthly_invoiced,
        "monthly_collected": monthly_collected,
    }


def get_employee_performance(
    organization_id: uuid.UUID,
    organization_timezone: str,
    scope: PermissionScope,
    caller_membership_id: uuid.UUID,
    *,
    period_start: date,
    period_end: date,
    target_membership_id: uuid.UUID | None = None,
) -> list[dict]:
    """FR-031 ("raw task counts are not a complete performance
    measure" - `completion_rate`/`avg_completion_time_hours` are
    included for exactly that reason, not as a replacement for the raw
    counts, which stay alongside them). `OWN` scope (Employee) is
    silently forced to the caller's own membership regardless of
    `target_membership_id` - never a flat 403, same oracle-prevention
    convention `list_tasks`'s own `assigned` scope already established.
    `FULL` (Owner/Manager) may pass `target_membership_id` to scope to
    one employee, or omit it for every active employee in the org.
    Any other scope is rejected.

    `assigned_tasks` counts tasks **created** within the period whose
    *current* assignee is this member - a documented simplification: a
    task reassigned into this member mid-period, but created earlier,
    isn't counted as "assigned" to them this period even though the
    reassignment itself happened in-period. `completed_tasks` is the
    precise one: every `TaskHistory` row marking *this member's* task
    completed within the period, which also drives
    `avg_completion_time_hours` (completion event time minus the
    task's own `created_at`, averaged over that same set - never
    computed from a different set than the count it's paired with).
    `completion_rate`/`avg_completion_time_hours` are `None`, never
    `0`/fabricated, when their denominator is zero - no performance
    signal exists to report yet.
    """
    if scope == PermissionScope.OWN:
        membership_ids = [caller_membership_id]
    elif scope == PermissionScope.FULL:
        if target_membership_id is not None:
            membership_ids = [target_membership_id]
        else:
            membership_ids = [
                row[0]
                for row in db.session.query(Membership.id)
                .filter(Membership.organization_id == organization_id, Membership.status == MembershipStatus.ACTIVE)
                .all()
            ]
    else:
        raise APIError("You do not have permission to do this.", status_code=403, code="FORBIDDEN")

    _validate_period(period_start, period_end)
    task_created_start, task_created_end = _datetime_range(period_start, period_end)
    history_start, history_end = task_created_start, task_created_end
    today = _today_in_timezone(organization_timezone)

    results = []
    for membership_id in membership_ids:
        membership = db.session.query(Membership).filter_by(id=membership_id, organization_id=organization_id).first()
        if membership is None:
            continue
        name = db.session.query(User.name).filter(User.id == membership.user_id).scalar()

        assigned_tasks = (
            db.session.query(func.count(Task.id))
            .filter(
                Task.organization_id == organization_id,
                Task.assignee_membership_id == membership_id,
                Task.created_at >= task_created_start,
                Task.created_at < task_created_end,
            )
            .scalar()
        )

        completion_rows = (
            db.session.query(TaskHistory.created_at, Task.created_at)
            .join(Task, TaskHistory.task_id == Task.id)
            .filter(
                TaskHistory.organization_id == organization_id,
                TaskHistory.event_type == "status_changed",
                TaskHistory.new_value == TaskStatus.COMPLETED.value,
                TaskHistory.created_at >= history_start,
                TaskHistory.created_at < history_end,
                Task.assignee_membership_id == membership_id,
            )
            .all()
        )
        completed_tasks = len(completion_rows)
        if completed_tasks:
            total_hours = sum((completed_at - task_created_at).total_seconds() / 3600 for completed_at, task_created_at in completion_rows)
            avg_completion_time_hours = total_hours / completed_tasks
        else:
            avg_completion_time_hours = None

        overdue_tasks = (
            db.session.query(func.count(Task.id))
            .filter(
                Task.organization_id == organization_id,
                Task.assignee_membership_id == membership_id,
                Task.due_date.isnot(None),
                Task.due_date < today,
                Task.status.notin_(_TERMINAL_TASK_STATUSES),
            )
            .scalar()
        )

        completion_rate = (completed_tasks / assigned_tasks) if assigned_tasks else None

        results.append(
            {
                "membership_id": membership_id,
                "name": name,
                "assigned_tasks": assigned_tasks,
                "completed_tasks": completed_tasks,
                "overdue_tasks": overdue_tasks,
                "completion_rate": completion_rate,
                "avg_completion_time_hours": avg_completion_time_hours,
            }
        )

    return results


def get_department_analytics(
    organization_id: uuid.UUID,
    organization_timezone: str,
    scope: PermissionScope,
    *,
    period_start: date,
    period_end: date,
    department_id: uuid.UUID | None = None,
) -> list[dict]:
    """FR-032. FULL scope only. One entry per active department in the
    organization (or just `department_id` if given), plus a trailing
    `department_id: None` entry for tasks genuinely unassigned to any
    department (`Task.department_id` is nullable) - never silently
    dropped. `request_volume` is derived via each request's assignee's
    own `EmployeeProfile.department_id` (see module docstring) and has
    no "no department" bucket of its own - an unattributable request
    (no assignee, or an assignee with no profile row) simply isn't
    counted anywhere, a different kind of gap than a task's genuinely
    nullable column.
    """
    _require_full_scope(scope)
    _validate_period(period_start, period_end)
    today = _today_in_timezone(organization_timezone)
    history_start, history_end = _datetime_range(period_start, period_end)
    request_start, request_end = _datetime_range(period_start, period_end)

    if department_id is not None:
        departments = (
            db.session.query(Department).filter_by(id=department_id, organization_id=organization_id).all()
        )
        include_unassigned = False
    else:
        departments = db.session.query(Department).filter_by(organization_id=organization_id).all()
        include_unassigned = True

    results = []
    for department in [*departments, None]:
        if department is None and not include_unassigned:
            continue
        dept_id = department.id if department is not None else None

        task_filter = [Task.organization_id == organization_id, Task.department_id == dept_id]
        active_tasks = (
            db.session.query(func.count(Task.id))
            .filter(*task_filter, Task.status.notin_(_TERMINAL_TASK_STATUSES))
            .scalar()
        )
        completed_tasks = (
            db.session.query(func.count(TaskHistory.id))
            .join(Task, TaskHistory.task_id == Task.id)
            .filter(
                TaskHistory.organization_id == organization_id,
                TaskHistory.event_type == "status_changed",
                TaskHistory.new_value == TaskStatus.COMPLETED.value,
                TaskHistory.created_at >= history_start,
                TaskHistory.created_at < history_end,
                Task.department_id == dept_id,
            )
            .scalar()
        )
        overdue_tasks = (
            db.session.query(func.count(Task.id))
            .filter(
                *task_filter,
                Task.due_date.isnot(None),
                Task.due_date < today,
                Task.status.notin_(_TERMINAL_TASK_STATUSES),
            )
            .scalar()
        )

        if dept_id is None:
            request_volume = 0
        else:
            request_volume = (
                db.session.query(func.count(CustomerRequest.id))
                .join(EmployeeProfile, CustomerRequest.assignee_membership_id == EmployeeProfile.membership_id)
                .filter(
                    CustomerRequest.organization_id == organization_id,
                    EmployeeProfile.department_id == dept_id,
                    CustomerRequest.created_at >= request_start,
                    CustomerRequest.created_at < request_end,
                )
                .scalar()
            )

        results.append(
            {
                "department_id": dept_id,
                "department_name": department.name if department is not None else None,
                "active_tasks": active_tasks,
                "completed_tasks": completed_tasks,
                "overdue_tasks": overdue_tasks,
                "request_volume": request_volume,
            }
        )

    return results


def get_financial_analytics(
    organization_id: uuid.UUID,
    organization_timezone: str,
    scope: PermissionScope,
    caller_role: MembershipRole,
    *,
    period_start: date,
    period_end: date,
    now: datetime | None = None,
) -> dict:
    """FR-033. `FULL`, or `LIMITED` when the caller is an Accountant -
    same scope+role disambiguation `app.activity.service.list_activity`
    already established for `ACTIVITY_HISTORY_VIEW`'s own dual-meaning
    `LIMITED`. Returns `get_financial_summary`'s own dict (FD-044:
    `total_invoiced`/`total_collected`/`outstanding_balance`/
    `overdue_invoice_count`/`monthly_revenue_collected`/
    `recent_payments`, already correctly all-time vs. period-scoped per
    field - not re-derived here) merged with two new, genuinely
    period-scoped fields: `revenue_by_day` (one real `Payment` sum per
    calendar day that actually had a payment - never a zero-filled day
    for a date nothing happened on) serves both "revenue over time"
    and "payment trends" from FR-033, which this module reads as the
    same underlying time series described two ways rather than two
    separately-computed, identically-shaped fields; `invoice_distribution`
    is a count of this organization's invoices, grouped by status,
    issued within the period.

    **`caller_role` is security-relevant** (the `LIMITED`+Accountant
    half of the check below) - it must always come from the caller's
    own server-resolved membership (e.g. `g.current_membership.role`),
    never from request body/query input. There is no route here yet to
    enforce that; FD-052's own route must not wire this from anything
    client-supplied.
    """
    if not (scope == PermissionScope.FULL or (scope == PermissionScope.LIMITED and caller_role == MembershipRole.ACCOUNTANT)):
        raise APIError("You do not have permission to do this.", status_code=403, code="FORBIDDEN")
    _validate_period(period_start, period_end)

    summary = get_financial_summary(
        organization_id, organization_timezone, period_start=period_start, period_end=period_end, now=now
    )

    revenue_rows = (
        db.session.query(Payment.payment_date, func.sum(Payment.amount))
        .filter(
            Payment.organization_id == organization_id,
            Payment.payment_date >= period_start,
            Payment.payment_date <= period_end,
        )
        .group_by(Payment.payment_date)
        .order_by(Payment.payment_date.asc())
        .all()
    )
    revenue_by_day = [{"date": payment_date, "amount": amount} for payment_date, amount in revenue_rows]

    distribution_rows = (
        db.session.query(Invoice.status, func.count(Invoice.id))
        .filter(
            Invoice.organization_id == organization_id,
            Invoice.issue_date.isnot(None),
            Invoice.issue_date >= period_start,
            Invoice.issue_date <= period_end,
        )
        .group_by(Invoice.status)
        .all()
    )
    invoice_distribution = {status.value: count for status, count in distribution_rows}

    return {
        **summary,
        "revenue_by_day": revenue_by_day,
        "invoice_distribution": invoice_distribution,
    }
