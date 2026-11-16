import uuid

import pytest

from app.extensions import db
from app.models import Customer, CustomerStatus, Membership, MembershipRole, Organization, User


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


def _make_customer(app, organization_id, **kwargs):
    with app.app_context():
        customer = Customer(organization_id=uuid.UUID(organization_id), name=kwargs.pop("name", "Customer"), **kwargs)
        db.session.add(customer)
        db.session.commit()
        return str(customer.id)


def _list_customers(client, org_id, **params):
    return client.get(f"/api/v1/organizations/{org_id}/customers", query_string=params)


def test_unauthenticated_request_returns_401(client):
    response = client.get("/api/v1/organizations/00000000-0000-0000-0000-000000000000/customers")
    assert response.status_code == 401


def test_non_member_gets_404(client):
    csrf_token = _register_and_login(client, "owner@example.com")
    org = _create_org(client, csrf_token)
    _register_and_login(client, "outsider@example.com")

    response = _list_customers(client, org["id"])

    assert response.status_code == 404


def test_employee_cannot_list_customers(client, app):
    csrf_token = _register_and_login(client, "owner2@example.com")
    org = _create_org(client, csrf_token)
    employee_csrf = _register_and_login(client, "employee2@example.com")
    _give_role(app, org["id"], "employee2@example.com", MembershipRole.EMPLOYEE)

    response = _list_customers(client, org["id"])

    assert response.status_code == 403


def test_owner_sees_every_customer_in_the_org(client, app):
    csrf_token = _register_and_login(client, "owner3@example.com")
    org = _create_org(client, csrf_token)
    _make_customer(app, org["id"], name="Customer A")
    _make_customer(app, org["id"], name="Customer B")

    response = _list_customers(client, org["id"])

    assert response.status_code == 200
    body = response.get_json()
    assert len(body["data"]) == 2
    assert body["meta"]["total"] == 2


def test_customer_support_sees_every_customer_in_the_org(client, app):
    csrf_token = _register_and_login(client, "owner4@example.com")
    org = _create_org(client, csrf_token)
    _make_customer(app, org["id"], name="Customer A")
    support_csrf = _register_and_login(client, "support4@example.com")
    _give_role(app, org["id"], "support4@example.com", MembershipRole.CUSTOMER_SUPPORT)

    response = _list_customers(client, org["id"])

    assert response.status_code == 200
    assert response.get_json()["meta"]["total"] == 1


def test_list_does_not_leak_another_organizations_customers(client, app):
    csrf_token = _register_and_login(client, "owner5@example.com")
    org_a = _create_org(client, csrf_token, name="Org A")
    org_b = _create_org(client, csrf_token, name="Org B")
    _make_customer(app, org_a["id"], name="Org A customer")
    _make_customer(app, org_b["id"], name="Org B customer")

    response = _list_customers(client, org_a["id"])

    assert response.status_code == 200
    body = response.get_json()
    assert len(body["data"]) == 1
    assert body["data"][0]["name"] == "Org A customer"


@pytest.mark.parametrize(
    "search,expected",
    [
        ("jane", "Jane Customer"),
        ("jane@example.com", "Jane Customer"),
        ("555-1234", "Jane Customer"),
        ("Bakery", "Jane Customer"),
    ],
)
def test_search_matches_name_email_phone_or_company(client, app, search, expected):
    csrf_token = _register_and_login(client, f"owner-{search.replace('@', '-').replace('.', '-')}@example.com")
    org = _create_org(client, csrf_token)
    _make_customer(
        app, org["id"], name="Jane Customer", email="jane@example.com", phone="555-1234", company="Jane's Bakery"
    )
    _make_customer(app, org["id"], name="Unrelated Customer")

    response = _list_customers(client, org["id"], search=search)

    assert response.status_code == 200
    body = response.get_json()["data"]
    assert len(body) == 1
    assert body[0]["name"] == expected


def test_list_includes_archived_customers_by_default(client, app):
    csrf_token = _register_and_login(client, "owner6@example.com")
    org = _create_org(client, csrf_token)
    _make_customer(app, org["id"], name="Active", status=CustomerStatus.ACTIVE)
    _make_customer(app, org["id"], name="Archived", status=CustomerStatus.ARCHIVED)

    response = _list_customers(client, org["id"])

    assert response.status_code == 200
    assert response.get_json()["meta"]["total"] == 2


def test_list_filters_by_status(client, app):
    csrf_token = _register_and_login(client, "owner7@example.com")
    org = _create_org(client, csrf_token)
    _make_customer(app, org["id"], name="Active", status=CustomerStatus.ACTIVE)
    _make_customer(app, org["id"], name="Archived", status=CustomerStatus.ARCHIVED)

    response = _list_customers(client, org["id"], status="archived")

    assert response.status_code == 200
    body = response.get_json()["data"]
    assert len(body) == 1
    assert body[0]["name"] == "Archived"


def test_pagination_meta(client, app):
    csrf_token = _register_and_login(client, "owner8@example.com")
    org = _create_org(client, csrf_token)
    for i in range(3):
        _make_customer(app, org["id"], name=f"Customer {i}")

    response = _list_customers(client, org["id"], per_page=2, page=1)

    assert response.status_code == 200
    body = response.get_json()
    assert len(body["data"]) == 2
    assert body["meta"] == {"page": 1, "per_page": 2, "total": 3, "total_pages": 2}


def test_rejects_an_unknown_query_param(client):
    csrf_token = _register_and_login(client, "owner9@example.com")
    org = _create_org(client, csrf_token)

    response = _list_customers(client, org["id"], bogus="x")

    assert response.status_code == 422
