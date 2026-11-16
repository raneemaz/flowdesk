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


def _issue(client, csrf_token, org_id, invoice_id):
    return client.patch(
        f"/api/v1/organizations/{org_id}/invoices/{invoice_id}/issue", headers={"X-CSRF-Token": csrf_token}
    )


def test_issue_transitions_draft_to_sent(client, app):
    csrf_token = _register_and_login(client, "owner@example.com")
    org = _create_org(client, csrf_token)
    customer_id = _make_customer(app, org["id"])
    invoice = _create_invoice(
        client,
        csrf_token,
        org["id"],
        customer_id=customer_id,
        line_items=[{"description": "Widget", "quantity": "1", "unit_price": "10.00"}],
    ).get_json()["data"]

    response = _issue(client, csrf_token, org["id"], invoice["id"])

    assert response.status_code == 200
    assert response.get_json()["data"]["status"] == "sent"


def test_issue_rejects_an_invoice_with_no_line_items(client, app):
    csrf_token = _register_and_login(client, "owner2@example.com")
    org = _create_org(client, csrf_token)
    customer_id = _make_customer(app, org["id"])
    invoice = _create_invoice(client, csrf_token, org["id"], customer_id=customer_id).get_json()["data"]

    response = _issue(client, csrf_token, org["id"], invoice["id"])

    assert response.status_code == 422
    assert response.get_json()["error"]["code"] == "EMPTY_INVOICE"


def test_issuing_an_already_issued_invoice_is_rejected_not_a_noop(client, app):
    csrf_token = _register_and_login(client, "owner3@example.com")
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

    response = _issue(client, csrf_token, org["id"], invoice["id"])

    assert response.status_code == 422
    assert response.get_json()["error"]["code"] == "INVALID_STATUS_TRANSITION"


def test_issue_for_a_cross_org_invoice_returns_404(client, app):
    owner_a_csrf = _register_and_login(client, "ownera@example.com")
    org_a = _create_org(client, owner_a_csrf, name="Org A")
    customer_a = _make_customer(app, org_a["id"])
    invoice_a = _create_invoice(client, owner_a_csrf, org_a["id"], customer_id=customer_a).get_json()["data"]

    owner_b_csrf = _register_and_login(client, "ownerb@example.com")
    org_b = _create_org(client, owner_b_csrf, name="Org B")

    response = _issue(client, owner_b_csrf, org_b["id"], invoice_a["id"])

    assert response.status_code == 404
