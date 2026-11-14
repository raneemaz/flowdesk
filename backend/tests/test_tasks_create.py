import uuid

import pytest

from app.extensions import db
from app.models import Department, DepartmentStatus, Membership, MembershipRole, MembershipStatus, Organization, User


@pytest.fixture(autouse=True)
def _clean(app):
    yield
    with app.app_context():
        from app.models import Task

        db.session.query(Task).delete()
        db.session.query(Department).delete()
        db.session.query(Membership).delete()
        db.session.query(Organization).delete()
        db.session.query(User).delete()
        db.session.commit()


def _login(client, email, password="correct horse battery"):
    login_response = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    return login_response.get_json()["data"]["csrf_token"]


def _register_and_login(client, email, name="Test User", password="correct horse battery"):
    client.post("/api/v1/auth/register", json={"name": name, "email": email, "password": password})
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


def _make_department(app, organization_id, name="Sales", status=DepartmentStatus.ACTIVE):
    with app.app_context():
        department = Department(organization_id=uuid.UUID(organization_id), name=name, status=status)
        db.session.add(department)
        db.session.commit()
        return str(department.id)


def _create_task(client, csrf_token, org_id, **body):
    body.setdefault("title", "Write report")
    return client.post(f"/api/v1/organizations/{org_id}/tasks", json=body, headers={"X-CSRF-Token": csrf_token})


def test_unauthenticated_request_returns_401(client):
    response = client.post("/api/v1/organizations/00000000-0000-0000-0000-000000000000/tasks", json={})
    assert response.status_code == 401


def test_owner_can_create_a_task(client):
    csrf_token = _register_and_login(client, "owner@example.com")
    org = _create_org(client, csrf_token)

    response = _create_task(client, csrf_token, org["id"], title="Write report")

    assert response.status_code == 201
    body = response.get_json()["data"]
    assert body["title"] == "Write report"
    assert body["status"] == "to_do"
    assert body["priority"] == "medium"
    assert body["description"] is None
    assert body["assignee_membership_id"] is None


def test_manager_can_create_a_task(client, app):
    csrf_token = _register_and_login(client, "owner2@example.com")
    org = _create_org(client, csrf_token)
    _register_and_login(client, "manager2@example.com", name="Manager Two")
    _give_role(app, org["id"], "manager2@example.com", MembershipRole.MANAGER)
    manager_csrf = _login(client, "manager2@example.com")

    response = _create_task(client, manager_csrf, org["id"])

    assert response.status_code == 201


@pytest.mark.parametrize("role", [MembershipRole.EMPLOYEE, MembershipRole.ACCOUNTANT, MembershipRole.CUSTOMER_SUPPORT])
def test_non_manager_roles_cannot_create_a_task(client, app, role):
    csrf_token = _register_and_login(client, f"owner-{role.value}@example.com")
    org = _create_org(client, csrf_token)
    other_email = f"{role.value}@example.com"
    _register_and_login(client, other_email, name="Other Role")
    _give_role(app, org["id"], other_email, role)
    other_csrf = _login(client, other_email)

    response = _create_task(client, other_csrf, org["id"])

    assert response.status_code == 403


def test_create_without_csrf_token_returns_403(client):
    csrf_token = _register_and_login(client, "owner3@example.com")
    org = _create_org(client, csrf_token)

    response = client.post(f"/api/v1/organizations/{org['id']}/tasks", json={"title": "Write report"})

    assert response.status_code == 403


def test_create_in_an_organization_the_caller_does_not_belong_to_returns_404(client):
    csrf_token = _register_and_login(client, "owner4@example.com")
    org = _create_org(client, csrf_token)
    outsider_csrf = _register_and_login(client, "outsider@example.com")

    response = _create_task(client, outsider_csrf, org["id"])

    assert response.status_code == 404


def test_create_requires_a_title(client):
    csrf_token = _register_and_login(client, "owner5@example.com")
    org = _create_org(client, csrf_token)

    response = client.post(
        f"/api/v1/organizations/{org['id']}/tasks", json={}, headers={"X-CSRF-Token": csrf_token}
    )

    assert response.status_code == 422


