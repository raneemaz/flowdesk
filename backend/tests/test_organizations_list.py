import pytest

from app.extensions import db
from app.models import Membership, MembershipStatus, Organization, User


@pytest.fixture(autouse=True)
def _clean(app):
    yield
    with app.app_context():
        db.session.query(Membership).delete()
        db.session.query(Organization).delete()
        db.session.query(User).delete()
        db.session.commit()


def _register_and_login(client, email, password="correct horse battery"):
    client.post("/api/v1/auth/register", json={"name": "Test User", "email": email, "password": password})
    login_response = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    return login_response.get_json()["data"]["csrf_token"]


def _create_org(client, csrf_token, name):
    return client.post(
        "/api/v1/organizations", json={"name": name}, headers={"X-CSRF-Token": csrf_token}
    ).get_json()["data"]


def test_list_organizations_without_a_session_returns_401(client):
    response = client.get("/api/v1/organizations")

    assert response.status_code == 401


def test_list_organizations_with_none_returns_an_empty_list(client):
    _register_and_login(client, "nobody@example.com")

    response = client.get("/api/v1/organizations")

    assert response.status_code == 200
    assert response.get_json()["data"] == []


def test_list_organizations_returns_the_callers_own_memberships(client):
    csrf_token = _register_and_login(client, "owner@example.com")
    _create_org(client, csrf_token, "Org One")
    _create_org(client, csrf_token, "Org Two")

    response = client.get("/api/v1/organizations")

    assert response.status_code == 200
    body = response.get_json()["data"]
    assert len(body) == 2
    names = {m["organization"]["name"] for m in body}
    assert names == {"Org One", "Org Two"}


def test_list_organizations_includes_role_and_status(client):
    csrf_token = _register_and_login(client, "owner2@example.com")
    _create_org(client, csrf_token, "Org One")

    response = client.get("/api/v1/organizations")

    membership = response.get_json()["data"][0]
    assert membership["role"] == "owner"
    assert membership["status"] == "active"
    assert "joined_at" in membership


def test_list_organizations_never_includes_another_users_memberships(client, app):
    csrf_token_a = _register_and_login(client, "user-a@example.com")
    _create_org(client, csrf_token_a, "User A's Org")
    client.post("/api/v1/auth/logout", headers={"X-CSRF-Token": csrf_token_a})

    csrf_token_b = _register_and_login(client, "user-b@example.com")
    _create_org(client, csrf_token_b, "User B's Org")

    response = client.get("/api/v1/organizations")

    body = response.get_json()["data"]
    names = {m["organization"]["name"] for m in body}
    assert names == {"User B's Org"}
    assert "User A's Org" not in names


def test_list_organizations_shows_inactive_status_rather_than_hiding_the_membership(client, app):
    """Deactivation never deletes historical visibility (mirrors FR-009's
    rule for employee status) - an inactive membership still shows up,
    just with its real status, not silently filtered out."""
    csrf_token = _register_and_login(client, "owner3@example.com")
    org_data = _create_org(client, csrf_token, "Org One")

    with app.app_context():
        user = db.session.query(User).filter_by(email="owner3@example.com").one()
        membership = db.session.query(Membership).filter_by(user_id=user.id).one()
        membership.status = MembershipStatus.INACTIVE
        db.session.commit()

    response = client.get("/api/v1/organizations")

    body = response.get_json()["data"]
    assert len(body) == 1
    assert body[0]["status"] == "inactive"
    assert body[0]["organization"]["id"] == org_data["id"]
