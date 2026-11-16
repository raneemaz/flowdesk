import uuid

import pytest

from app.extensions import db
from app.models import Customer, CustomerRequest, Membership, MembershipRole, Organization, RequestComment, User


@pytest.fixture(autouse=True)
def _clean(app):
    yield
    with app.app_context():
        db.session.query(RequestComment).delete()
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


def _post_comment(client, csrf_token, org_id, request_id, body="A comment"):
    return client.post(
        f"/api/v1/organizations/{org_id}/customer-requests/{request_id}/comments",
        json={"body": body},
        headers={"X-CSRF-Token": csrf_token},
    )


def _list_comments(client, org_id, request_id, **params):
    return client.get(
        f"/api/v1/organizations/{org_id}/customer-requests/{request_id}/comments", query_string=params
    )


def test_unauthenticated_post_returns_401(client):
    response = client.post(
        "/api/v1/organizations/00000000-0000-0000-0000-000000000000/customer-requests/"
        "00000000-0000-0000-0000-000000000000/comments",
        json={"body": "Hi"},
    )
    assert response.status_code == 401


def test_unauthenticated_get_returns_401(client):
    response = client.get(
        "/api/v1/organizations/00000000-0000-0000-0000-000000000000/customer-requests/"
        "00000000-0000-0000-0000-000000000000/comments"
    )
    assert response.status_code == 401


def test_owner_can_post_a_comment(client, app):
    csrf_token = _register_and_login(client, "owner@example.com")
    org = _create_org(client, csrf_token)
    owner_id = _membership_id(app, org["id"], "owner@example.com")
    customer_id = _make_customer(app, org["id"])
    request_id = _make_request(app, org["id"], customer_id, owner_id)

    response = _post_comment(client, csrf_token, org["id"], request_id, body="Looked into it.")

    assert response.status_code == 201
    body = response.get_json()["data"]
    assert body["body"] == "Looked into it."
    assert body["author_membership_id"] == owner_id
    assert "created_at" in body


def test_customer_support_can_post_a_comment(client, app):
    csrf_token = _register_and_login(client, "owner2@example.com")
    org = _create_org(client, csrf_token)
    owner_id = _membership_id(app, org["id"], "owner2@example.com")
    customer_id = _make_customer(app, org["id"])
    request_id = _make_request(app, org["id"], customer_id, owner_id)
    support_csrf = _register_and_login(client, "support2@example.com")
    _give_role(app, org["id"], "support2@example.com", MembershipRole.CUSTOMER_SUPPORT)

    response = _post_comment(client, support_csrf, org["id"], request_id)

    assert response.status_code == 201


def test_assignee_can_post_a_comment_on_their_own_request(client, app):
    csrf_token = _register_and_login(client, "owner3@example.com")
    org = _create_org(client, csrf_token)
    owner_id = _membership_id(app, org["id"], "owner3@example.com")
    customer_id = _make_customer(app, org["id"])
    _register_and_login(client, "employee3@example.com", name="Employee Three")
    employee_id = _give_role(app, org["id"], "employee3@example.com", MembershipRole.EMPLOYEE)
    request_id = _make_request(
        app, org["id"], customer_id, owner_id, assignee_membership_id=uuid.UUID(employee_id)
    )
    employee_csrf = _login(client, "employee3@example.com")

    response = _post_comment(client, employee_csrf, org["id"], request_id, body="Working on it.")

    assert response.status_code == 201
    assert response.get_json()["data"]["author_membership_id"] == employee_id


def test_employee_cannot_comment_on_a_request_not_assigned_to_them(client, app):
    csrf_token = _register_and_login(client, "owner4@example.com")
    org = _create_org(client, csrf_token)
    owner_id = _membership_id(app, org["id"], "owner4@example.com")
    customer_id = _make_customer(app, org["id"])
    _register_and_login(client, "employee4a@example.com", name="Employee A")
    employee_a_id = _give_role(app, org["id"], "employee4a@example.com", MembershipRole.EMPLOYEE)
    _register_and_login(client, "employee4b@example.com", name="Employee B")
    _give_role(app, org["id"], "employee4b@example.com", MembershipRole.EMPLOYEE)
    request_id = _make_request(
        app, org["id"], customer_id, owner_id, assignee_membership_id=uuid.UUID(employee_a_id)
    )
    employee_b_csrf = _login(client, "employee4b@example.com")

    response = _post_comment(client, employee_b_csrf, org["id"], request_id)

    assert response.status_code == 403


