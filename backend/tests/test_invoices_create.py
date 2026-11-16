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


def test_unauthenticated_request_returns_401(client):
    response = client.post(
        "/api/v1/organizations/00000000-0000-0000-0000-000000000000/invoices", json={}
    )
    assert response.status_code == 401


def test_owner_can_create_a_draft_invoice_with_no_line_items(client, app):
    csrf_token = _register_and_login(client, "owner@example.com")
    org = _create_org(client, csrf_token)
    customer_id = _make_customer(app, org["id"])

    response = _create_invoice(client, csrf_token, org["id"], customer_id=customer_id)

    assert response.status_code == 201
    body = response.get_json()["data"]
    assert body["status"] == "draft"
    assert body["customer_id"] == customer_id
    assert body["invoice_number"] == "INV-0001"
    assert body["subtotal"] == "0.00"
    assert body["total"] == "0.00"
    assert body["discount_type"] == "flat"


def test_create_computes_totals_from_line_items(client, app):
    csrf_token = _register_and_login(client, "owner2@example.com")
    org = _create_org(client, csrf_token)
    customer_id = _make_customer(app, org["id"])

    response = _create_invoice(
        client,
        csrf_token,
        org["id"],
        customer_id=customer_id,
        line_items=[
            {"description": "Widget", "quantity": "2", "unit_price": "10.00", "tax_rate": "10"},
            {"description": "Gadget", "quantity": "1", "unit_price": "5.00"},
        ],
    )

    assert response.status_code == 201
    body = response.get_json()["data"]
    assert body["subtotal"] == "25.00"
    assert body["tax_total"] == "2.00"
    assert body["total"] == "27.00"


def test_create_applies_a_percentage_discount(client, app):
    csrf_token = _register_and_login(client, "owner3@example.com")
    org = _create_org(client, csrf_token)
    customer_id = _make_customer(app, org["id"])

    response = _create_invoice(
        client,
        csrf_token,
        org["id"],
        customer_id=customer_id,
        discount_type="percentage",
        discount_value="10.00",
        line_items=[{"description": "Widget", "quantity": "1", "unit_price": "100.00"}],
    )

    assert response.status_code == 201
    body = response.get_json()["data"]
    assert body["discount_total"] == "10.00"
    assert body["total"] == "90.00"


def test_create_rejects_a_discount_that_would_make_the_total_negative(client, app):
    csrf_token = _register_and_login(client, "owner4@example.com")
    org = _create_org(client, csrf_token)
    customer_id = _make_customer(app, org["id"])

    response = _create_invoice(
        client,
        csrf_token,
        org["id"],
        customer_id=customer_id,
        discount_type="flat",
        discount_value="500.00",
        line_items=[{"description": "Widget", "quantity": "1", "unit_price": "100.00"}],
    )

    assert response.status_code == 422
    assert response.get_json()["error"]["code"] == "NEGATIVE_TOTAL"


def test_create_rejects_a_negative_line_item_unit_price(client, app):
    csrf_token = _register_and_login(client, "owner5@example.com")
    org = _create_org(client, csrf_token)
    customer_id = _make_customer(app, org["id"])

    response = _create_invoice(
        client,
        csrf_token,
        org["id"],
        customer_id=customer_id,
        line_items=[{"description": "Widget", "quantity": "1", "unit_price": "-5.00"}],
    )

    assert response.status_code == 422


def test_create_rejects_a_percentage_discount_over_100(client, app):
    csrf_token = _register_and_login(client, "owner6b@example.com")
    org = _create_org(client, csrf_token)
    customer_id = _make_customer(app, org["id"])

    response = _create_invoice(
        client,
        csrf_token,
        org["id"],
        customer_id=customer_id,
        discount_type="percentage",
        discount_value="150.00",
        line_items=[{"description": "Widget", "quantity": "1", "unit_price": "100.00", "tax_rate": "60"}],
    )

    assert response.status_code == 422


def test_create_rejects_a_zero_or_negative_quantity(client, app):
    csrf_token = _register_and_login(client, "owner6@example.com")
    org = _create_org(client, csrf_token)
    customer_id = _make_customer(app, org["id"])

    response = _create_invoice(
        client,
        csrf_token,
        org["id"],
        customer_id=customer_id,
        line_items=[{"description": "Widget", "quantity": "0", "unit_price": "5.00"}],
    )

    assert response.status_code == 422


def test_create_normalizes_currency_to_uppercase(client, app):
    csrf_token = _register_and_login(client, "owner7@example.com")
    org = _create_org(client, csrf_token)
    customer_id = _make_customer(app, org["id"])

    response = _create_invoice(client, csrf_token, org["id"], customer_id=customer_id, currency="usd")

    assert response.status_code == 201
    assert response.get_json()["data"]["currency"] == "USD"


def test_invoice_numbers_increment_sequentially_per_organization(client, app):
    csrf_token = _register_and_login(client, "owner8@example.com")
    org = _create_org(client, csrf_token)
    customer_id = _make_customer(app, org["id"])

    first = _create_invoice(client, csrf_token, org["id"], customer_id=customer_id).get_json()["data"]
    second = _create_invoice(client, csrf_token, org["id"], customer_id=customer_id).get_json()["data"]

    assert first["invoice_number"] == "INV-0001"
    assert second["invoice_number"] == "INV-0002"


