import pytest

from app.extensions import db
from app.models import Membership, MembershipRole, MembershipStatus, Organization, User


@pytest.fixture(autouse=True)
def _clean(app):
    yield
    with app.app_context():
        db.session.query(Membership).delete()
        db.session.query(Organization).delete()
        db.session.query(User).delete()
        db.session.commit()


def _register_and_login(client, email="ada@example.com", password="correct horse battery"):
    client.post("/api/v1/auth/register", json={"name": "Ada Lovelace", "email": email, "password": password})
    login_response = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    return login_response.get_json()["data"]["csrf_token"]


def test_create_organization_without_a_session_returns_401(client):
    response = client.post("/api/v1/organizations", json={"name": "Acme Inc"})

    assert response.status_code == 401


def test_create_organization_without_csrf_token_returns_403(client):
    _register_and_login(client)

    response = client.post("/api/v1/organizations", json={"name": "Acme Inc"})

    assert response.status_code == 403


def test_create_organization_with_valid_payload_returns_201(client):
    csrf_token = _register_and_login(client)

    response = client.post(
        "/api/v1/organizations", json={"name": "Acme Inc"}, headers={"X-CSRF-Token": csrf_token}
    )

    assert response.status_code == 201
    body = response.get_json()
    assert body["success"] is True
    assert body["data"]["name"] == "Acme Inc"
    assert body["data"]["slug"] == "acme-inc"
    assert body["data"]["currency"] == "USD"
    assert body["data"]["timezone"] == "UTC"


def test_create_organization_makes_the_creator_the_owner(client, app):
    csrf_token = _register_and_login(client)

    response = client.post(
        "/api/v1/organizations", json={"name": "Acme Inc"}, headers={"X-CSRF-Token": csrf_token}
    )
    org_id = response.get_json()["data"]["id"]

    with app.app_context():
        user = db.session.query(User).filter_by(email="ada@example.com").one()
        membership = db.session.query(Membership).filter_by(organization_id=org_id, user_id=user.id).one()
        assert membership.role == MembershipRole.OWNER
        assert membership.status == MembershipStatus.ACTIVE


def test_create_organization_atomicity_creates_exactly_one_org_and_one_membership(client, app):
    csrf_token = _register_and_login(client)

    client.post("/api/v1/organizations", json={"name": "Acme Inc"}, headers={"X-CSRF-Token": csrf_token})

    with app.app_context():
        assert db.session.query(Organization).count() == 1
        assert db.session.query(Membership).count() == 1


def test_create_organization_accepts_optional_fields(client):
    csrf_token = _register_and_login(client)

    response = client.post(
        "/api/v1/organizations",
        json={
            "name": "Acme Inc",
            "email": "hello@acme.example",
            "phone": "+1-555-0100",
            "currency": "eur",
            "timezone": "Europe/Paris",
        },
        headers={"X-CSRF-Token": csrf_token},
    )

    assert response.status_code == 201
    body = response.get_json()["data"]
    assert body["email"] == "hello@acme.example"
    assert body["phone"] == "+1-555-0100"
    assert body["currency"] == "EUR"
    assert body["timezone"] == "Europe/Paris"


def test_create_organization_missing_name_returns_422(client):
    csrf_token = _register_and_login(client)

    response = client.post("/api/v1/organizations", json={}, headers={"X-CSRF-Token": csrf_token})

    assert response.status_code == 422
    assert response.get_json()["error"]["code"] == "VALIDATION_ERROR"


@pytest.mark.parametrize("extra_field", ["role", "user_id", "organization_id", "slug"])
def test_create_organization_rejects_unknown_fields_that_could_imply_escalation(client, extra_field):
    """Defense in depth: the request schema has no role/user_id/org_id/slug
    field, so there was never a path to specify them - this makes that an
    explicit 422 (model_config extra='forbid') instead of relying on
    pydantic's default silent-drop behavior for undeclared fields."""
    csrf_token = _register_and_login(client)

    response = client.post(
        "/api/v1/organizations",
        json={"name": "Acme Inc", extra_field: "something"},
        headers={"X-CSRF-Token": csrf_token},
    )

    assert response.status_code == 422


def test_create_organization_malformed_json_returns_400(client):
    csrf_token = _register_and_login(client)

    response = client.post(
        "/api/v1/organizations", data="not json", content_type="application/json",
        headers={"X-CSRF-Token": csrf_token},
    )

    assert response.status_code == 400


def test_duplicate_organization_names_get_distinct_auto_generated_slugs(client):
    csrf_token = _register_and_login(client)

    first = client.post(
        "/api/v1/organizations", json={"name": "Acme Inc"}, headers={"X-CSRF-Token": csrf_token}
    ).get_json()["data"]
    second = client.post(
        "/api/v1/organizations", json={"name": "Acme Inc"}, headers={"X-CSRF-Token": csrf_token}
    ).get_json()["data"]

    assert first["slug"] == "acme-inc"
    assert second["slug"] == "acme-inc-2"
    assert first["slug"] != second["slug"]


def test_same_user_can_own_multiple_organizations(client, app):
    csrf_token = _register_and_login(client)

    client.post("/api/v1/organizations", json={"name": "Org One"}, headers={"X-CSRF-Token": csrf_token})
    client.post("/api/v1/organizations", json={"name": "Org Two"}, headers={"X-CSRF-Token": csrf_token})

    with app.app_context():
        user = db.session.query(User).filter_by(email="ada@example.com").one()
        memberships = db.session.query(Membership).filter_by(user_id=user.id).all()
        assert len(memberships) == 2
        assert all(m.role == MembershipRole.OWNER for m in memberships)
