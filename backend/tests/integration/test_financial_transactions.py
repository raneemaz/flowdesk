"""FD-062: every money-integrity rule below (overpayment rejection,
idempotency replay/conflict, the "no cancelling once paid" rule, lazy
overdue promotion) is already covered in isolation, one invoice and
one rule at a time, by test_payments_create.py / test_invoices_*.py.
What none of those tests prove is that running ALL of them together
against the SAME organization - several invoices in different terminal
states (paid, partially paid, cancelled-while-draft, overdue) at once -
still reconciles to the exact same numbers from both of the two
endpoints that independently compute them: `GET .../financial-summary`
(`app.invoices.service.get_financial_summary`) and
`GET .../analytics/overview` (`app.analytics.service.get_overview_metrics`).
Those two functions use genuinely different queries (one in the
invoices module, one in analytics) for what's supposed to be the same
underlying money - this test is the one place that would catch them
silently drifting apart.

Driven entirely through real HTTP routes via the Flask test client,
same convention as test_full_workflow.py."""

from datetime import datetime, timedelta, timezone

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


def _login(client, email, password="correct horse battery"):
    return client.post("/api/v1/auth/login", json={"email": email, "password": password}).get_json()["data"][
        "csrf_token"
    ]


def _register_and_login(client, email, name="Test User", password="correct horse battery"):
    client.post("/api/v1/auth/register", json={"name": name, "email": email, "password": password})
    return _login(client, email, password)


def _create_org(client, csrf_token, name="FlowDesk Finance Co"):
    return client.post("/api/v1/organizations", json={"name": name}, headers={"X-CSRF-Token": csrf_token}).get_json()[
        "data"
    ]


def _create_customer(client, csrf_token, org_id, name):
    return client.post(
        f"/api/v1/organizations/{org_id}/customers",
        json={"name": name, "email": f"ap@{name.lower()}-finance.example.com"},
        headers={"X-CSRF-Token": csrf_token},
    ).get_json()["data"]


def _create_invoice(client, csrf_token, org_id, customer_id, *, amount, issue_date=None, due_date=None):
    return client.post(
        f"/api/v1/organizations/{org_id}/invoices",
        json={
            "customer_id": customer_id,
            "currency": "USD",
            "issue_date": issue_date,
            "due_date": due_date,
            "line_items": [{"description": "Consulting", "quantity": "1", "unit_price": amount}],
        },
        headers={"X-CSRF-Token": csrf_token},
    ).get_json()["data"]


def _issue(client, csrf_token, org_id, invoice_id):
    return client.patch(
        f"/api/v1/organizations/{org_id}/invoices/{invoice_id}/issue", headers={"X-CSRF-Token": csrf_token}
    )


def _pay(client, csrf_token, org_id, invoice_id, *, amount, payment_date, idempotency_key):
    return client.post(
        f"/api/v1/organizations/{org_id}/invoices/{invoice_id}/payments",
        json={"amount": amount, "payment_date": payment_date, "method": "bank_transfer", "idempotency_key": idempotency_key},
        headers={"X-CSRF-Token": csrf_token},
    )


# UTC, not the OS's own local date - see test_full_workflow.py's own
# comment on the identical `TODAY` constant for why.
TODAY = datetime.now(timezone.utc).date()
TODAY_ISO = TODAY.isoformat()
YESTERDAY_ISO = (TODAY - timedelta(days=1)).isoformat()


