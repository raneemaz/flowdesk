"""FD-061: the permission-aware tool registry the conversational
assistant can call (FR-041). Each tool is a thin wrapper around one of
FD-051's own already-reviewed analytics functions - no new
authorization logic is invented here; a tool's real result still
depends entirely on the real caller's own scope/role, exactly as if
they'd called the equivalent HTTP endpoint directly
(`app.analytics.routes`).

Every tool's input schema is intentionally limited to the FR-034
period taxonomy only - no `target_membership_id`/`department_id`
filter is exposed to the model. Resolving a name the user typed ("how
is Ada doing") to a membership/department id would need a further
"search by name" tool this task was never asked to build; the model
can filter/summarize from a tool's own full-organization result in
its own final answer instead.

**"Permission-aware"**: a tool call the real caller's own role/scope
isn't allowed to make (`app.analytics.service`'s own internal
`_require_full_scope`/role checks, unchanged) raises `APIError`,
caught here and turned into a `{"error": ...}` JSON tool result fed
back to the model - never a crashed request. The model sees this like
any other tool result and is instructed (system prompt,
`app.ai_assistant.service`) to tell the user plainly it can't access
that information, never to guess a plausible-sounding number instead.

Serialization mirrors `app.analytics.routes`'s own JSON response
bodies exactly (`str()` for `Decimal`, `.isoformat()` for `date`,
`str()` for a UUID) - duplicated, not imported, same "don't
cross-import a private per-module helper" convention this codebase
already follows (e.g. `app.ai.snapshot`'s own near-identical
serializers)."""

import uuid
from datetime import date

from app.ai.providers import AIToolDefinition
from app.analytics.service import (
    get_department_analytics,
    get_employee_performance,
    get_financial_analytics,
    get_overview_metrics,
    resolve_period_filter,
)
from app.authz.permissions import MembershipRole, PermissionScope
from app.errors import APIError
from app.models import Organization

_PERIOD_SCHEMA = {
    "type": "object",
    "properties": {
        "period": {
            "type": "string",
            "enum": ["last_7_days", "last_30_days", "last_90_days", "current_month", "previous_month", "custom"],
            "description": "Which reporting period to use. Default to current_month unless the user names a different one.",
        },
        "period_start": {
            "type": "string",
            "description": "ISO date (YYYY-MM-DD). Required, and only allowed, when period is custom.",
        },
        "period_end": {
            "type": "string",
            "description": "ISO date (YYYY-MM-DD). Required, and only allowed, when period is custom.",
        },
    },
    "required": ["period"],
}

TOOL_DEFINITIONS = [
    AIToolDefinition(
        name="get_overview_metrics",
        description=(
            "Org-wide overview for a period: employee count, active/completed/overdue tasks, open requests, "
            "monthly invoiced/collected. Only available to Owner/Manager - returns an error for any other role."
        ),
        input_schema=_PERIOD_SCHEMA,
    ),
    AIToolDefinition(
        name="get_employee_performance",
        description=(
            "Per-employee task performance for a period: assigned/completed/overdue tasks, completion rate, "
            "average completion time. An Employee only ever sees their own row, regardless of who else exists."
        ),
        input_schema=_PERIOD_SCHEMA,
    ),
    AIToolDefinition(
        name="get_department_analytics",
        description=(
            "Per-department breakdown for a period: active/completed/overdue tasks and customer request volume. "
            "Only available to Owner/Manager - returns an error for any other role."
        ),
        input_schema=_PERIOD_SCHEMA,
    ),
    AIToolDefinition(
        name="get_financial_analytics",
        description=(
            "Financial analytics for a period: total invoiced/collected, outstanding balance, overdue invoice "
            "count, revenue by day, invoice distribution by status. Only available to Owner/Manager/Accountant - "
            "returns an error for any other role."
        ),
        input_schema=_PERIOD_SCHEMA,
    ),
]


def _parse_optional_date(value) -> date | None:
    if value is None:
        return None
    return date.fromisoformat(value)


def _resolve_period(organization: Organization, tool_input: dict) -> tuple[date, date]:
    return resolve_period_filter(
        tool_input.get("period", "current_month"),
        organization.timezone,
        period_start=_parse_optional_date(tool_input.get("period_start")),
        period_end=_parse_optional_date(tool_input.get("period_end")),
    )


def _money(value) -> str:
    return str(value)


def _serialize_overview(metrics: dict) -> dict:
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


def _serialize_employees(results: list[dict]) -> dict:
    return {
        "employees": [
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
    }


def _serialize_departments(results: list[dict]) -> dict:
    return {
        "departments": [
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
    }


def _serialize_finance(analytics: dict) -> dict:
    return {
        "total_invoiced": _money(analytics["total_invoiced"]),
        "total_collected": _money(analytics["total_collected"]),
        "outstanding_balance": _money(analytics["outstanding_balance"]),
        "overdue_invoice_count": analytics["overdue_invoice_count"],
        "period_start": analytics["period_start"].isoformat(),
        "period_end": analytics["period_end"].isoformat(),
        "monthly_revenue_collected": _money(analytics["monthly_revenue_collected"]),
        "revenue_by_day": [
            {"date": row["date"].isoformat(), "amount": _money(row["amount"])} for row in analytics["revenue_by_day"]
        ],
        # Already {status_value: count} with string keys and int values.
        "invoice_distribution": analytics["invoice_distribution"],
        # recent_payments deliberately omitted - the assistant answers
        # aggregate questions (FR-041's own examples), never "list my
        # payments"; that's not a question this tool set was asked to
        # serve.
    }


def execute_tool(
    tool_name: str,
    tool_input: dict,
    *,
    organization: Organization,
    scope: PermissionScope,
    role: MembershipRole,
    caller_membership_id: uuid.UUID,
) -> dict:
    """Runs one tool call with the REAL caller's own scope/role - never
    a broader one. Always returns a plain JSON-serializable dict:
    either the real (already-authorized) result, or `{"error": ...}`
    if the caller's own role/scope doesn't allow this tool, or the
    period itself was invalid - never raises, so one denied/invalid
    tool call never aborts the whole conversation."""
    try:
        period_start, period_end = _resolve_period(organization, tool_input)
    except (ValueError, APIError) as exc:
        message = exc.message if isinstance(exc, APIError) else str(exc)
        return {"error": f"Invalid period: {message}"}

    try:
        if tool_name == "get_overview_metrics":
            metrics = get_overview_metrics(
                organization.id, organization.timezone, scope, period_start=period_start, period_end=period_end
            )
            return _serialize_overview(metrics)
        if tool_name == "get_employee_performance":
            results = get_employee_performance(
                organization.id,
                organization.timezone,
                scope,
                caller_membership_id,
                period_start=period_start,
                period_end=period_end,
            )
            return _serialize_employees(results)
        if tool_name == "get_department_analytics":
            results = get_department_analytics(
                organization.id, organization.timezone, scope, period_start=period_start, period_end=period_end
            )
            return _serialize_departments(results)
        if tool_name == "get_financial_analytics":
            analytics = get_financial_analytics(
                organization.id, organization.timezone, scope, role, period_start=period_start, period_end=period_end
            )
            return _serialize_finance(analytics)
    except APIError as exc:
        return {"error": exc.message}

    return {"error": f"Unknown tool: {tool_name}"}
