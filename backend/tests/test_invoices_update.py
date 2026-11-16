import pytest

from app.extensions import db
from app.models import Customer, CustomerStatus, Invoice, InvoiceLineItem, Membership, Organization, Payment, User


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


def _patch_invoice(client, csrf_token, org_id, invoice_id, **body):
    return client.patch(
        f"/api/v1/organizations/{org_id}/invoices/{invoice_id}", json=body, headers={"X-CSRF-Token": csrf_token}
    )


def _issue(client, csrf_token, org_id, invoice_id):
    return client.patch(
        f"/api/v1/organizations/{org_id}/invoices/{invoice_id}/issue", headers={"X-CSRF-Token": csrf_token}
    )


def test_patch_updates_notes_and_due_date(client, app):
    csrf_token = _register_and_login(client, "owner@example.com")
    org = _create_org(client, csrf_token)
    customer_id = _make_customer(app, org["id"])
    invoice = _create_invoice(client, csrf_token, org["id"], customer_id=customer_id).get_json()["data"]

    response = _patch_invoice(
        client, csrf_token, org["id"], invoice["id"], notes="Thanks for your business", due_date="2026-03-01"
    )

    assert response.status_code == 200
    body = response.get_json()["data"]
    assert body["notes"] == "Thanks for your business"
    assert body["due_date"] == "2026-03-01"


def test_patch_replaces_line_items_and_recalculates_totals(client, app):
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
    assert invoice["total"] == "10.00"

    response = _patch_invoice(
        client,
        csrf_token,
        org["id"],
        invoice["id"],
        line_items=[{"description": "Gizmo", "quantity": "2", "unit_price": "20.00"}],
    )

    assert response.status_code == 200
    body = response.get_json()["data"]
    assert body["subtotal"] == "40.00"
    assert body["total"] == "40.00"


def test_patch_updates_discount_and_recalculates(client, app):
    csrf_token = _register_and_login(client, "owner3@example.com")
    org = _create_org(client, csrf_token)
    customer_id = _make_customer(app, org["id"])
    invoice = _create_invoice(
        client,
        csrf_token,
        org["id"],
        customer_id=customer_id,
        line_items=[{"description": "Widget", "quantity": "1", "unit_price": "100.00"}],
    ).get_json()["data"]

    response = _patch_invoice(
        client, csrf_token, org["id"], invoice["id"], discount_type="flat", discount_value="20.00"
    )

    assert response.status_code == 200
    body = response.get_json()["data"]
    assert body["discount_total"] == "20.00"
    assert body["total"] == "80.00"


def test_patch_rejects_a_percentage_discount_over_100_set_together(client, app):
    csrf_token = _register_and_login(client, "owner4b@example.com")
    org = _create_org(client, csrf_token)
    customer_id = _make_customer(app, org["id"])
    invoice = _create_invoice(client, csrf_token, org["id"], customer_id=customer_id).get_json()["data"]

    response = _patch_invoice(
        client, csrf_token, org["id"], invoice["id"], discount_type="percentage", discount_value="150.00"
    )

    assert response.status_code == 422


def test_patch_rejects_a_percentage_discount_over_100_against_an_already_percentage_invoice(client, app):
    """The schema can only catch this when both fields are sent
    together in the same request - this exercises the authoritative
    service-layer guard (recalculate_invoice) instead, by first setting
    discount_type=percentage, then PATCHing only discount_value in a
    separate request."""
    csrf_token = _register_and_login(client, "owner4c@example.com")
    org = _create_org(client, csrf_token)
    customer_id = _make_customer(app, org["id"])
    invoice = _create_invoice(client, csrf_token, org["id"], customer_id=customer_id).get_json()["data"]
    _patch_invoice(client, csrf_token, org["id"], invoice["id"], discount_type="percentage", discount_value="10.00")

    response = _patch_invoice(client, csrf_token, org["id"], invoice["id"], discount_value="150.00")

    assert response.status_code == 422
    assert response.get_json()["error"]["code"] == "INVALID_DISCOUNT"


def test_patch_rejects_a_negative_discount_value(client, app):
    csrf_token = _register_and_login(client, "owner4@example.com")
    org = _create_org(client, csrf_token)
    customer_id = _make_customer(app, org["id"])
    invoice = _create_invoice(client, csrf_token, org["id"], customer_id=customer_id).get_json()["data"]

    response = _patch_invoice(client, csrf_token, org["id"], invoice["id"], discount_value="-5.00")

    assert response.status_code == 422


def test_patch_once_issued_is_locked(client, app):
    csrf_token = _register_and_login(client, "owner5@example.com")
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

    response = _patch_invoice(client, csrf_token, org["id"], invoice["id"], notes="too late")

    assert response.status_code == 422
    assert response.get_json()["error"]["code"] == "INVOICE_LOCKED"


def test_patch_rejects_an_unknown_customer_id(client, app):
    csrf_token = _register_and_login(client, "owner6@example.com")
    org = _create_org(client, csrf_token)
    customer_id = _make_customer(app, org["id"])
    invoice = _create_invoice(client, csrf_token, org["id"], customer_id=customer_id).get_json()["data"]

    response = _patch_invoice(
        client, csrf_token, org["id"], invoice["id"], customer_id="00000000-0000-0000-0000-000000000000"
    )

    assert response.status_code == 422
    assert response.get_json()["error"]["code"] == "INVALID_CUSTOMER"


def test_patch_rejects_invoice_number_field(client, app):
    csrf_token = _register_and_login(client, "owner7@example.com")
    org = _create_org(client, csrf_token)
    customer_id = _make_customer(app, org["id"])
    invoice = _create_invoice(client, csrf_token, org["id"], customer_id=customer_id).get_json()["data"]

    response = _patch_invoice(client, csrf_token, org["id"], invoice["id"], invoice_number="INV-9999")

    assert response.status_code == 422


def test_patch_rejects_status_field(client, app):
    csrf_token = _register_and_login(client, "owner8@example.com")
    org = _create_org(client, csrf_token)
    customer_id = _make_customer(app, org["id"])
    invoice = _create_invoice(client, csrf_token, org["id"], customer_id=customer_id).get_json()["data"]

    response = _patch_invoice(client, csrf_token, org["id"], invoice["id"], status="sent")

    assert response.status_code == 422


def test_patch_for_a_cross_org_invoice_returns_404(client, app):
    owner_a_csrf = _register_and_login(client, "ownera@example.com")
    org_a = _create_org(client, owner_a_csrf, name="Org A")
    customer_a = _make_customer(app, org_a["id"])
    invoice_a = _create_invoice(client, owner_a_csrf, org_a["id"], customer_id=customer_a).get_json()["data"]

    owner_b_csrf = _register_and_login(client, "ownerb@example.com")
    org_b = _create_org(client, owner_b_csrf, name="Org B")

    response = _patch_invoice(client, owner_b_csrf, org_b["id"], invoice_a["id"], notes="nope")

    assert response.status_code == 404
