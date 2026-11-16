from datetime import date, timedelta

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


def test_a_sent_invoice_past_its_due_date_becomes_overdue_on_get(client, app):
    csrf_token = _register_and_login(client, "owner@example.com")
    org = _create_org(client, csrf_token)
    customer_id = _make_customer(app, org["id"])
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    invoice = _create_invoice(
        client,
        csrf_token,
        org["id"],
        customer_id=customer_id,
        due_date=yesterday,
        line_items=[{"description": "Widget", "quantity": "1", "unit_price": "10.00"}],
    ).get_json()["data"]
    _issue(client, csrf_token, org["id"], invoice["id"])

    response = client.get(f"/api/v1/organizations/{org['id']}/invoices/{invoice['id']}")

    assert response.status_code == 200
    assert response.get_json()["data"]["status"] == "overdue"


def test_a_sent_invoice_not_yet_due_stays_sent(client, app):
    csrf_token = _register_and_login(client, "owner2@example.com")
    org = _create_org(client, csrf_token)
    customer_id = _make_customer(app, org["id"])
    tomorrow = (date.today() + timedelta(days=1)).isoformat()
    invoice = _create_invoice(
        client,
        csrf_token,
        org["id"],
        customer_id=customer_id,
        due_date=tomorrow,
        line_items=[{"description": "Widget", "quantity": "1", "unit_price": "10.00"}],
    ).get_json()["data"]
    _issue(client, csrf_token, org["id"], invoice["id"])

    response = client.get(f"/api/v1/organizations/{org['id']}/invoices/{invoice['id']}")

    assert response.status_code == 200
    assert response.get_json()["data"]["status"] == "sent"


def test_a_draft_invoice_past_its_due_date_does_not_become_overdue(client, app):
    csrf_token = _register_and_login(client, "owner3@example.com")
    org = _create_org(client, csrf_token)
    customer_id = _make_customer(app, org["id"])
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    invoice = _create_invoice(
        client, csrf_token, org["id"], customer_id=customer_id, due_date=yesterday
    ).get_json()["data"]

    response = client.get(f"/api/v1/organizations/{org['id']}/invoices/{invoice['id']}")

    assert response.status_code == 200
    assert response.get_json()["data"]["status"] == "draft"


def test_listing_with_status_overdue_filter_picks_up_a_newly_overdue_invoice(client, app):
    """The bulk-UPDATE refresh runs before the filtered SELECT, so a
    `?status=overdue` filter sees a row that only *just* crossed its
    due date and whose stored column is still stale `sent` - proving
    the refresh isn't limited to whichever single invoice a caller
    happens to GET individually."""
    csrf_token = _register_and_login(client, "owner4@example.com")
    org = _create_org(client, csrf_token)
    customer_id = _make_customer(app, org["id"])
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    invoice = _create_invoice(
        client,
        csrf_token,
        org["id"],
        customer_id=customer_id,
        due_date=yesterday,
        line_items=[{"description": "Widget", "quantity": "1", "unit_price": "10.00"}],
    ).get_json()["data"]
    _issue(client, csrf_token, org["id"], invoice["id"])

    with app.app_context():
        from app.models import Invoice as InvoiceModel

        stored = db.session.get(InvoiceModel, invoice["id"])
        assert stored.status == InvoiceStatus.SENT

    response = client.get(f"/api/v1/organizations/{org['id']}/invoices?status=overdue")

    assert response.status_code == 200
    body = response.get_json()
    assert body["meta"]["total"] == 1
    assert body["data"][0]["id"] == invoice["id"]