def test_employee_cannot_comment_on_an_unassigned_request(client, app):
    csrf_token = _register_and_login(client, "owner5@example.com")
    org = _create_org(client, csrf_token)
    owner_id = _membership_id(app, org["id"], "owner5@example.com")
    customer_id = _make_customer(app, org["id"])
    _register_and_login(client, "employee5@example.com", name="Employee Five")
    _give_role(app, org["id"], "employee5@example.com", MembershipRole.EMPLOYEE)
    request_id = _make_request(app, org["id"], customer_id, owner_id)
    employee_csrf = _login(client, "employee5@example.com")

    response = _post_comment(client, employee_csrf, org["id"], request_id)

    assert response.status_code == 403


def test_accountant_cannot_comment(client, app):
    csrf_token = _register_and_login(client, "owner6@example.com")
    org = _create_org(client, csrf_token)
    owner_id = _membership_id(app, org["id"], "owner6@example.com")
    customer_id = _make_customer(app, org["id"])
    request_id = _make_request(app, org["id"], customer_id, owner_id)
    accountant_csrf = _register_and_login(client, "accountant6@example.com")
    _give_role(app, org["id"], "accountant6@example.com", MembershipRole.ACCOUNTANT)

    response = _post_comment(client, accountant_csrf, org["id"], request_id)

    assert response.status_code == 403


def test_post_without_csrf_returns_403(client, app):
    csrf_token = _register_and_login(client, "owner7@example.com")
    org = _create_org(client, csrf_token)
    owner_id = _membership_id(app, org["id"], "owner7@example.com")
    customer_id = _make_customer(app, org["id"])
    request_id = _make_request(app, org["id"], customer_id, owner_id)

    response = client.post(
        f"/api/v1/organizations/{org['id']}/customer-requests/{request_id}/comments", json={"body": "No csrf"}
    )

    assert response.status_code == 403


def test_post_to_nonexistent_request_returns_404(client):
    csrf_token = _register_and_login(client, "owner8@example.com")
    org = _create_org(client, csrf_token)

    response = _post_comment(client, csrf_token, org["id"], str(uuid.uuid4()))

    assert response.status_code == 404


def test_post_to_cross_org_request_returns_404(client, app):
    owner_a_csrf = _register_and_login(client, "owner9a@example.com")
    org_a = _create_org(client, owner_a_csrf, name="Org A")
    owner_b_csrf = _register_and_login(client, "owner9b@example.com")
    org_b = _create_org(client, owner_b_csrf, name="Org B")
    owner_b_id = _membership_id(app, org_b["id"], "owner9b@example.com")
    customer_b = _make_customer(app, org_b["id"])
    request_in_org_b = _make_request(app, org_b["id"], customer_b, owner_b_id)
    owner_a_csrf = _login(client, "owner9a@example.com")

    response = _post_comment(client, owner_a_csrf, org_a["id"], request_in_org_b)

    assert response.status_code == 404


def test_post_rejects_a_blank_body(client, app):
    csrf_token = _register_and_login(client, "owner10@example.com")
    org = _create_org(client, csrf_token)
    owner_id = _membership_id(app, org["id"], "owner10@example.com")
    customer_id = _make_customer(app, org["id"])
    request_id = _make_request(app, org["id"], customer_id, owner_id)

    response = _post_comment(client, csrf_token, org["id"], request_id, body="   ")

    assert response.status_code == 422


def test_post_rejects_unknown_fields(client, app):
    csrf_token = _register_and_login(client, "owner11@example.com")
    org = _create_org(client, csrf_token)
    owner_id = _membership_id(app, org["id"], "owner11@example.com")
    customer_id = _make_customer(app, org["id"])
    request_id = _make_request(app, org["id"], customer_id, owner_id)

    response = client.post(
        f"/api/v1/organizations/{org['id']}/customer-requests/{request_id}/comments",
        json={"body": "Hi", "author_membership_id": str(uuid.uuid4())},
        headers={"X-CSRF-Token": csrf_token},
    )

    assert response.status_code == 422


