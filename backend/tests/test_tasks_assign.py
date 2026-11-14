import uuid

import pytest

from app.extensions import db
from app.models import Membership, MembershipRole, MembershipStatus, Organization, Task, TaskHistory, User


@pytest.fixture(autouse=True)
def _clean(app):
    yield
    with app.app_context():
        db.session.query(TaskHistory).delete()
        db.session.query(Task).delete()
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


def _assign_task(client, csrf_token, org_id, task_id, assignee_membership_id):
    return client.patch(
        f"/api/v1/organizations/{org_id}/tasks/{task_id}/assign",
        json={"assignee_membership_id": assignee_membership_id},
        headers={"X-CSRF-Token": csrf_token},
    )


def test_unauthenticated_request_returns_401(client):
    response = client.patch(
        "/api/v1/organizations/00000000-0000-0000-0000-000000000000/tasks/"
        "00000000-0000-0000-0000-000000000000/assign",
        json={"assignee_membership_id": None},
    )
    assert response.status_code == 401


def test_owner_can_assign_a_task(client, app):
    csrf_token = _register_and_login(client, "owner@example.com")
    org = _create_org(client, csrf_token)
    owner_id = _membership_id(app, org["id"], "owner@example.com")
    task_id = _make_task(app, org["id"], owner_id)
    _register_and_login(client, "employee@example.com", name="Employee One")
    employee_id = _give_role(app, org["id"], "employee@example.com", MembershipRole.EMPLOYEE)
    owner_csrf = _login(client, "owner@example.com")

    response = _assign_task(client, owner_csrf, org["id"], task_id, employee_id)

    assert response.status_code == 200
    assert response.get_json()["data"]["assignee_membership_id"] == employee_id


def test_manager_can_reassign_a_task(client, app):
    csrf_token = _register_and_login(client, "owner2@example.com")
    org = _create_org(client, csrf_token)
    owner_id = _membership_id(app, org["id"], "owner2@example.com")
    _register_and_login(client, "manager2@example.com", name="Manager Two")
    _give_role(app, org["id"], "manager2@example.com", MembershipRole.MANAGER)
    _register_and_login(client, "employee2a@example.com", name="Employee A")
    employee_a_id = _give_role(app, org["id"], "employee2a@example.com", MembershipRole.EMPLOYEE)
    _register_and_login(client, "employee2b@example.com", name="Employee B")
    employee_b_id = _give_role(app, org["id"], "employee2b@example.com", MembershipRole.EMPLOYEE)
    task_id = _make_task(app, org["id"], owner_id, assignee_membership_id=uuid.UUID(employee_a_id))
    manager_csrf = _login(client, "manager2@example.com")

    response = _assign_task(client, manager_csrf, org["id"], task_id, employee_b_id)

    assert response.status_code == 200
    assert response.get_json()["data"]["assignee_membership_id"] == employee_b_id


def test_can_unassign_a_task(client, app):
    csrf_token = _register_and_login(client, "owner3@example.com")
    org = _create_org(client, csrf_token)
    owner_id = _membership_id(app, org["id"], "owner3@example.com")
    _register_and_login(client, "employee3@example.com", name="Employee Three")
    employee_id = _give_role(app, org["id"], "employee3@example.com", MembershipRole.EMPLOYEE)
    task_id = _make_task(app, org["id"], owner_id, assignee_membership_id=uuid.UUID(employee_id))
    owner_csrf = _login(client, "owner3@example.com")

    response = _assign_task(client, owner_csrf, org["id"], task_id, None)

    assert response.status_code == 200
    assert response.get_json()["data"]["assignee_membership_id"] is None


@pytest.mark.parametrize("role", [MembershipRole.EMPLOYEE, MembershipRole.ACCOUNTANT, MembershipRole.CUSTOMER_SUPPORT])
def test_non_manager_roles_cannot_assign_a_task(client, app, role):
    csrf_token = _register_and_login(client, f"owner-{role.value}@example.com")
    org = _create_org(client, csrf_token)
    owner_id = _membership_id(app, org["id"], f"owner-{role.value}@example.com")
    task_id = _make_task(app, org["id"], owner_id)
    other_email = f"{role.value}@example.com"
    _register_and_login(client, other_email, name="Other Role")
    _give_role(app, org["id"], other_email, role)
    other_csrf = _login(client, other_email)

    response = _assign_task(client, other_csrf, org["id"], task_id, None)

    assert response.status_code == 403


