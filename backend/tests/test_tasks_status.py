import uuid

import pytest

from app.extensions import db
from app.models import Membership, MembershipRole, MembershipStatus, Organization, Task, TaskHistory, TaskStatus, User


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


def _make_task(app, organization_id, creator_membership_id, status=TaskStatus.TODO, **kwargs):
    with app.app_context():
        task = Task(
            organization_id=uuid.UUID(organization_id),
            creator_membership_id=uuid.UUID(creator_membership_id),
            title=kwargs.pop("title", "Task"),
            status=status,
            **kwargs,
        )
        db.session.add(task)
        db.session.commit()
        return str(task.id)


def _set_status(client, csrf_token, org_id, task_id, status):
    return client.patch(
        f"/api/v1/organizations/{org_id}/tasks/{task_id}/status",
        json={"status": status},
        headers={"X-CSRF-Token": csrf_token},
    )


def test_unauthenticated_request_returns_401(client):
    response = client.patch(
        "/api/v1/organizations/00000000-0000-0000-0000-000000000000/tasks/"
        "00000000-0000-0000-0000-000000000000/status",
        json={"status": "in_progress"},
    )
    assert response.status_code == 401


@pytest.mark.parametrize(
    "from_status,to_status",
    [
        (TaskStatus.TODO, "in_progress"),
        (TaskStatus.IN_PROGRESS, "under_review"),
        (TaskStatus.UNDER_REVIEW, "completed"),
        (TaskStatus.UNDER_REVIEW, "in_progress"),
    ],
)
def test_owner_can_make_every_legal_transition(client, app, from_status, to_status):
    csrf_token = _register_and_login(client, f"owner-{from_status.value}-{to_status}@example.com")
    org = _create_org(client, csrf_token)
    owner_id = _membership_id(app, org["id"], f"owner-{from_status.value}-{to_status}@example.com")
    task_id = _make_task(app, org["id"], owner_id, status=from_status)

    response = _set_status(client, csrf_token, org["id"], task_id, to_status)

    assert response.status_code == 200
    assert response.get_json()["data"]["status"] == to_status


@pytest.mark.parametrize("from_status", [TaskStatus.TODO, TaskStatus.IN_PROGRESS, TaskStatus.UNDER_REVIEW])
def test_owner_can_cancel_any_non_terminal_task(client, app, from_status):
    csrf_token = _register_and_login(client, f"owner-cancel-{from_status.value}@example.com")
    org = _create_org(client, csrf_token)
    owner_id = _membership_id(app, org["id"], f"owner-cancel-{from_status.value}@example.com")
    task_id = _make_task(app, org["id"], owner_id, status=from_status)

    response = _set_status(client, csrf_token, org["id"], task_id, "cancelled")

    assert response.status_code == 200
    assert response.get_json()["data"]["status"] == "cancelled"


def test_manager_can_approve_a_task(client, app):
    csrf_token = _register_and_login(client, "owner-mgr@example.com")
    org = _create_org(client, csrf_token)
    owner_id = _membership_id(app, org["id"], "owner-mgr@example.com")
    task_id = _make_task(app, org["id"], owner_id, status=TaskStatus.UNDER_REVIEW)
    _register_and_login(client, "manager-status@example.com", name="Manager Status")
    _give_role(app, org["id"], "manager-status@example.com", MembershipRole.MANAGER)
    manager_csrf = _login(client, "manager-status@example.com")

    response = _set_status(client, manager_csrf, org["id"], task_id, "completed")

    assert response.status_code == 200


def test_assignee_can_start_their_own_task(client, app):
    csrf_token = _register_and_login(client, "owner2@example.com")
    org = _create_org(client, csrf_token)
    owner_id = _membership_id(app, org["id"], "owner2@example.com")
    _register_and_login(client, "employee2@example.com", name="Employee Two")
    employee_id = _give_role(app, org["id"], "employee2@example.com", MembershipRole.EMPLOYEE)
    task_id = _make_task(
        app, org["id"], owner_id, status=TaskStatus.TODO, assignee_membership_id=uuid.UUID(employee_id)
    )
    employee_csrf = _login(client, "employee2@example.com")

    response = _set_status(client, employee_csrf, org["id"], task_id, "in_progress")

    assert response.status_code == 200
    assert response.get_json()["data"]["status"] == "in_progress"


