import uuid
from datetime import date, datetime, timezone

import pytest

from app.extensions import db
from app.models import Department, Membership, MembershipRole, MembershipStatus, Organization, Task, TaskStatus, User


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


def _make_department(app, organization_id, name="Sales"):
    with app.app_context():
        department = Department(organization_id=uuid.UUID(organization_id), name=name)
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


def _list_tasks(client, org_id, **params):
    return client.get(f"/api/v1/organizations/{org_id}/tasks", query_string=params)


def test_unauthenticated_request_returns_401(client):
    response = client.get("/api/v1/organizations/00000000-0000-0000-0000-000000000000/tasks")
    assert response.status_code == 401


def test_non_member_gets_404(client):
    csrf_token = _register_and_login(client, "owner@example.com")
    org = _create_org(client, csrf_token)
    _register_and_login(client, "outsider@example.com")

    response = _list_tasks(client, org["id"])

    assert response.status_code == 404


def test_owner_sees_every_task_in_the_org(client, app):
    csrf_token = _register_and_login(client, "owner2@example.com")
    org = _create_org(client, csrf_token)
    _register_and_login(client, "employee2@example.com", name="Employee Two")
    employee_id = _give_role(app, org["id"], "employee2@example.com", MembershipRole.EMPLOYEE)
    _login(client, "owner2@example.com")

    with app.app_context():
        user = db.session.query(User).filter_by(email="owner2@example.com").one()
        membership = db.session.query(Membership).filter_by(user_id=user.id, organization_id=org["id"]).one()
        owner_membership_id = str(membership.id)

    _make_task(app, org["id"], owner_membership_id, title="Task A")
    _make_task(app, org["id"], owner_membership_id, title="Task B", assignee_membership_id=uuid.UUID(employee_id))

    response = _list_tasks(client, org["id"])

    assert response.status_code == 200
    body = response.get_json()
    assert len(body["data"]) == 2
    assert body["meta"]["total"] == 2


def test_manager_sees_every_task_in_the_org(client, app):
    csrf_token = _register_and_login(client, "owner-mgr@example.com")
    org = _create_org(client, csrf_token)
    with app.app_context():
        user = db.session.query(User).filter_by(email="owner-mgr@example.com").one()
        membership = db.session.query(Membership).filter_by(user_id=user.id, organization_id=org["id"]).one()
        owner_membership_id = str(membership.id)
    _register_and_login(client, "manager-list@example.com", name="Manager List")
    _give_role(app, org["id"], "manager-list@example.com", MembershipRole.MANAGER)

    _make_task(app, org["id"], owner_membership_id, title="Task A")
    _make_task(app, org["id"], owner_membership_id, title="Task B")

    manager_csrf = _login(client, "manager-list@example.com")

    response = _list_tasks(client, org["id"])

    assert response.status_code == 200
    assert response.get_json()["meta"]["total"] == 2


def test_employee_only_sees_tasks_assigned_to_them(client, app):
    csrf_token = _register_and_login(client, "owner3@example.com")
    org = _create_org(client, csrf_token)
    _register_and_login(client, "employee3a@example.com", name="Employee A")
    employee_a_id = _give_role(app, org["id"], "employee3a@example.com", MembershipRole.EMPLOYEE)
    _register_and_login(client, "employee3b@example.com", name="Employee B")
    employee_b_id = _give_role(app, org["id"], "employee3b@example.com", MembershipRole.EMPLOYEE)

    with app.app_context():
        owner_user = db.session.query(User).filter_by(email="owner3@example.com").one()
        owner_membership = (
            db.session.query(Membership).filter_by(user_id=owner_user.id, organization_id=org["id"]).one()
        )
        owner_membership_id = str(owner_membership.id)

    _make_task(app, org["id"], owner_membership_id, title="Assigned to A", assignee_membership_id=uuid.UUID(employee_a_id))
    _make_task(app, org["id"], owner_membership_id, title="Assigned to B", assignee_membership_id=uuid.UUID(employee_b_id))
    _make_task(app, org["id"], owner_membership_id, title="Unassigned")

    employee_a_csrf = _login(client, "employee3a@example.com")

    response = _list_tasks(client, org["id"])

    assert response.status_code == 200
    body = response.get_json()
    assert [t["title"] for t in body["data"]] == ["Assigned to A"]


