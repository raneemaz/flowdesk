import uuid

import pytest

from app.extensions import db
from app.models import (
    Customer,
    CustomerRequest,
    Membership,
    MembershipRole,
    MembershipStatus,
    Organization,
    RequestHistory,
    RequestStatus,
    User,
)


@pytest.fixture(autouse=True)
def _clean(app):
    yield
    with app.app_context():
        db.session.query(RequestHistory).delete()
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


def _give_role(app, organization_id, email, role, status=MembershipStatus.ACTIVE):
    with app.app_context():
        user = db.session.query(User).filter_by(email=email).one()
        membership = Membership(organization_id=organization_id, user_id=user.id, role=role, status=status)
        db.session.add(membership)
        db.session.commit()
        return str(membership.id)


def _membership_id(app, organization_id, email):
    with app.app_context():
        user = db.session.query(User).filter_by(email=email).one()
        membership = (
            db.session.query(Membership).filter_by(organization_id=uuid.UUID(organization_id), user_id=user.id).one()
        )
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


def _assign(client, csrf_token, org_id, request_id, assignee_membership_id):
    return client.patch(
        f"/api/v1/organizations/{org_id}/customer-requests/{request_id}/assign",
        json={"assignee_membership_id": assignee_membership_id},
        headers={"X-CSRF-Token": csrf_token},
    )


def test_unauthenticated_request_returns_401(client):
    response = client.patch(
        "/api/v1/organizations/00000000-0000-0000-0000-000000000000/customer-requests/"
        "00000000-0000-0000-0000-000000000000/assign",
        json={"assignee_membership_id": None},
    )
    assert response.status_code == 401


def test_owner_can_assign_a_request(client, app):
    csrf_token = _register_and_login(client, "owner@example.com")
    org = _create_org(client, csrf_token)
    owner_id = _membership_id(app, org["id"], "owner@example.com")
    customer_id = _make_customer(app, org["id"])
    request_id = _make_request(app, org["id"], customer_id, owner_id)
    _register_and_login(client, "employee@example.com", name="Employee")
    employee_id = _give_role(app, org["id"], "employee@example.com", MembershipRole.EMPLOYEE)
    owner_csrf = _login(client, "owner@example.com")

    response = _assign(client, owner_csrf, org["id"], request_id, employee_id)

    assert response.status_code == 200
    assert response.get_json()["data"]["assignee_membership_id"] == employee_id


def test_assigning_a_new_request_auto_advances_status_to_assigned(client, app):
    csrf_token = _register_and_login(client, "owner2@example.com")
    org = _create_org(client, csrf_token)
    owner_id = _membership_id(app, org["id"], "owner2@example.com")
    customer_id = _make_customer(app, org["id"])
    request_id = _make_request(app, org["id"], customer_id, owner_id)
    _register_and_login(client, "employee2@example.com", name="Employee")
    employee_id = _give_role(app, org["id"], "employee2@example.com", MembershipRole.EMPLOYEE)
    owner_csrf = _login(client, "owner2@example.com")

    response = _assign(client, owner_csrf, org["id"], request_id, employee_id)

    assert response.status_code == 200
    assert response.get_json()["data"]["status"] == "assigned"

    with app.app_context():
        entries = (
            db.session.query(RequestHistory)
            .filter_by(request_id=uuid.UUID(request_id))
            .order_by(RequestHistory.created_at)
            .all()
        )
        event_types = [e.event_type for e in entries]
        assert "assignee_changed" in event_types
        assert "status_changed" in event_types


def test_reassigning_an_in_progress_request_does_not_regress_status(client, app):
    csrf_token = _register_and_login(client, "owner3@example.com")
    org = _create_org(client, csrf_token)
    owner_id = _membership_id(app, org["id"], "owner3@example.com")
    customer_id = _make_customer(app, org["id"])
    request_id = _make_request(app, org["id"], customer_id, owner_id, status=RequestStatus.IN_PROGRESS)
    _register_and_login(client, "employee3a@example.com", name="Employee A")
    employee_a_id = _give_role(app, org["id"], "employee3a@example.com", MembershipRole.EMPLOYEE)
    _register_and_login(client, "employee3b@example.com", name="Employee B")
    employee_b_id = _give_role(app, org["id"], "employee3b@example.com", MembershipRole.EMPLOYEE)
    owner_csrf = _login(client, "owner3@example.com")
    _assign(client, owner_csrf, org["id"], request_id, employee_a_id)

    response = _assign(client, owner_csrf, org["id"], request_id, employee_b_id)

    assert response.status_code == 200
    assert response.get_json()["data"]["status"] == "in_progress"
    assert response.get_json()["data"]["assignee_membership_id"] == employee_b_id


def test_reassigning_to_the_same_assignee_is_a_no_op(client, app):
    csrf_token = _register_and_login(client, "owner4@example.com")
    org = _create_org(client, csrf_token)
    owner_id = _membership_id(app, org["id"], "owner4@example.com")
    customer_id = _make_customer(app, org["id"])
    _register_and_login(client, "employee4@example.com", name="Employee")
    employee_id = _give_role(app, org["id"], "employee4@example.com", MembershipRole.EMPLOYEE)
    request_id = _make_request(
        app, org["id"], customer_id, owner_id, assignee_membership_id=uuid.UUID(employee_id), status=RequestStatus.ASSIGNED
    )
    owner_csrf = _login(client, "owner4@example.com")

    response = _assign(client, owner_csrf, org["id"], request_id, employee_id)

    assert response.status_code == 200
    with app.app_context():
        assert db.session.query(RequestHistory).filter_by(request_id=uuid.UUID(request_id)).count() == 0


