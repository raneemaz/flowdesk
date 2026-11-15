import uuid

import pytest

from app.extensions import db
from app.models import (
    Department,
    DepartmentStatus,
    Membership,
    MembershipRole,
    MembershipStatus,
    Organization,
    Task,
    TaskHistory,
    User,
)


@pytest.fixture(autouse=True)
def _clean(app):
    yield
    with app.app_context():
        db.session.query(TaskHistory).delete()
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


def _make_department(app, organization_id, name="Sales", status=DepartmentStatus.ACTIVE):
    with app.app_context():
        department = Department(organization_id=uuid.UUID(organization_id), name=name, status=status)
        db.session.add(department)
        db.session.commit()
        return str(department.id)


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


def _patch_task(client, csrf_token, org_id, task_id, **body):
    return client.patch(
        f"/api/v1/organizations/{org_id}/tasks/{task_id}", json=body, headers={"X-CSRF-Token": csrf_token}
    )


def test_unauthenticated_request_returns_401(client):
    response = client.patch(
        "/api/v1/organizations/00000000-0000-0000-0000-000000000000/tasks/"
        "00000000-0000-0000-0000-000000000000",
        json={"title": "New title"},
    )
    assert response.status_code == 401


def test_owner_can_update_the_title(client, app):
    csrf_token = _register_and_login(client, "owner@example.com")
    org = _create_org(client, csrf_token)
    owner_id = _membership_id(app, org["id"], "owner@example.com")
    task_id = _make_task(app, org["id"], owner_id, title="Old title")

    response = _patch_task(client, csrf_token, org["id"], task_id, title="New title")

    assert response.status_code == 200
    assert response.get_json()["data"]["title"] == "New title"


def test_owner_can_update_multiple_fields_at_once(client, app):
    csrf_token = _register_and_login(client, "owner2@example.com")
    org = _create_org(client, csrf_token)
    owner_id = _membership_id(app, org["id"], "owner2@example.com")
    task_id = _make_task(app, org["id"], owner_id)

    response = _patch_task(
        client, csrf_token, org["id"], task_id, priority="urgent", description="Updated", estimated_hours="3.5"
    )

    assert response.status_code == 200
    body = response.get_json()["data"]
    assert body["priority"] == "urgent"
    assert body["description"] == "Updated"
    assert body["estimated_hours"] in ("3.5", "3.50")


def test_manager_can_update_a_task(client, app):
    csrf_token = _register_and_login(client, "owner3@example.com")
    org = _create_org(client, csrf_token)
    owner_id = _membership_id(app, org["id"], "owner3@example.com")
    task_id = _make_task(app, org["id"], owner_id)
    _register_and_login(client, "manager3@example.com", name="Manager Three")
    _give_role(app, org["id"], "manager3@example.com", MembershipRole.MANAGER)
    manager_csrf = _login(client, "manager3@example.com")

    response = _patch_task(client, manager_csrf, org["id"], task_id, title="Manager edit")

    assert response.status_code == 200


@pytest.mark.parametrize("role", [MembershipRole.EMPLOYEE, MembershipRole.ACCOUNTANT, MembershipRole.CUSTOMER_SUPPORT])
def test_non_manager_roles_cannot_edit_a_task(client, app, role):
    csrf_token = _register_and_login(client, f"owner-{role.value}@example.com")
    org = _create_org(client, csrf_token)
    owner_id = _membership_id(app, org["id"], f"owner-{role.value}@example.com")
    task_id = _make_task(app, org["id"], owner_id)
    other_email = f"{role.value}@example.com"
    _register_and_login(client, other_email, name="Other Role")
    _give_role(app, org["id"], other_email, role)
    other_csrf = _login(client, other_email)

    response = _patch_task(client, other_csrf, org["id"], task_id, title="Hacked")

    assert response.status_code == 403


