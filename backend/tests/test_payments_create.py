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
    body.setdefault("idempotency_key", "key-1")
    return client.post(
        f"/api/v1/organizations/{org_id}/invoices/{invoice_id}/payments",
        json=body,
        headers={"X-CSRF-Token": csrf_token},
    )


def test_unauthenticated_request_returns_401(client):
    response = client.post(
        "/api/v1/organizations/00000000-0000-0000-0000-000000000000/invoices/"
        "00000000-0000-0000-0000-000000000000/payments",
        json={},
    )
    assert response.status_code == 401


def test_full_payment_marks_the_invoice_paid(client, app):
    csrf_token = _register_and_login(client, "owner@example.com")
    org = _create_org(client, csrf_token)
    customer_id = _make_customer(app, org["id"])
    invoice = _create_and_issue_invoice(client, csrf_token, org["id"], customer_id)

    response = _record_payment(client, csrf_token, org["id"], invoice["id"], amount="100.00")

    assert response.status_code == 201
    body = response.get_json()["data"]
    assert body["payment"]["amount"] == "100.00"
    assert body["invoice"]["status"] == "paid"
    assert body["amount_paid"] == "100.00"
    assert body["balance_due"] == "0.00"


def test_partial_payment_marks_the_invoice_partially_paid(client, app):
    csrf_token = _register_and_login(client, "owner2@example.com")
    org = _create_org(client, csrf_token)
    customer_id = _make_customer(app, org["id"])
    invoice = _create_and_issue_invoice(client, csrf_token, org["id"], customer_id)

    response = _record_payment(client, csrf_token, org["id"], invoice["id"], amount="40.00")

    assert response.status_code == 201
    body = response.get_json()["data"]
    assert body["invoice"]["status"] == "partially_paid"
    assert body["amount_paid"] == "40.00"
    assert body["balance_due"] == "60.00"


def test_two_partial_payments_sum_correctly_and_then_pay_in_full(client, app):
    csrf_token = _register_and_login(client, "owner3@example.com")
    org = _create_org(client, csrf_token)
    customer_id = _make_customer(app, org["id"])
    invoice = _create_and_issue_invoice(client, csrf_token, org["id"], customer_id)

    first = _record_payment(
        client, csrf_token, org["id"], invoice["id"], amount="40.00", idempotency_key="key-a"
    )
    second = _record_payment(
        client, csrf_token, org["id"], invoice["id"], amount="60.00", idempotency_key="key-b"
    )

    assert first.status_code == 201
    assert second.status_code == 201
    body = second.get_json()["data"]
    assert body["invoice"]["status"] == "paid"
    assert body["amount_paid"] == "100.00"
    assert body["balance_due"] == "0.00"


def test_overpayment_is_rejected(client, app):
    csrf_token = _register_and_login(client, "owner4@example.com")
    org = _create_org(client, csrf_token)
    customer_id = _make_customer(app, org["id"])
    invoice = _create_and_issue_invoice(client, csrf_token, org["id"], customer_id)

    response = _record_payment(client, csrf_token, org["id"], invoice["id"], amount="150.00")

    assert response.status_code == 422
    assert response.get_json()["error"]["code"] == "OVERPAYMENT"


def test_a_second_payment_exceeding_the_remaining_balance_is_rejected(client, app):
    csrf_token = _register_and_login(client, "owner5@example.com")
    org = _create_org(client, csrf_token)
    customer_id = _make_customer(app, org["id"])
    invoice = _create_and_issue_invoice(client, csrf_token, org["id"], customer_id)
    _record_payment(client, csrf_token, org["id"], invoice["id"], amount="60.00", idempotency_key="key-a")

    response = _record_payment(client, csrf_token, org["id"], invoice["id"], amount="60.00", idempotency_key="key-b")

    assert response.status_code == 422
    assert response.get_json()["error"]["code"] == "OVERPAYMENT"


def test_payment_against_a_draft_invoice_is_rejected(client, app):
    csrf_token = _register_and_login(client, "owner6@example.com")
    org = _create_org(client, csrf_token)
    customer_id = _make_customer(app, org["id"])
    invoice = client.post(
        f"/api/v1/organizations/{org['id']}/invoices",
        json={"customer_id": customer_id, "currency": "USD"},
        headers={"X-CSRF-Token": csrf_token},
    ).get_json()["data"]

    response = _record_payment(client, csrf_token, org["id"], invoice["id"], amount="10.00")

    assert response.status_code == 422
    assert response.get_json()["error"]["code"] == "INVOICE_NOT_PAYABLE"


