import uuid

import pytest

from app.extensions import db
from app.models import Customer, CustomerRequest, Membership, MembershipRole, Organization, User


@pytest.fixture(autouse=True)
def _clean(app):
    yield
    with app.app_context():
        db.session.query(CustomerRequest).delete()
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


def _make_customer(app, organization_id, name="Customer"):
    with app.app_context():
        customer = Customer(organization_id=uuid.UUID(organization_id), name=name)
        db.session.add(customer)
        db.session.commit()
        return str(customer.id)


def _make_request(app, organization_id, customer_id, creator_membership_id, **kwargs):
    with app.app_context():
        customer_request = CustomerRequest(
            organization_id=uuid.UUID(organization_id),
            customer_id=uuid.UUID(customer_id),
            creator_membership_id=uuid.UUID(creator_membership_id),
            title=kwargs.pop("title", "Request"),
            **kwargs,
        )
        db.session.add(customer_request)
        db.session.commit()
        return str(customer_request.id)


def _get_request(client, org_id, request_id):
    return client.get(f"/api/v1/organizations/{org_id}/customer-requests/{request_id}")


def test_unauthenticated_request_returns_401(client):
    response = client.get(
        "/api/v1/organizations/00000000-0000-0000-0000-000000000000/customer-requests/"
        "00000000-0000-0000-0000-000000000000"
    )
    assert response.status_code == 401


def test_owner_can_view_a_request(client, app):
    csrf_token = _register_and_login(client, "owner@example.com")
    org = _create_org(client, csrf_token)
    with app.app_context():
        user = db.session.query(User).filter_by(email="owner@example.com").one()
        membership = db.session.query(Membership).filter_by(user_id=user.id, organization_id=org["id"]).one()
        owner_membership_id = str(membership.id)
    customer_id = _make_customer(app, org["id"])
    request_id = _make_request(app, org["id"], customer_id, owner_membership_id)

    response = _get_request(client, org["id"], request_id)

    assert response.status_code == 200
    assert response.get_json()["data"]["id"] == request_id


def test_employee_can_view_their_own_assigned_request(client, app):
    csrf_token = _register_and_login(client, "owner2@example.com")
    org = _create_org(client, csrf_token)
    with app.app_context():
        user = db.session.query(User).filter_by(email="owner2@example.com").one()
        membership = db.session.query(Membership).filter_by(user_id=user.id, organization_id=org["id"]).one()
        owner_membership_id = str(membership.id)
    customer_id = _make_customer(app, org["id"])
    employee_csrf = _register_and_login(client, "employee2@example.com")
    employee_id = _give_role(app, org["id"], "employee2@example.com", MembershipRole.EMPLOYEE)
    request_id = _make_request(
        app, org["id"], customer_id, owner_membership_id, assignee_membership_id=uuid.UUID(employee_id)
    )

    response = _get_request(client, org["id"], request_id)

    assert response.status_code == 200


def test_employee_cannot_view_a_request_not_assigned_to_them(client, app):
    csrf_token = _register_and_login(client, "owner3@example.com")
    org = _create_org(client, csrf_token)
    with app.app_context():
        user = db.session.query(User).filter_by(email="owner3@example.com").one()
        membership = db.session.query(Membership).filter_by(user_id=user.id, organization_id=org["id"]).one()
        owner_membership_id = str(membership.id)
    customer_id = _make_customer(app, org["id"])
    employee_csrf = _register_and_login(client, "employee3@example.com")
    _give_role(app, org["id"], "employee3@example.com", MembershipRole.EMPLOYEE)
    request_id = _make_request(app, org["id"], customer_id, owner_membership_id)

    response = _get_request(client, org["id"], request_id)

    assert response.status_code == 403


def test_accountant_cannot_view_a_request(client, app):
    csrf_token = _register_and_login(client, "owner4@example.com")
    org = _create_org(client, csrf_token)
    with app.app_context():
        user = db.session.query(User).filter_by(email="owner4@example.com").one()
        membership = db.session.query(Membership).filter_by(user_id=user.id, organization_id=org["id"]).one()
        owner_membership_id = str(membership.id)
    customer_id = _make_customer(app, org["id"])
    accountant_csrf = _register_and_login(client, "accountant4@example.com")
    _give_role(app, org["id"], "accountant4@example.com", MembershipRole.ACCOUNTANT)
    request_id = _make_request(app, org["id"], customer_id, owner_membership_id)

    response = _get_request(client, org["id"], request_id)

    assert response.status_code == 403


def test_get_nonexistent_request_returns_404(client):
    csrf_token = _register_and_login(client, "owner5@example.com")
    org = _create_org(client, csrf_token)

    response = _get_request(client, org["id"], "00000000-0000-0000-0000-000000000000")

    assert response.status_code == 404


def test_get_cross_org_request_returns_404(client, app):
    csrf_token = _register_and_login(client, "owner6@example.com")
    org_a = _create_org(client, csrf_token, name="Org A")
    org_b = _create_org(client, csrf_token, name="Org B")
    with app.app_context():
        user = db.session.query(User).filter_by(email="owner6@example.com").one()
        membership_a = db.session.query(Membership).filter_by(user_id=user.id, organization_id=org_a["id"]).one()
    customer_a = _make_customer(app, org_a["id"])
    request_in_org_a = _make_request(app, org_a["id"], customer_a, str(membership_a.id))

    response = _get_request(client, org_b["id"], request_in_org_a)

    assert response.status_code == 404