def test_create_rejects_a_blank_title(client):
    csrf_token = _register_and_login(client, "owner6@example.com")
    org = _create_org(client, csrf_token)

    response = _create_task(client, csrf_token, org["id"], title="   ")

    assert response.status_code == 422


def test_create_with_all_fields(client):
    csrf_token = _register_and_login(client, "owner7@example.com")
    org = _create_org(client, csrf_token)

    response = _create_task(
        client,
        csrf_token,
        org["id"],
        title="Write report",
        description="Quarterly report",
        priority="high",
        start_date="2026-01-01",
        due_date="2026-01-10",
        estimated_hours="4.5",
    )

    assert response.status_code == 201
    body = response.get_json()["data"]
    assert body["description"] == "Quarterly report"
    assert body["priority"] == "high"
    assert body["start_date"] == "2026-01-01"
    assert body["due_date"] == "2026-01-10"
    assert body["estimated_hours"] == "4.5" or body["estimated_hours"] == "4.50"


def test_create_rejects_an_unknown_department_id(client):
    csrf_token = _register_and_login(client, "owner8@example.com")
    org = _create_org(client, csrf_token)

    response = _create_task(client, csrf_token, org["id"], department_id="00000000-0000-0000-0000-000000000000")

    assert response.status_code == 422
    assert response.get_json()["error"]["code"] == "INVALID_DEPARTMENT"


def test_create_rejects_a_cross_org_department_id(client, app):
    owner_a_csrf = _register_and_login(client, "owner9a@example.com")
    org_a = _create_org(client, owner_a_csrf, name="Org A")
    owner_b_csrf = _register_and_login(client, "owner9b@example.com")
    org_b = _create_org(client, owner_b_csrf, name="Org B")
    foreign_department_id = _make_department(app, org_b["id"])
    owner_a_csrf = _login(client, "owner9a@example.com")

    response = _create_task(client, owner_a_csrf, org_a["id"], department_id=foreign_department_id)

    assert response.status_code == 422
    assert response.get_json()["error"]["code"] == "INVALID_DEPARTMENT"


def test_create_rejects_an_inactive_department_id(client, app):
    csrf_token = _register_and_login(client, "owner10@example.com")
    org = _create_org(client, csrf_token)
    inactive_department_id = _make_department(app, org["id"], status=DepartmentStatus.INACTIVE)
    owner_csrf = _login(client, "owner10@example.com")

    response = _create_task(client, owner_csrf, org["id"], department_id=inactive_department_id)

    assert response.status_code == 422
    assert response.get_json()["error"]["code"] == "INVALID_DEPARTMENT"


def test_create_rejects_due_date_before_start_date(client):
    csrf_token = _register_and_login(client, "owner11@example.com")
    org = _create_org(client, csrf_token)

    response = _create_task(client, csrf_token, org["id"], start_date="2026-01-10", due_date="2026-01-01")

    assert response.status_code == 422


def test_create_rejects_unknown_fields(client):
    csrf_token = _register_and_login(client, "owner12@example.com")
    org = _create_org(client, csrf_token)

    response = _create_task(client, csrf_token, org["id"], assignee_membership_id="00000000-0000-0000-0000-000000000000")

    assert response.status_code == 422


def test_create_rejects_estimated_hours_out_of_range(client):
    csrf_token = _register_and_login(client, "owner13@example.com")
    org = _create_org(client, csrf_token)

    response = _create_task(client, csrf_token, org["id"], estimated_hours="-1")

    assert response.status_code == 422


def test_create_sets_creator_to_the_caller_regardless_of_body(client, app):
    csrf_token = _register_and_login(client, "owner14@example.com")
    org = _create_org(client, csrf_token)

    response = _create_task(client, csrf_token, org["id"])
    assert response.status_code == 201
    task_id = response.get_json()["data"]["id"]

    with app.app_context():
        from app.models import Task

        task = db.session.get(Task, task_id)
        user = db.session.query(User).filter_by(email="owner14@example.com").one()
        creator_membership = (
            db.session.query(Membership).filter_by(user_id=user.id, organization_id=task.organization_id).one()
        )
        assert str(task.creator_membership_id) == str(creator_membership.id)
