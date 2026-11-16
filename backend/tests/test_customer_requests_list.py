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


def _list_requests(client, org_id, **params):
    return client.get(f"/api/v1/organizations/{org_id}/customer-requests", query_string=params)


def test_unauthenticated_request_returns_401(client):
    response = client.get("/api/v1/organizations/00000000-0000-0000-0000-000000000000/customer-requests")
    assert response.status_code == 401


def test_non_member_gets_404(client):
    csrf_token = _register_and_login(client, "owner@example.com")
    org = _create_org(client, csrf_token)
    _register_and_login(client, "outsider@example.com")

    response = _list_requests(client, org["id"])

    assert response.status_code == 404


def test_accountant_cannot_list_requests(client, app):
    csrf_token = _register_and_login(client, "owner2@example.com")
    org = _create_org(client, csrf_token)
    accountant_csrf = _register_and_login(client, "accountant2@example.com")
    _give_role(app, org["id"], "accountant2@example.com", MembershipRole.ACCOUNTANT)

    response = _list_requests(client, org["id"])

    assert response.status_code == 403


def test_owner_sees_every_request_in_the_org(client, app):
    csrf_token = _register_and_login(client, "owner3@example.com")
    org = _create_org(client, csrf_token)
    with app.app_context():
        user = db.session.query(User).filter_by(email="owner3@example.com").one()
        membership = db.session.query(Membership).filter_by(user_id=user.id, organization_id=org["id"]).one()
        owner_membership_id = str(membership.id)
    customer_id = _make_customer(app, org["id"])

    _make_request(app, org["id"], customer_id, owner_membership_id, title="Request A")
    _make_request(app, org["id"], customer_id, owner_membership_id, title="Request B")

    response = _list_requests(client, org["id"])

    assert response.status_code == 200
    body = response.get_json()
    assert len(body["data"]) == 2
    assert body["meta"]["total"] == 2


def test_customer_support_sees_every_request_in_the_org(client, app):
    csrf_token = _register_and_login(client, "owner4@example.com")
    org = _create_org(client, csrf_token)
    with app.app_context():
        user = db.session.query(User).filter_by(email="owner4@example.com").one()
        membership = db.session.query(Membership).filter_by(user_id=user.id, organization_id=org["id"]).one()
        owner_membership_id = str(membership.id)
    customer_id = _make_customer(app, org["id"])
    _make_request(app, org["id"], customer_id, owner_membership_id, title="Request A")
    support_csrf = _register_and_login(client, "support4@example.com")
    _give_role(app, org["id"], "support4@example.com", MembershipRole.CUSTOMER_SUPPORT)

    response = _list_requests(client, org["id"])

    assert response.status_code == 200
    assert response.get_json()["meta"]["total"] == 1


def test_employee_only_sees_requests_assigned_to_them(client, app):
    csrf_token = _register_and_login(client, "owner5@example.com")
    org = _create_org(client, csrf_token)
    with app.app_context():
        user = db.session.query(User).filter_by(email="owner5@example.com").one()
        membership = db.session.query(Membership).filter_by(user_id=user.id, organization_id=org["id"]).one()
        owner_membership_id = str(membership.id)
    customer_id = _make_customer(app, org["id"])
    _register_and_login(client, "employee5a@example.com", name="Employee A")
    employee_a_id = _give_role(app, org["id"], "employee5a@example.com", MembershipRole.EMPLOYEE)
    _register_and_login(client, "employee5b@example.com", name="Employee B")
    employee_b_id = _give_role(app, org["id"], "employee5b@example.com", MembershipRole.EMPLOYEE)

    _make_request(
        app, org["id"], customer_id, owner_membership_id, title="Assigned to A", assignee_membership_id=uuid.UUID(employee_a_id)
    )
    _make_request(
        app, org["id"], customer_id, owner_membership_id, title="Assigned to B", assignee_membership_id=uuid.UUID(employee_b_id)
    )
    _make_request(app, org["id"], customer_id, owner_membership_id, title="Unassigned")

    employee_a_csrf = _login(client, "employee5a@example.com")

    response = _list_requests(client, org["id"])

    assert response.status_code == 200
    body = response.get_json()
    assert [r["title"] for r in body["data"]] == ["Assigned to A"]


