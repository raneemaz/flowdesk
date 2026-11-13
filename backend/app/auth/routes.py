from flask import Blueprint, jsonify, request
from pydantic import ValidationError

from app.auth.decorators import csrf_protect, login_required
from app.auth.schemas import LoginRequest, RegisterRequest
from app.auth.service import authenticate_user, create_session, destroy_session, register_user
from app.errors import APIError

auth_bp = Blueprint("auth", __name__)


def _validation_error_details(exc: ValidationError) -> dict:
    details = {}
    for error in exc.errors():
        field = ".".join(str(part) for part in error["loc"]) or "body"
        details[field] = error["msg"]
    return details


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
            details=_validation_error_details(exc),
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
            details=_validation_error_details(exc),
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