def test_invoice_numbers_can_repeat_across_different_organizations(client, app):
    owner_a_csrf = _register_and_login(client, "owner9a@example.com")
    org_a = _create_org(client, owner_a_csrf, name="Org A")
    customer_a = _make_customer(app, org_a["id"])
    owner_b_csrf = _register_and_login(client, "owner9b@example.com")
    org_b = _create_org(client, owner_b_csrf, name="Org B")
    customer_b = _make_customer(app, org_b["id"])

    owner_a_csrf = _login(client, "owner9a@example.com")
    invoice_a = _create_invoice(client, owner_a_csrf, org_a["id"], customer_id=customer_a).get_json()["data"]
    owner_b_csrf = _login(client, "owner9b@example.com")
    invoice_b = _create_invoice(client, owner_b_csrf, org_b["id"], customer_id=customer_b).get_json()["data"]

    assert invoice_a["invoice_number"] == "INV-0001"
    assert invoice_b["invoice_number"] == "INV-0001"


@pytest.mark.parametrize("role", [MembershipRole.OWNER, MembershipRole.ACCOUNTANT])
def test_roles_with_invoice_payment_manage_can_create_an_invoice(client, app, role):
    csrf_token = _register_and_login(client, f"owner-{role.value}@example.com")
    org = _create_org(client, csrf_token)
    customer_id = _make_customer(app, org["id"])
    other_email = f"{role.value}@example.com"
    other_csrf = _register_and_login(client, other_email)
    _give_role(app, org["id"], other_email, role)

    response = _create_invoice(client, other_csrf, org["id"], customer_id=customer_id)

    assert response.status_code == 201


@pytest.mark.parametrize("role", [MembershipRole.MANAGER, MembershipRole.EMPLOYEE, MembershipRole.CUSTOMER_SUPPORT])
def test_roles_without_invoice_payment_manage_cannot_create_an_invoice(client, app, role):
    csrf_token = _register_and_login(client, f"owner2-{role.value}@example.com")
    org = _create_org(client, csrf_token)
    customer_id = _make_customer(app, org["id"])
    other_email = f"{role.value}2@example.com"
    other_csrf = _register_and_login(client, other_email)
    _give_role(app, org["id"], other_email, role)

    response = _create_invoice(client, other_csrf, org["id"], customer_id=customer_id)

    assert response.status_code == 403


def test_create_without_csrf_token_returns_403(client, app):
    csrf_token = _register_and_login(client, "owner10@example.com")
    org = _create_org(client, csrf_token)
    customer_id = _make_customer(app, org["id"])

    response = client.post(
        f"/api/v1/organizations/{org['id']}/invoices", json={"customer_id": customer_id, "currency": "USD"}
    )

    assert response.status_code == 403


def test_create_in_an_organization_the_caller_does_not_belong_to_returns_404(client, app):
    csrf_token = _register_and_login(client, "owner11@example.com")
    org = _create_org(client, csrf_token)
    customer_id = _make_customer(app, org["id"])
    outsider_csrf = _register_and_login(client, "outsider@example.com")

    response = _create_invoice(client, outsider_csrf, org["id"], customer_id=customer_id)

    assert response.status_code == 404


def test_create_rejects_an_unknown_customer_id(client):
    csrf_token = _register_and_login(client, "owner12@example.com")
    org = _create_org(client, csrf_token)

    response = _create_invoice(
        client, csrf_token, org["id"], customer_id="00000000-0000-0000-0000-000000000000"
    )

    assert response.status_code == 422
    assert response.get_json()["error"]["code"] == "INVALID_CUSTOMER"


def test_create_rejects_a_cross_org_customer_id(client, app):
    owner_a_csrf = _register_and_login(client, "owner13a@example.com")
    org_a = _create_org(client, owner_a_csrf, name="Org A")
    owner_b_csrf = _register_and_login(client, "owner13b@example.com")
    org_b = _create_org(client, owner_b_csrf, name="Org B")
    foreign_customer_id = _make_customer(app, org_b["id"])
    owner_a_csrf = _login(client, "owner13a@example.com")

    response = _create_invoice(client, owner_a_csrf, org_a["id"], customer_id=foreign_customer_id)

    assert response.status_code == 422
    assert response.get_json()["error"]["code"] == "INVALID_CUSTOMER"


def test_create_rejects_an_archived_customer_id(client, app):
    csrf_token = _register_and_login(client, "owner14@example.com")
    org = _create_org(client, csrf_token)
    archived_customer_id = _make_customer(app, org["id"], status=CustomerStatus.ARCHIVED)

    response = _create_invoice(client, csrf_token, org["id"], customer_id=archived_customer_id)

    assert response.status_code == 422
    assert response.get_json()["error"]["code"] == "INVALID_CUSTOMER"


def test_create_rejects_unknown_fields(client, app):
    csrf_token = _register_and_login(client, "owner15@example.com")
    org = _create_org(client, csrf_token)
    customer_id = _make_customer(app, org["id"])

    response = _create_invoice(client, csrf_token, org["id"], customer_id=customer_id, status="sent")

    assert response.status_code == 422


def test_create_sets_created_by_to_the_caller_regardless_of_body(client, app):
    csrf_token = _register_and_login(client, "owner16@example.com")
    org = _create_org(client, csrf_token)
    customer_id = _make_customer(app, org["id"])

    response = _create_invoice(client, csrf_token, org["id"], customer_id=customer_id)
    assert response.status_code == 201
    invoice_id = response.get_json()["data"]["id"]

    with app.app_context():
        invoice = db.session.get(Invoice, invoice_id)
        user = db.session.query(User).filter_by(email="owner16@example.com").one()
        creator_membership = (
            db.session.query(Membership).filter_by(user_id=user.id, organization_id=invoice.organization_id).one()
        )
        assert str(invoice.created_by) == str(creator_membership.id)
