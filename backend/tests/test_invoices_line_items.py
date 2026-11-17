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


def _give_role(app, organization_id, email, role):
    with app.app_context():
        user = db.session.query(User).filter_by(email=email).one()
        membership = Membership(organization_id=organization_id, user_id=user.id, role=role, status=MembershipStatus.ACTIVE)
        db.session.add(membership)
        db.session.commit()


def _make_customer(app, organization_id, name="Jane Customer", status=CustomerStatus.ACTIVE):
    with app.app_context():
        import uuid

        customer = Customer(organization_id=uuid.UUID(organization_id), name=name, status=status)
        db.session.add(customer)
        db.session.commit()
        return str(customer.id)


def _create_invoice(client, csrf_token, org_id, customer_id, line_items):
    return client.post(
        f"/api/v1/organizations/{org_id}/invoices",
        json={"customer_id": customer_id, "currency": "USD", "line_items": line_items},
        headers={"X-CSRF-Token": csrf_token},
    ).get_json()["data"]


def test_line_items_returns_what_was_created(client, app):
    csrf_token = _register_and_login(client, "owner@example.com")
    org = _create_org(client, csrf_token)
    customer_id = _make_customer(app, org["id"])
    invoice = _create_invoice(
        client,
        csrf_token,
        org["id"],
        customer_id,
        [
            {"description": "Widget", "quantity": "2", "unit_price": "10.00", "tax_rate": "8.25"},
            {"description": "Gadget", "quantity": "1", "unit_price": "5.00"},
        ],
    )

    response = client.get(f"/api/v1/organizations/{org['id']}/invoices/{invoice['id']}/line-items")

    assert response.status_code == 200
    body = response.get_json()["data"]
    assert len(body) == 2
    assert body[0]["description"] == "Widget"
    assert body[0]["quantity"] == "2.00"
    assert body[0]["unit_price"] == "10.00"
    assert body[0]["tax_rate"] == "8.25"
    assert body[0]["line_total"] == "20.00"
    assert body[1]["description"] == "Gadget"
    assert body[1]["tax_rate"] is None


def test_line_items_for_a_draft_with_none_is_an_empty_list(client, app):
    csrf_token = _register_and_login(client, "owner2@example.com")
    org = _create_org(client, csrf_token)
    customer_id = _make_customer(app, org["id"])
    invoice = _create_invoice(client, csrf_token, org["id"], customer_id, [])

    response = client.get(f"/api/v1/organizations/{org['id']}/invoices/{invoice['id']}/line-items")

    assert response.status_code == 200
    assert response.get_json()["data"] == []


def test_line_items_for_a_missing_invoice_returns_404(client, app):
    csrf_token = _register_and_login(client, "owner3@example.com")
    org = _create_org(client, csrf_token)

    response = client.get(
        f"/api/v1/organizations/{org['id']}/invoices/00000000-0000-0000-0000-000000000000/line-items"
    )

    assert response.status_code == 404


def test_line_items_for_a_cross_org_invoice_returns_404(client, app):
    owner_a_csrf = _register_and_login(client, "ownera@example.com")
    org_a = _create_org(client, owner_a_csrf, name="Org A")
    customer_a = _make_customer(app, org_a["id"])
    invoice_a = _create_invoice(client, owner_a_csrf, org_a["id"], customer_a, [])

    owner_b_csrf = _register_and_login(client, "ownerb@example.com")
    org_b = _create_org(client, owner_b_csrf, name="Org B")

    response = client.get(f"/api/v1/organizations/{org_b['id']}/invoices/{invoice_a['id']}/line-items")

    assert response.status_code == 404


@pytest.mark.parametrize("role", [MembershipRole.MANAGER, MembershipRole.EMPLOYEE, MembershipRole.CUSTOMER_SUPPORT])
def test_roles_without_invoice_payment_manage_cannot_view_line_items(client, app, role):
    csrf_token = _register_and_login(client, f"owner-{role.value}@example.com")
    org = _create_org(client, csrf_token)
    customer_id = _make_customer(app, org["id"])
    invoice = _create_invoice(client, csrf_token, org["id"], customer_id, [])
    other_email = f"{role.value}@example.com"
    other_csrf = _register_and_login(client, other_email)
    _give_role(app, org["id"], other_email, role)

    response = client.get(f"/api/v1/organizations/{org['id']}/invoices/{invoice['id']}/line-items")

    assert response.status_code == 403
