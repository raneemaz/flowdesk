import pytest

from app.extensions import db
from app.models import Customer, CustomerStatus, Invoice, InvoiceLineItem, Membership, MembershipRole, Organization, Payment, User


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


def _create_and_issue_invoice(client, csrf_token, org_id, customer_id, unit_price="100.00"):
    invoice = client.post(
        f"/api/v1/organizations/{org_id}/invoices",
        json={
            "customer_id": customer_id,
            "currency": "USD",
            "line_items": [{"description": "Widget", "quantity": "1", "unit_price": unit_price}],
        },
        headers={"X-CSRF-Token": csrf_token},
    ).get_json()["data"]
    client.patch(
        f"/api/v1/organizations/{org_id}/invoices/{invoice['id']}/issue", headers={"X-CSRF-Token": csrf_token}
    )
    return invoice


def _record_payment(client, csrf_token, org_id, invoice_id, **body):
    body.setdefault("payment_date", "2026-01-15")
    body.setdefault("method", "bank_transfer")
    return client.post(
        f"/api/v1/organizations/{org_id}/invoices/{invoice_id}/payments",
        json=body,
        headers={"X-CSRF-Token": csrf_token},
    )


def test_list_returns_payments_chronologically(client, app):
    csrf_token = _register_and_login(client, "owner@example.com")
    org = _create_org(client, csrf_token)
    customer_id = _make_customer(app, org["id"])
    invoice = _create_and_issue_invoice(client, csrf_token, org["id"], customer_id)
    _record_payment(client, csrf_token, org["id"], invoice["id"], amount="40.00", idempotency_key="key-a")
    _record_payment(client, csrf_token, org["id"], invoice["id"], amount="60.00", idempotency_key="key-b")

    response = client.get(f"/api/v1/organizations/{org['id']}/invoices/{invoice['id']}/payments")

    assert response.status_code == 200
    body = response.get_json()
    assert body["meta"]["total"] == 2
    assert [item["amount"] for item in body["data"]] == ["40.00", "60.00"]


def test_list_is_paginated(client, app):
    csrf_token = _register_and_login(client, "owner2@example.com")
    org = _create_org(client, csrf_token)
    customer_id = _make_customer(app, org["id"])
    invoice = _create_and_issue_invoice(client, csrf_token, org["id"], customer_id, unit_price="300.00")
    for i in range(3):
        _record_payment(
            client, csrf_token, org["id"], invoice["id"], amount="100.00", idempotency_key=f"key-{i}"
        )

    response = client.get(f"/api/v1/organizations/{org['id']}/invoices/{invoice['id']}/payments?page=1&per_page=2")

    assert response.status_code == 200
    body = response.get_json()
    assert len(body["data"]) == 2
    assert body["meta"]["total"] == 3


def test_list_for_a_missing_invoice_returns_404(client, app):
    csrf_token = _register_and_login(client, "owner3@example.com")
    org = _create_org(client, csrf_token)

    response = client.get(
        f"/api/v1/organizations/{org['id']}/invoices/00000000-0000-0000-0000-000000000000/payments"
    )

    assert response.status_code == 404


def test_list_for_a_cross_org_invoice_returns_404(client, app):
    owner_a_csrf = _register_and_login(client, "ownera@example.com")
    org_a = _create_org(client, owner_a_csrf, name="Org A")
    customer_a = _make_customer(app, org_a["id"])
    invoice_a = _create_and_issue_invoice(client, owner_a_csrf, org_a["id"], customer_a)

    owner_b_csrf = _register_and_login(client, "ownerb@example.com")
    org_b = _create_org(client, owner_b_csrf, name="Org B")

    response = client.get(f"/api/v1/organizations/{org_b['id']}/invoices/{invoice_a['id']}/payments")

    assert response.status_code == 404


@pytest.mark.parametrize("role", [MembershipRole.MANAGER, MembershipRole.EMPLOYEE, MembershipRole.CUSTOMER_SUPPORT])
def test_roles_without_invoice_payment_manage_cannot_list_payments(client, app, role):
    csrf_token = _register_and_login(client, f"owner4-{role.value}@example.com")
    org = _create_org(client, csrf_token)
    customer_id = _make_customer(app, org["id"])
    invoice = _create_and_issue_invoice(client, csrf_token, org["id"], customer_id)
    other_email = f"{role.value}4@example.com"
    _register_and_login(client, other_email)
    from app.models import Membership as MembershipModel, MembershipStatus

    with app.app_context():
        user = db.session.query(User).filter_by(email=other_email).one()
        membership = MembershipModel(
            organization_id=org["id"], user_id=user.id, role=role, status=MembershipStatus.ACTIVE
        )
        db.session.add(membership)
        db.session.commit()
    _login(client, other_email)

    response = client.get(f"/api/v1/organizations/{org['id']}/invoices/{invoice['id']}/payments")

    assert response.status_code == 403
