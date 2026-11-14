import pytest

from app.extensions import db
from app.models import Invitation, Membership, MembershipRole, MembershipStatus, Organization, User


@pytest.fixture(autouse=True)
def _clean(app):
    yield
    with app.app_context():
        db.session.query(Invitation).delete()
        db.session.query(Membership).delete()
        db.session.query(Organization).delete()
        db.session.query(User).delete()
        db.session.commit()


def _register_and_login(client, email, password="correct horse battery"):
    client.post("/api/v1/auth/register", json={"name": "Test User", "email": email, "password": password})
    login_response = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    return login_response.get_json()["data"]["csrf_token"]


def _create_org(client, csrf_token, name="Org One"):
    return client.post("/api/v1/organizations", json={"name": name}, headers={"X-CSRF-Token": csrf_token}).get_json()[
        "data"
    ]


def _give_role(app, organization_id, email, role, status=MembershipStatus.ACTIVE):
    with app.app_context():
        user = db.session.query(User).filter_by(email=email).one()
        membership = Membership(organization_id=organization_id, user_id=user.id, role=role, status=status)
        db.session.add(membership)
        db.session.commit()


def _invite(client, csrf_token, org_id, email="invitee@example.com", role="employee"):
    return client.post(
        f"/api/v1/organizations/{org_id}/invitations",
        json={"email": email, "role": role},
        headers={"X-CSRF-Token": csrf_token},
    )


def test_unauthenticated_request_returns_401(client, app):
    response = client.post(
        "/api/v1/organizations/00000000-0000-0000-0000-000000000000/invitations", json={}
    )
    assert response.status_code == 401


def test_owner_can_invite_an_employee(client, app):
    csrf_token = _register_and_login(client, "owner@example.com")
    org = _create_org(client, csrf_token)

    response = _invite(client, csrf_token, org["id"])

    assert response.status_code == 201
    body = response.get_json()["data"]
    assert body["email"] == "invitee@example.com"
    assert body["role"] == "employee"
    assert body["status"] == "pending"
    assert body["email_delivery"] == "sent"  # dev-log fallback, no SMTP_HOST in testing
    assert "token" not in body
    assert "token_hash" not in body


def test_owner_can_invite_a_manager(client, app):
    csrf_token = _register_and_login(client, "owner2@example.com")
    org = _create_org(client, csrf_token)

    response = _invite(client, csrf_token, org["id"], role="manager")

    assert response.status_code == 201


def test_without_csrf_token_returns_403(client, app):
    csrf_token = _register_and_login(client, "owner3@example.com")
    org = _create_org(client, csrf_token)

    response = client.post(f"/api/v1/organizations/{org['id']}/invitations", json={"email": "x@example.com", "role": "employee"})

    assert response.status_code == 403
    assert response.get_json()["error"]["code"] == "CSRF_TOKEN_INVALID"


def test_non_member_gets_404(client, app):
    owner_csrf = _register_and_login(client, "realowner@example.com")
    org = _create_org(client, owner_csrf)
    client.post("/api/v1/auth/logout", headers={"X-CSRF-Token": owner_csrf})

    # Logging in as the stranger last, right before the request under
    # test, is deliberate - _register_and_login's login overwrites the
    # test client's one session cookie, so whichever login happens last
    # is who the next request is actually made as.
    csrf_token = _register_and_login(client, "stranger@example.com")
    response = _invite(client, csrf_token, org["id"])

    assert response.status_code == 404


def test_employee_has_no_permission_to_invite_returns_403(client, app):
    owner_csrf = _register_and_login(client, "owner4@example.com")
    org = _create_org(client, owner_csrf)
    client.post("/api/v1/auth/logout", headers={"X-CSRF-Token": owner_csrf})

    csrf_token = _register_and_login(client, "employee@example.com")
    _give_role(app, org["id"], "employee@example.com", MembershipRole.EMPLOYEE)

    response = _invite(client, csrf_token, org["id"])

    assert response.status_code == 403
    assert response.get_json()["error"]["code"] == "FORBIDDEN"


