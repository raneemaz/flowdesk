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
    )


def test_unauthenticated_request_returns_401(client):
    response = client.post(
        "/api/v1/organizations/00000000-0000-0000-0000-000000000000/customers", json={"name": "Jane Customer"}
    )
    assert response.status_code == 401


def test_owner_can_create_a_customer(client):
    csrf_token = _register_and_login(client, "owner@example.com")
    org = _create_org(client, csrf_token)

    response = _create_customer(
        client,
        csrf_token,
        org["id"],
        name="Jane Customer",
        email="jane@example.com",
        phone="555-1234",
        company="Jane's Bakery",
        address="1 Main St",
        notes="Prefers email contact",
    )

    assert response.status_code == 201
    body = response.get_json()["data"]
    assert body["name"] == "Jane Customer"
    assert body["email"] == "jane@example.com"
    assert body["phone"] == "555-1234"
    assert body["company"] == "Jane's Bakery"
    assert body["address"] == "1 Main St"
    assert body["notes"] == "Prefers email contact"
    assert body["organization_id"] == org["id"]
    assert body["status"] == "active"


@pytest.mark.parametrize(
    "role", [MembershipRole.MANAGER, MembershipRole.ACCOUNTANT, MembershipRole.CUSTOMER_SUPPORT]
)
def test_roles_with_customer_manage_can_create_a_customer(client, app, role):
    csrf_token = _register_and_login(client, f"owner-{role.value}@example.com")
    org = _create_org(client, csrf_token)
    other_email = f"{role.value}@example.com"
    other_csrf = _register_and_login(client, other_email)
    _give_role(app, org["id"], other_email, role)

    response = _create_customer(client, other_csrf, org["id"])

    assert response.status_code == 201


def test_employee_cannot_create_a_customer(client, app):
    csrf_token = _register_and_login(client, "owner2@example.com")
    org = _create_org(client, csrf_token)
    employee_csrf = _register_and_login(client, "employee2@example.com")
    _give_role(app, org["id"], "employee2@example.com", MembershipRole.EMPLOYEE)

    response = _create_customer(client, employee_csrf, org["id"])

    assert response.status_code == 403
    assert response.get_json()["error"]["code"] == "FORBIDDEN"


def test_create_without_csrf_token_returns_403(client):
    csrf_token = _register_and_login(client, "owner3@example.com")
    org = _create_org(client, csrf_token)

    response = client.post(f"/api/v1/organizations/{org['id']}/customers", json={"name": "Jane Customer"})

    assert response.status_code == 403


def test_create_in_an_organization_the_caller_does_not_belong_to_returns_404(client):
    csrf_token = _register_and_login(client, "owner4@example.com")
    org = _create_org(client, csrf_token)

    outsider_csrf = _register_and_login(client, "outsider@example.com")

    response = _create_customer(client, outsider_csrf, org["id"])

    assert response.status_code == 404


def test_create_missing_name_returns_422(client):
    csrf_token = _register_and_login(client, "owner5@example.com")
    org = _create_org(client, csrf_token)

    response = client.post(
        f"/api/v1/organizations/{org['id']}/customers", json={}, headers={"X-CSRF-Token": csrf_token}
    )

    assert response.status_code == 422
    assert response.get_json()["error"]["code"] == "VALIDATION_ERROR"


def test_create_with_a_whitespace_only_name_returns_422(client):
    csrf_token = _register_and_login(client, "owner6@example.com")
    org = _create_org(client, csrf_token)

    response = _create_customer(client, csrf_token, org["id"], name="   ")

    assert response.status_code == 422


def test_create_with_an_invalid_email_returns_422(client):
    csrf_token = _register_and_login(client, "owner7@example.com")
    org = _create_org(client, csrf_token)

    response = _create_customer(client, csrf_token, org["id"], email="not-an-email")

    assert response.status_code == 422


def test_create_with_no_optional_fields_succeeds(client):
    csrf_token = _register_and_login(client, "owner8@example.com")
    org = _create_org(client, csrf_token)

    response = _create_customer(client, csrf_token, org["id"], name="Jane Customer")

    assert response.status_code == 201
    body = response.get_json()["data"]
    assert body["email"] is None
    assert body["phone"] is None
    assert body["company"] is None
    assert body["address"] is None
    assert body["notes"] is None


@pytest.mark.parametrize("extra_field", ["id", "organization_id", "status"])
def test_create_rejects_unknown_fields(client, extra_field):
    csrf_token = _register_and_login(client, "owner9@example.com")
    org = _create_org(client, csrf_token)

    response = _create_customer(client, csrf_token, org["id"], **{extra_field: "something"})

    assert response.status_code == 422
