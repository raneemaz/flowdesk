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


def _get_customer(client, org_id, customer_id):
    return client.get(f"/api/v1/organizations/{org_id}/customers/{customer_id}")


def test_unauthenticated_request_returns_401(client):
    response = client.get(
        "/api/v1/organizations/00000000-0000-0000-0000-000000000000/customers/"
        "00000000-0000-0000-0000-000000000000"
    )
    assert response.status_code == 401


def test_owner_can_view_a_customer(client):
    csrf_token = _register_and_login(client, "owner@example.com")
    org = _create_org(client, csrf_token)
    customer = _create_customer(client, csrf_token, org["id"], email="jane@example.com")

    response = _get_customer(client, org["id"], customer["id"])

    assert response.status_code == 200
    body = response.get_json()["data"]
    assert body["id"] == customer["id"]
    assert body["email"] == "jane@example.com"


def test_employee_cannot_view_a_customer(client, app):
    csrf_token = _register_and_login(client, "owner2@example.com")
    org = _create_org(client, csrf_token)
    customer = _create_customer(client, csrf_token, org["id"])

    employee_csrf = _register_and_login(client, "employee2@example.com")
    _give_role(app, org["id"], "employee2@example.com", MembershipRole.EMPLOYEE)

    response = _get_customer(client, org["id"], customer["id"])

    assert response.status_code == 403


def test_get_nonexistent_customer_returns_404(client):
    csrf_token = _register_and_login(client, "owner3@example.com")
    org = _create_org(client, csrf_token)

    response = _get_customer(client, org["id"], "00000000-0000-0000-0000-000000000000")

    assert response.status_code == 404


def test_get_cross_org_customer_returns_404(client):
    csrf_token = _register_and_login(client, "owner4@example.com")
    org_a = _create_org(client, csrf_token, name="Org A")
    org_b = _create_org(client, csrf_token, name="Org B")
    customer_in_org_a = _create_customer(client, csrf_token, org_a["id"])

    response = _get_customer(client, org_b["id"], customer_in_org_a["id"])

    assert response.status_code == 404