def test_assignee_can_submit_their_own_task_for_review(client, app):
    csrf_token = _register_and_login(client, "owner3@example.com")
    org = _create_org(client, csrf_token)
    owner_id = _membership_id(app, org["id"], "owner3@example.com")
    _register_and_login(client, "employee3@example.com", name="Employee Three")
    employee_id = _give_role(app, org["id"], "employee3@example.com", MembershipRole.EMPLOYEE)
    task_id = _make_task(
        app, org["id"], owner_id, status=TaskStatus.IN_PROGRESS, assignee_membership_id=uuid.UUID(employee_id)
    )
    employee_csrf = _login(client, "employee3@example.com")

    response = _set_status(client, employee_csrf, org["id"], task_id, "under_review")

    assert response.status_code == 200
    assert response.get_json()["data"]["status"] == "under_review"


def test_assignee_cannot_approve_their_own_task(client, app):
    csrf_token = _register_and_login(client, "owner4@example.com")
    org = _create_org(client, csrf_token)
    owner_id = _membership_id(app, org["id"], "owner4@example.com")
    _register_and_login(client, "employee4@example.com", name="Employee Four")
    employee_id = _give_role(app, org["id"], "employee4@example.com", MembershipRole.EMPLOYEE)
    task_id = _make_task(
        app, org["id"], owner_id, status=TaskStatus.UNDER_REVIEW, assignee_membership_id=uuid.UUID(employee_id)
    )
    employee_csrf = _login(client, "employee4@example.com")

    response = _set_status(client, employee_csrf, org["id"], task_id, "completed")

    assert response.status_code == 403


def test_assignee_cannot_return_their_own_task_for_revision(client, app):
    csrf_token = _register_and_login(client, "owner5@example.com")
    org = _create_org(client, csrf_token)
    owner_id = _membership_id(app, org["id"], "owner5@example.com")
    _register_and_login(client, "employee5@example.com", name="Employee Five")
    employee_id = _give_role(app, org["id"], "employee5@example.com", MembershipRole.EMPLOYEE)
    task_id = _make_task(
        app, org["id"], owner_id, status=TaskStatus.UNDER_REVIEW, assignee_membership_id=uuid.UUID(employee_id)
    )
    employee_csrf = _login(client, "employee5@example.com")

    response = _set_status(client, employee_csrf, org["id"], task_id, "in_progress")

    assert response.status_code == 403


def test_assignee_cannot_cancel_their_own_task(client, app):
    csrf_token = _register_and_login(client, "owner6@example.com")
    org = _create_org(client, csrf_token)
    owner_id = _membership_id(app, org["id"], "owner6@example.com")
    _register_and_login(client, "employee6@example.com", name="Employee Six")
    employee_id = _give_role(app, org["id"], "employee6@example.com", MembershipRole.EMPLOYEE)
    task_id = _make_task(
        app, org["id"], owner_id, status=TaskStatus.TODO, assignee_membership_id=uuid.UUID(employee_id)
    )
    employee_csrf = _login(client, "employee6@example.com")

    response = _set_status(client, employee_csrf, org["id"], task_id, "cancelled")

    assert response.status_code == 403


def test_employee_cannot_act_on_a_task_not_assigned_to_them(client, app):
    csrf_token = _register_and_login(client, "owner7@example.com")
    org = _create_org(client, csrf_token)
    owner_id = _membership_id(app, org["id"], "owner7@example.com")
    _register_and_login(client, "employee7a@example.com", name="Employee A")
    employee_a_id = _give_role(app, org["id"], "employee7a@example.com", MembershipRole.EMPLOYEE)
    _register_and_login(client, "employee7b@example.com", name="Employee B")
    _give_role(app, org["id"], "employee7b@example.com", MembershipRole.EMPLOYEE)
    task_id = _make_task(
        app, org["id"], owner_id, status=TaskStatus.TODO, assignee_membership_id=uuid.UUID(employee_a_id)
    )
    employee_b_csrf = _login(client, "employee7b@example.com")

    response = _set_status(client, employee_b_csrf, org["id"], task_id, "in_progress")

    assert response.status_code == 403


