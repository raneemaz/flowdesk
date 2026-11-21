"""FD-062: the canonical end-to-end business workflow spec Section 36
("One realistic end-to-end workflow") and Section 31's own release
acceptance criterion ("a user can complete the full customer -> request
-> task -> invoice -> payment workflow") both name explicitly: a
customer submits a request, support logs it, a manager assigns it, an
employee works it, it's resolved, a task is created and completed for
the underlying work, an accountant invoices the customer, a payment is
recorded, and analytics/activity/notifications all reflect what
happened - ending with an AI weekly report whose own metrics_snapshot
embeds the same real numbers (FR-042: never fabricated).

Driven entirely through real HTTP routes via the Flask test client,
including the real invitation/accept flow (FD-016) - not a single
direct ORM insert anywhere except reading the invitation token out of
a monkeypatched "sent" email, the same convention
test_invitations_accept.py already established (the token is
deliberately never in any API response).

`Task` and `CustomerRequest` have no FK relationship to each other
anywhere in this codebase (confirmed by inspection) - Section 31's
"request -> task" is a business-process link, not a structural one, so
this test creates both as independent records tied together only by
organization/customer, exactly as a real user would."""

import re
from datetime import date

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


def _create_org(client, csrf_token, name="FlowDesk Integration Co"):
    return client.post("/api/v1/organizations", json={"name": name}, headers={"X-CSRF-Token": csrf_token}).get_json()[
        "data"
    ]


def _invite_and_accept(client, inviter_email, org_id, sent_emails, email, role, name):
    """The real HTTP invitation+accept round trip (FD-016), not a
    direct Membership insert - the invitee registers their own account
    first (same real-world order a brand-new teammate would follow),
    then accepts using the token pulled out of their own "inbox".

    Re-logs in as `inviter_email` right before posting the invitation,
    rather than trusting a csrf_token passed in from an earlier call -
    the shared Flask test client's session cookie was left pointing at
    whichever invitee that earlier call last registered/logged-in as,
    so reusing a stale csrf_token here would either 403 on CSRF or,
    worse, silently run as the wrong actor. The same recurring
    session-switch bug this codebase's own test suite has hit (and
    fixed the same way) many times before."""
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


OWNER = "owner@flowdesk-integration.example.com"
MANAGER = "manager@flowdesk-integration.example.com"
EMPLOYEE = "employee@flowdesk-integration.example.com"
ACCOUNTANT = "accountant@flowdesk-integration.example.com"
SUPPORT = "support@flowdesk-integration.example.com"

# The money/analytics assertions below need a period that actually
# contains every event this test drives through real HTTP routes (task
# completion, invoice issuance - both stamped with the real wall-clock
# "now" the test runs at, not a fixed fixture date). Using today's own
# date for the explicit payment_date/issue_date, and a one-day period
# bounding it, keeps the analytics/financial-summary/AI-report windows
# consistent with what the server itself actually recorded.
TODAY = date.today().isoformat()