def test_payment_against_a_cancelled_invoice_is_rejected(client, app):
    csrf_token = _register_and_login(client, "owner7@example.com")
    org = _create_org(client, csrf_token)
    customer_id = _make_customer(app, org["id"])
    invoice = _create_and_issue_invoice(client, csrf_token, org["id"], customer_id)
    client.patch(
        f"/api/v1/organizations/{org['id']}/invoices/{invoice['id']}/cancel", headers={"X-CSRF-Token": csrf_token}
    )

    response = _record_payment(client, csrf_token, org["id"], invoice["id"], amount="10.00")

    assert response.status_code == 422
    assert response.get_json()["error"]["code"] == "INVOICE_NOT_PAYABLE"


def test_payment_against_an_already_paid_invoice_is_rejected(client, app):
    csrf_token = _register_and_login(client, "owner8@example.com")
    org = _create_org(client, csrf_token)
    customer_id = _make_customer(app, org["id"])
    invoice = _create_and_issue_invoice(client, csrf_token, org["id"], customer_id)
    _record_payment(client, csrf_token, org["id"], invoice["id"], amount="100.00", idempotency_key="key-a")

    response = _record_payment(client, csrf_token, org["id"], invoice["id"], amount="10.00", idempotency_key="key-b")

    assert response.status_code == 422
    assert response.get_json()["error"]["code"] == "INVOICE_NOT_PAYABLE"


def test_replaying_the_same_idempotency_key_does_not_create_a_second_payment(client, app):
    csrf_token = _register_and_login(client, "owner9@example.com")
    org = _create_org(client, csrf_token)
    customer_id = _make_customer(app, org["id"])
    invoice = _create_and_issue_invoice(client, csrf_token, org["id"], customer_id)

    first = _record_payment(
        client, csrf_token, org["id"], invoice["id"], amount="40.00", idempotency_key="replay-key"
    )
    second = _record_payment(
        client, csrf_token, org["id"], invoice["id"], amount="40.00", idempotency_key="replay-key"
    )

    assert first.status_code == 201
    assert second.status_code == 200
    assert first.get_json()["data"]["payment"]["id"] == second.get_json()["data"]["payment"]["id"]

    with app.app_context():
        assert db.session.query(Payment).count() == 1


def test_reusing_an_idempotency_key_with_different_payment_details_is_a_conflict(client, app):
    csrf_token = _register_and_login(client, "owner10@example.com")
    org = _create_org(client, csrf_token)
    customer_id = _make_customer(app, org["id"])
    invoice = _create_and_issue_invoice(client, csrf_token, org["id"], customer_id)
    _record_payment(client, csrf_token, org["id"], invoice["id"], amount="40.00", idempotency_key="reused-key")

    response = _record_payment(
        client, csrf_token, org["id"], invoice["id"], amount="50.00", idempotency_key="reused-key"
    )

    assert response.status_code == 409
    assert response.get_json()["error"]["code"] == "IDEMPOTENCY_KEY_CONFLICT"


def test_reusing_an_idempotency_key_across_different_invoices_is_a_conflict(client, app):
    csrf_token = _register_and_login(client, "owner11@example.com")
    org = _create_org(client, csrf_token)
    customer_id = _make_customer(app, org["id"])
    invoice_1 = _create_and_issue_invoice(client, csrf_token, org["id"], customer_id)
    invoice_2 = _create_and_issue_invoice(client, csrf_token, org["id"], customer_id)
    _record_payment(client, csrf_token, org["id"], invoice_1["id"], amount="40.00", idempotency_key="cross-invoice-key")

    response = _record_payment(
        client, csrf_token, org["id"], invoice_2["id"], amount="40.00", idempotency_key="cross-invoice-key"
    )

    assert response.status_code == 409
    assert response.get_json()["error"]["code"] == "IDEMPOTENCY_KEY_CONFLICT"


def test_amount_must_be_positive(client, app):
    csrf_token = _register_and_login(client, "owner12@example.com")
    org = _create_org(client, csrf_token)
    customer_id = _make_customer(app, org["id"])
    invoice = _create_and_issue_invoice(client, csrf_token, org["id"], customer_id)

    response = _record_payment(client, csrf_token, org["id"], invoice["id"], amount="0.00")

    assert response.status_code == 422