def test_manager_can_invite_an_employee(client, app):
    owner_csrf = _register_and_login(client, "owner5@example.com")
    org = _create_org(client, owner_csrf)
    client.post("/api/v1/auth/logout", headers={"X-CSRF-Token": owner_csrf})

    csrf_token = _register_and_login(client, "manager@example.com")
    _give_role(app, org["id"], "manager@example.com", MembershipRole.MANAGER)

    response = _invite(client, csrf_token, org["id"], role="employee")

    assert response.status_code == 201


def test_manager_cannot_invite_a_manager(client, app):
    owner_csrf = _register_and_login(client, "owner6@example.com")
    org = _create_org(client, owner_csrf)
    client.post("/api/v1/auth/logout", headers={"X-CSRF-Token": owner_csrf})

    csrf_token = _register_and_login(client, "manager2@example.com")
    _give_role(app, org["id"], "manager2@example.com", MembershipRole.MANAGER)

    response = _invite(client, csrf_token, org["id"], role="manager")

    assert response.status_code == 403
    assert response.get_json()["error"]["code"] == "FORBIDDEN"


def test_manager_cannot_invite_an_owner(client, app):
    owner_csrf = _register_and_login(client, "owner7@example.com")
    org = _create_org(client, owner_csrf)
    client.post("/api/v1/auth/logout", headers={"X-CSRF-Token": owner_csrf})

    csrf_token = _register_and_login(client, "manager3@example.com")
    _give_role(app, org["id"], "manager3@example.com", MembershipRole.MANAGER)

    response = _invite(client, csrf_token, org["id"], role="owner")

    assert response.status_code == 403
    assert response.get_json()["error"]["code"] == "FORBIDDEN"


def test_inviting_an_already_pending_email_returns_409(client, app):
    csrf_token = _register_and_login(client, "owner8@example.com")
    org = _create_org(client, csrf_token)
    _invite(client, csrf_token, org["id"], email="dup@example.com")

    response = _invite(client, csrf_token, org["id"], email="dup@example.com")

    assert response.status_code == 409
    assert response.get_json()["error"]["code"] == "INVITATION_ALREADY_PENDING"


def test_inviting_an_existing_active_member_returns_409(client, app):
    owner_csrf = _register_and_login(client, "owner9@example.com")
    org = _create_org(client, owner_csrf)
    # Register only - must not switch the ambient session away from the
    # owner, since the next request needs to be made as them.
    client.post(
        "/api/v1/auth/register",
        json={"name": "Test User", "email": "already-member@example.com", "password": "correct horse battery"},
    )
    _give_role(app, org["id"], "already-member@example.com", MembershipRole.EMPLOYEE)

    response = _invite(client, owner_csrf, org["id"], email="already-member@example.com")

    assert response.status_code == 409
    assert response.get_json()["error"]["code"] == "ALREADY_A_MEMBER"


def test_invalid_role_returns_422(client, app):
    csrf_token = _register_and_login(client, "owner10@example.com")
    org = _create_org(client, csrf_token)

    response = _invite(client, csrf_token, org["id"], role="superadmin")

    assert response.status_code == 422


def test_extra_fields_are_rejected_with_422(client, app):
    csrf_token = _register_and_login(client, "owner11@example.com")
    org = _create_org(client, csrf_token)

    response = client.post(
        f"/api/v1/organizations/{org['id']}/invitations",
        json={"email": "x@example.com", "role": "employee", "organization_id": "smuggled"},
        headers={"X-CSRF-Token": csrf_token},
    )

    assert response.status_code == 422


def test_invitation_email_is_normalized(client, app):
    csrf_token = _register_and_login(client, "owner12@example.com")
    org = _create_org(client, csrf_token)

    response = _invite(client, csrf_token, org["id"], email="Mixed-Case@Example.com")

    assert response.status_code == 201
    assert response.get_json()["data"]["email"] == "mixed-case@example.com"