def test_assign_without_csrf_token_returns_403(client, app):
    csrf_token = _register_and_login(client, "owner4@example.com")
    org = _create_org(client, csrf_token)
    owner_id = _membership_id(app, org["id"], "owner4@example.com")
    task_id = _make_task(app, org["id"], owner_id)

    response = client.patch(
        f"/api/v1/organizations/{org['id']}/tasks/{task_id}/assign", json={"assignee_membership_id": None}
    )

    assert response.status_code == 403


def test_assign_a_nonexistent_task_returns_404(client):
    csrf_token = _register_and_login(client, "owner5@example.com")
    org = _create_org(client, csrf_token)

    response = _assign_task(client, csrf_token, org["id"], str(uuid.uuid4()), None)

    assert response.status_code == 404


def test_assign_a_cross_org_task_returns_404(client, app):
    owner_a_csrf = _register_and_login(client, "owner6a@example.com")
    org_a = _create_org(client, owner_a_csrf, name="Org A")
    owner_b_csrf = _register_and_login(client, "owner6b@example.com")
    org_b = _create_org(client, owner_b_csrf, name="Org B")
    owner_b_id = _membership_id(app, org_b["id"], "owner6b@example.com")
    task_in_org_b = _make_task(app, org_b["id"], owner_b_id)
    owner_a_csrf = _login(client, "owner6a@example.com")

    response = _assign_task(client, owner_a_csrf, org_a["id"], task_in_org_b, None)

    assert response.status_code == 404


def test_assign_rejects_an_unknown_assignee(client, app):
    csrf_token = _register_and_login(client, "owner7@example.com")
    org = _create_org(client, csrf_token)
    owner_id = _membership_id(app, org["id"], "owner7@example.com")
    task_id = _make_task(app, org["id"], owner_id)

    response = _assign_task(client, csrf_token, org["id"], task_id, str(uuid.uuid4()))

    assert response.status_code == 422
    assert response.get_json()["error"]["code"] == "INVALID_ASSIGNEE"


def test_assign_rejects_a_cross_org_assignee(client, app):
    owner_a_csrf = _register_and_login(client, "owner8a@example.com")
    org_a = _create_org(client, owner_a_csrf, name="Org A")
    owner_b_csrf = _register_and_login(client, "owner8b@example.com")
    org_b = _create_org(client, owner_b_csrf, name="Org B")
    owner_a_id = _membership_id(app, org_a["id"], "owner8a@example.com")
    foreign_membership_id = _membership_id(app, org_b["id"], "owner8b@example.com")
    task_id = _make_task(app, org_a["id"], owner_a_id)
    owner_a_csrf = _login(client, "owner8a@example.com")

    response = _assign_task(client, owner_a_csrf, org_a["id"], task_id, foreign_membership_id)

    assert response.status_code == 422
    assert response.get_json()["error"]["code"] == "INVALID_ASSIGNEE"


def test_assign_rejects_an_inactive_assignee(client, app):
    csrf_token = _register_and_login(client, "owner9@example.com")
    org = _create_org(client, csrf_token)
    owner_id = _membership_id(app, org["id"], "owner9@example.com")
    _register_and_login(client, "inactive9@example.com", name="Inactive Employee")
    inactive_id = _give_role(
        app, org["id"], "inactive9@example.com", MembershipRole.EMPLOYEE, status=MembershipStatus.INACTIVE
    )
    task_id = _make_task(app, org["id"], owner_id)
    owner_csrf = _login(client, "owner9@example.com")

    response = _assign_task(client, owner_csrf, org["id"], task_id, inactive_id)

    assert response.status_code == 422
    assert response.get_json()["error"]["code"] == "INVALID_ASSIGNEE"


def test_assign_requires_the_field(client, app):
    csrf_token = _register_and_login(client, "owner10@example.com")
    org = _create_org(client, csrf_token)
    owner_id = _membership_id(app, org["id"], "owner10@example.com")
    task_id = _make_task(app, org["id"], owner_id)

    response = client.patch(
        f"/api/v1/organizations/{org['id']}/tasks/{task_id}/assign", json={}, headers={"X-CSRF-Token": csrf_token}
    )

    assert response.status_code == 422


