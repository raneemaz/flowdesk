import uuid

import pytest

from app.extensions import db
from app.models import Customer, Membership, MembershipRole, Organization, User


@pytest.fixture(autouse=True)
def _clean(app):
    yield
    with app.app_context():
        db.session.query(Customer).delete()
        db.session.query(Membership).delete()
        db.session.query(Organization).delete()
        db.session.query(User).delete()
        db.session.commit()


def _login(client, email, password="correct horse battery"):
    login_response = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    return login_response.get_json()["data"]["csrf_token"]


def _register_and_login(client, email, password="correct horse battery"):
    client.post("/api/v1/auth/register", json={"name": "Test User", "email": email, "password": password})
    return _login(client, email, password)


def _create_org(client, csrf_token, name="Org One"):
    return client.post(
        "/api/v1/organizations", json={"name": name}, headers={"X-CSRF-Token": csrf_token}
    ).get_json()["data"]


def _give_role(app, organization_id, email, role):
    with app.app_context():
        user = db.session.query(User).filter_by(email=email).one()
        membership = Membership(organization_id=organization_id, user_id=user.id, role=role)
        db.session.add(membership)
        db.session.commit()
        return str(membership.id)


def _create_customer(client, csrf_token, org_id, **body):
    body.setdefault("name", "Jane Customer")
    return client.post(
        f"/api/v1/organizations/{org_id}/customers", json=body, headers={"X-CSRF-Token": csrf_token}
    ).get_json()["data"]


def _update(client, csrf_token, org_id, customer_id, **body):
    return client.patch(
        f"/api/v1/organizations/{org_id}/customers/{customer_id}", json=body, headers={"X-CSRF-Token": csrf_token}
    )


def test_owner_can_update_the_name(client):
    csrf_token = _register_and_login(client, "owner@example.com")
    org = _create_org(client, csrf_token)
    customer = _create_customer(client, csrf_token, org["id"])

    response = _update(client, csrf_token, org["id"], customer["id"], name="Jane Updated")

    assert response.status_code == 200
    assert response.get_json()["data"]["name"] == "Jane Updated"


def test_owner_can_update_multiple_fields_at_once(client):
    csrf_token = _register_and_login(client, "owner2@example.com")
    org = _create_org(client, csrf_token)
    customer = _create_customer(client, csrf_token, org["id"])

    response = _update(
        client,
        csrf_token,
        org["id"],
        customer["id"],
        email="new@example.com",
        phone="555-9999",
        company="New Co",
    )

    assert response.status_code == 200
    body = response.get_json()["data"]
    assert body["email"] == "new@example.com"
    assert body["phone"] == "555-9999"
    assert body["company"] == "New Co"


@pytest.mark.parametrize("role", [MembershipRole.MANAGER, MembershipRole.ACCOUNTANT, MembershipRole.CUSTOMER_SUPPORT])
def test_roles_with_customer_manage_can_update_a_customer(client, app, role):
    csrf_token = _register_and_login(client, f"owner-{role.value}@example.com")
    org = _create_org(client, csrf_token)
    customer = _create_customer(client, csrf_token, org["id"])
    other_email = f"{role.value}@example.com"
    other_csrf = _register_and_login(client, other_email)
    _give_role(app, org["id"], other_email, role)

    response = _update(client, other_csrf, org["id"], customer["id"], name="Updated")

    assert response.status_code == 200


def test_employee_cannot_update_a_customer(client, app):
    csrf_token = _register_and_login(client, "owner3@example.com")
    org = _create_org(client, csrf_token)
    customer = _create_customer(client, csrf_token, org["id"])

    employee_csrf = _register_and_login(client, "employee3@example.com")
    _give_role(app, org["id"], "employee3@example.com", MembershipRole.EMPLOYEE)

    response = _update(client, employee_csrf, org["id"], customer["id"], name="Updated")

    assert response.status_code == 403