def test_the_full_customer_to_request_to_task_to_invoice_to_payment_workflow(client, app, sent_emails):
    # --- Owner registers and creates the organization -----------------
    owner_csrf = _register_and_login(client, OWNER, name="Olivia Owner")
    org = _create_org(client, owner_csrf)
    org_id = org["id"]

    # --- Owner invites a Manager, an Employee, an Accountant, and ------
    # --- Customer Support staffer, each accepting for real. Every ------
    # --- subsequent action below re-logs in as the correct actor ------
    # --- first - the shared Flask test client has exactly one session ---
    # --- cookie, which the last login/register call left pointing at. ---
    _invite_and_accept(client, OWNER, org_id, sent_emails, MANAGER, "manager", "Mia Manager")
    _invite_and_accept(client, OWNER, org_id, sent_emails, EMPLOYEE, "employee", "Evan Employee")
    _invite_and_accept(client, OWNER, org_id, sent_emails, ACCOUNTANT, "accountant", "Amy Accountant")
    _invite_and_accept(client, OWNER, org_id, sent_emails, SUPPORT, "customer_support", "Sam Support")

    with app.app_context():
        import uuid as uuid_module

        def membership_id(email):
            user = db.session.query(User).filter_by(email=email.lower()).one()
            membership = (
                db.session.query(Membership)
                .filter_by(organization_id=uuid_module.UUID(org_id), user_id=user.id)
                .one()
            )
            return str(membership.id)

        manager_id = membership_id(MANAGER)
        employee_id = membership_id(EMPLOYEE)

    # --- A department exists, with the employee in it ------------------
    owner_csrf = _login(client, OWNER)
    department = client.post(
        f"/api/v1/organizations/{org_id}/departments",
        json={"name": "Support Engineering", "manager_membership_id": manager_id},
        headers={"X-CSRF-Token": owner_csrf},
    ).get_json()["data"]
    client.patch(
        f"/api/v1/organizations/{org_id}/employees/{employee_id}",
        json={"department_id": department["id"]},
        headers={"X-CSRF-Token": owner_csrf},
    )

    # --- Customer Support logs a customer and their request -----------
    support_csrf = _login(client, SUPPORT)
    customer = client.post(
        f"/api/v1/organizations/{org_id}/customers",
        json={"name": "Northwind Traders", "email": "ap@northwind-integration.example.com"},
        headers={"X-CSRF-Token": support_csrf},
    ).get_json()["data"]

    request = client.post(
        f"/api/v1/organizations/{org_id}/customer-requests",
        json={"customer_id": customer["id"], "title": "Production outage - checkout is down", "priority": "high"},
        headers={"X-CSRF-Token": support_csrf},
    ).get_json()["data"]
    assert request["status"] == "new"

    # --- Manager assigns the request to the employee -------------------
    manager_csrf = _login(client, MANAGER)
    assign_response = client.patch(
        f"/api/v1/organizations/{org_id}/customer-requests/{request['id']}/assign",
        json={"assignee_membership_id": employee_id},
        headers={"X-CSRF-Token": manager_csrf},
    )
    assert assign_response.status_code == 200
    assert assign_response.get_json()["data"]["status"] == "assigned"

    # --- The employee works the request (New -> Assigned -> In --------
    # --- Progress -> Waiting for Customer are the two forward moves ---
    # --- an assignee may drive themselves); resolving is reserved for -
    # --- Owner/Manager/CustomerSupport, matching the spec's own --------
    # --- narrative exactly ("employee completes it -> manager --------
    # --- resolves it") -------------------------------------------------
    employee_csrf = _login(client, EMPLOYEE)
    client.patch(
        f"/api/v1/organizations/{org_id}/customer-requests/{request['id']}/status",
        json={"status": "in_progress"},
        headers={"X-CSRF-Token": employee_csrf},
    )
    waiting_response = client.patch(
        f"/api/v1/organizations/{org_id}/customer-requests/{request['id']}/status",
        json={"status": "waiting_for_customer"},
        headers={"X-CSRF-Token": employee_csrf},
    )
    assert waiting_response.status_code == 200
    assert waiting_response.get_json()["data"]["status"] == "waiting_for_customer"

    manager_csrf = _login(client, MANAGER)
    resolve_response = client.patch(
        f"/api/v1/organizations/{org_id}/customer-requests/{request['id']}/status",
        json={"status": "resolved", "resolution_notes": "Restarted the checkout service; root cause was a bad deploy."},
        headers={"X-CSRF-Token": manager_csrf},
    )
    assert resolve_response.status_code == 200
    assert resolve_response.get_json()["data"]["status"] == "resolved"

    # --- A task tracks the actual remediation work (no FK to the ------
    # --- request - independent entities, tied together only by org) ---
    manager_csrf = _login(client, MANAGER)
    task = client.post(
        f"/api/v1/organizations/{org_id}/tasks",
        json={
            "title": "Post-mortem: checkout outage",
            "department_id": department["id"],
            "due_date": "2026-12-31",
        },
        headers={"X-CSRF-Token": manager_csrf},
    ).get_json()["data"]
    client.patch(
        f"/api/v1/organizations/{org_id}/tasks/{task['id']}/assign",
        json={"assignee_membership_id": employee_id},
        headers={"X-CSRF-Token": manager_csrf},
    )

    # --- To Do -> In Progress -> Under Review are the two forward -----
    # --- moves the assignee may drive themselves; approving a task ----
    # --- to Completed (from Under Review) is Owner/Manager-only, ------
    # --- same reservation pattern as resolving a request above. -------
    employee_csrf = _login(client, EMPLOYEE)
    client.patch(
        f"/api/v1/organizations/{org_id}/tasks/{task['id']}/status",
        json={"status": "in_progress"},
        headers={"X-CSRF-Token": employee_csrf},
    )
    under_review_response = client.patch(
        f"/api/v1/organizations/{org_id}/tasks/{task['id']}/status",
        json={"status": "under_review"},
        headers={"X-CSRF-Token": employee_csrf},
    )
    assert under_review_response.status_code == 200
    assert under_review_response.get_json()["data"]["status"] == "under_review"

    manager_csrf = _login(client, MANAGER)
    complete_response = client.patch(
        f"/api/v1/organizations/{org_id}/tasks/{task['id']}/status",
        json={"status": "completed"},
        headers={"X-CSRF-Token": manager_csrf},
    )
    assert complete_response.status_code == 200
    assert complete_response.get_json()["data"]["status"] == "completed"

    # --- The accountant bills the customer for the work ----------------
    accountant_csrf = _login(client, ACCOUNTANT)
    invoice = client.post(
        f"/api/v1/organizations/{org_id}/invoices",
        json={
            "customer_id": customer["id"],
            "currency": "USD",
            "issue_date": TODAY,
            "line_items": [
                {"description": "Emergency incident response (4 hours)", "quantity": "4", "unit_price": "150.00"},
            ],
        },
        headers={"X-CSRF-Token": accountant_csrf},
    ).get_json()["data"]
    assert invoice["status"] == "draft"
    assert invoice["total"] == "600.00"

    issue_response = client.patch(
        f"/api/v1/organizations/{org_id}/invoices/{invoice['id']}/issue",
        headers={"X-CSRF-Token": accountant_csrf},
    )
    assert issue_response.status_code == 200
    assert issue_response.get_json()["data"]["status"] == "sent"

    # --- The customer pays in full -------------------------------------
    payment_response = client.post(
        f"/api/v1/organizations/{org_id}/invoices/{invoice['id']}/payments",
        json={
            "amount": "600.00",
            "payment_date": TODAY,
            "method": "bank_transfer",
            "idempotency_key": "integration-test-payment-1",
        },
        headers={"X-CSRF-Token": accountant_csrf},
    )
    assert payment_response.status_code == 201
    paid_invoice = client.get(
        f"/api/v1/organizations/{org_id}/invoices/{invoice['id']}", headers={"X-CSRF-Token": accountant_csrf}
    ).get_json()["data"]
    assert paid_invoice["status"] == "paid"

    # --- Financial transactions: the summary reflects the real numbers
    summary = client.get(
        f"/api/v1/organizations/{org_id}/invoices/financial-summary?period_start={TODAY}&period_end={TODAY}",
        headers={"X-CSRF-Token": accountant_csrf},
    ).get_json()["data"]
    assert summary["total_invoiced"] == "600.00"
    assert summary["total_collected"] == "600.00"
    assert summary["outstanding_balance"] == "0.00"
    assert len(summary["recent_payments"]) == 1

    # --- Analytics: the overview reflects the real state of the world -
    owner_csrf = _login(client, OWNER)
    overview = client.get(
        f"/api/v1/organizations/{org_id}/analytics/overview?period=custom&period_start={TODAY}&period_end={TODAY}",
        headers={"X-CSRF-Token": owner_csrf},
    ).get_json()["data"]
    assert overview["employee_count"] == 5  # owner + manager + employee + accountant + support
    assert overview["completed_tasks"] == 1
    assert overview["monthly_invoiced"] == "600.00"
    assert overview["monthly_collected"] == "600.00"

    department_analytics = client.get(
        f"/api/v1/organizations/{org_id}/analytics/departments?period=custom&period_start={TODAY}&period_end={TODAY}",
        headers={"X-CSRF-Token": owner_csrf},
    ).get_json()["data"]
    support_engineering = next(row for row in department_analytics if row["department_name"] == "Support Engineering")
    assert support_engineering["completed_tasks"] == 1

    # --- Activity log: the key events were recorded --------------------
    activity = client.get(
        f"/api/v1/organizations/{org_id}/activity?per_page=50", headers={"X-CSRF-Token": owner_csrf}
    ).get_json()["data"]
    activity_actions = {entry["action"] for entry in activity}
    assert "payment_recorded" in activity_actions
    assert "task_completed" in activity_actions

    # --- Notifications: the employee was told about their assignment --
    employee_csrf = _login(client, EMPLOYEE)
    employee_notifications = client.get(
        f"/api/v1/organizations/{org_id}/notifications", headers={"X-CSRF-Token": employee_csrf}
    ).get_json()["data"]
    assert any(n["type"] == "task_assigned" for n in employee_notifications)
    assert any(n["type"] == "request_assigned" for n in employee_notifications)

    # --- The AI weekly summary's own metrics_snapshot embeds these -----
    # --- same real numbers (FR-042: never fabricated) ------------------
    import json as json_module

    from app.ai.providers import AICompletionResponse, AIProvider

    class _FakeProvider(AIProvider):
        def complete(self, request, *, timeout_seconds):
            return AICompletionResponse(
                text=json_module.dumps(
                    {
                        "business_overview": "The team resolved a production incident and completed the follow-up task.",
                        "employee_productivity": "Evan Employee completed 1 task this period.",
                        "financial_overview": "Invoiced $600.00 and collected $600.00 in full.",
                        "operational_problems": "No overdue tasks or unresolved requests remain.",
                        "recommendations": ["Review the incident post-mortem for recurring root causes."],
                        "missing_data": [],
                    }
                ),
                model="claude-haiku-5-5",
                input_tokens=1,
                output_tokens=1,
            )

    owner_csrf = _login(client, OWNER)
    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setattr("app.ai.service.build_default_provider", lambda: _FakeProvider())

        report_response = client.post(
            f"/api/v1/organizations/{org_id}/ai-reports/generate",
            json={"period": "custom", "period_start": TODAY, "period_end": TODAY},
            headers={"X-CSRF-Token": owner_csrf},
        )

    assert report_response.status_code == 201
    report = report_response.get_json()["data"]
    assert report["metrics_snapshot"]["overview"]["completed_tasks"] == 1
    assert report["metrics_snapshot"]["finance"]["total_collected"] == "600.00"
    assert report["recommendations"] == ["Review the incident post-mortem for recurring root causes."]
