import pytest

from app.extensions import db
from app.models import User


@pytest.fixture(autouse=True)
def _clean_users(app):
    yield
    with app.app_context():
        db.session.query(User).delete()
        db.session.commit()


def _register(client, **overrides):
    payload = {"name": "Ada Lovelace", "email": "ada@example.com", "password": "correct horse battery"}
    payload.update(overrides)
    return client.post("/api/v1/auth/register", json=payload)


def test_register_with_valid_payload_returns_201_and_the_created_user(client):
    response = _register(client)

    assert response.status_code == 201
    body = response.get_json()
    assert body["success"] is True
    assert body["data"]["email"] == "ada@example.com"
    assert body["data"]["name"] == "Ada Lovelace"
    assert body["data"]["status"] == "active"
    assert "id" in body["data"]


def test_register_response_never_includes_the_password_hash(client):
    response = _register(client)

    body = response.get_json()
    assert "password" not in body["data"]
    assert "password_hash" not in body["data"]


def test_register_persists_a_hashed_password_not_plaintext(client, app):
    _register(client, email="hash-check@example.com")

    with app.app_context():
        user = db.session.query(User).filter_by(email="hash-check@example.com").one()
        assert user.password_hash != "correct horse battery"
        assert user.verify_password("correct horse battery") is True


def test_register_normalizes_email_case(client):
    response = _register(client, email="ADA@Example.COM")

    assert response.status_code == 201
    assert response.get_json()["data"]["email"] == "ada@example.com"


def test_duplicate_email_returns_409(client):
    first = _register(client, email="dup@example.com")
    assert first.status_code == 201

    second = _register(client, email="DUP@example.com", name="Someone Else")

    assert second.status_code == 409
    body = second.get_json()
    assert body["success"] is False
    assert body["error"]["code"] == "EMAIL_ALREADY_REGISTERED"


def test_duplicate_email_does_not_create_a_second_row(client, app):
    _register(client, email="dup2@example.com")
    _register(client, email="dup2@example.com")

    with app.app_context():
        count = db.session.query(User).filter_by(email="dup2@example.com").count()
    assert count == 1


@pytest.mark.parametrize(
    "overrides",
    [
        {"email": "not-an-email"},
        {"password": "short"},
        {"name": ""},
    ],
)
def test_invalid_payloads_return_422(client, overrides):
    response = _register(client, **overrides)

    assert response.status_code == 422
    body = response.get_json()
    assert body["success"] is False
    assert body["error"]["code"] == "VALIDATION_ERROR"
    assert body["error"]["details"]


def test_missing_required_field_returns_422(client):
    response = client.post("/api/v1/auth/register", json={"email": "a@example.com"})

    assert response.status_code == 422


def test_malformed_json_body_returns_400(client):
    response = client.post(
        "/api/v1/auth/register", data="not json", content_type="application/json"
    )

    assert response.status_code == 400
    assert response.get_json()["error"]["code"] == "BAD_REQUEST"
