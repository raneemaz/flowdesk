import pytest

from app.extensions import db
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


def _create_invoice(client, csrf_token, org_id, **body):
    body.setdefault("customer_id", None)
    body.setdefault("currency", "USD")
    return client.post(f"/api/v1/organizations/{org_id}/invoices", json=body, headers={"X-CSRF-Token": csrf_token})


def test_list_is_scoped_to_the_organization(client, app):
    owner_a_csrf = _register_and_login(client, "ownera@example.com")
    org_a = _create_org(client, owner_a_csrf, name="Org A")
    customer_a = _make_customer(app, org_a["id"])
    _create_invoice(client, owner_a_csrf, org_a["id"], customer_id=customer_a)

    owner_b_csrf = _register_and_login(client, "ownerb@example.com")
    org_b = _create_org(client, owner_b_csrf, name="Org B")
    customer_b = _make_customer(app, org_b["id"])
    _create_invoice(client, owner_b_csrf, org_b["id"], customer_id=customer_b)

    owner_a_csrf = _login(client, "ownera@example.com")
    response = client.get(f"/api/v1/organizations/{org_a['id']}/invoices")

    assert response.status_code == 200
    body = response.get_json()
    assert body["meta"]["total"] == 1
    assert body["data"][0]["customer_id"] == customer_a


def test_list_filters_by_customer_id(client, app):
    csrf_token = _register_and_login(client, "owner2@example.com")
    org = _create_org(client, csrf_token)
    customer_1 = _make_customer(app, org["id"], name="Customer 1")
    customer_2 = _make_customer(app, org["id"], name="Customer 2")
    _create_invoice(client, csrf_token, org["id"], customer_id=customer_1)
    _create_invoice(client, csrf_token, org["id"], customer_id=customer_2)

    response = client.get(f"/api/v1/organizations/{org['id']}/invoices?customer_id={customer_1}")

    assert response.status_code == 200
    body = response.get_json()
    assert body["meta"]["total"] == 1
    assert body["data"][0]["customer_id"] == customer_1


def test_list_filters_by_status(client, app):
    csrf_token = _register_and_login(client, "owner3@example.com")
    org = _create_org(client, csrf_token)
    customer_id = _make_customer(app, org["id"])
    draft = _create_invoice(client, csrf_token, org["id"], customer_id=customer_id).get_json()["data"]
    sent = _create_invoice(
        client,
        csrf_token,
        org["id"],
        customer_id=customer_id,
        line_items=[{"description": "Widget", "quantity": "1", "unit_price": "10.00"}],
    ).get_json()["data"]
    client.patch(f"/api/v1/organizations/{org['id']}/invoices/{sent['id']}/issue", headers={"X-CSRF-Token": csrf_token})

    response = client.get(f"/api/v1/organizations/{org['id']}/invoices?status=sent")

    assert response.status_code == 200
    body = response.get_json()
    assert body["meta"]["total"] == 1
    assert body["data"][0]["id"] == sent["id"]


def test_list_due_date_range_filter_rejects_inverted_range(client, app):
    csrf_token = _register_and_login(client, "owner4@example.com")
    org = _create_org(client, csrf_token)

    response = client.get(
        f"/api/v1/organizations/{org['id']}/invoices?due_date_from=2026-02-01&due_date_to=2026-01-01"
    )

    assert response.status_code == 422


def test_list_is_paginated(client, app):
    csrf_token = _register_and_login(client, "owner5@example.com")
    org = _create_org(client, csrf_token)
    customer_id = _make_customer(app, org["id"])
    for _ in range(3):
        _create_invoice(client, csrf_token, org["id"], customer_id=customer_id)

    response = client.get(f"/api/v1/organizations/{org['id']}/invoices?page=1&per_page=2")

    assert response.status_code == 200
    body = response.get_json()
    assert len(body["data"]) == 2
    assert body["meta"]["total"] == 3
    assert body["meta"]["total_pages"] == 2


@pytest.mark.parametrize("role", [MembershipRole.MANAGER, MembershipRole.EMPLOYEE, MembershipRole.CUSTOMER_SUPPORT])
def test_roles_without_invoice_payment_manage_cannot_list_invoices(client, app, role):
    csrf_token = _register_and_login(client, f"owner6-{role.value}@example.com")
    org = _create_org(client, csrf_token)
    other_email = f"{role.value}6@example.com"
    _register_and_login(client, other_email)
    _give_role(app, org["id"], other_email, role)
    _login(client, other_email)

    response = client.get(f"/api/v1/organizations/{org['id']}/invoices")

    assert response.status_code == 403


def test_list_in_an_organization_the_caller_does_not_belong_to_returns_404(client, app):
    csrf_token = _register_and_login(client, "owner7@example.com")
    org = _create_org(client, csrf_token)
    _register_and_login(client, "outsider@example.com")

    response = client.get(f"/api/v1/organizations/{org['id']}/invoices")

    assert response.status_code == 404
