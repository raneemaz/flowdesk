import pytest

from app.extensions import db
from app.models import Department, Membership, MembershipRole, MembershipStatus, Organization, User


@pytest.fixture(autouse=True)
def _clean(app):
    yield
    with app.app_context():
        db.session.query(Department).delete()
        db.session.query(Membership).delete()
        db.session.query(Organization).delete()
        db.session.query(User).delete()
        db.session.commit()


def _login(client, email, password="correct horse battery"):
    login_response = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    return login_response.get_json()["data"]["csrf_token"]


def _register_and_login(client, email, password="correct horse battery"):
    client.post("/api/v1/auth/register", json={"name": "Test User", "email": email, "password": password})
    return _login(client, email, password)


def _create_org(client, csrf_token, name="Org One"):
    return client.post(
        "/api/v1/organizations", json={"name": name}, headers={"X-CSRF-Token": csrf_token}
    ).get_json()["data"]


def _give_role(app, organization_id, email, role, status=MembershipStatus.ACTIVE):
    with app.app_context():
        user = db.session.query(User).filter_by(email=email).one()
        membership = Membership(organization_id=organization_id, user_id=user.id, role=role, status=status)
        db.session.add(membership)
        db.session.commit()
        return str(membership.id)


def _create_department(client, csrf_token, org_id, **body):
    body.setdefault("name", "Sales")
    return client.post(
        f"/api/v1/organizations/{org_id}/departments", json=body, headers={"X-CSRF-Token": csrf_token}
    )


def test_unauthenticated_request_returns_401(client):
    response = client.post(
        "/api/v1/organizations/00000000-0000-0000-0000-000000000000/departments", json={"name": "Sales"}
    )
    assert response.status_code == 401


def test_owner_can_create_a_department(client):
    csrf_token = _register_and_login(client, "owner@example.com")
    org = _create_org(client, csrf_token)

    response = _create_department(client, csrf_token, org["id"], name="Sales", description="Revenue team")

    assert response.status_code == 201
    body = response.get_json()["data"]
    assert body["name"] == "Sales"
    assert body["description"] == "Revenue team"
    assert body["organization_id"] == org["id"]
    assert body["manager_membership_id"] is None
    assert body["status"] == "active"


def test_manager_can_create_a_department(client, app):
    csrf_token = _register_and_login(client, "owner2@example.com")
    org = _create_org(client, csrf_token)
    manager_csrf = _register_and_login(client, "manager2@example.com")
    _give_role(app, org["id"], "manager2@example.com", MembershipRole.MANAGER)

    response = _create_department(client, manager_csrf, org["id"])

    assert response.status_code == 201


@pytest.mark.parametrize(
    "role", [MembershipRole.EMPLOYEE, MembershipRole.ACCOUNTANT, MembershipRole.CUSTOMER_SUPPORT]
)
def test_other_roles_cannot_create_a_department(client, app, role):
    csrf_token = _register_and_login(client, "owner3@example.com")
    org = _create_org(client, csrf_token)
    other_email = f"{role.value}@example.com"
    other_csrf = _register_and_login(client, other_email)
    _give_role(app, org["id"], other_email, role)

    response = _create_department(client, other_csrf, org["id"])

    assert response.status_code == 403
    assert response.get_json()["error"]["code"] == "FORBIDDEN"


def test_create_without_csrf_token_returns_403(client):
    csrf_token = _register_and_login(client, "owner4@example.com")
    org = _create_org(client, csrf_token)

    response = client.post(f"/api/v1/organizations/{org['id']}/departments", json={"name": "Sales"})

    assert response.status_code == 403


def test_create_in_an_organization_the_caller_does_not_belong_to_returns_404(client):
    csrf_token = _register_and_login(client, "owner5@example.com")
    org = _create_org(client, csrf_token)

    # Registering (and therefore logging in as) the outsider last - the
    # test client has a single session cookie, so whoever logs in last
    # is who the next request acts as.
    outsider_csrf = _register_and_login(client, "outsider@example.com")

    response = _create_department(client, outsider_csrf, org["id"])

    assert response.status_code == 404


