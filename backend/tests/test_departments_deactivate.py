import pytest

from app.extensions import db
from app.models import Department, EmployeeProfile, Membership, MembershipRole, MembershipStatus, Organization, User


@pytest.fixture(autouse=True)
def _clean(app):
    yield
    with app.app_context():
        db.session.query(EmployeeProfile).delete()
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


def _deactivate(client, csrf_token, org_id, dept_id):
    return client.delete(
        f"/api/v1/organizations/{org_id}/departments/{dept_id}", headers={"X-CSRF-Token": csrf_token}
    )


def test_deactivate_sets_status_to_inactive(client):
    csrf_token = _register_and_login(client, "owner@example.com")
    org = _create_org(client, csrf_token)
    department = _create_department(client, csrf_token, org["id"])

    response = _deactivate(client, csrf_token, org["id"], department["id"])

    assert response.status_code == 200
    assert response.get_json()["data"]["status"] == "inactive"


def test_deactivate_is_idempotent(client):
    csrf_token = _register_and_login(client, "owner2@example.com")
    org = _create_org(client, csrf_token)
    department = _create_department(client, csrf_token, org["id"])
    _deactivate(client, csrf_token, org["id"], department["id"])

    response = _deactivate(client, csrf_token, org["id"], department["id"])

    assert response.status_code == 200
    assert response.get_json()["data"]["status"] == "inactive"


def test_deactivate_does_not_delete_the_department_row(client, app):
    csrf_token = _register_and_login(client, "owner3@example.com")
    org = _create_org(client, csrf_token)
    department = _create_department(client, csrf_token, org["id"])

    _deactivate(client, csrf_token, org["id"], department["id"])

    with app.app_context():
        import uuid

        survivor = db.session.get(Department, uuid.UUID(department["id"]))
        assert survivor is not None
        assert survivor.name == "Sales"


def test_deactivate_preserves_an_employees_historical_department_reference(client, app):
    """Safe-deletion policy (this task's own wording): an EmployeeProfile
    that was in this department keeps pointing to it - deactivation
    never deletes historical references, unlike a hard delete which
    would have to SET NULL them (Department.employee_profiles' FK)."""
    csrf_token = _register_and_login(client, "owner4@example.com")
    org = _create_org(client, csrf_token)
    department = _create_department(client, csrf_token, org["id"])

    with app.app_context():
        import uuid

        membership = db.session.query(Membership).filter_by(organization_id=uuid.UUID(org["id"])).one()
        profile = EmployeeProfile(
            organization_id=uuid.UUID(org["id"]),
            membership_id=membership.id,
            department_id=uuid.UUID(department["id"]),
        )
        db.session.add(profile)
        db.session.commit()
        profile_id = profile.id

    _deactivate(client, csrf_token, org["id"], department["id"])

    with app.app_context():
        survivor = db.session.get(EmployeeProfile, profile_id)
        assert survivor is not None
        assert str(survivor.department_id) == department["id"]


def test_deactivate_a_nonexistent_department_returns_404(client):
    csrf_token = _register_and_login(client, "owner5@example.com")
    org = _create_org(client, csrf_token)

    response = _deactivate(client, csrf_token, org["id"], "00000000-0000-0000-0000-000000000000")

    assert response.status_code == 404


def test_deactivate_a_department_from_a_different_organization_returns_404(client):
    csrf_token = _register_and_login(client, "owner6@example.com")
    org_a = _create_org(client, csrf_token, name="Org A")
    org_b = _create_org(client, csrf_token, name="Org B")
    department_in_org_a = _create_department(client, csrf_token, org_a["id"])

    response = _deactivate(client, csrf_token, org_b["id"], department_in_org_a["id"])

    assert response.status_code == 404


def test_deactivate_without_csrf_token_returns_403(client):
    csrf_token = _register_and_login(client, "owner7@example.com")
    org = _create_org(client, csrf_token)
    department = _create_department(client, csrf_token, org["id"])

    response = client.delete(f"/api/v1/organizations/{org['id']}/departments/{department['id']}")

    assert response.status_code == 403


def test_employee_cannot_deactivate_a_department(client, app):
    csrf_token = _register_and_login(client, "owner8@example.com")
    org = _create_org(client, csrf_token)
    department = _create_department(client, csrf_token, org["id"])

    employee_csrf = _register_and_login(client, "employee8@example.com")
    _give_role(app, org["id"], "employee8@example.com", MembershipRole.EMPLOYEE)

    response = _deactivate(client, employee_csrf, org["id"], department["id"])

    assert response.status_code == 403
