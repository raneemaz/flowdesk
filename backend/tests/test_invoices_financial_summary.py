from datetime import date, datetime, timedelta, timezone

import pytest

from app.extensions import db
from app.invoices.service import _current_month_bounds
from app.models import (
    Customer,
    CustomerStatus,
    Invoice,
    InvoiceLineItem,
    Membership,
    MembershipRole,
    MembershipStatus,
    Organization,
    Payment,
    User,
)


@pytest.fixture(autouse=True)
def _clean(app):
    yield
    with app.app_context():
        db.session.query(Payment).delete()
        db.session.query(InvoiceLineItem).delete()
        db.session.query(Invoice).delete()
        db.session.query(Customer).delete()
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
    return client.post("/api/v1/organizations", json={"name": name}, headers={"X-CSRF-Token": csrf_token}).get_json()[
        "data"
    ]


def _give_role(app, organization_id, email, role, status=MembershipStatus.ACTIVE):
    with app.app_context():
        user = db.session.query(User).filter_by(email=email).one()
        membership = Membership(organization_id=organization_id, user_id=user.id, role=role, status=status)
        db.session.add(membership)
        db.session.commit()
        return str(membership.id)


def _make_customer(app, organization_id, name="Jane Customer", status=CustomerStatus.ACTIVE):
    with app.app_context():
        import uuid

        customer = Customer(organization_id=uuid.UUID(organization_id), name=name, status=status)
        db.session.add(customer)
        db.session.commit()
        return str(customer.id)


def _create_invoice(client, csrf_token, org_id, customer_id, unit_price="100.00", due_date=None):
    body = {
        "customer_id": customer_id,
        "currency": "USD",
        "line_items": [{"description": "Widget", "quantity": "1", "unit_price": unit_price}],
    }
    if due_date is not None:
        body["due_date"] = due_date
    return client.post(f"/api/v1/organizations/{org_id}/invoices", json=body, headers={"X-CSRF-Token": csrf_token}).get_json()[
        "data"
    ]


def _issue(client, csrf_token, org_id, invoice_id):
    client.patch(f"/api/v1/organizations/{org_id}/invoices/{invoice_id}/issue", headers={"X-CSRF-Token": csrf_token})


def _cancel(client, csrf_token, org_id, invoice_id):
    client.patch(f"/api/v1/organizations/{org_id}/invoices/{invoice_id}/cancel", headers={"X-CSRF-Token": csrf_token})


def _record_payment(client, csrf_token, org_id, invoice_id, amount, payment_date, idempotency_key):
    return client.post(
        f"/api/v1/organizations/{org_id}/invoices/{invoice_id}/payments",
        json={
            "amount": amount,
            "payment_date": payment_date,
            "method": "bank_transfer",
            "idempotency_key": idempotency_key,
        },
        headers={"X-CSRF-Token": csrf_token},
    )


def _get_summary(client, org_id, **params):
    return client.get(f"/api/v1/organizations/{org_id}/invoices/financial-summary", query_string=params)


def _today_utc() -> date:
    """`date.today()` is the OS's own local date, which can differ
    from the app's own UTC-anchored "today" (every test org here
    defaults to `timezone="UTC"`, and overdue detection/month-bounds
    compare against that) for a few hours around local midnight,
    depending on the machine's own timezone offset - using this
    instead keeps a "yesterday"/"today" fixture reliably on the
    correct side of the app's own boundaries regardless of when the
    suite happens to run."""
    return datetime.now(timezone.utc).date()


def test_current_month_bounds_rolls_over_from_december_to_january():
    december_instant = datetime(2026, 12, 15, 12, 0, tzinfo=timezone.utc)

    period_start, period_end = _current_month_bounds("UTC", now=december_instant)

    assert period_start == date(2026, 12, 1)
    assert period_end == date(2026, 12, 31)


def test_unauthenticated_request_returns_401(client):
    response = client.get(
        "/api/v1/organizations/00000000-0000-0000-0000-000000000000/invoices/financial-summary"
    )
    assert response.status_code == 401