def test_idempotency_key_is_required(client, app):
    csrf_token = _register_and_login(client, "owner13@example.com")
    org = _create_org(client, csrf_token)
    customer_id = _make_customer(app, org["id"])
    invoice = _create_and_issue_invoice(client, csrf_token, org["id"], customer_id)

    response = client.post(
        f"/api/v1/organizations/{org['id']}/invoices/{invoice['id']}/payments",
        json={"amount": "10.00", "payment_date": "2026-01-15", "method": "cash"},
        headers={"X-CSRF-Token": csrf_token},
    )

    assert response.status_code == 422


def test_recorded_by_is_always_the_caller(client, app):
    csrf_token = _register_and_login(client, "owner14@example.com")
    org = _create_org(client, csrf_token)
    customer_id = _make_customer(app, org["id"])
    invoice = _create_and_issue_invoice(client, csrf_token, org["id"], customer_id)

    response = _record_payment(client, csrf_token, org["id"], invoice["id"], amount="10.00")
    payment_id = response.get_json()["data"]["payment"]["id"]

    with app.app_context():
        payment = db.session.get(Payment, payment_id)
        user = db.session.query(User).filter_by(email="owner14@example.com").one()
        creator = db.session.query(Membership).filter_by(user_id=user.id, organization_id=payment.organization_id).one()
        assert str(payment.recorded_by) == str(creator.id)


@pytest.mark.parametrize("role", [MembershipRole.OWNER, MembershipRole.ACCOUNTANT])
def test_roles_with_invoice_payment_manage_can_record_a_payment(client, app, role):
    csrf_token = _register_and_login(client, f"owner-{role.value}@example.com")
    org = _create_org(client, csrf_token)
    customer_id = _make_customer(app, org["id"])
    invoice = _create_and_issue_invoice(client, csrf_token, org["id"], customer_id)
    other_email = f"{role.value}@example.com"
    other_csrf = _register_and_login(client, other_email)
    _give_role(app, org["id"], other_email, role)

    response = _record_payment(client, other_csrf, org["id"], invoice["id"], amount="10.00")

    assert response.status_code == 201


@pytest.mark.parametrize("role", [MembershipRole.MANAGER, MembershipRole.EMPLOYEE, MembershipRole.CUSTOMER_SUPPORT])
def test_roles_without_invoice_payment_manage_cannot_record_a_payment(client, app, role):
    csrf_token = _register_and_login(client, f"owner2-{role.value}@example.com")
    org = _create_org(client, csrf_token)
    customer_id = _make_customer(app, org["id"])
    invoice = _create_and_issue_invoice(client, csrf_token, org["id"], customer_id)
    other_email = f"{role.value}2@example.com"
    other_csrf = _register_and_login(client, other_email)
    _give_role(app, org["id"], other_email, role)

    response = _record_payment(client, other_csrf, org["id"], invoice["id"], amount="10.00")

    assert response.status_code == 403


def test_without_csrf_token_returns_403(client, app):
    csrf_token = _register_and_login(client, "owner15@example.com")
    org = _create_org(client, csrf_token)
    customer_id = _make_customer(app, org["id"])
    invoice = _create_and_issue_invoice(client, csrf_token, org["id"], customer_id)

    response = client.post(
        f"/api/v1/organizations/{org['id']}/invoices/{invoice['id']}/payments",
        json={"amount": "10.00", "payment_date": "2026-01-15", "method": "cash", "idempotency_key": "key-1"},
    )

    assert response.status_code == 403


def test_for_a_cross_org_invoice_returns_404(client, app):
    owner_a_csrf = _register_and_login(client, "ownera@example.com")
    org_a = _create_org(client, owner_a_csrf, name="Org A")
    customer_a = _make_customer(app, org_a["id"])
    invoice_a = _create_and_issue_invoice(client, owner_a_csrf, org_a["id"], customer_a)

    owner_b_csrf = _register_and_login(client, "ownerb@example.com")
    org_b = _create_org(client, owner_b_csrf, name="Org B")

    response = _record_payment(client, owner_b_csrf, org_b["id"], invoice_a["id"], amount="10.00")

    assert response.status_code == 404
