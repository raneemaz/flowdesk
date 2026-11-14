from flask import Blueprint, g, jsonify, request
from pydantic import ValidationError

from app.auth.decorators import csrf_protect, login_required
from app.authz.decorators import require_permission
from app.authz.permissions import Permission
from app.errors import APIError, validation_error_details
from app.invitations.schemas import AcceptInvitationRequest, CreateInvitationRequest
from app.invitations.service import accept_invitation, cancel_invitation, create_invitation, list_invitations

invitations_bp = Blueprint("invitations", __name__)


@invitations_bp.route("/organizations/<uuid:organization_id>/invitations", methods=["POST"])
@login_required
@csrf_protect
@require_permission(Permission.MEMBERSHIP_MANAGE)
def post_invitations(organization_id):
    payload = request.get_json(silent=True)
    if payload is None:
        raise APIError("Request body must be valid JSON.", status_code=400, code="BAD_REQUEST")

    try:
        data = CreateInvitationRequest.model_validate(payload)
    except ValidationError as exc:
        raise APIError("Validation failed", status_code=422, code="VALIDATION_ERROR", details=validation_error_details(exc))

    organization = g.current_membership.organization
    invitation, email_delivery = create_invitation(g.current_membership, organization, data.email, data.role)

    body = {
        "success": True,
        "message": "Invitation created",
        "data": {**invitation.to_public_dict(), "email_delivery": email_delivery},
    }
    return jsonify(body), 201


@invitations_bp.route("/organizations/<uuid:organization_id>/invitations", methods=["GET"])
@login_required
@require_permission(Permission.MEMBERSHIP_MANAGE)
def get_invitations(organization_id):
    invitations = list_invitations(organization_id)

    body = {
        "success": True,
        "message": "Invitations retrieved",
        "data": [invitation.to_public_dict() for invitation in invitations],
    }
    return jsonify(body), 200


@invitations_bp.route("/organizations/<uuid:organization_id>/invitations/<uuid:invitation_id>", methods=["DELETE"])
@login_required
@csrf_protect
@require_permission(Permission.MEMBERSHIP_MANAGE)
def delete_invitation(organization_id, invitation_id):
    invitation = cancel_invitation(g.current_membership, organization_id, invitation_id)

    body = {
        "success": True,
        "message": "Invitation cancelled",
        "data": invitation.to_public_dict(),
    }
    return jsonify(body), 200


@invitations_bp.route("/invitations/accept", methods=["POST"])
@login_required
@csrf_protect
def post_invitations_accept():
    payload = request.get_json(silent=True)
    if payload is None:
        raise APIError("Request body must be valid JSON.", status_code=400, code="BAD_REQUEST")

    try:
        data = AcceptInvitationRequest.model_validate(payload)
    except ValidationError as exc:
        raise APIError("Validation failed", status_code=422, code="VALIDATION_ERROR", details=validation_error_details(exc))

    membership = accept_invitation(g.current_user, data.token)

    body = {
        "success": True,
        "message": "Invitation accepted",
        "data": membership.to_public_dict(),
    }
    return jsonify(body), 200
