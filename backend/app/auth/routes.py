from flask import Blueprint, jsonify, request
from pydantic import ValidationError

from app.auth.schemas import RegisterRequest
from app.auth.service import register_user
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
