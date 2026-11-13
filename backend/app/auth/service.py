from sqlalchemy.exc import IntegrityError

from app.errors import APIError
from app.extensions import db
from app.models import User


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