def test_update_without_csrf_returns_403(client):
    csrf_token = _register_and_login(client, "owner4@example.com")
    org = _create_org(client, csrf_token)
    customer = _create_customer(client, csrf_token, org["id"])

    response = client.patch(
        f"/api/v1/organizations/{org['id']}/customers/{customer['id']}", json={"name": "Updated"}
    )

    assert response.status_code == 403


def test_update_nonexistent_customer_returns_404(client):
    csrf_token = _register_and_login(client, "owner5@example.com")
    org = _create_org(client, csrf_token)

    response = _update(client, csrf_token, org["id"], "00000000-0000-0000-0000-000000000000", name="Updated")

    assert response.status_code == 404


def test_update_cross_org_customer_returns_404(client):
    csrf_token = _register_and_login(client, "owner6@example.com")
    org_a = _create_org(client, csrf_token, name="Org A")
    org_b = _create_org(client, csrf_token, name="Org B")
    customer_in_org_a = _create_customer(client, csrf_token, org_a["id"])

    response = _update(client, csrf_token, org_b["id"], customer_in_org_a["id"], name="Updated")

    assert response.status_code == 404


def test_update_rejects_a_blank_name(client):
    csrf_token = _register_and_login(client, "owner7@example.com")
    org = _create_org(client, csrf_token)
    customer = _create_customer(client, csrf_token, org["id"])

    response = _update(client, csrf_token, org["id"], customer["id"], name="   ")

    assert response.status_code == 422


def test_update_rejects_explicit_null_name(client):
    csrf_token = _register_and_login(client, "owner8@example.com")
    org = _create_org(client, csrf_token)
    customer = _create_customer(client, csrf_token, org["id"])

    response = _update(client, csrf_token, org["id"], customer["id"], name=None)

    assert response.status_code == 422


def test_update_rejects_explicit_null_status(client):
    csrf_token = _register_and_login(client, "owner9@example.com")
    org = _create_org(client, csrf_token)
    customer = _create_customer(client, csrf_token, org["id"])

    response = _update(client, csrf_token, org["id"], customer["id"], status=None)

    assert response.status_code == 422


def test_update_rejects_an_invalid_email(client):
    csrf_token = _register_and_login(client, "owner10@example.com")
    org = _create_org(client, csrf_token)
    customer = _create_customer(client, csrf_token, org["id"])

    response = _update(client, csrf_token, org["id"], customer["id"], email="not-an-email")

    assert response.status_code == 422


def test_update_can_clear_clearable_fields(client, app):
    csrf_token = _register_and_login(client, "owner11@example.com")
    org = _create_org(client, csrf_token)
    customer = _create_customer(
        client, csrf_token, org["id"], email="jane@example.com", phone="555-1234", company="Co", address="1 St", notes="n"
    )

    response = _update(
        client,
        csrf_token,
        org["id"],
        customer["id"],
        email=None,
        phone=None,
        company=None,
        address=None,
        notes=None,
    )

    assert response.status_code == 200
    body = response.get_json()["data"]
    assert body["email"] is None
    assert body["phone"] is None
    assert body["company"] is None
    assert body["address"] is None
    assert body["notes"] is None


def test_update_with_no_actual_changes_is_a_noop(client):
    csrf_token = _register_and_login(client, "owner12@example.com")
    org = _create_org(client, csrf_token)
    customer = _create_customer(client, csrf_token, org["id"], email="jane@example.com")

    response = _update(client, csrf_token, org["id"], customer["id"], email="jane@example.com")

    assert response.status_code == 200
    assert response.get_json()["data"]["email"] == "jane@example.com"


@pytest.mark.parametrize("extra_field", ["id", "organization_id"])
def test_update_rejects_unknown_fields(client, extra_field):
    csrf_token = _register_and_login(client, "owner13@example.com")
    org = _create_org(client, csrf_token)
    customer = _create_customer(client, csrf_token, org["id"])

    response = _update(client, csrf_token, org["id"], customer["id"], **{extra_field: "something"})

    assert response.status_code == 422