def test_employee_cannot_see_another_employees_tasks_via_assignee_filter(client, app):
    """The assigned-scope filter is forced server-side, regardless of
    any assignee_membership_id the caller themselves requests."""
    csrf_token = _register_and_login(client, "owner4@example.com")
    org = _create_org(client, csrf_token)
    _register_and_login(client, "employee4a@example.com", name="Employee A")
    employee_a_id = _give_role(app, org["id"], "employee4a@example.com", MembershipRole.EMPLOYEE)
    _register_and_login(client, "employee4b@example.com", name="Employee B")
    employee_b_id = _give_role(app, org["id"], "employee4b@example.com", MembershipRole.EMPLOYEE)

    with app.app_context():
        owner_user = db.session.query(User).filter_by(email="owner4@example.com").one()
        owner_membership = (
            db.session.query(Membership).filter_by(user_id=owner_user.id, organization_id=org["id"]).one()
        )
        owner_membership_id = str(owner_membership.id)

    _make_task(app, org["id"], owner_membership_id, title="Assigned to B", assignee_membership_id=uuid.UUID(employee_b_id))

    employee_a_csrf = _login(client, "employee4a@example.com")

    response = _list_tasks(client, org["id"], assignee_membership_id=employee_b_id)

    assert response.status_code == 200
    assert response.get_json()["data"] == []


def test_filter_by_status(client, app):
    csrf_token = _register_and_login(client, "owner5@example.com")
    org = _create_org(client, csrf_token)
    with app.app_context():
        user = db.session.query(User).filter_by(email="owner5@example.com").one()
        membership = db.session.query(Membership).filter_by(user_id=user.id, organization_id=org["id"]).one()
        owner_membership_id = str(membership.id)

    _make_task(app, org["id"], owner_membership_id, title="Todo task")
    completed_id = _make_task(app, org["id"], owner_membership_id, title="Done task")
    with app.app_context():
        from app.models import TaskStatus

        task = db.session.get(Task, completed_id)
        task.status = TaskStatus.COMPLETED
        db.session.commit()

    response = _list_tasks(client, org["id"], status="completed")

    assert response.status_code == 200
    body = response.get_json()["data"]
    assert len(body) == 1
    assert body[0]["title"] == "Done task"


def test_filter_by_department(client, app):
    csrf_token = _register_and_login(client, "owner6@example.com")
    org = _create_org(client, csrf_token)
    department_id = _make_department(app, org["id"])
    with app.app_context():
        user = db.session.query(User).filter_by(email="owner6@example.com").one()
        membership = db.session.query(Membership).filter_by(user_id=user.id, organization_id=org["id"]).one()
        owner_membership_id = str(membership.id)

    _make_task(app, org["id"], owner_membership_id, title="In Sales", department_id=uuid.UUID(department_id))
    _make_task(app, org["id"], owner_membership_id, title="No department")

    response = _list_tasks(client, org["id"], department_id=department_id)

    assert response.status_code == 200
    body = response.get_json()["data"]
    assert len(body) == 1
    assert body[0]["title"] == "In Sales"


def test_filter_by_due_date_range(client, app):
    csrf_token = _register_and_login(client, "owner7@example.com")
    org = _create_org(client, csrf_token)
    with app.app_context():
        user = db.session.query(User).filter_by(email="owner7@example.com").one()
        membership = db.session.query(Membership).filter_by(user_id=user.id, organization_id=org["id"]).one()
        owner_membership_id = str(membership.id)

    from datetime import date

    _make_task(app, org["id"], owner_membership_id, title="Early", due_date=date(2026, 1, 1))
    _make_task(app, org["id"], owner_membership_id, title="Mid", due_date=date(2026, 6, 1))
    _make_task(app, org["id"], owner_membership_id, title="Late", due_date=date(2026, 12, 1))

    response = _list_tasks(client, org["id"], due_date_from="2026-02-01", due_date_to="2026-07-01")

    assert response.status_code == 200
    body = response.get_json()["data"]
    assert [t["title"] for t in body] == ["Mid"]


def test_pagination_meta(client, app):
    csrf_token = _register_and_login(client, "owner8@example.com")
    org = _create_org(client, csrf_token)
    with app.app_context():
        user = db.session.query(User).filter_by(email="owner8@example.com").one()
        membership = db.session.query(Membership).filter_by(user_id=user.id, organization_id=org["id"]).one()
        owner_membership_id = str(membership.id)

    for i in range(3):
        _make_task(app, org["id"], owner_membership_id, title=f"Task {i}")

    response = _list_tasks(client, org["id"], per_page=2, page=1)

    assert response.status_code == 200
    body = response.get_json()
    assert len(body["data"]) == 2
    assert body["meta"] == {"page": 1, "per_page": 2, "total": 3, "total_pages": 2}