def test_can_unassign_a_request(client, app):
    csrf_token = _register_and_login(client, "owner5@example.com")
    org = _create_org(client, csrf_token)
    owner_id = _membership_id(app, org["id"], "owner5@example.com")
    customer_id = _make_customer(app, org["id"])
    _register_and_login(client, "employee5@example.com", name="Employee")
    employee_id = _give_role(app, org["id"], "employee5@example.com", MembershipRole.EMPLOYEE)
    request_id = _make_request(
        app, org["id"], customer_id, owner_id, assignee_membership_id=uuid.UUID(employee_id), status=RequestStatus.ASSIGNED
    )
    owner_csrf = _login(client, "owner5@example.com")

    response = _assign(client, owner_csrf, org["id"], request_id, None)

    assert response.status_code == 200
    assert response.get_json()["data"]["assignee_membership_id"] is None


def test_employee_cannot_assign_a_request(client, app):
    csrf_token = _register_and_login(client, "owner6@example.com")
    org = _create_org(client, csrf_token)
    owner_id = _membership_id(app, org["id"], "owner6@example.com")
    customer_id = _make_customer(app, org["id"])
    request_id = _make_request(app, org["id"], customer_id, owner_id)
    employee_csrf = _register_and_login(client, "employee6@example.com")
    employee_id = _give_role(app, org["id"], "employee6@example.com", MembershipRole.EMPLOYEE)

    response = _assign(client, employee_csrf, org["id"], request_id, employee_id)

    assert response.status_code == 403


def test_accountant_cannot_assign_a_request(client, app):
    csrf_token = _register_and_login(client, "owner7@example.com")
    org = _create_org(client, csrf_token)
    owner_id = _membership_id(app, org["id"], "owner7@example.com")
    customer_id = _make_customer(app, org["id"])
    request_id = _make_request(app, org["id"], customer_id, owner_id)
    accountant_csrf = _register_and_login(client, "accountant7@example.com")
    _give_role(app, org["id"], "accountant7@example.com", MembershipRole.ACCOUNTANT)

    response = _assign(client, accountant_csrf, org["id"], request_id, owner_id)

    assert response.status_code == 403


def test_assign_rejects_an_inactive_assignee(client, app):
    csrf_token = _register_and_login(client, "owner8@example.com")
    org = _create_org(client, csrf_token)
    owner_id = _membership_id(app, org["id"], "owner8@example.com")
    customer_id = _make_customer(app, org["id"])
    request_id = _make_request(app, org["id"], customer_id, owner_id)
    _register_and_login(client, "employee8@example.com", name="Employee")
    inactive_id = _give_role(
        app, org["id"], "employee8@example.com", MembershipRole.EMPLOYEE, status=MembershipStatus.INACTIVE
    )
    owner_csrf = _login(client, "owner8@example.com")

    response = _assign(client, owner_csrf, org["id"], request_id, inactive_id)

    assert response.status_code == 422
    assert response.get_json()["error"]["code"] == "INVALID_ASSIGNEE"


def test_assign_rejects_a_cross_org_assignee(client, app):
    csrf_token = _register_and_login(client, "owner9@example.com")
    org_a = _create_org(client, csrf_token, name="Org A")
    org_b = _create_org(client, csrf_token, name="Org B")
    owner_a_id = _membership_id(app, org_a["id"], "owner9@example.com")
    customer_id = _make_customer(app, org_a["id"])
    request_id = _make_request(app, org_a["id"], customer_id, owner_a_id)
    _register_and_login(client, "employee9@example.com")
    foreign_employee_id = _give_role(app, org_b["id"], "employee9@example.com", MembershipRole.EMPLOYEE)
    owner_csrf = _login(client, "owner9@example.com")

    response = _assign(client, owner_csrf, org_a["id"], request_id, foreign_employee_id)

    assert response.status_code == 422
    assert response.get_json()["error"]["code"] == "INVALID_ASSIGNEE"


def test_assign_without_csrf_returns_403(client, app):
    csrf_token = _register_and_login(client, "owner10@example.com")
    org = _create_org(client, csrf_token)
    owner_id = _membership_id(app, org["id"], "owner10@example.com")
    customer_id = _make_customer(app, org["id"])
    request_id = _make_request(app, org["id"], customer_id, owner_id)

    response = client.patch(
        f"/api/v1/organizations/{org['id']}/customer-requests/{request_id}/assign",
        json={"assignee_membership_id": owner_id},
    )

    assert response.status_code == 403


def test_assign_nonexistent_request_returns_404(client, app):
    csrf_token = _register_and_login(client, "owner11@example.com")
    org = _create_org(client, csrf_token)

    response = _assign(client, csrf_token, org["id"], "00000000-0000-0000-0000-000000000000", None)

    assert response.status_code == 404


def test_assign_cross_org_request_returns_404(client, app):
    csrf_token = _register_and_login(client, "owner12@example.com")
    org_a = _create_org(client, csrf_token, name="Org A")
    org_b = _create_org(client, csrf_token, name="Org B")
    owner_a_id = _membership_id(app, org_a["id"], "owner12@example.com")
    customer_id = _make_customer(app, org_a["id"])
    request_in_org_a = _make_request(app, org_a["id"], customer_id, owner_a_id)

    response = _assign(client, csrf_token, org_b["id"], request_in_org_a, None)

    assert response.status_code == 404