def test_employee_cannot_edit_even_their_own_assigned_task(client, app):
    """Editing is gated by TASK_CREATE_ASSIGN (Owner/Manager only),
    not TASK_VIEW_UPDATE's assigned scope - confirms this is a
    different capability from status progression (FD-028)."""
    csrf_token = _register_and_login(client, "owner4@example.com")
    org = _create_org(client, csrf_token)
    owner_id = _membership_id(app, org["id"], "owner4@example.com")
    _register_and_login(client, "employee4@example.com", name="Employee Four")
    employee_id = _give_role(app, org["id"], "employee4@example.com", MembershipRole.EMPLOYEE)
    task_id = _make_task(app, org["id"], owner_id, assignee_membership_id=uuid.UUID(employee_id))
    employee_csrf = _login(client, "employee4@example.com")

    response = _patch_task(client, employee_csrf, org["id"], task_id, title="Self edit")

    assert response.status_code == 403


def test_update_without_csrf_returns_403(client, app):
    csrf_token = _register_and_login(client, "owner5@example.com")
    org = _create_org(client, csrf_token)
    owner_id = _membership_id(app, org["id"], "owner5@example.com")
    task_id = _make_task(app, org["id"], owner_id)

    response = client.patch(f"/api/v1/organizations/{org['id']}/tasks/{task_id}", json={"title": "No csrf"})

    assert response.status_code == 403


def test_update_nonexistent_task_returns_404(client):
    csrf_token = _register_and_login(client, "owner6@example.com")
    org = _create_org(client, csrf_token)

    response = _patch_task(client, csrf_token, org["id"], str(uuid.uuid4()), title="Nope")

    assert response.status_code == 404


def test_update_cross_org_task_returns_404(client, app):
    owner_a_csrf = _register_and_login(client, "owner7a@example.com")
    org_a = _create_org(client, owner_a_csrf, name="Org A")
    owner_b_csrf = _register_and_login(client, "owner7b@example.com")
    org_b = _create_org(client, owner_b_csrf, name="Org B")
    owner_b_id = _membership_id(app, org_b["id"], "owner7b@example.com")
    task_in_org_b = _make_task(app, org_b["id"], owner_b_id)
    owner_a_csrf = _login(client, "owner7a@example.com")

    response = _patch_task(client, owner_a_csrf, org_a["id"], task_in_org_b, title="Nope")

    assert response.status_code == 404


def test_update_rejects_a_blank_title(client, app):
    csrf_token = _register_and_login(client, "owner8@example.com")
    org = _create_org(client, csrf_token)
    owner_id = _membership_id(app, org["id"], "owner8@example.com")
    task_id = _make_task(app, org["id"], owner_id)

    response = _patch_task(client, csrf_token, org["id"], task_id, title="   ")

    assert response.status_code == 422


def test_update_rejects_explicit_null_title(client, app):
    csrf_token = _register_and_login(client, "owner9@example.com")
    org = _create_org(client, csrf_token)
    owner_id = _membership_id(app, org["id"], "owner9@example.com")
    task_id = _make_task(app, org["id"], owner_id)

    response = _patch_task(client, csrf_token, org["id"], task_id, title=None)

    assert response.status_code == 422


def test_update_rejects_explicit_null_priority(client, app):
    csrf_token = _register_and_login(client, "owner10@example.com")
    org = _create_org(client, csrf_token)
    owner_id = _membership_id(app, org["id"], "owner10@example.com")
    task_id = _make_task(app, org["id"], owner_id)

    response = _patch_task(client, csrf_token, org["id"], task_id, priority=None)

    assert response.status_code == 422