def test_totals_exclude_draft_and_cancelled_invoices(client, app):
    csrf_token = _register_and_login(client, "owner@example.com")
    org = _create_org(client, csrf_token)
    customer_id = _make_customer(app, org["id"])

    _create_invoice(client, csrf_token, org["id"], customer_id, unit_price="50.00")  # stays draft
    cancelled = _create_invoice(client, csrf_token, org["id"], customer_id, unit_price="70.00")
    _issue(client, csrf_token, org["id"], cancelled["id"])
    _cancel(client, csrf_token, org["id"], cancelled["id"])
    sent = _create_invoice(client, csrf_token, org["id"], customer_id, unit_price="100.00")
    _issue(client, csrf_token, org["id"], sent["id"])

    response = _get_summary(client, org["id"])

    assert response.status_code == 200
    body = response.get_json()["data"]
    assert body["total_invoiced"] == "100.00"
    assert body["total_collected"] == "0.00"
    assert body["outstanding_balance"] == "100.00"


def test_total_collected_and_outstanding_balance_after_a_partial_payment(client, app):
    csrf_token = _register_and_login(client, "owner2@example.com")
    org = _create_org(client, csrf_token)
    customer_id = _make_customer(app, org["id"])
    invoice = _create_invoice(client, csrf_token, org["id"], customer_id, unit_price="100.00")
    _issue(client, csrf_token, org["id"], invoice["id"])
    _record_payment(client, csrf_token, org["id"], invoice["id"], "40.00", _today_utc().isoformat(), "key-1")

    response = _get_summary(client, org["id"])

    assert response.status_code == 200
    body = response.get_json()["data"]
    assert body["total_invoiced"] == "100.00"
    assert body["total_collected"] == "40.00"
    assert body["outstanding_balance"] == "60.00"


def test_fully_paid_invoice_contributes_zero_outstanding(client, app):
    csrf_token = _register_and_login(client, "owner3@example.com")
    org = _create_org(client, csrf_token)
    customer_id = _make_customer(app, org["id"])
    invoice = _create_invoice(client, csrf_token, org["id"], customer_id, unit_price="100.00")
    _issue(client, csrf_token, org["id"], invoice["id"])
    _record_payment(client, csrf_token, org["id"], invoice["id"], "100.00", _today_utc().isoformat(), "key-1")

    response = _get_summary(client, org["id"])

    assert response.status_code == 200
    body = response.get_json()["data"]
    assert body["total_invoiced"] == "100.00"
    assert body["total_collected"] == "100.00"
    assert body["outstanding_balance"] == "0.00"


def test_overdue_invoice_count_reflects_the_lazy_overdue_refresh(client, app):
    csrf_token = _register_and_login(client, "owner4@example.com")
    org = _create_org(client, csrf_token)
    customer_id = _make_customer(app, org["id"])
    yesterday = (_today_utc() - timedelta(days=1)).isoformat()
    invoice = _create_invoice(client, csrf_token, org["id"], customer_id, unit_price="100.00", due_date=yesterday)
    _issue(client, csrf_token, org["id"], invoice["id"])

    response = _get_summary(client, org["id"])

    assert response.status_code == 200
    assert response.get_json()["data"]["overdue_invoice_count"] == 1


def test_monthly_revenue_collected_defaults_to_the_current_month(client, app):
    csrf_token = _register_and_login(client, "owner5@example.com")
    org = _create_org(client, csrf_token)
    customer_id = _make_customer(app, org["id"])
    invoice = _create_invoice(client, csrf_token, org["id"], customer_id, unit_price="200.00")
    _issue(client, csrf_token, org["id"], invoice["id"])
    older_invoice_date = (_today_utc() - timedelta(days=45)).isoformat()
    _record_payment(client, csrf_token, org["id"], invoice["id"], "30.00", older_invoice_date, "key-old")
    _record_payment(client, csrf_token, org["id"], invoice["id"], "50.00", _today_utc().isoformat(), "key-new")

    response = _get_summary(client, org["id"])

    assert response.status_code == 200
    body = response.get_json()["data"]
    assert body["monthly_revenue_collected"] == "50.00"
    assert body["total_collected"] == "80.00"


def test_period_override_returns_a_different_months_revenue(client, app):
    csrf_token = _register_and_login(client, "owner6@example.com")
    org = _create_org(client, csrf_token)
    customer_id = _make_customer(app, org["id"])
    invoice = _create_invoice(client, csrf_token, org["id"], customer_id, unit_price="200.00")
    _issue(client, csrf_token, org["id"], invoice["id"])
    _record_payment(client, csrf_token, org["id"], invoice["id"], "60.00", "2026-01-15", "key-1")

    response = _get_summary(client, org["id"], period_start="2026-01-01", period_end="2026-01-31")

    assert response.status_code == 200
    body = response.get_json()["data"]
    assert body["monthly_revenue_collected"] == "60.00"
    assert body["period_start"] == "2026-01-01"
    assert body["period_end"] == "2026-01-31"


