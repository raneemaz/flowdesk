"""FD-062: Section 13's tenant-isolation scenarios are already covered,
one resource at a time, by every module's own test suite (each proving
a single cross-org GET/PATCH/DELETE 404s). What none of those tests can
prove is that running TWO organizations' full business workflows
side-by-side, with real overlapping data (same titles, same day, same
amounts), never leaks across a *list* or an *aggregate* endpoint -
exactly the class of bug a missing `organization_id` filter on a JOIN,
or an aggregate query that forgets to scope by org, would produce and a
single-resource 404 check would never catch.

Driven entirely through real HTTP routes via the Flask test client,
same convention as test_full_workflow.py."""

import json as json_module
import re
from datetime import datetime, timezone

from app.ai.providers import AICompletionResponse, AIProvider
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


def _create_org(client, csrf_token, name):
    return client.post("/api/v1/organizations", json={"name": name}, headers={"X-CSRF-Token": csrf_token}).get_json()[
        "data"
    ]


# UTC, not the OS's own local date - see test_full_workflow.py's own
# comment on the identical `TODAY` constant for why.
TODAY = datetime.now(timezone.utc).date().isoformat()


def _run_mini_workflow(client, app, sent_emails, *, owner_email, employee_email, org_name, title_prefix, amount):
    """One organization's own condensed customer -> request -> task ->
    invoice -> payment workflow, returning everything the isolation
    assertions below need to check. Deliberately uses the SAME shape of
    data (same titles/day/currency) as its counterpart organization -
    the whole point is overlapping data, not merely distinct data that
    would also pass a sloppier, string-based "doesn't contain the
    other org's name" check."""
    owner_csrf = _register_and_login(client, owner_email, name=f"Owner {org_name}")
    org = _create_org(client, owner_csrf, name=org_name)
    org_id = org["id"]

    employee_csrf = _register_and_login(client, employee_email, name=f"Employee {org_name}")
    owner_csrf = _login(client, owner_email)
    invite_response = client.post(
        f"/api/v1/organizations/{org_id}/invitations",
        json={"email": employee_email, "role": "employee"},
        headers={"X-CSRF-Token": owner_csrf},
    )
    assert invite_response.status_code == 201, invite_response.get_json()

    token_match = re.search(r"token=([\w\-\.]+)", sent_emails[-1]["body"])
    assert token_match, f"no invitation token found in the sent email: {sent_emails[-1]['body']!r}"
    token = token_match.group(1)

    employee_csrf = _login(client, employee_email)
    accept_response = client.post(
        "/api/v1/invitations/accept", json={"token": token}, headers={"X-CSRF-Token": employee_csrf}
    )
    assert accept_response.status_code == 200, accept_response.get_json()

    with app.app_context():
        import uuid as uuid_module

        employee_user = db.session.query(User).filter_by(email=employee_email.lower()).one()
        employee_membership_id = str(
            db.session.query(Membership)
            .filter_by(organization_id=uuid_module.UUID(org_id), user_id=employee_user.id)
            .one()
            .id
        )

    owner_csrf = _login(client, owner_email)
    department = client.post(
        f"/api/v1/organizations/{org_id}/departments",
        json={"name": f"{title_prefix} Department"},
        headers={"X-CSRF-Token": owner_csrf},
    ).get_json()["data"]

    customer = client.post(
        f"/api/v1/organizations/{org_id}/customers",
        json={"name": f"{title_prefix} Customer", "email": f"ap@{title_prefix.lower()}-isolation.example.com"},
        headers={"X-CSRF-Token": owner_csrf},
    ).get_json()["data"]

    request = client.post(
        f"/api/v1/organizations/{org_id}/customer-requests",
        json={"customer_id": customer["id"], "title": "Production outage - checkout is down", "priority": "high"},
        headers={"X-CSRF-Token": owner_csrf},
    ).get_json()["data"]
    client.patch(
        f"/api/v1/organizations/{org_id}/customer-requests/{request['id']}/assign",
        json={"assignee_membership_id": employee_membership_id},
        headers={"X-CSRF-Token": owner_csrf},
    )

    task = client.post(
        f"/api/v1/organizations/{org_id}/tasks",
        json={"title": "Post-mortem: checkout outage", "department_id": department["id"], "due_date": "2026-12-31"},
        headers={"X-CSRF-Token": owner_csrf},
    ).get_json()["data"]
    client.patch(
        f"/api/v1/organizations/{org_id}/tasks/{task['id']}/assign",
        json={"assignee_membership_id": employee_membership_id},
        headers={"X-CSRF-Token": owner_csrf},
    )

    employee_csrf = _login(client, employee_email)
    client.patch(
        f"/api/v1/organizations/{org_id}/tasks/{task['id']}/status",
        json={"status": "in_progress"},
        headers={"X-CSRF-Token": employee_csrf},
    )
    client.patch(
        f"/api/v1/organizations/{org_id}/tasks/{task['id']}/status",
        json={"status": "under_review"},
        headers={"X-CSRF-Token": employee_csrf},
    )

    owner_csrf = _login(client, owner_email)
    complete_response = client.patch(
        f"/api/v1/organizations/{org_id}/tasks/{task['id']}/status",
        json={"status": "completed"},
        headers={"X-CSRF-Token": owner_csrf},
    )
    assert complete_response.status_code == 200

    invoice = client.post(
        f"/api/v1/organizations/{org_id}/invoices",
        json={
            "customer_id": customer["id"],
            "currency": "USD",
            "issue_date": TODAY,
            "line_items": [{"description": "Incident response", "quantity": "1", "unit_price": str(amount)}],
        },
        headers={"X-CSRF-Token": owner_csrf},
    ).get_json()["data"]
    client.patch(f"/api/v1/organizations/{org_id}/invoices/{invoice['id']}/issue", headers={"X-CSRF-Token": owner_csrf})
    client.post(
        f"/api/v1/organizations/{org_id}/invoices/{invoice['id']}/payments",
        json={
            "amount": str(amount),
            "payment_date": TODAY,
            "method": "bank_transfer",
            "idempotency_key": f"isolation-test-payment-{title_prefix}",
        },
        headers={"X-CSRF-Token": owner_csrf},
    )

    return {
        "org_id": org_id,
        "owner_csrf": owner_csrf,
        "department_id": department["id"],
        "customer_id": customer["id"],
        "request_id": request["id"],
        "task_id": task["id"],
        "invoice_id": invoice["id"],
        "employee_membership_id": employee_membership_id,
    }


