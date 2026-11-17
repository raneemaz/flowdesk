from flask import Blueprint, g, jsonify, request
from pydantic import ValidationError

from app.activity.schemas import ListActivityQuery
from app.activity.service import list_activity
from app.auth.decorators import login_required
from app.authz.decorators import require_permission
from app.authz.permissions import Permission
from app.errors import APIError, validation_error_details

activity_bp = Blueprint("activity", __name__)


@activity_bp.route("/organizations/<uuid:organization_id>/activity", methods=["GET"])
@login_required
@require_permission(Permission.ACTIVITY_HISTORY_VIEW)
def get_activity(organization_id):
    try:
        query = ListActivityQuery.model_validate(request.args.to_dict())
    except ValidationError as exc:
        raise APIError(
            "Validation failed", status_code=422, code="VALIDATION_ERROR", details=validation_error_details(exc)
        )

    entries, total = list_activity(
        organization_id,
        scope=g.permission_scope,
        caller_role=g.current_membership.role,
        caller_membership_id=g.current_membership.id,
        page=query.page,
        per_page=query.per_page,
    )
    total_pages = (total + query.per_page - 1) // query.per_page if total else 0

    body = {
        "success": True,
        "message": "Activity retrieved",
        "data": [entry.to_public_dict() for entry in entries],
        "meta": {"page": query.page, "per_page": query.per_page, "total": total, "total_pages": total_pages},
    }
    return jsonify(body), 200