def test_update_can_clear_clearable_fields(client, app):
    csrf_token = _register_and_login(client, "owner11@example.com")
    org = _create_org(client, csrf_token)
    owner_id = _membership_id(app, org["id"], "owner11@example.com")
    department_id = _make_department(app, org["id"])
    from datetime import date

    task_id = _make_task(
        app,
        org["id"],
        owner_id,
        description="Something",
        department_id=uuid.UUID(department_id),
        start_date=date(2026, 1, 1),
        due_date=date(2026, 1, 10),
        estimated_hours="4.0",
    )

    response = _patch_task(
        client,
        csrf_token,
        org["id"],
        task_id,
        description=None,
        department_id=None,
        start_date=None,
        due_date=None,
        estimated_hours=None,
    )

    assert response.status_code == 200
    body = response.get_json()["data"]
    assert body["description"] is None
    assert body["department_id"] is None
    assert body["start_date"] is None
    assert body["due_date"] is None
    assert body["estimated_hours"] is None


def test_update_rejects_an_unknown_department_id(client, app):
    csrf_token = _register_and_login(client, "owner12@example.com")
    org = _create_org(client, csrf_token)
    owner_id = _membership_id(app, org["id"], "owner12@example.com")
    task_id = _make_task(app, org["id"], owner_id)

    response = _patch_task(client, csrf_token, org["id"], task_id, department_id=str(uuid.uuid4()))

    assert response.status_code == 422
    assert response.get_json()["error"]["code"] == "INVALID_DEPARTMENT"


def test_update_rejects_a_cross_org_department_id(client, app):
    owner_a_csrf = _register_and_login(client, "owner13a@example.com")
    org_a = _create_org(client, owner_a_csrf, name="Org A")
    owner_b_csrf = _register_and_login(client, "owner13b@example.com")
    org_b = _create_org(client, owner_b_csrf, name="Org B")
    foreign_department_id = _make_department(app, org_b["id"])
    owner_a_id = _membership_id(app, org_a["id"], "owner13a@example.com")
    task_id = _make_task(app, org_a["id"], owner_a_id)
    owner_a_csrf = _login(client, "owner13a@example.com")

    response = _patch_task(client, owner_a_csrf, org_a["id"], task_id, department_id=foreign_department_id)

    assert response.status_code == 422
    assert response.get_json()["error"]["code"] == "INVALID_DEPARTMENT"


def test_update_rejects_an_inactive_department_id(client, app):
    csrf_token = _register_and_login(client, "owner14@example.com")
    org = _create_org(client, csrf_token)
    owner_id = _membership_id(app, org["id"], "owner14@example.com")
    inactive_department_id = _make_department(app, org["id"], status=DepartmentStatus.INACTIVE)
    task_id = _make_task(app, org["id"], owner_id)

    response = _patch_task(client, csrf_token, org["id"], task_id, department_id=inactive_department_id)

    assert response.status_code == 422
    assert response.get_json()["error"]["code"] == "INVALID_DEPARTMENT"


def test_update_rejects_due_date_before_start_date_within_same_request(client, app):
    csrf_token = _register_and_login(client, "owner15@example.com")
    org = _create_org(client, csrf_token)
    owner_id = _membership_id(app, org["id"], "owner15@example.com")
    task_id = _make_task(app, org["id"], owner_id)

    response = _patch_task(
        client, csrf_token, org["id"], task_id, start_date="2026-06-01", due_date="2026-01-01"
    )

    assert response.status_code == 422


def test_update_rejects_due_date_before_the_existing_start_date(client, app):
    """Merged-state check: only due_date is in this request, but the
    task's existing (unchanged) start_date makes the result invalid."""
    csrf_token = _register_and_login(client, "owner16@example.com")
    org = _create_org(client, csrf_token)
    owner_id = _membership_id(app, org["id"], "owner16@example.com")
    from datetime import date

    task_id = _make_task(app, org["id"], owner_id, start_date=date(2026, 6, 1))

    response = _patch_task(client, csrf_token, org["id"], task_id, due_date="2026-01-01")

    assert response.status_code == 422
    assert response.get_json()["error"]["code"] == "INVALID_DATE_RANGE"