def test_employee_cannot_see_another_employees_requests_via_assignee_filter(client, app):
    """The assigned-scope filter is forced server-side, regardless of
    any assignee_membership_id the caller themselves requests - same
    oracle-prevention property app.tasks.service.list_tasks already
    established."""
    csrf_token = _register_and_login(client, "owner5b@example.com")
    org = _create_org(client, csrf_token)
    with app.app_context():
        user = db.session.query(User).filter_by(email="owner5b@example.com").one()
        membership = db.session.query(Membership).filter_by(user_id=user.id, organization_id=org["id"]).one()
        owner_membership_id = str(membership.id)
    customer_id = _make_customer(app, org["id"])
    _register_and_login(client, "employee5c@example.com", name="Employee A")
    employee_a_id = _give_role(app, org["id"], "employee5c@example.com", MembershipRole.EMPLOYEE)
    _register_and_login(client, "employee5d@example.com", name="Employee B")
    employee_b_id = _give_role(app, org["id"], "employee5d@example.com", MembershipRole.EMPLOYEE)
    _make_request(
        app, org["id"], customer_id, owner_membership_id, title="Assigned to B", assignee_membership_id=uuid.UUID(employee_b_id)
    )

    employee_a_csrf = _login(client, "employee5c@example.com")

    response = _list_requests(client, org["id"], assignee_membership_id=employee_b_id)

    assert response.status_code == 200
    assert response.get_json()["data"] == []


def test_list_does_not_leak_another_organizations_requests(client, app):
    csrf_token = _register_and_login(client, "owner6@example.com")
    org_a = _create_org(client, csrf_token, name="Org A")
    org_b = _create_org(client, csrf_token, name="Org B")
    with app.app_context():
        user = db.session.query(User).filter_by(email="owner6@example.com").one()
        membership_a = db.session.query(Membership).filter_by(user_id=user.id, organization_id=org_a["id"]).one()
        membership_b = db.session.query(Membership).filter_by(user_id=user.id, organization_id=org_b["id"]).one()
    customer_a = _make_customer(app, org_a["id"], name="Org A customer")
    customer_b = _make_customer(app, org_b["id"], name="Org B customer")
    _make_request(app, org_a["id"], customer_a, str(membership_a.id), title="Org A request")
    _make_request(app, org_b["id"], customer_b, str(membership_b.id), title="Org B request")

    response = _list_requests(client, org_a["id"])

    assert response.status_code == 200
    body = response.get_json()
    assert len(body["data"]) == 1
    assert body["data"][0]["title"] == "Org A request"


def test_filter_by_customer_id(client, app):
    csrf_token = _register_and_login(client, "owner7@example.com")
    org = _create_org(client, csrf_token)
    with app.app_context():
        user = db.session.query(User).filter_by(email="owner7@example.com").one()
        membership = db.session.query(Membership).filter_by(user_id=user.id, organization_id=org["id"]).one()
        owner_membership_id = str(membership.id)
    customer_a = _make_customer(app, org["id"], name="Customer A")
    customer_b = _make_customer(app, org["id"], name="Customer B")
    _make_request(app, org["id"], customer_a, owner_membership_id, title="For A")
    _make_request(app, org["id"], customer_b, owner_membership_id, title="For B")

    response = _list_requests(client, org["id"], customer_id=customer_a)

    assert response.status_code == 200
    body = response.get_json()["data"]
    assert len(body) == 1
    assert body[0]["title"] == "For A"


def test_filter_by_status(client, app):
    from app.models import RequestStatus

    csrf_token = _register_and_login(client, "owner8@example.com")
    org = _create_org(client, csrf_token)
    with app.app_context():
        user = db.session.query(User).filter_by(email="owner8@example.com").one()
        membership = db.session.query(Membership).filter_by(user_id=user.id, organization_id=org["id"]).one()
        owner_membership_id = str(membership.id)
    customer_id = _make_customer(app, org["id"])
    _make_request(app, org["id"], customer_id, owner_membership_id, title="New one")
    _make_request(app, org["id"], customer_id, owner_membership_id, title="Closed one", status=RequestStatus.CLOSED)

    response = _list_requests(client, org["id"], status="closed")

    assert response.status_code == 200
    body = response.get_json()["data"]
    assert len(body) == 1
    assert body[0]["title"] == "Closed one"


def test_pagination_meta(client, app):
    csrf_token = _register_and_login(client, "owner9@example.com")
    org = _create_org(client, csrf_token)
    with app.app_context():
        user = db.session.query(User).filter_by(email="owner9@example.com").one()
        membership = db.session.query(Membership).filter_by(user_id=user.id, organization_id=org["id"]).one()
        owner_membership_id = str(membership.id)
    customer_id = _make_customer(app, org["id"])
    for i in range(3):
        _make_request(app, org["id"], customer_id, owner_membership_id, title=f"Request {i}")

    response = _list_requests(client, org["id"], per_page=2, page=1)

    assert response.status_code == 200
    body = response.get_json()
    assert len(body["data"]) == 2
    assert body["meta"] == {"page": 1, "per_page": 2, "total": 3, "total_pages": 2}


def test_rejects_an_inverted_due_date_range(client):
    csrf_token = _register_and_login(client, "owner10@example.com")
    org = _create_org(client, csrf_token)

    response = _list_requests(client, org["id"], due_date_from="2026-06-01", due_date_to="2026-01-01")

    assert response.status_code == 422
