from flask import Blueprint, g, jsonify, request
from pydantic import ValidationError

from app.auth.decorators import csrf_protect, login_required
from app.auth.schemas import ChangePasswordRequest, LoginRequest, RegisterRequest, UpdateProfileRequest
from app.auth.service import authenticate_user, create_session, destroy_session, register_user
from app.auth.turnstile import require_turnstile
from app.errors import APIError, validation_error_details
from app.extensions import db, limiter

auth_bp = Blueprint("auth", __name__)


# FD-064 (Section 13's "auth rate limiting" item). Per-IP (app.extensions's
# own `key_func=get_remote_address`), not per-account - these two routes
# are the only ones in this app an unauthenticated caller can hit
# repeatedly for free, so they're the only ones that need it: register
# (signup spam) and login (credential brute-forcing). Limits are
# deliberately generous enough that no genuine user ever notices them in
# normal use, while still bounding an automated attempt to a trickle.
@auth_bp.route("/auth/register", methods=["POST"])
@limiter.limit("5 per hour")
def post_register():
    payload = request.get_json(silent=True)
    if payload is None:
        raise APIError("Request body must be valid JSON.", status_code=400, code="BAD_REQUEST")

    # Bot check first, so automated sign-ups never reach validation or the
    # database. The token is not part of the account data.
    require_turnstile(payload.pop("turnstile_token", None) if isinstance(payload, dict) else None, "signup")

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
@limiter.limit("10 per minute")
def post_login():
    payload = request.get_json(silent=True)
    if payload is None:
        raise APIError("Request body must be valid JSON.", status_code=400, code="BAD_REQUEST")

    require_turnstile(payload.pop("turnstile_token", None) if isinstance(payload, dict) else None, "login")

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


@auth_bp.route("/auth/me", methods=["PATCH"])
@login_required
@csrf_protect
def patch_me():
    data = _validated(UpdateProfileRequest, request.get_json(silent=True))
    if not data.name.strip():
        raise APIError("Validation failed", status_code=422, code="VALIDATION_ERROR", details={"name": "Name is required."})
    g.current_user.name = data.name  # the model's own validator trims it
    db.session.commit()
    return jsonify({"success": True, "message": "Profile updated", "data": g.current_user.to_public_dict()}), 200


# Same per-IP throttle idea as login: a stolen session must not become an
# unlimited oracle for guessing the account's current password.
@auth_bp.route("/auth/change-password", methods=["POST"])
@limiter.limit("10 per hour")
@login_required
@csrf_protect
def post_change_password():
    data = _validated(ChangePasswordRequest, request.get_json(silent=True))
    if not g.current_user.verify_password(data.current_password):
        raise APIError(
            "Your current password is incorrect.",
            status_code=400,
            code="INVALID_CURRENT_PASSWORD",
            details={"current_password": "Incorrect password."},
        )
    if data.new_password == data.current_password:
        raise APIError(
            "Validation failed",
            status_code=422,
            code="VALIDATION_ERROR",
            details={"new_password": "Choose a password different from your current one."},
        )
    g.current_user.set_password(data.new_password)
    db.session.commit()
    return jsonify({"success": True, "message": "Password changed", "data": None}), 200


def _validated(model, payload):
    if payload is None:
        raise APIError("Request body must be valid JSON.", status_code=400, code="BAD_REQUEST")
    try:
        return model.model_validate(payload)
    except ValidationError as exc:
        raise APIError(
            "Validation failed", status_code=422, code="VALIDATION_ERROR", details=validation_error_details(exc)
        )
