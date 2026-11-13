import hmac
import uuid
from functools import wraps

from flask import g, request, session

from app.errors import APIError
from app.extensions import db
from app.models import User, UserStatus


def login_required(view):
    """Loads the current user from the session into g.current_user, or
    raises 401. Session-cookie presence is never trusted as authorization
    by itself - the user_id it names must still exist and be active."""

    @wraps(view)
    def wrapped(*args, **kwargs):
        user = None
        raw_user_id = session.get("user_id")
        if raw_user_id:
            try:
                user_id = uuid.UUID(raw_user_id)
            except ValueError:
                user_id = None
            if user_id is not None:
                user = db.session.get(User, user_id)

        if user is None:
            raise APIError("Authentication required.", status_code=401, code="UNAUTHENTICATED")

        # Re-checked on every request, not just at login: a session
        # created while the account was active must stop working as soon
        # as the account is suspended/deactivated, not just block future
        # logins. This is exactly what a revocable (Redis-backed) session
        # is for.
        if user.status != UserStatus.ACTIVE:
            raise APIError("Authentication required.", status_code=401, code="UNAUTHENTICATED")

        g.current_user = user
        return view(*args, **kwargs)

    return wrapped


def csrf_protect(view):
    """Double-submit CSRF check for state-changing requests on an
    authenticated session. Must sit *inside* login_required (run after
    it) so a session actually exists to compare against."""

    @wraps(view)
    def wrapped(*args, **kwargs):
        expected = session.get("csrf_token")
        provided = request.headers.get("X-CSRF-Token")

        if not expected or not provided or not _constant_time_eq(expected, provided):
            raise APIError("Missing or invalid CSRF token.", status_code=403, code="CSRF_TOKEN_INVALID")

        return view(*args, **kwargs)

    return wrapped


def _constant_time_eq(a: str, b: str) -> bool:
    return hmac.compare_digest(a, b)
