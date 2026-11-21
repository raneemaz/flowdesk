"""FD-061: the one conversational-assistant endpoint (FR-041).

Gated by `require_permission(Permission.ANALYTICS_VIEW)` - but every
role has at least some non-`NONE` scope for this permission (Owner/
Manager `full`, Employee `own`, Accountant/CustomerSupport `limited`),
so this never actually rejects anyone at the route layer; what varies
by role is the REAL answer each tool call in `app.ai_assistant.tools`
produces, exactly like `GET .../analytics/employees` already varies
by caller scope rather than by a route-level gate.

`@csrf_protect` even though this makes no database write - a request
here spends real money on an AI provider call, which deserves the
same forgery protection as a persisted write."""

from flask import Blueprint, g, jsonify, request
from pydantic import ValidationError

from app.ai_assistant.schemas import AskAssistantRequest
from app.ai_assistant.service import AIAssistantError, ask_assistant
from app.auth.decorators import csrf_protect, login_required
from app.authz.decorators import require_permission
from app.authz.permissions import Permission
from app.errors import APIError, validation_error_details

ai_assistant_bp = Blueprint("ai_assistant", __name__)


@ai_assistant_bp.route("/organizations/<uuid:organization_id>/ai-assistant/ask", methods=["POST"])
@login_required
@csrf_protect
@require_permission(Permission.ANALYTICS_VIEW)
def post_ask_assistant(organization_id):
    try:
        body = AskAssistantRequest.model_validate(request.get_json(silent=True) or {})
    except ValidationError as exc:
        raise APIError(
            "Validation failed", status_code=422, code="VALIDATION_ERROR", details=validation_error_details(exc)
        )

    try:
        answer = ask_assistant(
            g.current_membership.organization,
            g.permission_scope,
            g.current_membership.role,
            g.current_membership.id,
            body.question,
        )
    except AIAssistantError as exc:
        from flask import current_app

        current_app.logger.warning("AI assistant failed for organization %s: %s", organization_id, exc)
        raise APIError(
            "The assistant could not answer that question.",
            status_code=502,
            code="AI_ASSISTANT_FAILED",
            details={"reason": "upstream_provider_error"},
        )

    response_body = {"success": True, "message": "Assistant answered", "data": {"answer": answer}}
    return jsonify(response_body), 200
