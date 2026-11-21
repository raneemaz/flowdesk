"""FD-062: `get_overview_metrics`, `get_department_analytics`, and
`get_employee_performance` (app.analytics.service) are three
INDEPENDENT queries, each written against the same underlying
Task/TaskHistory/CustomerRequest/EmployeeProfile rows but summed a
different way (org-wide, per-department, per-employee). Every module's
own unit tests already prove each one is correct in isolation, with
its own purpose-built fixture data. What they cannot prove is that the
three views of the SAME real data - built via real HTTP routes, not a
fixture shaped to make the arithmetic convenient - actually add up to
each other: the department total should equal the sum of its own
employees' numbers plus the unassigned bucket, and the org-wide
overview should equal the sum across every department.

Driven entirely through real HTTP routes via the Flask test client,
including the real invitation/accept flow (FD-016), same convention as
test_full_workflow.py."""

import re
from datetime import datetime, timedelta, timezone

from app.email import client as email_client
from app.extensions import db
from app.models import (
    ActivityLog,
    AIReport,
    Customer,
    CustomerRequest,
    Department,
    EmployeeProfile,
    Invitation,
    Invoice,
    InvoiceLineItem,
    Membership,
    Notification,
    Organization,
    Payment,
    Task,
    TaskHistory,
    User,
)

import pytest


@pytest.fixture(autouse=True)
def _clean(app):
    yield
    with app.app_context():
        db.session.query(AIReport).delete()
        db.session.query(Notification).delete()
        db.session.query(ActivityLog).delete()
        db.session.query(Payment).delete()
        db.session.query(InvoiceLineItem).delete()
        db.session.query(Invoice).delete()
        db.session.query(TaskHistory).delete()
        db.session.query(Task).delete()
        db.session.query(CustomerRequest).delete()
        db.session.query(Customer).delete()
        db.session.query(EmployeeProfile).delete()
        db.session.query(Department).delete()
        db.session.query(Invitation).delete()
        db.session.query(Membership).delete()
        db.session.query(Organization).delete()
        db.session.query(User).delete()
        db.session.commit()


@pytest.fixture
def sent_emails(monkeypatch):
    captured = []

    def _fake_send_email(*, to, subject, body):
        captured.append({"to": to, "subject": subject, "body": body})

    monkeypatch.setattr(email_client, "send_email", _fake_send_email)
    return captured


def _login(client, email, password="correct horse battery"):
    return client.post("/api/v1/auth/login", json={"email": email, "password": password}).get_json()["data"][
        "csrf_token"
    ]


def _register_and_login(client, email, name="Test User", password="correct horse battery"):
    client.post("/api/v1/auth/register", json={"name": name, "email": email, "password": password})
    return _login(client, email, password)


def _create_org(client, csrf_token, name="FlowDesk Analytics Co"):
    return client.post("/api/v1/organizations", json={"name": name}, headers={"X-CSRF-Token": csrf_token}).get_json()[
        "data"
    ]


def _invite_and_accept(client, inviter_email, org_id, sent_emails, email, role, name):
    """Same real HTTP invitation+accept round trip as
    test_full_workflow.py's own helper of the same name - re-logs in as
    `inviter_email` right before posting, rather than trusting a
    csrf_token captured earlier, since the invitee's own
    register/login call below it would otherwise have left the shared
    test client's session pointed at the wrong actor."""
    inviter_csrf = _login(client, inviter_email)
    client.post(
        f"/api/v1/organizations/{org_id}/invitations",
        json={"email": email, "role": role},
        headers={"X-CSRF-Token": inviter_csrf},
    )
    token_match = re.search(r"token=([\w\-\.]+)", sent_emails[-1]["body"])
    assert token_match, f"no invitation token found in the sent email: {sent_emails[-1]['body']!r}"
    token = token_match.group(1)

    invitee_csrf = _register_and_login(client, email, name=name)
    accept_response = client.post(
        "/api/v1/invitations/accept", json={"token": token}, headers={"X-CSRF-Token": invitee_csrf}
    )
    assert accept_response.status_code == 200, accept_response.get_json()
    return invitee_csrf


def _membership_id(app, org_id, email):
    with app.app_context():
        import uuid as uuid_module

        user = db.session.query(User).filter_by(email=email.lower()).one()
        membership = (
            db.session.query(Membership)
            .filter_by(organization_id=uuid_module.UUID(org_id), user_id=user.id)
            .one()
        )
        return str(membership.id)


OWNER = "owner@flowdesk-analytics.example.com"
EMPLOYEE_1 = "employee1@flowdesk-analytics.example.com"
EMPLOYEE_2 = "employee2@flowdesk-analytics.example.com"

