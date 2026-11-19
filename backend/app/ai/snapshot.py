"""FD-056: idempotent weekly-metrics aggregation - the one producer of
a concrete shape for FD-055's `WeeklyReportInput.metrics_snapshot`
contract. Combines FD-051's four already-deterministic, already-
reviewed analytics functions (`app.analytics.service`) into one
JSON-serializable dict for one organization and one already-resolved
period. This module adds no new query and no new aggregation logic
of its own - everything it returns is already computed by FD-051.

**"Idempotent"**: `build_weekly_metrics_snapshot` is a pure, read-only
function - no database write, no side effect, no caching, no random
component. Calling it twice for the same `(organization_id,
period_start, period_end)` over an unchanged database returns a
byte-for-byte identical result, so retrying it (e.g. after a
transient failure further down a future scheduled job) is always
safe. The *persisted* idempotency a scheduled job needs - never
writing a second `AIReport` row for the same organization+period on
retry - is FD-058's job, not this one: this function has nothing of
its own to deduplicate, since it writes nothing.

**Why `app.ai`, not `app.analytics`**: this module belongs to Epic
E08 (AI Business Assistant)'s own pipeline, not E07 (Analytics,
Activity History and Notifications) - it only *consumes* E07's
already-shipped service functions, the same way
`app.analytics.service.get_overview_metrics` itself already reuses
`app.invoices.service.get_financial_summary` rather than
recomputing it.

**Always `PermissionScope.FULL`, never a caller's own scope** - there
is no HTTP caller here to scope to. A weekly business summary is
inherently an org-wide report (FR-040: "who completed tasks", "what's
still overdue", "invoiced, collected, outstanding" - the whole
organization, never one employee's own view), and this module is
only ever reachable from a future internal job (FD-059, not yet
built), never from a member's own request - there is no route to
this function, unlike every `scope`-taking call in
`app.analytics.routes`, which always comes from `g.permission_scope`.
`caller_membership_id=None` below is genuinely never read -
`get_employee_performance` only consults it when `scope == OWN`,
which this call never passes; a real membership id would misleadingly
imply some specific member is "asking". Likewise
`caller_role=MembershipRole.OWNER` is never read - `get_financial_
analytics` only consults `caller_role` when `scope == LIMITED`.

**Serialization mirrors `app.analytics.routes`'s own JSON response
bodies exactly** (`str()` for `Decimal`, `.isoformat()` for `date`,
`str()` for a UUID) - the same values, shaped the same way, just
combined into one object instead of four HTTP responses - because
this dict is about to be JSON-serialized again
(`app.ai.service._build_user_prompt`) and shipped to an external AI
provider: nothing in it may be a non-JSON-native Python object (a raw
`Decimal`/`date`/`UUID`/ORM instance).

`finance.recent_payments` is trimmed to the same four fields FD-054's
own CSV/PDF export already chose to expose externally
(`payment_date`/`amount`/`method`/`reference`) - not `id`/
`idempotency_key`/`recorded_by`/`notes`, which are internal
bookkeeping with no business-summary value and no reason to leave
this system."""

import uuid
from datetime import date
from decimal import Decimal
from typing import Any

from app.analytics.service import (
    get_department_analytics,
    get_employee_performance,
    get_financial_analytics,
    get_overview_metrics,
)
from app.authz.permissions import MembershipRole, PermissionScope


def _money(value: Decimal) -> str:
    return str(value)


def _serialize_overview(metrics: dict) -> dict[str, Any]:
    return {
        "period_start": metrics["period_start"].isoformat(),
        "period_end": metrics["period_end"].isoformat(),
        "employee_count": metrics["employee_count"],
        "active_tasks": metrics["active_tasks"],
        "completed_tasks": metrics["completed_tasks"],
        "overdue_tasks": metrics["overdue_tasks"],
        "open_requests": metrics["open_requests"],
        "monthly_invoiced": _money(metrics["monthly_invoiced"]),
        "monthly_collected": _money(metrics["monthly_collected"]),
    }


def _serialize_employees(results: list[dict]) -> list[dict[str, Any]]:
    return [
        {
            "membership_id": str(row["membership_id"]),
            "name": row["name"],
            "assigned_tasks": row["assigned_tasks"],
            "completed_tasks": row["completed_tasks"],
            "overdue_tasks": row["overdue_tasks"],
            "completion_rate": row["completion_rate"],
            "avg_completion_time_hours": row["avg_completion_time_hours"],
        }
        for row in results
    ]


def _serialize_departments(results: list[dict]) -> list[dict[str, Any]]:
    return [
        {
            "department_id": str(row["department_id"]) if row["department_id"] is not None else None,
            "department_name": row["department_name"],
            "active_tasks": row["active_tasks"],
            "completed_tasks": row["completed_tasks"],
            "overdue_tasks": row["overdue_tasks"],
            "request_volume": row["request_volume"],
        }
        for row in results
    ]


def _serialize_finance(analytics: dict) -> dict[str, Any]:
    return {
        "total_invoiced": _money(analytics["total_invoiced"]),
        "total_collected": _money(analytics["total_collected"]),
        "outstanding_balance": _money(analytics["outstanding_balance"]),
        "overdue_invoice_count": analytics["overdue_invoice_count"],
        "period_start": analytics["period_start"].isoformat(),
        "period_end": analytics["period_end"].isoformat(),
        "monthly_revenue_collected": _money(analytics["monthly_revenue_collected"]),
        "recent_payments": [
            {
                "payment_date": payment.payment_date.isoformat(),
                "amount": _money(payment.amount),
                "method": payment.method,
                "reference": payment.reference,
            }
            for payment in analytics["recent_payments"]
        ],
        "revenue_by_day": [
            {"date": row["date"].isoformat(), "amount": _money(row["amount"])} for row in analytics["revenue_by_day"]
        ],
        # Already {status_value: count} with string keys and int values
        # (app.analytics.service.get_financial_analytics's own
        # dict-comprehension) - nothing left to serialize.
        "invoice_distribution": analytics["invoice_distribution"],
    }


def build_weekly_metrics_snapshot(
    organization_id: uuid.UUID,
    organization_timezone: str,
    *,
    period_start: date,
    period_end: date,
) -> dict[str, Any]:
    overview = get_overview_metrics(
        organization_id, organization_timezone, PermissionScope.FULL, period_start=period_start, period_end=period_end
    )
    employees = get_employee_performance(
        organization_id,
        organization_timezone,
        PermissionScope.FULL,
        None,  # caller_membership_id - never read for FULL scope, see module docstring
        period_start=period_start,
        period_end=period_end,
    )
    departments = get_department_analytics(
        organization_id, organization_timezone, PermissionScope.FULL, period_start=period_start, period_end=period_end
    )
    finance = get_financial_analytics(
        organization_id,
        organization_timezone,
        PermissionScope.FULL,
        MembershipRole.OWNER,  # caller_role - never read for FULL scope, see module docstring
        period_start=period_start,
        period_end=period_end,
    )

    return {
        "overview": _serialize_overview(overview),
        "employees": _serialize_employees(employees),
        "departments": _serialize_departments(departments),
        "finance": _serialize_finance(finance),
    }