def test_employee_cannot_act_on_an_unassigned_task(client, app):
    csrf_token = _register_and_login(client, "owner8@example.com")
    org = _create_org(client, csrf_token)
    owner_id = _membership_id(app, org["id"], "owner8@example.com")
    _register_and_login(client, "employee8@example.com", name="Employee Eight")
    _give_role(app, org["id"], "employee8@example.com", MembershipRole.EMPLOYEE)
    task_id = _make_task(app, org["id"], owner_id, status=TaskStatus.TODO)
    employee_csrf = _login(client, "employee8@example.com")

    response = _set_status(client, employee_csrf, org["id"], task_id, "in_progress")

    assert response.status_code == 403


@pytest.mark.parametrize("illegal_status", ["under_review", "completed"])
def test_owner_cannot_skip_stages_from_todo(client, app, illegal_status):
    csrf_token = _register_and_login(client, f"owner-skip-{illegal_status}@example.com")
    org = _create_org(client, csrf_token)
    owner_id = _membership_id(app, org["id"], f"owner-skip-{illegal_status}@example.com")
    task_id = _make_task(app, org["id"], owner_id, status=TaskStatus.TODO)

    response = _set_status(client, csrf_token, org["id"], task_id, illegal_status)

    assert response.status_code == 422
    assert response.get_json()["error"]["code"] == "INVALID_STATUS_TRANSITION"


def test_owner_cannot_move_a_completed_task_anywhere(client, app):
    csrf_token = _register_and_login(client, "owner9@example.com")
    org = _create_org(client, csrf_token)
    owner_id = _membership_id(app, org["id"], "owner9@example.com")
    task_id = _make_task(app, org["id"], owner_id, status=TaskStatus.COMPLETED)

    response = _set_status(client, csrf_token, org["id"], task_id, "in_progress")

    assert response.status_code == 422
    assert response.get_json()["error"]["code"] == "INVALID_STATUS_TRANSITION"


def test_owner_cannot_move_a_cancelled_task_anywhere(client, app):
    csrf_token = _register_and_login(client, "owner10@example.com")
    org = _create_org(client, csrf_token)
    owner_id = _membership_id(app, org["id"], "owner10@example.com")
    task_id = _make_task(app, org["id"], owner_id, status=TaskStatus.CANCELLED)

    response = _set_status(client, csrf_token, org["id"], task_id, "to_do")

    assert response.status_code == 422
    assert response.get_json()["error"]["code"] == "INVALID_STATUS_TRANSITION"


def test_same_status_is_a_noop(client, app):
    csrf_token = _register_and_login(client, "owner11@example.com")
    org = _create_org(client, csrf_token)
    owner_id = _membership_id(app, org["id"], "owner11@example.com")
    task_id = _make_task(app, org["id"], owner_id, status=TaskStatus.TODO)

    response = _set_status(client, csrf_token, org["id"], task_id, "to_do")

    assert response.status_code == 200
    with app.app_context():
        assert db.session.query(TaskHistory).filter_by(task_id=uuid.UUID(task_id)).count() == 0


def test_non_assignee_same_status_request_still_gets_403_not_a_noop(client, app):
    """The idempotency shortcut must not let a non-assignee confirm a
    task's current status via a free 200 - the object-level reach
    check has to run first."""
    csrf_token = _register_and_login(client, "owner12@example.com")
    org = _create_org(client, csrf_token)
    owner_id = _membership_id(app, org["id"], "owner12@example.com")
    _register_and_login(client, "employee12@example.com", name="Employee Twelve")
    _give_role(app, org["id"], "employee12@example.com", MembershipRole.EMPLOYEE)
    task_id = _make_task(app, org["id"], owner_id, status=TaskStatus.TODO)
    employee_csrf = _login(client, "employee12@example.com")

    response = _set_status(client, employee_csrf, org["id"], task_id, "to_do")

    assert response.status_code == 403


