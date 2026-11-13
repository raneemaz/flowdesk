from flask import Blueprint, g, jsonify, request
from pydantic import ValidationError

from app.auth.decorators import csrf_protect, login_required
from app.auth.schemas import LoginRequest, RegisterRequest
from app.auth.service import authenticate_user, create_session, destroy_session, register_user
from app.errors import APIError, validation_error_details

auth_bp = Blueprint("auth", __name__)


@auth_bp.route("/auth/register", methods=["POST"])
def post_register():
    payload = request.get_json(silent=True)
    if payload is None:
        raise APIError("Request body must be valid JSON.", status_code=400, code="BAD_REQUEST")

    try:
        data = RegisterRequest.model_validate(payload)
    except ValidationError as exc:
        raise APIError(
            "Validation failed",
            status_code=422,
            code="VALIDATION_ERROR",
            details=validation_error_details(exc),
        )

    user = register_user(name=data.name, email=data.email, password=data.password)

    body = {
        "success": True,
        "message": "Account created successfully",
        "data": user.to_public_dict(),
    }
    return jsonify(body), 201


@auth_bp.route("/auth/login", methods=["POST"])
def post_login():
    payload = request.get_json(silent=True)
    if payload is None:
        raise APIError("Request body must be valid JSON.", status_code=400, code="BAD_REQUEST")

    try:
        data = LoginRequest.model_validate(payload)
    except ValidationError as exc:
        raise APIError(
            "Validation failed",
            status_code=422,
            code="VALIDATION_ERROR",
            details=validation_error_details(exc),
        )

    user = authenticate_user(email=data.email, password=data.password)
    csrf_token = create_session(user)

    body = {
        "success": True,
        "message": "Logged in successfully",
        "data": {"user": user.to_public_dict(), "csrf_token": csrf_token},
    }
    return jsonify(body), 200


@auth_bp.route("/auth/logout", methods=["POST"])
@login_required
@csrf_protect
def post_logout():
    destroy_session()

    body = {"success": True, "message": "Logged out successfully", "data": None}
    return jsonify(body), 200


@auth_bp.route("/auth/me", methods=["GET"])
@login_required
def get_me():
    # Memberships still aren't included: the Membership model exists
    # since FD-012, but adding them to this response isn't part of any
    # assigned task yet (not FD-011, FD-012, or FD-013) - revisit once
    # one explicitly calls for it rather than adding it speculatively.
    body = {
        "success": True,
        "message": "Current user retrieved",
        "data": g.current_user.to_public_dict(),
    }
    return jsonify(body), 200
