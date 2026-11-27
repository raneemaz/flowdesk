from flask import Blueprint, g, jsonify, request
from pydantic import ValidationError

from app.auth.decorators import csrf_protect, login_required
from app.authz.decorators import require_permission
from app.authz.permissions import Permission
from app.errors import APIError, validation_error_details
from app.organizations.schemas import CreateOrganizationRequest, UpdateMemberRequest, UpdateOrganizationRequest
from app.organizations.service import create_organization, list_user_memberships
from app.organizations.settings import list_members, serialize_member, update_member, update_organization

organizations_bp = Blueprint("organizations", __name__)


@organizations_bp.route("/organizations", methods=["POST"])
@login_required
@csrf_protect
def post_organizations():
    payload = request.get_json(silent=True)
    if payload is None:
        raise APIError("Request body must be valid JSON.", status_code=400, code="BAD_REQUEST")

    try:
        data = CreateOrganizationRequest.model_validate(payload)
    except ValidationError as exc:
        raise APIError(
            "Validation failed",
            status_code=422,
            code="VALIDATION_ERROR",
            details=validation_error_details(exc),
        )

    # Only pass fields the caller actually supplied - an explicit None
    # would override Organization's own currency/timezone defaults
    # (USD/UTC) instead of falling through to them.
    optional_fields = {k: v for k, v in data.model_dump(exclude={"name"}).items() if v is not None}

    organization = create_organization(creator=g.current_user, name=data.name, **optional_fields)

    body = {
        "success": True,
        "message": "Organization created successfully",
        "data": organization.to_public_dict(),
    }
    return jsonify(body), 201


@organizations_bp.route("/organizations", methods=["GET"])
@login_required
def get_organizations():
    memberships = list_user_memberships(g.current_user)

    body = {
        "success": True,
        "message": "Organizations retrieved",
        "data": [m.to_public_dict() for m in memberships],
    }
    return jsonify(body), 200


def _validated(model, payload):
    if payload is None:
        raise APIError("Request body must be valid JSON.", status_code=400, code="BAD_REQUEST")
    try:
        return model.model_validate(payload)
    except ValidationError as exc:
        raise APIError(
            "Validation failed", status_code=422, code="VALIDATION_ERROR", details=validation_error_details(exc)
        )


@organizations_bp.route("/organizations/<uuid:organization_id>", methods=["PATCH"])
@login_required
@csrf_protect
@require_permission(Permission.ORGANIZATION_SETTINGS_MANAGE)
def patch_organization(organization_id):
    """Settings > Organization. Owner: every field. Manager: contact
    details and date format only (403 naming the Owner-only fields)."""
    data = _validated(UpdateOrganizationRequest, request.get_json(silent=True))
    organization = update_organization(g.current_membership, g.permission_scope, data.model_dump(exclude_unset=True))
    return jsonify({"success": True, "message": "Organization updated", "data": organization.to_public_dict()}), 200


@organizations_bp.route("/organizations/<uuid:organization_id>/members", methods=["GET"])
@login_required
@require_permission(Permission.MEMBERSHIP_MANAGE)
def get_members(organization_id):
    """Settings > Members: everyone with a membership, including removed
    members (so their access can be restored). Owner/Manager only."""
    members = [serialize_member(m) for m in list_members(organization_id)]
    return jsonify({"success": True, "message": "Members retrieved", "data": members}), 200


@organizations_bp.route("/organizations/<uuid:organization_id>/members/<uuid:membership_id>", methods=["PATCH"])
@login_required
@csrf_protect
@require_permission(Permission.MEMBERSHIP_MANAGE)
def patch_member(organization_id, membership_id):
    data = _validated(UpdateMemberRequest, request.get_json(silent=True))
    member = update_member(g.current_membership, membership_id, data.role, data.status)
    return jsonify({"success": True, "message": "Member updated", "data": serialize_member(member)}), 200