def test_create_missing_name_returns_422(client):
    csrf_token = _register_and_login(client, "owner6@example.com")
    org = _create_org(client, csrf_token)

    response = client.post(
        f"/api/v1/organizations/{org['id']}/departments", json={}, headers={"X-CSRF-Token": csrf_token}
    )

    assert response.status_code == 422
    assert response.get_json()["error"]["code"] == "VALIDATION_ERROR"


def test_create_with_a_whitespace_only_name_returns_422(client):
    csrf_token = _register_and_login(client, "owner7@example.com")
    org = _create_org(client, csrf_token)

    response = _create_department(client, csrf_token, org["id"], name="   ")

    assert response.status_code == 422


@pytest.mark.parametrize("extra_field", ["id", "organization_id", "status"])
def test_create_rejects_unknown_fields(client, extra_field):
    csrf_token = _register_and_login(client, "owner8@example.com")
    org = _create_org(client, csrf_token)

    response = _create_department(client, csrf_token, org["id"], **{extra_field: "something"})

    assert response.status_code == 422


def test_create_with_a_valid_manager_membership_succeeds(client, app):
    csrf_token = _register_and_login(client, "owner9@example.com")
    org = _create_org(client, csrf_token)

    _register_and_login(client, "manager9@example.com")
    manager_membership_id = _give_role(app, org["id"], "manager9@example.com", MembershipRole.MANAGER)

    # Switch the session back to the owner (last) - the test client has
    # a single session cookie, and the owner is who's actually tested.
    csrf_token = _login(client, "owner9@example.com")

    response = _create_department(client, csrf_token, org["id"], manager_membership_id=manager_membership_id)

    assert response.status_code == 201
    assert response.get_json()["data"]["manager_membership_id"] == manager_membership_id


def test_create_with_a_manager_membership_from_a_different_organization_returns_422(client, app):
    csrf_token = _register_and_login(client, "owner10@example.com")
    org_a = _create_org(client, csrf_token, name="Org A")
    org_b = _create_org(client, csrf_token, name="Org B")

    _register_and_login(client, "manager10@example.com")
    manager_membership_in_org_b = _give_role(app, org_b["id"], "manager10@example.com", MembershipRole.MANAGER)

    csrf_token = _login(client, "owner10@example.com")

    response = _create_department(
        client, csrf_token, org_a["id"], manager_membership_id=manager_membership_in_org_b
    )

    assert response.status_code == 422
    assert response.get_json()["error"]["code"] == "INVALID_MANAGER_MEMBERSHIP"


def test_create_with_an_inactive_manager_membership_returns_422(client, app):
    csrf_token = _register_and_login(client, "owner11@example.com")
    org = _create_org(client, csrf_token)

    _register_and_login(client, "manager11@example.com")
    inactive_manager_membership = _give_role(
        app, org["id"], "manager11@example.com", MembershipRole.MANAGER, status=MembershipStatus.INACTIVE
    )

    csrf_token = _login(client, "owner11@example.com")

    response = _create_department(
        client, csrf_token, org["id"], manager_membership_id=inactive_manager_membership
    )

    assert response.status_code == 422
    assert response.get_json()["error"]["code"] == "INVALID_MANAGER_MEMBERSHIP"


def test_create_with_a_nonexistent_manager_membership_returns_422(client):
    csrf_token = _register_and_login(client, "owner12@example.com")
    org = _create_org(client, csrf_token)

    response = _create_department(
        client, csrf_token, org["id"], manager_membership_id="00000000-0000-0000-0000-000000000000"
    )

    assert response.status_code == 422
    assert response.get_json()["error"]["code"] == "INVALID_MANAGER_MEMBERSHIP"
