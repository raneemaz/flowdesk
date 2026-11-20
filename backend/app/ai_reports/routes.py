"""FD-058: the three `ai-reports` HTTP endpoints (Section 11.1's own
outline: "AI Reports | GET/POST | .../ai-reports[/{id}], /generate").

All three are gated by **`require_permission(Permission.ANALYTICS_VIEW)`**
plus an explicit **`scope == PermissionScope.FULL`** check in this
module (never delegated to a service-layer helper, unlike
`app.analytics.service`'s own `_require_full_scope` - there's no
per-category scope split to make here, every AI report is the same
org-wide shape) - reusing `ANALYTICS_VIEW` rather than inventing a new
`Permission` the spec never names, required for consistency: a
report's content includes department/employee/overview data an
Accountant/CustomerSupport (`LIMITED`) or Employee (`OWN`) can't
otherwise see via the analytics API at their own scope, so letting
them read a full AI report would be a real authorization leak, not
just a style inconsistency.

`POST .../ai-reports/generate` is the only state-changing endpoint
here (`@csrf_protect`) - it both calls the real AI provider and
writes a database row. A collision with an existing report for the
same organization/type/period is `409` (see
`app.ai_reports.service.save_ai_report`'s own docstring), and any
`AIReportGenerationError` (provider failure, unparseable/invalid
response) becomes a `502` - the provider/upstream failed, this
codebase's own request was fine, same distinction `APIError`'s own
status-code convention makes elsewhere for an external dependency
failing.

**The 502's own `AIReportGenerationError` text is logged, never
returned to the client** - that exception can wrap an upstream
Anthropic HTTP error body (`app.ai.providers._send_anthropic_request`)
or other uncontrolled vendor text, and no other `APIError` raise in
this codebase forwards a caught exception's own `str()` into a
client-facing response; the response body stays a fixed, generic
message/code, exactly like every other `APIError` here."""

from flask import Blueprint, current_app, g, jsonify, request
from pydantic import ValidationError

from app.ai.service import AIReportGenerationError
from app.ai_reports.schemas import GenerateReportRequest, ListAIReportsQuery
from app.ai_reports.service import generate_and_store_report, get_ai_report_or_404, list_ai_reports
from app.analytics.service import resolve_period_filter
from app.auth.decorators import csrf_protect, login_required
from app.authz.decorators import require_permission
from app.authz.permissions import Permission, PermissionScope
from app.errors import APIError, validation_error_details

ai_reports_bp = Blueprint("ai_reports", __name__)


def _require_full_scope(scope: PermissionScope) -> None:
    if scope != PermissionScope.FULL:
        raise APIError("You do not have permission to do this.", status_code=403, code="FORBIDDEN")


@ai_reports_bp.route("/organizations/<uuid:organization_id>/ai-reports/generate", methods=["POST"])
@login_required
@csrf_protect
@require_permission(Permission.ANALYTICS_VIEW)
def post_generate_ai_report(organization_id):
    _require_full_scope(g.permission_scope)

    try:
        query = GenerateReportRequest.model_validate(request.get_json(silent=True) or {})
    except ValidationError as exc:
        raise APIError(
            "Validation failed", status_code=422, code="VALIDATION_ERROR", details=validation_error_details(exc)
        )

    organization = g.current_membership.organization
    period_start, period_end = resolve_period_filter(
        query.period, organization.timezone, period_start=query.period_start, period_end=query.period_end
    )

    try:
        report = generate_and_store_report(organization, period_start=period_start, period_end=period_end)
    except AIReportGenerationError as exc:
        current_app.logger.warning("AI report generation failed for organization %s: %s", organization_id, exc)
        raise APIError(
            "The AI report could not be generated.",
            status_code=502,
            code="AI_GENERATION_FAILED",
            details={"reason": "upstream_provider_error"},
        )

    body = {"success": True, "message": "AI report generated", "data": report.to_public_dict()}
    return jsonify(body), 201


@ai_reports_bp.route("/organizations/<uuid:organization_id>/ai-reports", methods=["GET"])
@login_required
@require_permission(Permission.ANALYTICS_VIEW)
def get_ai_reports(organization_id):
    _require_full_scope(g.permission_scope)

    try:
        query = ListAIReportsQuery.model_validate(request.args.to_dict())
    except ValidationError as exc:
        raise APIError(
            "Validation failed", status_code=422, code="VALIDATION_ERROR", details=validation_error_details(exc)
        )

    reports, total = list_ai_reports(organization_id, page=query.page, per_page=query.per_page)
    total_pages = (total + query.per_page - 1) // query.per_page if total else 0

    body = {
        "success": True,
        "message": "AI reports retrieved",
        "data": [report.to_public_dict() for report in reports],
        "meta": {"page": query.page, "per_page": query.per_page, "total": total, "total_pages": total_pages},
    }
    return jsonify(body), 200


@ai_reports_bp.route("/organizations/<uuid:organization_id>/ai-reports/<uuid:report_id>", methods=["GET"])
@login_required
@require_permission(Permission.ANALYTICS_VIEW)
def get_ai_report(organization_id, report_id):
    _require_full_scope(g.permission_scope)

    report = get_ai_report_or_404(organization_id, report_id)

    body = {"success": True, "message": "AI report retrieved", "data": report.to_public_dict()}
    return jsonify(body), 200