def test_update_rejects_start_date_after_the_existing_due_date(client, app):
    """Merged-state check, the other direction: only start_date is in
    this request, but the task's existing due_date makes it invalid."""
    csrf_token = _register_and_login(client, "owner17@example.com")
    org = _create_org(client, csrf_token)
    owner_id = _membership_id(app, org["id"], "owner17@example.com")
    from datetime import date

    task_id = _make_task(app, org["id"], owner_id, due_date=date(2026, 1, 1))

    response = _patch_task(client, csrf_token, org["id"], task_id, start_date="2026-06-01")

    assert response.status_code == 422
    assert response.get_json()["error"]["code"] == "INVALID_DATE_RANGE"


def test_update_rejects_assignee_membership_id_field(client, app):
    csrf_token = _register_and_login(client, "owner18@example.com")
    org = _create_org(client, csrf_token)
    owner_id = _membership_id(app, org["id"], "owner18@example.com")
    task_id = _make_task(app, org["id"], owner_id)

    response = _patch_task(client, csrf_token, org["id"], task_id, assignee_membership_id=None)

    assert response.status_code == 422


def test_update_rejects_status_field(client, app):
    csrf_token = _register_and_login(client, "owner19@example.com")
    org = _create_org(client, csrf_token)
    owner_id = _membership_id(app, org["id"], "owner19@example.com")
    task_id = _make_task(app, org["id"], owner_id)

    response = _patch_task(client, csrf_token, org["id"], task_id, status="completed")

    assert response.status_code == 422


def test_update_records_history_for_each_changed_field(client, app):
    csrf_token = _register_and_login(client, "owner20@example.com")
    org = _create_org(client, csrf_token)
    owner_id = _membership_id(app, org["id"], "owner20@example.com")
    task_id = _make_task(app, org["id"], owner_id, title="Old title")

    response = _patch_task(client, csrf_token, org["id"], task_id, title="New title", priority="high")
    assert response.status_code == 200

    with app.app_context():
        entries = {
            e.event_type: e for e in db.session.query(TaskHistory).filter_by(task_id=uuid.UUID(task_id)).all()
        }
        assert set(entries.keys()) == {"title_changed", "priority_changed"}
        assert entries["title_changed"].previous_value == "Old title"
        assert entries["title_changed"].new_value == "New title"
        assert entries["priority_changed"].previous_value == "medium"
        assert entries["priority_changed"].new_value == "high"
        assert str(entries["title_changed"].actor_membership_id) == owner_id


def test_update_does_not_record_history_for_an_unchanged_field(client, app):
    csrf_token = _register_and_login(client, "owner21@example.com")
    org = _create_org(client, csrf_token)
    owner_id = _membership_id(app, org["id"], "owner21@example.com")
    task_id = _make_task(app, org["id"], owner_id, title="Same title", priority="high")

    response = _patch_task(client, csrf_token, org["id"], task_id, title="Same title", priority="urgent")
    assert response.status_code == 200

    with app.app_context():
        entries = db.session.query(TaskHistory).filter_by(task_id=uuid.UUID(task_id)).all()
        assert len(entries) == 1
        assert entries[0].event_type == "priority_changed"


def test_update_with_no_actual_changes_is_a_noop(client, app):
    csrf_token = _register_and_login(client, "owner22@example.com")
    org = _create_org(client, csrf_token)
    owner_id = _membership_id(app, org["id"], "owner22@example.com")
    task_id = _make_task(app, org["id"], owner_id, title="Same title")

    response = _patch_task(client, csrf_token, org["id"], task_id, title="Same title")

    assert response.status_code == 200
    with app.app_context():
        assert db.session.query(TaskHistory).filter_by(task_id=uuid.UUID(task_id)).count() == 0


def test_update_rejects_unknown_fields(client, app):
    csrf_token = _register_and_login(client, "owner23@example.com")
    org = _create_org(client, csrf_token)
    owner_id = _membership_id(app, org["id"], "owner23@example.com")
    task_id = _make_task(app, org["id"], owner_id)

    response = _patch_task(client, csrf_token, org["id"], task_id, creator_membership_id=str(uuid.uuid4()))

    assert response.status_code == 422
