"""FD-052: the four analytics endpoints (FR-030/031/032/033), all
gated by `Permission.ANALYTICS_VIEW` and thin wrappers around
`app.analytics.service`. Routes - not the service functions
themselves - do the cross-organization existence check for a
caller-supplied `target_membership_id`/`department_id` before calling
in, exactly per the service module's own documented warning that it
otherwise silently returns an empty result rather than a 404 for a
bad id."""

from flask import Blueprint, g, jsonify, request
from pydantic import ValidationError

from app.analytics.schemas import (
    DepartmentAnalyticsQuery,
    EmployeeAnalyticsQuery,
    FinancialAnalyticsQuery,
    OverviewAnalyticsQuery,
)
from app.analytics.service import (
    get_department_analytics,
    get_employee_performance,
    get_financial_analytics,
    get_overview_metrics,
    resolve_period_filter,
)
from app.auth.decorators import login_required
from app.authz.decorators import require_permission
from app.authz.permissions import Permission
from app.departments.service import get_department_or_404
from app.employees.service import get_target_membership_or_404
from app.errors import APIError, validation_error_details

analytics_bp = Blueprint("analytics", __name__)


def _validate_query(schema_cls, args):
    try:
        return schema_cls.model_validate(args)
    except ValidationError as exc:
        raise APIError(
            "Validation failed", status_code=422, code="VALIDATION_ERROR", details=validation_error_details(exc)
        )


@analytics_bp.route("/organizations/<uuid:organization_id>/analytics/overview", methods=["GET"])
@login_required
@require_permission(Permission.ANALYTICS_VIEW)
def get_analytics_overview(organization_id):
    query = _validate_query(OverviewAnalyticsQuery, request.args.to_dict())
    organization_timezone = g.current_membership.organization.timezone
    period_start, period_end = resolve_period_filter(
        query.period, organization_timezone, period_start=query.period_start, period_end=query.period_end
    )

    metrics = get_overview_metrics(
        organization_id, organization_timezone, g.permission_scope, period_start=period_start, period_end=period_end
    )

    body = {
        "success": True,
        "message": "Overview analytics retrieved",
        "data": {
            "period_start": metrics["period_start"].isoformat(),
            "period_end": metrics["period_end"].isoformat(),
            "employee_count": metrics["employee_count"],
            "active_tasks": metrics["active_tasks"],
            "completed_tasks": metrics["completed_tasks"],
            "overdue_tasks": metrics["overdue_tasks"],
            "open_requests": metrics["open_requests"],
            "monthly_invoiced": str(metrics["monthly_invoiced"]),
            "monthly_collected": str(metrics["monthly_collected"]),
        },
    }
    return jsonify(body), 200


@analytics_bp.route("/organizations/<uuid:organization_id>/analytics/employees", methods=["GET"])
@login_required
@require_permission(Permission.ANALYTICS_VIEW)
def get_analytics_employees(organization_id):
    query = _validate_query(EmployeeAnalyticsQuery, request.args.to_dict())
    organization_timezone = g.current_membership.organization.timezone
    period_start, period_end = resolve_period_filter(
        query.period, organization_timezone, period_start=query.period_start, period_end=query.period_end
    )

    if query.target_membership_id is not None:
        get_target_membership_or_404(organization_id, query.target_membership_id)

    results = get_employee_performance(
        organization_id,
        organization_timezone,
        g.permission_scope,
        g.current_membership.id,
        period_start=period_start,
        period_end=period_end,
        target_membership_id=query.target_membership_id,
    )

    body = {
        "success": True,
        "message": "Employee performance analytics retrieved",
        "data": [
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
        ],
        "meta": {"period_start": period_start.isoformat(), "period_end": period_end.isoformat()},
    }
    return jsonify(body), 200


@analytics_bp.route("/organizations/<uuid:organization_id>/analytics/departments", methods=["GET"])
@login_required
@require_permission(Permission.ANALYTICS_VIEW)
def get_analytics_departments(organization_id):
    query = _validate_query(DepartmentAnalyticsQuery, request.args.to_dict())
    organization_timezone = g.current_membership.organization.timezone
    period_start, period_end = resolve_period_filter(
        query.period, organization_timezone, period_start=query.period_start, period_end=query.period_end
    )

    if query.department_id is not None:
        get_department_or_404(organization_id, query.department_id)

    results = get_department_analytics(
        organization_id,
        organization_timezone,
        g.permission_scope,
        period_start=period_start,
        period_end=period_end,
        department_id=query.department_id,
    )

    body = {
        "success": True,
        "message": "Department analytics retrieved",
        "data": [
            {
                "department_id": str(row["department_id"]) if row["department_id"] is not None else None,
                "department_name": row["department_name"],
                "active_tasks": row["active_tasks"],
                "completed_tasks": row["completed_tasks"],
                "overdue_tasks": row["overdue_tasks"],
                "request_volume": row["request_volume"],
            }
            for row in results
        ],
        "meta": {"period_start": period_start.isoformat(), "period_end": period_end.isoformat()},
    }
    return jsonify(body), 200


@analytics_bp.route("/organizations/<uuid:organization_id>/analytics/finance", methods=["GET"])
@login_required
@require_permission(Permission.ANALYTICS_VIEW)
def get_analytics_finance(organization_id):
    query = _validate_query(FinancialAnalyticsQuery, request.args.to_dict())
    organization_timezone = g.current_membership.organization.timezone
    period_start, period_end = resolve_period_filter(
        query.period, organization_timezone, period_start=query.period_start, period_end=query.period_end
    )

    analytics = get_financial_analytics(
        organization_id,
        organization_timezone,
        g.permission_scope,
        g.current_membership.role,
        period_start=period_start,
        period_end=period_end,
    )

    body = {
        "success": True,
        "message": "Financial analytics retrieved",
        "data": {
            "total_invoiced": str(analytics["total_invoiced"]),
            "total_collected": str(analytics["total_collected"]),
            "outstanding_balance": str(analytics["outstanding_balance"]),
            "overdue_invoice_count": analytics["overdue_invoice_count"],
            "period_start": analytics["period_start"].isoformat(),
            "period_end": analytics["period_end"].isoformat(),
            "monthly_revenue_collected": str(analytics["monthly_revenue_collected"]),
            "recent_payments": [payment.to_public_dict() for payment in analytics["recent_payments"]],
            "revenue_by_day": [
                {"date": row["date"].isoformat(), "amount": str(row["amount"])} for row in analytics["revenue_by_day"]
            ],
            "invoice_distribution": analytics["invoice_distribution"],
        },
    }
    return jsonify(body), 200