def test_two_organizations_full_workflows_never_leak_into_each_others_lists_or_aggregates(client, app, sent_emails):
    org_a = _run_mini_workflow(
        client,
        app,
        sent_emails,
        owner_email="owner-a@flowdesk-isolation.example.com",
        employee_email="employee-a@flowdesk-isolation.example.com",
        org_name="Org A",
        title_prefix="Alpha",
        amount="100.00",
    )
    org_b = _run_mini_workflow(
        client,
        app,
        sent_emails,
        owner_email="owner-b@flowdesk-isolation.example.com",
        employee_email="employee-b@flowdesk-isolation.example.com",
        org_name="Org B",
        title_prefix="Beta",
        amount="250.00",
    )

    owner_a_csrf = _login(client, "owner-a@flowdesk-isolation.example.com")

    # --- List endpoints: Org A sees exactly its own one of each, never
    # --- Org B's, even though both share the same title/day/currency --
    for path, id_field in (
        ("customers", "id"),
        ("customer-requests", "id"),
        ("tasks", "id"),
        ("invoices", "id"),
        ("departments", "id"),
        ("employees", "membership_id"),
    ):
        listing = client.get(
            f"/api/v1/organizations/{org_a['org_id']}/{path}", headers={"X-CSRF-Token": owner_a_csrf}
        ).get_json()["data"]
        ids = {row[id_field] for row in listing}
        assert org_b["org_id"] not in str(listing), f"Org B leaked into Org A's /{path} listing: {listing}"
        for key in ("customer_id", "request_id", "task_id", "invoice_id", "department_id", "employee_membership_id"):
            if key in org_b and org_b[key] in ids:
                pytest.fail(f"Org B's {key} appeared in Org A's /{path} listing")

    activity_a = client.get(
        f"/api/v1/organizations/{org_a['org_id']}/activity?per_page=100", headers={"X-CSRF-Token": owner_a_csrf}
    ).get_json()["data"]
    assert all(entry["organization_id"] == org_a["org_id"] for entry in activity_a)

    # Notifications are always scoped to the CALLER's own
    # recipient_membership_id (app.notifications.routes's own
    # ownership-based access, not a Permission check) - the owner
    # never received one here, so this checks the employee who did.
    employee_a_csrf = _login(client, "employee-a@flowdesk-isolation.example.com")
    notifications_a = client.get(
        f"/api/v1/organizations/{org_a['org_id']}/notifications", headers={"X-CSRF-Token": employee_a_csrf}
    ).get_json()["data"]
    assert notifications_a, "Org A's employee should have at least one notification (task/request assignment)"
    assert all(entry["organization_id"] == org_a["org_id"] for entry in notifications_a)
    owner_a_csrf = _login(client, "owner-a@flowdesk-isolation.example.com")

    # --- Aggregate endpoints: the precise, aggregate-leak-sensitive ----
    # --- counts, not just "doesn't contain an id" ----------------------
    overview_a = client.get(
        f"/api/v1/organizations/{org_a['org_id']}/analytics/overview"
        f"?period=custom&period_start={TODAY}&period_end={TODAY}",
        headers={"X-CSRF-Token": owner_a_csrf},
    ).get_json()["data"]
    assert overview_a["employee_count"] == 2
    assert overview_a["completed_tasks"] == 1
    assert overview_a["monthly_invoiced"] == "100.00"
    assert overview_a["monthly_collected"] == "100.00"

    financial_summary_a = client.get(
        f"/api/v1/organizations/{org_a['org_id']}/invoices/financial-summary"
        f"?period_start={TODAY}&period_end={TODAY}",
        headers={"X-CSRF-Token": owner_a_csrf},
    ).get_json()["data"]
    assert financial_summary_a["total_invoiced"] == "100.00"
    assert financial_summary_a["total_collected"] == "100.00"
    assert len(financial_summary_a["recent_payments"]) == 1

    # --- The three other independent analytics queries (departments/
    # --- employees/finance), each its own cross-tenant-leak risk, not
    # --- already covered above (overview is a fourth, separate query) --
    departments_a = client.get(
        f"/api/v1/organizations/{org_a['org_id']}/analytics/departments"
        f"?period=custom&period_start={TODAY}&period_end={TODAY}",
        headers={"X-CSRF-Token": owner_a_csrf},
    ).get_json()["data"]
    alpha_dept = next(row for row in departments_a if row["department_name"] == "Alpha Department")
    assert alpha_dept["completed_tasks"] == 1
    assert all(row["department_name"] != "Beta Department" for row in departments_a)

    employees_a = client.get(
        f"/api/v1/organizations/{org_a['org_id']}/analytics/employees"
        f"?period=custom&period_start={TODAY}&period_end={TODAY}",
        headers={"X-CSRF-Token": owner_a_csrf},
    ).get_json()["data"]
    employee_a_perf = next(row for row in employees_a if row["membership_id"] == org_a["employee_membership_id"])
    assert employee_a_perf["completed_tasks"] == 1
    assert all(row["membership_id"] != org_b["employee_membership_id"] for row in employees_a)

    finance_a = client.get(
        f"/api/v1/organizations/{org_a['org_id']}/analytics/finance"
        f"?period=custom&period_start={TODAY}&period_end={TODAY}",
        headers={"X-CSRF-Token": owner_a_csrf},
    ).get_json()["data"]
    assert finance_a["total_invoiced"] == "100.00"
    assert all(payment["invoice_id"] != org_b["invoice_id"] for payment in finance_a["recent_payments"])

    # --- The mirror image for Org B, so a bug that happened to only ---
    # --- favor whichever org ran first is still caught -----------------
    owner_b_csrf = _login(client, "owner-b@flowdesk-isolation.example.com")
    overview_b = client.get(
        f"/api/v1/organizations/{org_b['org_id']}/analytics/overview"
        f"?period=custom&period_start={TODAY}&period_end={TODAY}",
        headers={"X-CSRF-Token": owner_b_csrf},
    ).get_json()["data"]
    assert overview_b["employee_count"] == 2
    assert overview_b["completed_tasks"] == 1
    assert overview_b["monthly_invoiced"] == "250.00"
    assert overview_b["monthly_collected"] == "250.00"

    departments_b = client.get(
        f"/api/v1/organizations/{org_b['org_id']}/analytics/departments"
        f"?period=custom&period_start={TODAY}&period_end={TODAY}",
        headers={"X-CSRF-Token": owner_b_csrf},
    ).get_json()["data"]
    beta_dept = next(row for row in departments_b if row["department_name"] == "Beta Department")
    assert beta_dept["completed_tasks"] == 1
    assert all(row["department_name"] != "Alpha Department" for row in departments_b)

    employees_b = client.get(
        f"/api/v1/organizations/{org_b['org_id']}/analytics/employees"
        f"?period=custom&period_start={TODAY}&period_end={TODAY}",
        headers={"X-CSRF-Token": owner_b_csrf},
    ).get_json()["data"]
    employee_b_perf = next(row for row in employees_b if row["membership_id"] == org_b["employee_membership_id"])
    assert employee_b_perf["completed_tasks"] == 1
    assert all(row["membership_id"] != org_a["employee_membership_id"] for row in employees_b)

    finance_b = client.get(
        f"/api/v1/organizations/{org_b['org_id']}/analytics/finance"
        f"?period=custom&period_start={TODAY}&period_end={TODAY}",
        headers={"X-CSRF-Token": owner_b_csrf},
    ).get_json()["data"]
    assert finance_b["total_invoiced"] == "250.00"
    assert all(payment["invoice_id"] != org_a["invoice_id"] for payment in finance_b["recent_payments"])

    # --- Direct cross-org access to every resource type: 404, never ---
    # --- a 403 that would confirm the resource exists -------------------
    owner_a_csrf = _login(client, "owner-a@flowdesk-isolation.example.com")
    cross_org_checks = [
        f"/api/v1/organizations/{org_a['org_id']}/customers/{org_b['customer_id']}",
        f"/api/v1/organizations/{org_a['org_id']}/customer-requests/{org_b['request_id']}",
        f"/api/v1/organizations/{org_a['org_id']}/tasks/{org_b['task_id']}",
        f"/api/v1/organizations/{org_a['org_id']}/invoices/{org_b['invoice_id']}",
        f"/api/v1/organizations/{org_a['org_id']}/employees/{org_b['employee_membership_id']}",
    ]
    for url in cross_org_checks:
        response = client.get(url, headers={"X-CSRF-Token": owner_a_csrf})
        assert response.status_code == 404, f"{url} returned {response.status_code}, expected 404"

    # Departments have no GET-by-id route (list/PATCH/DELETE only), so
    # the cross-org check for this resource goes through PATCH instead.
    department_patch = client.patch(
        f"/api/v1/organizations/{org_a['org_id']}/departments/{org_b['department_id']}",
        json={"name": "Hijacked"},
        headers={"X-CSRF-Token": owner_a_csrf},
    )
    assert department_patch.status_code == 404, department_patch.get_json()

    # --- Org A cannot even act on Org B's org id at all - membership ---
    # --- there doesn't exist, so every write is rejected before it ----
    # --- ever reaches the resource-level check --------------------------
    forbidden_write = client.patch(
        f"/api/v1/organizations/{org_b['org_id']}/tasks/{org_b['task_id']}/status",
        json={"status": "in_progress"},
        headers={"X-CSRF-Token": owner_a_csrf},
    )
    # A missing membership and a non-active one are deliberately
    # indistinguishable to the caller (app.authz.service's own
    # documented convention) - always 404, never a 403 that would
    # confirm org B or its task exist.
    assert forbidden_write.status_code == 404

    # --- AI reports: one more org-scoped resource with its own list ---
    # --- and detail routes, generated here (never a direct ORM insert,
    # --- same real-HTTP convention as everything else in this file) ---
    class _FakeProvider(AIProvider):
        def complete(self, request, *, timeout_seconds):
            return AICompletionResponse(
                text=json_module.dumps(
                    {
                        "business_overview": "Stub.",
                        "employee_productivity": "Stub.",
                        "financial_overview": "Stub.",
                        "operational_problems": "Stub.",
                        "recommendations": [],
                        "missing_data": [],
                    }
                ),
                model="claude-haiku-5-5",
                input_tokens=1,
                output_tokens=1,
            )

    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setattr("app.ai.service.build_default_provider", lambda: _FakeProvider())
        report_a = client.post(
            f"/api/v1/organizations/{org_a['org_id']}/ai-reports/generate",
            json={"period": "custom", "period_start": TODAY, "period_end": TODAY},
            headers={"X-CSRF-Token": owner_a_csrf},
        ).get_json()["data"]
        owner_b_csrf = _login(client, "owner-b@flowdesk-isolation.example.com")
        report_b = client.post(
            f"/api/v1/organizations/{org_b['org_id']}/ai-reports/generate",
            json={"period": "custom", "period_start": TODAY, "period_end": TODAY},
            headers={"X-CSRF-Token": owner_b_csrf},
        ).get_json()["data"]

    owner_a_csrf = _login(client, "owner-a@flowdesk-isolation.example.com")
    ai_reports_a = client.get(
        f"/api/v1/organizations/{org_a['org_id']}/ai-reports", headers={"X-CSRF-Token": owner_a_csrf}
    ).get_json()["data"]
    assert {report["id"] for report in ai_reports_a} == {report_a["id"]}

    cross_org_report = client.get(
        f"/api/v1/organizations/{org_a['org_id']}/ai-reports/{report_b['id']}", headers={"X-CSRF-Token": owner_a_csrf}
    )
    assert cross_org_report.status_code == 404
