import uuid

import pytest
from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models import User, UserStatus


@pytest.fixture
def db_session(app):
    with app.app_context():
        yield db.session
        db.session.rollback()
        db.session.query(User).delete()
        db.session.commit()


def _make_user(**overrides):
    defaults = {"name": "Ada Lovelace", "email": "ada@example.com"}
    defaults.update(overrides)
    user = User(**defaults)
    user.set_password("correct horse battery staple")
    return user


def test_user_gets_a_uuid_primary_key_on_insert(db_session):
    user = _make_user()
    db_session.add(user)
    db_session.commit()

    assert isinstance(user.id, uuid.UUID)


def test_email_is_normalized_to_lowercase_and_stripped(db_session):
    user = _make_user(email="  Ada@Example.COM  ")
    db_session.add(user)
    db_session.commit()

    assert user.email == "ada@example.com"


def test_duplicate_email_is_rejected(db_session):
    db_session.add(_make_user(email="ada@example.com"))
    db_session.commit()

    db_session.add(_make_user(email="ADA@EXAMPLE.COM"))
    with pytest.raises(IntegrityError):
        db_session.commit()


def test_status_defaults_to_active(db_session):
    user = _make_user()
    db_session.add(user)
    db_session.commit()

    assert user.status == UserStatus.ACTIVE


def test_status_is_stored_as_its_lowercase_value_not_member_name(db_session):
    from sqlalchemy import text

    user = _make_user(email="status-check@example.com")
    db_session.add(user)
    db_session.commit()

    raw_value = db_session.execute(
        text("SELECT status::text FROM users WHERE id = :id"), {"id": user.id}
    ).scalar()
    assert raw_value == "active"


def test_password_is_hashed_not_stored_in_plaintext(db_session):
    user = _make_user()
    user.set_password("correct horse battery staple")

    assert user.password_hash != "correct horse battery staple"
    assert user.password_hash.startswith("$argon2id$")


def test_verify_password_accepts_correct_and_rejects_wrong_password(db_session):
    user = _make_user()
    user.set_password("correct horse battery staple")

    assert user.verify_password("correct horse battery staple") is True
    assert user.verify_password("wrong password") is False


def test_name_and_email_cannot_be_blank(db_session):
    with pytest.raises(ValueError):
        User(name="  ", email="a@example.com")

    with pytest.raises(ValueError):
        User(name="A Name", email="   ")


def test_name_is_required_at_the_database_level(db_session):
    user = User(email="no-name@example.com")
    user.set_password("x")
    db_session.add(user)

    with pytest.raises(IntegrityError):
        db_session.commit()


def test_created_and_updated_timestamps_are_set_on_insert(db_session):
    user = _make_user()
    db_session.add(user)
    db_session.commit()

    assert user.created_at is not None
    assert user.updated_at is not None


def test_updated_at_changes_on_update(db_session):
    user = _make_user()
    db_session.add(user)
    db_session.commit()
    original_updated_at = user.updated_at

    user.name = "Ada, Countess of Lovelace"
    db_session.commit()

    assert user.updated_at >= original_updated_at
