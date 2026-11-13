from flask import Blueprint, g, jsonify, request
from pydantic import ValidationError

from app.auth.decorators import csrf_protect, login_required
from app.errors import APIError, validation_error_details
from app.organizations.schemas import CreateOrganizationRequest
from app.organizations.service import create_organization

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