def test_multiple_invoices_in_different_terminal_states_reconcile_exactly_across_endpoints(client, app):
    owner_csrf = _register_and_login(client, "owner@flowdesk-finance.example.com", name="Owner")
    org = _create_org(client, owner_csrf)
    org_id = org["id"]

    customer_a = _create_customer(client, owner_csrf, org_id, "Acme")
    customer_b = _create_customer(client, owner_csrf, org_id, "Bravo")
    customer_c = _create_customer(client, owner_csrf, org_id, "Cosmo")
    customer_d = _create_customer(client, owner_csrf, org_id, "Delta")

    # --- Invoice A: issued, paid in full via two partial payments -----
    invoice_a = _create_invoice(client, owner_csrf, org_id, customer_a["id"], amount="500.00", issue_date=TODAY_ISO)
    assert invoice_a["total"] == "500.00"
    assert _issue(client, owner_csrf, org_id, invoice_a["id"]).status_code == 200
    first_payment = _pay(
        client, owner_csrf, org_id, invoice_a["id"], amount="200.00", payment_date=TODAY_ISO, idempotency_key="a-1"
    )
    assert first_payment.status_code == 201
    assert first_payment.get_json()["data"]["invoice"]["status"] == "partially_paid"
    second_payment = _pay(
        client, owner_csrf, org_id, invoice_a["id"], amount="300.00", payment_date=TODAY_ISO, idempotency_key="a-2"
    )
    assert second_payment.status_code == 201
    assert second_payment.get_json()["data"]["invoice"]["status"] == "paid"

    # --- Replaying Invoice A's first idempotency key is a true no-op --
    # --- (same response, no second payment created), never a second ---
    # --- charge against the same key --------------------------------
    replay = _pay(client, owner_csrf, org_id, invoice_a["id"], amount="200.00", payment_date=TODAY_ISO, idempotency_key="a-1")
    assert replay.status_code == 200
    assert replay.get_json()["data"]["payment"]["id"] == first_payment.get_json()["data"]["payment"]["id"]

    # --- Reusing Invoice A's key against a different invoice conflicts
    invoice_b = _create_invoice(client, owner_csrf, org_id, customer_b["id"], amount="300.00", issue_date=TODAY_ISO)
    _issue(client, owner_csrf, org_id, invoice_b["id"])
    cross_invoice_conflict = _pay(
        client, owner_csrf, org_id, invoice_b["id"], amount="200.00", payment_date=TODAY_ISO, idempotency_key="a-1"
    )
    assert cross_invoice_conflict.status_code == 409
    assert cross_invoice_conflict.get_json()["error"]["code"] == "IDEMPOTENCY_KEY_CONFLICT"

    # --- Invoice A, now fully paid, can never be cancelled - money ----
    # --- already moved ("the Important Invoice Rule") ------------------
    blocked_cancel = client.patch(
        f"/api/v1/organizations/{org_id}/invoices/{invoice_a['id']}/cancel", headers={"X-CSRF-Token": owner_csrf}
    )
    assert blocked_cancel.status_code == 422
    assert blocked_cancel.get_json()["error"]["code"] == "INVALID_STATUS_TRANSITION"

    # --- Invoice B: issued, partially paid, then an overpayment on ----
    # --- the remaining balance is rejected outright --------------------
    partial_payment_b = _pay(
        client, owner_csrf, org_id, invoice_b["id"], amount="120.00", payment_date=TODAY_ISO, idempotency_key="b-1"
    )
    assert partial_payment_b.status_code == 201
    overpayment = _pay(
        client, owner_csrf, org_id, invoice_b["id"], amount="999.00", payment_date=TODAY_ISO, idempotency_key="b-2"
    )
    assert overpayment.status_code == 422
    assert overpayment.get_json()["error"]["code"] == "OVERPAYMENT"

    # --- Invoice C: cancelled while still a draft - never billed, -----
    # --- never counted anywhere below ------------------------------------
    invoice_c = _create_invoice(client, owner_csrf, org_id, customer_c["id"], amount="400.00", issue_date=TODAY_ISO)
    cancel_c = client.patch(
        f"/api/v1/organizations/{org_id}/invoices/{invoice_c['id']}/cancel", headers={"X-CSRF-Token": owner_csrf}
    )
    assert cancel_c.status_code == 200
    assert cancel_c.get_json()["data"]["status"] == "cancelled"

    # --- Invoice D: issued with a due date already in the past, never -
    # --- paid - the lazy overdue refresh must promote it before any ---
    # --- summary endpoint is read -----------------------------------
    invoice_d = _create_invoice(
        client, owner_csrf, org_id, customer_d["id"], amount="150.00", issue_date=TODAY_ISO, due_date=YESTERDAY_ISO
    )
    _issue(client, owner_csrf, org_id, invoice_d["id"])

    # --- Reconciliation #1: the financial-summary endpoint -------------
    # --- total_invoiced/total_collected are all-time (FD-044), so this
    # --- single org-wide call already reflects every invoice above ----
    summary = client.get(
        f"/api/v1/organizations/{org_id}/invoices/financial-summary?period_start={TODAY_ISO}&period_end={TODAY_ISO}",
        headers={"X-CSRF-Token": owner_csrf},
    ).get_json()["data"]
    # A (500, paid) + B (300, sent/partially_paid) + D (150, overdue) -
    # C is cancelled and never counted.
    assert summary["total_invoiced"] == "950.00"
    # A (200 + 300) + B (120) - the idempotency replay never double-counted
    assert summary["total_collected"] == "620.00"
    assert summary["outstanding_balance"] == "330.00"
    assert summary["overdue_invoice_count"] == 1

    # --- Invoice D is now actually `overdue`, not still `sent` ---------
    invoice_d_after = client.get(
        f"/api/v1/organizations/{org_id}/invoices/{invoice_d['id']}", headers={"X-CSRF-Token": owner_csrf}
    ).get_json()["data"]
    assert invoice_d_after["status"] == "overdue"

    # --- Reconciliation #2: analytics/overview computes monthly_invoiced
    # --- / monthly_collected via its OWN, independent query - this is
    # --- exactly the pair of endpoints that could silently drift apart
    overview = client.get(
        f"/api/v1/organizations/{org_id}/analytics/overview?period=custom&period_start={TODAY_ISO}&period_end={TODAY_ISO}",
        headers={"X-CSRF-Token": owner_csrf},
    ).get_json()["data"]
    assert overview["monthly_invoiced"] == "950.00"
    assert overview["monthly_collected"] == "620.00"

    # --- Reconciliation #3: the activity log's own counts must match --
    # --- exactly - 4 invoices created (A/B/C/D), 3 real payments ------
    # --- (a-1, a-2, b-1 - the replayed key and the two rejected calls -
    # --- logged nothing new, since nothing new happened) ----------------
    activity = client.get(
        f"/api/v1/organizations/{org_id}/activity?per_page=50", headers={"X-CSRF-Token": owner_csrf}
    ).get_json()["data"]
    actions = [entry["action"] for entry in activity]
    assert actions.count("invoice_created") == 4
    assert actions.count("payment_recorded") == 3
