import pytest

from app.extensions import db
from app.models import Customer, CustomerStatus, Invoice, InvoiceLineItem, InvoiceStatus, Membership, Organization, Payment, User


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


def _make_customer(app, organization_id, name="Jane Customer", status=CustomerStatus.ACTIVE):
    with app.app_context():
        import uuid

        customer = Customer(organization_id=uuid.UUID(organization_id), name=name, status=status)
        db.session.add(customer)
        db.session.commit()
        return str(customer.id)


def _create_invoice(client, csrf_token, org_id, **body):
    body.setdefault("customer_id", None)
    body.setdefault("currency", "USD")
    return client.post(f"/api/v1/organizations/{org_id}/invoices", json=body, headers={"X-CSRF-Token": csrf_token})


def _issue(client, csrf_token, org_id, invoice_id):
    return client.patch(
        f"/api/v1/organizations/{org_id}/invoices/{invoice_id}/issue", headers={"X-CSRF-Token": csrf_token}
    )


def _cancel(client, csrf_token, org_id, invoice_id):
    return client.patch(
        f"/api/v1/organizations/{org_id}/invoices/{invoice_id}/cancel", headers={"X-CSRF-Token": csrf_token}
    )


def _force_status(app, invoice_id, status):
    """Test-only shortcut: FD-043 (payment recording) doesn't exist yet,
    so partially_paid/paid can't be reached through the real API. This
    directly sets the column to exercise cancel_invoice's own blocking
    rule for those two statuses ahead of that task existing."""
    with app.app_context():
        invoice = db.session.get(Invoice, invoice_id)
        invoice.status = status
        db.session.commit()


def test_cancel_a_draft_invoice(client, app):
    csrf_token = _register_and_login(client, "owner@example.com")
    org = _create_org(client, csrf_token)
    customer_id = _make_customer(app, org["id"])
    invoice = _create_invoice(client, csrf_token, org["id"], customer_id=customer_id).get_json()["data"]

    response = _cancel(client, csrf_token, org["id"], invoice["id"])

    assert response.status_code == 200
    assert response.get_json()["data"]["status"] == "cancelled"


def test_cancel_a_sent_invoice(client, app):
    csrf_token = _register_and_login(client, "owner2@example.com")
    org = _create_org(client, csrf_token)
    customer_id = _make_customer(app, org["id"])
    invoice = _create_invoice(
        client,
        csrf_token,
        org["id"],
        customer_id=customer_id,
        line_items=[{"description": "Widget", "quantity": "1", "unit_price": "10.00"}],
    ).get_json()["data"]
    _issue(client, csrf_token, org["id"], invoice["id"])

    response = _cancel(client, csrf_token, org["id"], invoice["id"])

    assert response.status_code == 200
    assert response.get_json()["data"]["status"] == "cancelled"


def test_cancel_is_idempotent(client, app):
    csrf_token = _register_and_login(client, "owner3@example.com")
    org = _create_org(client, csrf_token)
    customer_id = _make_customer(app, org["id"])
    invoice = _create_invoice(client, csrf_token, org["id"], customer_id=customer_id).get_json()["data"]
    _cancel(client, csrf_token, org["id"], invoice["id"])

    response = _cancel(client, csrf_token, org["id"], invoice["id"])

    assert response.status_code == 200
    assert response.get_json()["data"]["status"] == "cancelled"


@pytest.mark.parametrize("status", [InvoiceStatus.PARTIALLY_PAID, InvoiceStatus.PAID])
def test_cancel_is_blocked_once_a_payment_has_been_recorded(client, app, status):
    csrf_token = _register_and_login(client, f"owner4-{status.value}@example.com")
    org = _create_org(client, csrf_token)
    customer_id = _make_customer(app, org["id"])
    invoice = _create_invoice(
        client,
        csrf_token,
        org["id"],
        customer_id=customer_id,
        line_items=[{"description": "Widget", "quantity": "1", "unit_price": "10.00"}],
    ).get_json()["data"]
    _issue(client, csrf_token, org["id"], invoice["id"])
    _force_status(app, invoice["id"], status)

    response = _cancel(client, csrf_token, org["id"], invoice["id"])

    assert response.status_code == 422
    assert response.get_json()["error"]["code"] == "INVALID_STATUS_TRANSITION"


def test_cancel_for_a_cross_org_invoice_returns_404(client, app):
    owner_a_csrf = _register_and_login(client, "ownera@example.com")
    org_a = _create_org(client, owner_a_csrf, name="Org A")
    customer_a = _make_customer(app, org_a["id"])
    invoice_a = _create_invoice(client, owner_a_csrf, org_a["id"], customer_id=customer_a).get_json()["data"]

    owner_b_csrf = _register_and_login(client, "ownerb@example.com")
    org_b = _create_org(client, owner_b_csrf, name="Org B")

    response = _cancel(client, owner_b_csrf, org_b["id"], invoice_a["id"])

    assert response.status_code == 404
