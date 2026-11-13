import pytest

from app.extensions import db
from app.models import User


@pytest.fixture(autouse=True)
def _clean_users(app):
    yield
    with app.app_context():
        db.session.query(User).delete()
        db.session.commit()


def _register(client, email="ada@example.com", password="correct horse battery"):
    client.post(
        "/api/v1/auth/register",
        json={"name": "Ada Lovelace", "email": email, "password": password},
    )


def _login(client, email="ada@example.com", password="correct horse battery"):
    return client.post("/api/v1/auth/login", json={"email": email, "password": password})


def test_me_without_a_session_returns_401(client):
    response = client.get("/api/v1/auth/me")

    assert response.status_code == 401
    assert response.get_json()["error"]["code"] == "UNAUTHENTICATED"


def test_me_with_a_valid_session_returns_the_current_user(client):
    _register(client)
    _login(client)

    response = client.get("/api/v1/auth/me")

    assert response.status_code == 200
    body = response.get_json()
    assert body["success"] is True
    assert body["data"]["email"] == "ada@example.com"
    assert body["data"]["name"] == "Ada Lovelace"


def test_me_response_never_includes_the_password_hash(client):
    _register(client)
    _login(client)

    response = client.get("/api/v1/auth/me")

    body = response.get_json()
    assert "password" not in body["data"]
    assert "password_hash" not in body["data"]


def test_me_does_not_require_a_csrf_token(client):
    """GET is a read, not a state change - CSRF protection only applies
    to state-changing requests, matching csrf_protect's own scope."""
    _register(client)
    _login(client)

    response = client.get("/api/v1/auth/me")

    assert response.status_code == 200


def test_me_after_logout_returns_401_again(client):
    _register(client)
    login_response = _login(client)
    csrf_token = login_response.get_json()["data"]["csrf_token"]

    client.post("/api/v1/auth/logout", headers={"X-CSRF-Token": csrf_token})
    response = client.get("/api/v1/auth/me")

    assert response.status_code == 401