def test_owner_can_list_comments(client, app):
    csrf_token = _register_and_login(client, "owner12@example.com")
    org = _create_org(client, csrf_token)
    owner_id = _membership_id(app, org["id"], "owner12@example.com")
    customer_id = _make_customer(app, org["id"])
    request_id = _make_request(app, org["id"], customer_id, owner_id)
    _post_comment(client, csrf_token, org["id"], request_id, body="First")
    _post_comment(client, csrf_token, org["id"], request_id, body="Second")

    response = _list_comments(client, org["id"], request_id)

    assert response.status_code == 200
    body = response.get_json()
    assert [c["body"] for c in body["data"]] == ["First", "Second"]
    assert body["meta"]["total"] == 2


def test_assignee_can_list_comments_on_their_own_request(client, app):
    csrf_token = _register_and_login(client, "owner13@example.com")
    org = _create_org(client, csrf_token)
    owner_id = _membership_id(app, org["id"], "owner13@example.com")
    customer_id = _make_customer(app, org["id"])
    _register_and_login(client, "employee13@example.com", name="Employee Thirteen")
    employee_id = _give_role(app, org["id"], "employee13@example.com", MembershipRole.EMPLOYEE)
    request_id = _make_request(
        app, org["id"], customer_id, owner_id, assignee_membership_id=uuid.UUID(employee_id)
    )
    owner_csrf = _login(client, "owner13@example.com")
    post_response = _post_comment(client, owner_csrf, org["id"], request_id, body="From owner")
    assert post_response.status_code == 201
    employee_csrf = _login(client, "employee13@example.com")

    response = _list_comments(client, org["id"], request_id)

    assert response.status_code == 200
    assert len(response.get_json()["data"]) == 1


def test_employee_cannot_list_comments_on_a_request_not_assigned_to_them(client, app):
    csrf_token = _register_and_login(client, "owner14@example.com")
    org = _create_org(client, csrf_token)
    owner_id = _membership_id(app, org["id"], "owner14@example.com")
    customer_id = _make_customer(app, org["id"])
    _register_and_login(client, "employee14@example.com", name="Employee Fourteen")
    _give_role(app, org["id"], "employee14@example.com", MembershipRole.EMPLOYEE)
    request_id = _make_request(app, org["id"], customer_id, owner_id)
    employee_csrf = _login(client, "employee14@example.com")

    response = _list_comments(client, org["id"], request_id)

    assert response.status_code == 403


def test_list_nonexistent_request_returns_404(client):
    csrf_token = _register_and_login(client, "owner15@example.com")
    org = _create_org(client, csrf_token)

    response = _list_comments(client, org["id"], str(uuid.uuid4()))

    assert response.status_code == 404


def test_list_cross_org_request_returns_404(client, app):
    owner_a_csrf = _register_and_login(client, "owner16a@example.com")
    org_a = _create_org(client, owner_a_csrf, name="Org A")
    owner_b_csrf = _register_and_login(client, "owner16b@example.com")
    org_b = _create_org(client, owner_b_csrf, name="Org B")
    owner_b_id = _membership_id(app, org_b["id"], "owner16b@example.com")
    customer_b = _make_customer(app, org_b["id"])
    request_in_org_b = _make_request(app, org_b["id"], customer_b, owner_b_id)
    _login(client, "owner16a@example.com")

    response = _list_comments(client, org_a["id"], request_in_org_b)

    assert response.status_code == 404


def test_pagination_meta(client, app):
    csrf_token = _register_and_login(client, "owner17@example.com")
    org = _create_org(client, csrf_token)
    owner_id = _membership_id(app, org["id"], "owner17@example.com")
    customer_id = _make_customer(app, org["id"])
    request_id = _make_request(app, org["id"], customer_id, owner_id)
    for i in range(3):
        _post_comment(client, csrf_token, org["id"], request_id, body=f"Comment {i}")

    response = _list_comments(client, org["id"], request_id, per_page=2, page=1)

    assert response.status_code == 200
    body = response.get_json()
    assert len(body["data"]) == 2
    assert body["meta"] == {"page": 1, "per_page": 2, "total": 3, "total_pages": 2}
