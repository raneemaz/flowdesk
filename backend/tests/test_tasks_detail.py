import uuid

import pytest

from app.extensions import db
from app.models import Department, Membership, MembershipRole, MembershipStatus, Organization, Task, User


@pytest.fixture(autouse=True)
def _clean(app):
    yield
    with app.app_context():
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


def _membership_id(app, organization_id, email):
    with app.app_context():
        user = db.session.query(User).filter_by(email=email).one()
        membership = (
            db.session.query(Membership)
            .filter_by(organization_id=uuid.UUID(organization_id), user_id=user.id)
            .one()
        )
        return str(membership.id)


def _make_task(app, organization_id, creator_membership_id, **kwargs):
    with app.app_context():
        task = Task(
            organization_id=uuid.UUID(organization_id),
            creator_membership_id=uuid.UUID(creator_membership_id),
            title=kwargs.pop("title", "Task"),
            **kwargs,
        )
        db.session.add(task)
        db.session.commit()
        return str(task.id)


def _get_task(client, org_id, task_id):
    return client.get(f"/api/v1/organizations/{org_id}/tasks/{task_id}")


def test_unauthenticated_request_returns_401(client):
    response = client.get(
        "/api/v1/organizations/00000000-0000-0000-0000-000000000000/tasks/"
        "00000000-0000-0000-0000-000000000000"
    )
    assert response.status_code == 401


def test_nonexistent_task_returns_404(client):
    csrf_token = _register_and_login(client, "owner@example.com")
    org = _create_org(client, csrf_token)

    response = _get_task(client, org["id"], str(uuid.uuid4()))

    assert response.status_code == 404


def test_cross_org_task_returns_404(client, app):
    owner_a_csrf = _register_and_login(client, "owner2a@example.com")
    org_a = _create_org(client, owner_a_csrf, name="Org A")
    owner_b_csrf = _register_and_login(client, "owner2b@example.com")
    org_b = _create_org(client, owner_b_csrf, name="Org B")
    owner_b_membership_id = _membership_id(app, org_b["id"], "owner2b@example.com")
    task_in_org_b = _make_task(app, org_b["id"], owner_b_membership_id)
    _login(client, "owner2a@example.com")

    response = _get_task(client, org_a["id"], task_in_org_b)

    assert response.status_code == 404


def test_owner_can_view_any_task(client, app):
    csrf_token = _register_and_login(client, "owner3@example.com")
    org = _create_org(client, csrf_token)
    owner_membership_id = _membership_id(app, org["id"], "owner3@example.com")
    task_id = _make_task(app, org["id"], owner_membership_id, title="Write report")

    response = _get_task(client, org["id"], task_id)

    assert response.status_code == 200
    assert response.get_json()["data"]["title"] == "Write report"


def test_manager_can_view_any_task(client, app):
    csrf_token = _register_and_login(client, "owner-mgr@example.com")
    org = _create_org(client, csrf_token)
    owner_membership_id = _membership_id(app, org["id"], "owner-mgr@example.com")
    task_id = _make_task(app, org["id"], owner_membership_id, title="Write report")
    _register_and_login(client, "manager-detail@example.com", name="Manager Detail")
    _give_role(app, org["id"], "manager-detail@example.com", MembershipRole.MANAGER)
    _login(client, "manager-detail@example.com")

    response = _get_task(client, org["id"], task_id)

    assert response.status_code == 200
    assert response.get_json()["data"]["title"] == "Write report"


def test_employee_can_view_their_own_assigned_task(client, app):
    csrf_token = _register_and_login(client, "owner4@example.com")
    org = _create_org(client, csrf_token)
    owner_membership_id = _membership_id(app, org["id"], "owner4@example.com")
    _register_and_login(client, "employee4@example.com", name="Employee Four")
    employee_id = _give_role(app, org["id"], "employee4@example.com", MembershipRole.EMPLOYEE)
    task_id = _make_task(
        app, org["id"], owner_membership_id, title="Assigned", assignee_membership_id=uuid.UUID(employee_id)
    )
    _login(client, "employee4@example.com")

    response = _get_task(client, org["id"], task_id)

    assert response.status_code == 200
    assert response.get_json()["data"]["title"] == "Assigned"


def test_employee_cannot_view_a_task_assigned_to_someone_else(client, app):
    csrf_token = _register_and_login(client, "owner5@example.com")
    org = _create_org(client, csrf_token)
    owner_membership_id = _membership_id(app, org["id"], "owner5@example.com")
    _register_and_login(client, "employee5a@example.com", name="Employee A")
    employee_a_id = _give_role(app, org["id"], "employee5a@example.com", MembershipRole.EMPLOYEE)
    _register_and_login(client, "employee5b@example.com", name="Employee B")
    _give_role(app, org["id"], "employee5b@example.com", MembershipRole.EMPLOYEE)
    task_id = _make_task(
        app, org["id"], owner_membership_id, title="Assigned to A", assignee_membership_id=uuid.UUID(employee_a_id)
    )
    _login(client, "employee5b@example.com")

    response = _get_task(client, org["id"], task_id)

    assert response.status_code == 403


def test_employee_cannot_view_an_unassigned_task(client, app):
    csrf_token = _register_and_login(client, "owner6@example.com")
    org = _create_org(client, csrf_token)
    owner_membership_id = _membership_id(app, org["id"], "owner6@example.com")
    _register_and_login(client, "employee6@example.com", name="Employee Six")
    _give_role(app, org["id"], "employee6@example.com", MembershipRole.EMPLOYEE)
    task_id = _make_task(app, org["id"], owner_membership_id, title="Unassigned")
    _login(client, "employee6@example.com")

    response = _get_task(client, org["id"], task_id)

    assert response.status_code == 403