# UTC, not the OS's own local date - see test_full_workflow.py's own
# comment on the identical `TODAY` constant for why.
TODAY = datetime.now(timezone.utc).date()
TODAY_ISO = TODAY.isoformat()
YESTERDAY_ISO = (TODAY - timedelta(days=1)).isoformat()
NEXT_YEAR_ISO = (TODAY + timedelta(days=365)).isoformat()


def test_overview_department_and_employee_analytics_reconcile_against_each_other(client, app, sent_emails):
    owner_csrf = _register_and_login(client, OWNER, name="Owner")
    org = _create_org(client, owner_csrf)
    org_id = org["id"]

    _invite_and_accept(client, OWNER, org_id, sent_emails, EMPLOYEE_1, "employee", "Employee One")
    _invite_and_accept(client, OWNER, org_id, sent_emails, EMPLOYEE_2, "employee", "Employee Two")
    employee_1_id = _membership_id(app, org_id, EMPLOYEE_1)
    employee_2_id = _membership_id(app, org_id, EMPLOYEE_2)

    # --- Only Employee One belongs to a department ----------------------
    owner_csrf = _login(client, OWNER)
    department = client.post(
        f"/api/v1/organizations/{org_id}/departments",
        json={"name": "Engineering"},
        headers={"X-CSRF-Token": owner_csrf},
    ).get_json()["data"]
    client.patch(
        f"/api/v1/organizations/{org_id}/employees/{employee_1_id}",
        json={"department_id": department["id"]},
        headers={"X-CSRF-Token": owner_csrf},
    )

    # --- Task 1: Engineering, Employee One, overdue, still open --------
    task_1 = client.post(
        f"/api/v1/organizations/{org_id}/tasks",
        json={"title": "Overdue migration", "department_id": department["id"], "due_date": YESTERDAY_ISO},
        headers={"X-CSRF-Token": owner_csrf},
    ).get_json()["data"]
    client.patch(
        f"/api/v1/organizations/{org_id}/tasks/{task_1['id']}/assign",
        json={"assignee_membership_id": employee_1_id},
        headers={"X-CSRF-Token": owner_csrf},
    )

    # --- Task 2: Engineering, Employee One, completed -------------------
    task_2 = client.post(
        f"/api/v1/organizations/{org_id}/tasks",
        json={"title": "Finished migration", "department_id": department["id"], "due_date": NEXT_YEAR_ISO},
        headers={"X-CSRF-Token": owner_csrf},
    ).get_json()["data"]
    client.patch(
        f"/api/v1/organizations/{org_id}/tasks/{task_2['id']}/assign",
        json={"assignee_membership_id": employee_1_id},
        headers={"X-CSRF-Token": owner_csrf},
    )
    employee_1_csrf = _login(client, EMPLOYEE_1)
    client.patch(
        f"/api/v1/organizations/{org_id}/tasks/{task_2['id']}/status",
        json={"status": "in_progress"},
        headers={"X-CSRF-Token": employee_1_csrf},
    )
    client.patch(
        f"/api/v1/organizations/{org_id}/tasks/{task_2['id']}/status",
        json={"status": "under_review"},
        headers={"X-CSRF-Token": employee_1_csrf},
    )
    owner_csrf = _login(client, OWNER)
    complete_response = client.patch(
        f"/api/v1/organizations/{org_id}/tasks/{task_2['id']}/status",
        json={"status": "completed"},
        headers={"X-CSRF-Token": owner_csrf},
    )
    assert complete_response.status_code == 200

    # --- Task 3: no department, Employee Two, still open, not overdue --
    task_3 = client.post(
        f"/api/v1/organizations/{org_id}/tasks",
        json={"title": "Unassigned-department task", "due_date": NEXT_YEAR_ISO},
        headers={"X-CSRF-Token": owner_csrf},
    ).get_json()["data"]
    client.patch(
        f"/api/v1/organizations/{org_id}/tasks/{task_3['id']}/assign",
        json={"assignee_membership_id": employee_2_id},
        headers={"X-CSRF-Token": owner_csrf},
    )
    employee_2_csrf = _login(client, EMPLOYEE_2)
    client.patch(
        f"/api/v1/organizations/{org_id}/tasks/{task_3['id']}/status",
        json={"status": "in_progress"},
        headers={"X-CSRF-Token": employee_2_csrf},
    )

    # --- A customer with two requests: one assigned to Employee One ---
    # --- (counts toward Engineering's request_volume), one left -------
    # --- unassigned (counts toward nothing, by design) ------------------
    owner_csrf = _login(client, OWNER)
    customer = client.post(
        f"/api/v1/organizations/{org_id}/customers",
        json={"name": "Reconciliation Customer", "email": "ap@reconciliation-analytics.example.com"},
        headers={"X-CSRF-Token": owner_csrf},
    ).get_json()["data"]
    request_1 = client.post(
        f"/api/v1/organizations/{org_id}/customer-requests",
        json={"customer_id": customer["id"], "title": "Assigned request", "priority": "medium"},
        headers={"X-CSRF-Token": owner_csrf},
    ).get_json()["data"]
    client.patch(
        f"/api/v1/organizations/{org_id}/customer-requests/{request_1['id']}/assign",
        json={"assignee_membership_id": employee_1_id},
        headers={"X-CSRF-Token": owner_csrf},
    )
    client.post(
        f"/api/v1/organizations/{org_id}/customer-requests",
        json={"customer_id": customer["id"], "title": "Unassigned request", "priority": "low"},
        headers={"X-CSRF-Token": owner_csrf},
    )

    period_qs = f"period=custom&period_start={TODAY_ISO}&period_end={TODAY_ISO}"

    # --- The org-wide overview ------------------------------------------
    overview = client.get(
        f"/api/v1/organizations/{org_id}/analytics/overview?{period_qs}", headers={"X-CSRF-Token": owner_csrf}
    ).get_json()["data"]
    assert overview["active_tasks"] == 2  # task_1 (todo, overdue) + task_3 (in_progress)
    assert overview["completed_tasks"] == 1  # task_2
    assert overview["overdue_tasks"] == 1  # task_1
    assert overview["open_requests"] == 2  # both requests are new/assigned, neither resolved/closed

    # --- The department breakdown: Engineering + the trailing ----------
    # --- "no department" bucket, which must still be present -----------
    departments = client.get(
        f"/api/v1/organizations/{org_id}/analytics/departments?{period_qs}", headers={"X-CSRF-Token": owner_csrf}
    ).get_json()["data"]
    engineering = next(row for row in departments if row["department_name"] == "Engineering")
    unassigned = next(row for row in departments if row["department_name"] is None)

    assert engineering["active_tasks"] == 1  # task_1
    assert engineering["completed_tasks"] == 1  # task_2
    assert engineering["overdue_tasks"] == 1  # task_1
    assert engineering["request_volume"] == 1  # request_1 only - request_2 is unassigned, counted nowhere

    assert unassigned["active_tasks"] == 1  # task_3
    assert unassigned["completed_tasks"] == 0
    assert unassigned["overdue_tasks"] == 0
    assert unassigned["request_volume"] == 0  # always 0 for the unassigned bucket, by design

    # --- Cross-check #1: the department breakdown, summed across every
    # --- department (including "no department"), equals the overview's
    # --- own org-wide numbers - two independent queries, same total ---
    assert sum(row["active_tasks"] for row in departments) == overview["active_tasks"]
    assert sum(row["completed_tasks"] for row in departments) == overview["completed_tasks"]
    assert sum(row["overdue_tasks"] for row in departments) == overview["overdue_tasks"]

    # --- The per-employee breakdown --------------------------------------
    employees_performance = client.get(
        f"/api/v1/organizations/{org_id}/analytics/employees?{period_qs}", headers={"X-CSRF-Token": owner_csrf}
    ).get_json()["data"]
    employee_1_perf = next(row for row in employees_performance if row["membership_id"] == employee_1_id)
    employee_2_perf = next(row for row in employees_performance if row["membership_id"] == employee_2_id)

    assert employee_1_perf["assigned_tasks"] == 2  # task_1 + task_2
    assert employee_1_perf["completed_tasks"] == 1  # task_2
    assert employee_1_perf["overdue_tasks"] == 1  # task_1
    assert employee_1_perf["completion_rate"] == 0.5

    assert employee_2_perf["assigned_tasks"] == 1  # task_3
    assert employee_2_perf["completed_tasks"] == 0
    assert employee_2_perf["overdue_tasks"] == 0
    assert employee_2_perf["completion_rate"] == 0.0

    # --- Cross-check #2: Engineering's own completed/overdue counts ----
    # --- equal exactly Employee One's own numbers (the only Engineering
    # --- employee) - the department view and the employee view, two ---
    # --- more independent queries, must still agree -----------------------
    assert engineering["completed_tasks"] == employee_1_perf["completed_tasks"]
    assert engineering["overdue_tasks"] == employee_1_perf["overdue_tasks"]
    assert engineering["active_tasks"] == employee_1_perf["assigned_tasks"] - employee_1_perf["completed_tasks"]

    # --- Cross-check #3: summed across every employee, completed/------
    # --- overdue equal the org-wide overview too ------------------------
    assert sum(row["completed_tasks"] for row in employees_performance) == overview["completed_tasks"]
    assert sum(row["overdue_tasks"] for row in employees_performance) == overview["overdue_tasks"]