def test_rejects_an_inverted_due_date_range(client):
    csrf_token = _register_and_login(client, "owner9@example.com")
    org = _create_org(client, csrf_token)

    response = _list_tasks(client, org["id"], due_date_from="2026-06-01", due_date_to="2026-01-01")

    assert response.status_code == 422


def test_list_marks_a_past_due_non_terminal_task_as_overdue(client, app):
    """FD-033. due_date is a day safely in the past in every timezone,
    so this doesn't need to pin the clock - it only needs the task to
    actually have a stored due_date that's passed."""
    csrf_token = _register_and_login(client, "owner10@example.com")
    org = _create_org(client, csrf_token)
    with app.app_context():
        user = db.session.query(User).filter_by(email="owner10@example.com").one()
        membership = db.session.query(Membership).filter_by(user_id=user.id, organization_id=org["id"]).one()
        owner_membership_id = str(membership.id)

    _make_task(app, org["id"], owner_membership_id, title="Overdue", due_date=date(2020, 1, 1))
    _make_task(app, org["id"], owner_membership_id, title="No due date")

    response = _list_tasks(client, org["id"])

    assert response.status_code == 200
    by_title = {t["title"]: t["is_overdue"] for t in response.get_json()["data"]}
    assert by_title == {"Overdue": True, "No due date": False}


def test_list_never_marks_a_completed_or_cancelled_task_as_overdue(client, app):
    csrf_token = _register_and_login(client, "owner11@example.com")
    org = _create_org(client, csrf_token)
    with app.app_context():
        user = db.session.query(User).filter_by(email="owner11@example.com").one()
        membership = db.session.query(Membership).filter_by(user_id=user.id, organization_id=org["id"]).one()
        owner_membership_id = str(membership.id)

    _make_task(
        app, org["id"], owner_membership_id, title="Done", due_date=date(2020, 1, 1), status=TaskStatus.COMPLETED
    )
    _make_task(
        app, org["id"], owner_membership_id, title="Scrapped", due_date=date(2020, 1, 1), status=TaskStatus.CANCELLED
    )

    response = _list_tasks(client, org["id"])

    assert response.status_code == 200
    by_title = {t["title"]: t["is_overdue"] for t in response.get_json()["data"]}
    assert by_title == {"Done": False, "Scrapped": False}


def test_overdue_detection_uses_the_organizations_own_timezone_not_utc(client, app, monkeypatch):
    """At the pinned instant 2026-11-11T02:00:00Z, America/New_York
    (UTC-5, standard time) is still on 2026-11-10 while UTC itself has
    already rolled over to 2026-11-11. A due_date of 2026-11-10 is
    therefore still "today" - not overdue - for this organization, and
    would be wrongly flagged overdue by any implementation that
    compared against UTC's own date instead of the organization's.
    Freezes app.tasks.service's own `datetime.now()` (no new test
    dependency) so this is deterministic regardless of when the suite
    actually runs."""
    import app.tasks.service as tasks_service

    class _FrozenDateTime(datetime):
        FIXED = datetime(2026, 11, 11, 2, 0, tzinfo=timezone.utc)

        @classmethod
        def now(cls, tz=None):
            return cls.FIXED.astimezone(tz) if tz is not None else cls.FIXED

    monkeypatch.setattr(tasks_service, "datetime", _FrozenDateTime)

    csrf_token = _register_and_login(client, "owner12@example.com")
    org = client.post(
        "/api/v1/organizations",
        json={"name": "NY Org", "timezone": "America/New_York"},
        headers={"X-CSRF-Token": csrf_token},
    ).get_json()["data"]
    with app.app_context():
        user = db.session.query(User).filter_by(email="owner12@example.com").one()
        membership = db.session.query(Membership).filter_by(user_id=user.id, organization_id=org["id"]).one()
        owner_membership_id = str(membership.id)

    _make_task(app, org["id"], owner_membership_id, title="Due today in NY", due_date=date(2026, 11, 10))

    response = _list_tasks(client, org["id"])

    assert response.status_code == 200
    assert response.get_json()["data"][0]["is_overdue"] is False
