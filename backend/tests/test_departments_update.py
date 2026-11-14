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
    ).get_json()["data"]


def _patch_department(client, csrf_token, org_id, dept_id, **body):
    return client.patch(
        f"/api/v1/organizations/{org_id}/departments/{dept_id}", json=body, headers={"X-CSRF-Token": csrf_token}
    )


def test_update_name_and_description(client):
    csrf_token = _register_and_login(client, "owner@example.com")
    org = _create_org(client, csrf_token)
    department = _create_department(client, csrf_token, org["id"], description="Old")

    response = _patch_department(
        client, csrf_token, org["id"], department["id"], name="Revenue", description="New"
    )

    assert response.status_code == 200
    body = response.get_json()["data"]
    assert body["name"] == "Revenue"
    assert body["description"] == "New"


def test_update_only_touches_fields_actually_sent(client):
    csrf_token = _register_and_login(client, "owner2@example.com")
    org = _create_org(client, csrf_token)
    department = _create_department(client, csrf_token, org["id"], description="Keep me")

    response = _patch_department(client, csrf_token, org["id"], department["id"], name="Renamed")

    assert response.status_code == 200
    body = response.get_json()["data"]
    assert body["name"] == "Renamed"
    assert body["description"] == "Keep me"


def test_update_can_clear_description_with_an_explicit_null(client):
    csrf_token = _register_and_login(client, "owner3@example.com")
    org = _create_org(client, csrf_token)
    department = _create_department(client, csrf_token, org["id"], description="Clear me")

    response = _patch_department(client, csrf_token, org["id"], department["id"], description=None)

    assert response.status_code == 200
    assert response.get_json()["data"]["description"] is None


def test_update_rejects_an_explicit_null_name(client):
    csrf_token = _register_and_login(client, "owner4@example.com")
    org = _create_org(client, csrf_token)
    department = _create_department(client, csrf_token, org["id"])

    response = _patch_department(client, csrf_token, org["id"], department["id"], name=None)

    assert response.status_code == 422


def test_update_rejects_an_explicit_null_status(client):
    csrf_token = _register_and_login(client, "owner5@example.com")
    org = _create_org(client, csrf_token)
    department = _create_department(client, csrf_token, org["id"])

    response = _patch_department(client, csrf_token, org["id"], department["id"], status=None)

    assert response.status_code == 422


def test_update_can_reactivate_a_deactivated_department(client):
    csrf_token = _register_and_login(client, "owner6@example.com")
    org = _create_org(client, csrf_token)
    department = _create_department(client, csrf_token, org["id"])
    client.delete(
        f"/api/v1/organizations/{org['id']}/departments/{department['id']}", headers={"X-CSRF-Token": csrf_token}
    )

    response = _patch_department(client, csrf_token, org["id"], department["id"], status="active")

    assert response.status_code == 200
    assert response.get_json()["data"]["status"] == "active"


def test_update_can_assign_and_then_clear_a_manager(client, app):
    csrf_token = _register_and_login(client, "owner7@example.com")
    org = _create_org(client, csrf_token)
    department = _create_department(client, csrf_token, org["id"])

    _register_and_login(client, "manager7@example.com")
    manager_membership_id = _give_role(app, org["id"], "manager7@example.com", MembershipRole.MANAGER)
    csrf_token = _login(client, "owner7@example.com")

    assign_response = _patch_department(
        client, csrf_token, org["id"], department["id"], manager_membership_id=manager_membership_id
    )
    assert assign_response.status_code == 200
    assert assign_response.get_json()["data"]["manager_membership_id"] == manager_membership_id

    clear_response = _patch_department(
        client, csrf_token, org["id"], department["id"], manager_membership_id=None
    )
    assert clear_response.status_code == 200
    assert clear_response.get_json()["data"]["manager_membership_id"] is None


def test_update_with_a_manager_from_a_different_organization_returns_422(client, app):
    csrf_token = _register_and_login(client, "owner8@example.com")
    org_a = _create_org(client, csrf_token, name="Org A")
    org_b = _create_org(client, csrf_token, name="Org B")
    department = _create_department(client, csrf_token, org_a["id"])

    _register_and_login(client, "manager8@example.com")
    manager_in_org_b = _give_role(app, org_b["id"], "manager8@example.com", MembershipRole.MANAGER)
    csrf_token = _login(client, "owner8@example.com")

    response = _patch_department(
        client, csrf_token, org_a["id"], department["id"], manager_membership_id=manager_in_org_b
    )

    assert response.status_code == 422
    assert response.get_json()["error"]["code"] == "INVALID_MANAGER_MEMBERSHIP"


def test_update_a_nonexistent_department_returns_404(client):
    csrf_token = _register_and_login(client, "owner9@example.com")
    org = _create_org(client, csrf_token)

    response = _patch_department(
        client, csrf_token, org["id"], "00000000-0000-0000-0000-000000000000", name="Renamed"
    )

    assert response.status_code == 404


def test_update_a_department_from_a_different_organization_returns_404(client):
    csrf_token = _register_and_login(client, "owner10@example.com")
    org_a = _create_org(client, csrf_token, name="Org A")
    org_b = _create_org(client, csrf_token, name="Org B")
    department_in_org_a = _create_department(client, csrf_token, org_a["id"])

    response = _patch_department(
        client, csrf_token, org_b["id"], department_in_org_a["id"], name="Hijacked"
    )

    assert response.status_code == 404


def test_update_without_csrf_token_returns_403(client):
    csrf_token = _register_and_login(client, "owner11@example.com")
    org = _create_org(client, csrf_token)
    department = _create_department(client, csrf_token, org["id"])

    response = client.patch(
        f"/api/v1/organizations/{org['id']}/departments/{department['id']}", json={"name": "Renamed"}
    )

    assert response.status_code == 403


def test_employee_cannot_update_a_department(client, app):
    csrf_token = _register_and_login(client, "owner12@example.com")
    org = _create_org(client, csrf_token)
    department = _create_department(client, csrf_token, org["id"])

    employee_csrf = _register_and_login(client, "employee12@example.com")
    _give_role(app, org["id"], "employee12@example.com", MembershipRole.EMPLOYEE)

    response = _patch_department(client, employee_csrf, org["id"], department["id"], name="Hijacked")

    assert response.status_code == 403