def test_period_must_be_given_as_both_bounds_or_neither(client, app):
    csrf_token = _register_and_login(client, "owner7@example.com")
    org = _create_org(client, csrf_token)

    response = _get_summary(client, org["id"], period_start="2026-01-01")

    assert response.status_code == 422


def test_period_rejects_an_inverted_range(client, app):
    csrf_token = _register_and_login(client, "owner8@example.com")
    org = _create_org(client, csrf_token)

    response = _get_summary(client, org["id"], period_start="2026-02-01", period_end="2026-01-01")

    assert response.status_code == 422


def test_recent_payments_are_ordered_newest_first(client, app):
    csrf_token = _register_and_login(client, "owner9@example.com")
    org = _create_org(client, csrf_token)
    customer_id = _make_customer(app, org["id"])
    invoice = _create_invoice(client, csrf_token, org["id"], customer_id, unit_price="200.00")
    _issue(client, csrf_token, org["id"], invoice["id"])
    _record_payment(client, csrf_token, org["id"], invoice["id"], "10.00", _today_utc().isoformat(), "key-1")
    _record_payment(client, csrf_token, org["id"], invoice["id"], "20.00", _today_utc().isoformat(), "key-2")

    response = _get_summary(client, org["id"])

    assert response.status_code == 200
    amounts = [p["amount"] for p in response.get_json()["data"]["recent_payments"]]
    assert amounts == ["20.00", "10.00"]


def test_summary_is_scoped_to_the_organization(client, app):
    owner_a_csrf = _register_and_login(client, "ownera@example.com")
    org_a = _create_org(client, owner_a_csrf, name="Org A")
    customer_a = _make_customer(app, org_a["id"])
    invoice_a = _create_invoice(client, owner_a_csrf, org_a["id"], customer_a, unit_price="100.00")
    _issue(client, owner_a_csrf, org_a["id"], invoice_a["id"])

    owner_b_csrf = _register_and_login(client, "ownerb@example.com")
    org_b = _create_org(client, owner_b_csrf, name="Org B")
    customer_b = _make_customer(app, org_b["id"])
    invoice_b = _create_invoice(client, owner_b_csrf, org_b["id"], customer_b, unit_price="500.00")
    _issue(client, owner_b_csrf, org_b["id"], invoice_b["id"])

    owner_a_csrf = _login(client, "ownera@example.com")
    response = _get_summary(client, org_a["id"])

    assert response.status_code == 200
    assert response.get_json()["data"]["total_invoiced"] == "100.00"


def test_organization_the_caller_does_not_belong_to_returns_404(client, app):
    csrf_token = _register_and_login(client, "owner10@example.com")
    org = _create_org(client, csrf_token)
    _register_and_login(client, "outsider@example.com")

    response = _get_summary(client, org["id"])

    assert response.status_code == 404


@pytest.mark.parametrize("role", [MembershipRole.OWNER, MembershipRole.ACCOUNTANT])
def test_roles_with_financial_reports_view_can_see_the_summary(client, app, role):
    csrf_token = _register_and_login(client, f"owner-{role.value}@example.com")
    org = _create_org(client, csrf_token)
    other_email = f"{role.value}@example.com"
    other_csrf = _register_and_login(client, other_email)
    _give_role(app, org["id"], other_email, role)

    response = _get_summary(client, org["id"])

    assert response.status_code == 200


@pytest.mark.parametrize("role", [MembershipRole.MANAGER, MembershipRole.EMPLOYEE, MembershipRole.CUSTOMER_SUPPORT])
def test_roles_without_financial_reports_view_cannot_see_the_summary(client, app, role):
    csrf_token = _register_and_login(client, f"owner2-{role.value}@example.com")
    org = _create_org(client, csrf_token)
    other_email = f"{role.value}2@example.com"
    other_csrf = _register_and_login(client, other_email)
    _give_role(app, org["id"], other_email, role)

    response = _get_summary(client, org["id"])

    assert response.status_code == 403