def test_status_change_records_a_task_history_entry(client, app):
    csrf_token = _register_and_login(client, "owner13@example.com")
    org = _create_org(client, csrf_token)
    owner_id = _membership_id(app, org["id"], "owner13@example.com")
    task_id = _make_task(app, org["id"], owner_id, status=TaskStatus.TODO)

    response = _set_status(client, csrf_token, org["id"], task_id, "in_progress")
    assert response.status_code == 200

    with app.app_context():
        entries = db.session.query(TaskHistory).filter_by(task_id=uuid.UUID(task_id)).all()
        assert len(entries) == 1
        assert entries[0].event_type == "status_changed"
        assert entries[0].previous_value == "to_do"
        assert entries[0].new_value == "in_progress"
        assert str(entries[0].actor_membership_id) == owner_id


def test_status_update_without_csrf_returns_403(client, app):
    csrf_token = _register_and_login(client, "owner14@example.com")
    org = _create_org(client, csrf_token)
    owner_id = _membership_id(app, org["id"], "owner14@example.com")
    task_id = _make_task(app, org["id"], owner_id, status=TaskStatus.TODO)

    response = client.patch(
        f"/api/v1/organizations/{org['id']}/tasks/{task_id}/status", json={"status": "in_progress"}
    )

    assert response.status_code == 403


def test_status_update_nonexistent_task_returns_404(client):
    csrf_token = _register_and_login(client, "owner15@example.com")
    org = _create_org(client, csrf_token)

    response = _set_status(client, csrf_token, org["id"], str(uuid.uuid4()), "in_progress")

    assert response.status_code == 404


def test_status_update_cross_org_task_returns_404(client, app):
    owner_a_csrf = _register_and_login(client, "owner16a@example.com")
    org_a = _create_org(client, owner_a_csrf, name="Org A")
    owner_b_csrf = _register_and_login(client, "owner16b@example.com")
    org_b = _create_org(client, owner_b_csrf, name="Org B")
    owner_b_id = _membership_id(app, org_b["id"], "owner16b@example.com")
    task_in_org_b = _make_task(app, org_b["id"], owner_b_id, status=TaskStatus.TODO)
    owner_a_csrf = _login(client, "owner16a@example.com")

    response = _set_status(client, owner_a_csrf, org_a["id"], task_in_org_b, "in_progress")

    assert response.status_code == 404


def test_status_update_requires_the_field(client, app):
    csrf_token = _register_and_login(client, "owner17@example.com")
    org = _create_org(client, csrf_token)
    owner_id = _membership_id(app, org["id"], "owner17@example.com")
    task_id = _make_task(app, org["id"], owner_id, status=TaskStatus.TODO)

    response = client.patch(
        f"/api/v1/organizations/{org['id']}/tasks/{task_id}/status", json={}, headers={"X-CSRF-Token": csrf_token}
    )

    assert response.status_code == 422


def test_status_update_rejects_unknown_fields(client, app):
    csrf_token = _register_and_login(client, "owner18@example.com")
    org = _create_org(client, csrf_token)
    owner_id = _membership_id(app, org["id"], "owner18@example.com")
    task_id = _make_task(app, org["id"], owner_id, status=TaskStatus.TODO)

    response = client.patch(
        f"/api/v1/organizations/{org['id']}/tasks/{task_id}/status",
        json={"status": "in_progress", "assignee_membership_id": None},
        headers={"X-CSRF-Token": csrf_token},
    )

    assert response.status_code == 422


def test_status_update_rejects_an_unknown_status_value(client, app):
    csrf_token = _register_and_login(client, "owner19@example.com")
    org = _create_org(client, csrf_token)
    owner_id = _membership_id(app, org["id"], "owner19@example.com")
    task_id = _make_task(app, org["id"], owner_id, status=TaskStatus.TODO)

    response = client.patch(
        f"/api/v1/organizations/{org['id']}/tasks/{task_id}/status",
        json={"status": "archived"},
        headers={"X-CSRF-Token": csrf_token},
    )

    assert response.status_code == 422
