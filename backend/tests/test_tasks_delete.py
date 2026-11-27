"""DELETE /organizations/{id}/tasks/{task_id} - permanent task delete."""

import uuid

import pytest

from app.extensions import db
from app.models import (
    ActivityLog,
    Membership,
    MembershipRole,
    MembershipStatus,
    Notification,
    Organization,
    Task,
    TaskComment,
    TaskHistory,
    User,
)

OWNER = "owner@tasks-delete.example.com"
MANAGER = "manager@tasks-delete.example.com"
EMPLOYEE = "employee@tasks-delete.example.com"
ACCOUNTANT = "accountant@tasks-delete.example.com"
OUTSIDER = "outsider@tasks-delete.example.com"


@pytest.fixture(autouse=True)
def _clean(app):
    yield
    with app.app_context():
        db.session.query(Notification).delete()
        db.session.query(ActivityLog).delete()
        db.session.query(TaskComment).delete()
        db.session.query(TaskHistory).delete()
        db.session.query(Task).delete()
        db.session.query(Membership).delete()
        db.session.query(Organization).delete()
        db.session.query(User).delete()
        db.session.commit()


def _login(client, email, password="correct horse battery"):
    return client.post("/api/v1/auth/login", json={"email": email, "password": password}).get_json()["data"]["csrf_token"]


def _register(client, email):
    client.post("/api/v1/auth/register", json={"name": email.split("@")[0], "email": email, "password": "correct horse battery"})


def _give_role(app, organization_id, email, role):
    with app.app_context():
        user = db.session.query(User).filter_by(email=email).one()
        membership = Membership(
            organization_id=uuid.UUID(organization_id), user_id=user.id, role=role, status=MembershipStatus.ACTIVE
        )
        db.session.add(membership)
        db.session.commit()
        return str(membership.id)


@pytest.fixture
def org(app, client):
    for email in (OWNER, MANAGER, EMPLOYEE, ACCOUNTANT, OUTSIDER):
        _register(client, email)
    csrf = _login(client, OWNER)
    org = client.post("/api/v1/organizations", json={"name": "Delete Org"}, headers={"X-CSRF-Token": csrf}).get_json()["data"]
    _give_role(app, org["id"], MANAGER, MembershipRole.MANAGER)
    employee_id = _give_role(app, org["id"], EMPLOYEE, MembershipRole.EMPLOYEE)
    _give_role(app, org["id"], ACCOUNTANT, MembershipRole.ACCOUNTANT)

    # A task with a comment, history (from assignment) and a notification.
    task = client.post(
        f"/api/v1/organizations/{org['id']}/tasks", json={"title": "Doomed task"}, headers={"X-CSRF-Token": csrf}
    ).get_json()["data"]
    client.patch(
        f"/api/v1/organizations/{org['id']}/tasks/{task['id']}/assign",
        json={"assignee_membership_id": employee_id},
        headers={"X-CSRF-Token": csrf},
    )
    client.post(
        f"/api/v1/organizations/{org['id']}/tasks/{task['id']}/comments",
        json={"body": "First comment"},
        headers={"X-CSRF-Token": csrf},
    )
    return {"id": org["id"], "task_id": task["id"]}


def _delete(client, csrf, org_id, task_id):
    return client.delete(f"/api/v1/organizations/{org_id}/tasks/{task_id}", headers={"X-CSRF-Token": csrf})


@pytest.mark.parametrize("email", [OWNER, MANAGER])
def test_owner_and_manager_can_delete_a_task_permanently(app, client, org, email):
    csrf = _login(client, email)
    with app.app_context():
        task_uuid = uuid.UUID(org["task_id"])
        assert db.session.query(TaskComment).filter_by(task_id=task_uuid).count() == 1
        assert db.session.query(TaskHistory).filter_by(task_id=task_uuid).count() >= 1
        assert db.session.query(Notification).filter_by(entity_type="task", entity_id=task_uuid).count() >= 1

    response = _delete(client, csrf, org["id"], org["task_id"])

    assert response.status_code == 200
    assert response.get_json()["message"] == "Task deleted"
    assert client.get(f"/api/v1/organizations/{org['id']}/tasks/{org['task_id']}").status_code == 404
    with app.app_context():
        assert db.session.get(Task, task_uuid) is None
        assert db.session.query(TaskComment).filter_by(task_id=task_uuid).count() == 0
        assert db.session.query(TaskHistory).filter_by(task_id=task_uuid).count() == 0
        assert db.session.query(Notification).filter_by(entity_type="task", entity_id=task_uuid).count() == 0
        # The audit trail survives, with a record of the deletion.
        deleted_entry = db.session.query(ActivityLog).filter_by(action="task_deleted", entity_id=task_uuid).one()
        assert deleted_entry.metadata_["title"] == "Doomed task"
        assert db.session.query(ActivityLog).filter_by(action="task_created", entity_id=task_uuid).count() == 1


@pytest.mark.parametrize("email", [EMPLOYEE, ACCOUNTANT])
def test_other_roles_cannot_delete_tasks(app, client, org, email):
    csrf = _login(client, email)

    response = _delete(client, csrf, org["id"], org["task_id"])

    assert response.status_code == 403
    with app.app_context():
        assert db.session.get(Task, uuid.UUID(org["task_id"])) is not None


def test_cannot_delete_a_task_in_another_organization(app, client, org):
    csrf = _login(client, OUTSIDER)
    other_org = client.post(
        "/api/v1/organizations", json={"name": "Other Org"}, headers={"X-CSRF-Token": csrf}
    ).get_json()["data"]

    # Outsider owns their own org; the task belongs to a different one.
    # Through their own org the task isn't found; through the task's org
    # they aren't a member - both 404, never revealing it exists.
    assert _delete(client, csrf, other_org["id"], org["task_id"]).status_code == 404
    assert _delete(client, csrf, org["id"], org["task_id"]).status_code == 404
    with app.app_context():
        assert db.session.get(Task, uuid.UUID(org["task_id"])) is not None


def test_delete_requires_csrf_token(app, client, org):
    _login(client, OWNER)

    response = client.delete(f"/api/v1/organizations/{org['id']}/tasks/{org['task_id']}")

    assert response.status_code == 403
    with app.app_context():
        assert db.session.get(Task, uuid.UUID(org["task_id"])) is not None


def test_deleting_a_missing_task_is_404(client, org):
    csrf = _login(client, OWNER)

    assert _delete(client, csrf, org["id"], str(uuid.uuid4())).status_code == 404
