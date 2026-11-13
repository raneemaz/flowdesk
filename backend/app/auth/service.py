import secrets

from flask import current_app, session
from sqlalchemy.exc import IntegrityError

from app.errors import APIError
from app.extensions import db
from app.models import User, UserStatus
from app.security import DUMMY_PASSWORD_HASH, verify_password


def register_user(name: str, email: str, password: str) -> User:
    """Creates a User. Relies on the DB's unique constraint on email
    (not a check-then-insert) so concurrent registrations with the same
    email can never both succeed - a SELECT-first check would race."""
    user = User(name=name, email=email)
    user.set_password(password)

    db.session.add(user)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        raise APIError(
            "An account with this email already exists.",
            status_code=409,
            code="EMAIL_ALREADY_REGISTERED",
            details={"email": "already registered"},
        )

    return user


def authenticate_user(email: str, password: str) -> User:
    """Verifies credentials. Deliberately generic on failure (no
    'email not found' vs 'wrong password' distinction) to avoid account
    enumeration via login. Account-status checks only happen *after*
    credentials are proven correct, since at that point the caller has
    already demonstrated they control the account.

    Always runs an Argon2 verification, even when no user matches -
    against a fixed dummy hash - so a non-existent email can't be
    distinguished from a wrong password by response time. Argon2 is
    deliberately expensive; short-circuiting it only for unknown emails
    would otherwise make "no such account" measurably faster than "wrong
    password", leaking the same thing the generic error message is
    trying to hide.
    """
    # The email column only ever holds normalized (lowercased, trimmed)
    # values - see User._normalize_email - so an exact match is sufficient
    # and keeps this sargable against ix_users_email.
    normalized_email = (email or "").strip().lower()
    user = db.session.query(User).filter(User.email == normalized_email).one_or_none()

    password_hash = user.password_hash if user is not None else DUMMY_PASSWORD_HASH
    credentials_valid = verify_password(password_hash, password)

    if user is None or not credentials_valid:
        raise APIError(
            "Invalid email or password.",
            status_code=401,
            code="INVALID_CREDENTIALS",
        )

    if user.status != UserStatus.ACTIVE:
        raise APIError(
            f"This account is {user.status.value}.",
            status_code=403,
            code=f"ACCOUNT_{user.status.value.upper()}",
        )

    return user


def create_session(user: User) -> str:
    """Starts a server-side (Redis-backed) session and returns a fresh
    CSRF token tied to it, per Section 35 open decision #3.

    Rotates the session ID (not just the data) via regenerate(), which
    deletes whatever Redis entry the pre-login session ID pointed at and
    issues a fresh, unguessable one. Without this, session.clear() alone
    would keep the *same* session ID across login - a session-fixation
    hole: an attacker who gets a victim's browser to carry a
    pre-chosen/known session ID (set before authentication) would have
    that ID become authenticated once the victim logs in.
    """
    session.clear()
    current_app.session_interface.regenerate(session)
    session.permanent = True
    session["user_id"] = str(user.id)
    csrf_token = secrets.token_urlsafe(32)
    session["csrf_token"] = csrf_token
    return csrf_token


def destroy_session() -> None:
    session.clear()
