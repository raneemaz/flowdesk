import pytest

from app.extensions import db
from app.models import User, UserStatus


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


def test_login_with_correct_credentials_returns_200_and_a_csrf_token(client):
    _register(client)

    response = _login(client)

    assert response.status_code == 200
    body = response.get_json()
    assert body["success"] is True
    assert body["data"]["user"]["email"] == "ada@example.com"
    assert body["data"]["csrf_token"]


def test_login_sets_a_working_session_cookie(client):
    _register(client)
    login_response = _login(client)
    csrf_token = login_response.get_json()["data"]["csrf_token"]

    logout_response = client.post("/api/v1/auth/logout", headers={"X-CSRF-Token": csrf_token})

    assert logout_response.status_code == 200


def test_suspending_a_user_breaks_their_already_active_session(client, app):
    """A session created while active must stop working the moment the
    account is suspended - not just block a future login. This exercises
    login_required's own status re-check, distinct from the check in
    authenticate_user (which only runs at login time)."""
    _register(client, email="goes-suspended@example.com")
    login_response = _login(client, email="goes-suspended@example.com")
    csrf_token = login_response.get_json()["data"]["csrf_token"]

    with app.app_context():
        user = db.session.query(User).filter_by(email="goes-suspended@example.com").one()
        user.status = UserStatus.SUSPENDED
        db.session.commit()

    response = client.post("/api/v1/auth/logout", headers={"X-CSRF-Token": csrf_token})

    assert response.status_code == 401
    assert response.get_json()["error"]["code"] == "UNAUTHENTICATED"


def test_login_with_wrong_password_returns_401_generic_message(client):
    _register(client)

    response = _login(client, password="totally wrong password")

    assert response.status_code == 401
    body = response.get_json()
    assert body["error"]["code"] == "INVALID_CREDENTIALS"


def test_login_with_unknown_email_returns_the_same_401_as_wrong_password(client):
    response = _login(client, email="nobody@example.com")

    assert response.status_code == 401
    assert response.get_json()["error"]["code"] == "INVALID_CREDENTIALS"


def test_login_for_suspended_account_returns_403_once_credentials_are_valid(client, app):
    _register(client, email="suspended@example.com")
    with app.app_context():
        user = db.session.query(User).filter_by(email="suspended@example.com").one()
        user.status = UserStatus.SUSPENDED
        db.session.commit()

    response = _login(client, email="suspended@example.com")

    assert response.status_code == 403
    assert response.get_json()["error"]["code"] == "ACCOUNT_SUSPENDED"


def test_login_for_suspended_account_with_wrong_password_still_returns_401(client, app):
    """Status is only revealed once credentials are proven correct -
    otherwise this would leak account status to a guessing attacker."""
    _register(client, email="suspended2@example.com")
    with app.app_context():
        user = db.session.query(User).filter_by(email="suspended2@example.com").one()
        user.status = UserStatus.SUSPENDED
        db.session.commit()

    response = _login(client, email="suspended2@example.com", password="wrong password here")

    assert response.status_code == 401
    assert response.get_json()["error"]["code"] == "INVALID_CREDENTIALS"


def test_login_with_invalid_payload_returns_422(client):
    response = client.post("/api/v1/auth/login", json={"email": "not-an-email", "password": ""})

    assert response.status_code == 422


def test_login_malformed_json_returns_400(client):
    response = client.post("/api/v1/auth/login", data="not json", content_type="application/json")

    assert response.status_code == 400


def test_logout_without_being_logged_in_returns_401(client):
    response = client.post("/api/v1/auth/logout", headers={"X-CSRF-Token": "anything"})

    assert response.status_code == 401
    assert response.get_json()["error"]["code"] == "UNAUTHENTICATED"


def test_logout_without_csrf_token_returns_403(client):
    _register(client)
    _login(client)

    response = client.post("/api/v1/auth/logout")

    assert response.status_code == 403
    assert response.get_json()["error"]["code"] == "CSRF_TOKEN_INVALID"


def test_logout_with_wrong_csrf_token_returns_403(client):
    _register(client)
    _login(client)

    response = client.post("/api/v1/auth/logout", headers={"X-CSRF-Token": "not-the-real-token"})

    assert response.status_code == 403


def test_logout_actually_destroys_the_session(client):
    _register(client)
    login_response = _login(client)
    csrf_token = login_response.get_json()["data"]["csrf_token"]

    logout_response = client.post("/api/v1/auth/logout", headers={"X-CSRF-Token": csrf_token})
    assert logout_response.status_code == 200

    # The same cookie, reused for a second logout, must now fail - the
    # server-side session is gone, not just "the client forgot the token".
    second_logout = client.post("/api/v1/auth/logout", headers={"X-CSRF-Token": csrf_token})
    assert second_logout.status_code == 401


def test_each_login_issues_a_fresh_csrf_token(client):
    _register(client)
    first = _login(client).get_json()["data"]["csrf_token"]
    client.post("/api/v1/auth/logout", headers={"X-CSRF-Token": first})

    second = _login(client).get_json()["data"]["csrf_token"]

    assert first != second


def test_login_rotates_the_session_id_preventing_fixation(client):
    """An attacker who gets a victim's browser to carry a pre-chosen
    session cookie (set before the victim authenticates) must not have
    that cookie become valid once the victim logs in - the session ID
    itself has to change, not just its contents."""
    _register(client)
    client.set_cookie("session", "attacker-planted-session-id")

    response = _login(client)

    assert response.status_code == 200
    new_cookie = client.get_cookie("session")
    assert new_cookie is not None
    assert new_cookie.value != "attacker-planted-session-id"