def test_assign_rejects_unknown_fields(client, app):
    csrf_token = _register_and_login(client, "owner11@example.com")
    org = _create_org(client, csrf_token)
    owner_id = _membership_id(app, org["id"], "owner11@example.com")
    task_id = _make_task(app, org["id"], owner_id)

    response = client.patch(
        f"/api/v1/organizations/{org['id']}/tasks/{task_id}/assign",
        json={"assignee_membership_id": None, "status": "completed"},
        headers={"X-CSRF-Token": csrf_token},
    )

    assert response.status_code == 422


def test_assigning_records_a_task_history_entry(client, app):
    csrf_token = _register_and_login(client, "owner12@example.com")
    org = _create_org(client, csrf_token)
    owner_id = _membership_id(app, org["id"], "owner12@example.com")
    task_id = _make_task(app, org["id"], owner_id)
    _register_and_login(client, "employee12@example.com", name="Employee Twelve")
    employee_id = _give_role(app, org["id"], "employee12@example.com", MembershipRole.EMPLOYEE)
    owner_csrf = _login(client, "owner12@example.com")

    response = _assign_task(client, owner_csrf, org["id"], task_id, employee_id)
    assert response.status_code == 200

    with app.app_context():
        entries = db.session.query(TaskHistory).filter_by(task_id=uuid.UUID(task_id)).all()
        assert len(entries) == 1
        assert entries[0].event_type == "assignee_changed"
        assert entries[0].previous_value is None
        assert entries[0].new_value == employee_id
        assert str(entries[0].actor_membership_id) == owner_id


def test_reassigning_records_previous_and_new_assignee(client, app):
    csrf_token = _register_and_login(client, "owner13@example.com")
    org = _create_org(client, csrf_token)
    owner_id = _membership_id(app, org["id"], "owner13@example.com")
    _register_and_login(client, "employee13a@example.com", name="Employee A")
    employee_a_id = _give_role(app, org["id"], "employee13a@example.com", MembershipRole.EMPLOYEE)
    _register_and_login(client, "employee13b@example.com", name="Employee B")
    employee_b_id = _give_role(app, org["id"], "employee13b@example.com", MembershipRole.EMPLOYEE)
    task_id = _make_task(app, org["id"], owner_id, assignee_membership_id=uuid.UUID(employee_a_id))
    owner_csrf = _login(client, "owner13@example.com")

    response = _assign_task(client, owner_csrf, org["id"], task_id, employee_b_id)
    assert response.status_code == 200

    with app.app_context():
        entries = db.session.query(TaskHistory).filter_by(task_id=uuid.UUID(task_id)).all()
        assert len(entries) == 1
        assert entries[0].previous_value == employee_a_id
        assert entries[0].new_value == employee_b_id


def test_reassigning_to_the_same_assignee_is_a_no_op(client, app):
    csrf_token = _register_and_login(client, "owner14@example.com")
    org = _create_org(client, csrf_token)
    owner_id = _membership_id(app, org["id"], "owner14@example.com")
    _register_and_login(client, "employee14@example.com", name="Employee Fourteen")
    employee_id = _give_role(app, org["id"], "employee14@example.com", MembershipRole.EMPLOYEE)
    task_id = _make_task(app, org["id"], owner_id, assignee_membership_id=uuid.UUID(employee_id))
    owner_csrf = _login(client, "owner14@example.com")

    response = _assign_task(client, owner_csrf, org["id"], task_id, employee_id)

    assert response.status_code == 200
    with app.app_context():
        assert db.session.query(TaskHistory).filter_by(task_id=uuid.UUID(task_id)).count() == 0


def test_unassigning_an_already_unassigned_task_is_a_no_op(client, app):
    csrf_token = _register_and_login(client, "owner15@example.com")
    org = _create_org(client, csrf_token)
    owner_id = _membership_id(app, org["id"], "owner15@example.com")
    task_id = _make_task(app, org["id"], owner_id)

    response = _assign_task(client, csrf_token, org["id"], task_id, None)

    assert response.status_code == 200
    with app.app_context():
        assert db.session.query(TaskHistory).filter_by(task_id=uuid.UUID(task_id)).count() == 0
