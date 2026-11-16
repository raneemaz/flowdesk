import uuid

import pytest

from app.extensions import db
from app.models import Customer, CustomerStatus, Membership, MembershipRole, MembershipStatus, Organization, User


@pytest.fixture(autouse=True)
def _clean(app):
    yield
    with app.app_context():
        from app.models import CustomerRequest

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


def _make_customer(app, organization_id, name="Jane Customer", status=CustomerStatus.ACTIVE):
    with app.app_context():
        customer = Customer(organization_id=uuid.UUID(organization_id), name=name, status=status)
        db.session.add(customer)
        db.session.commit()
        return str(customer.id)


def _create_request(client, csrf_token, org_id, **body):
    body.setdefault("title", "Can't log in")
    return client.post(
        f"/api/v1/organizations/{org_id}/customer-requests", json=body, headers={"X-CSRF-Token": csrf_token}
    )


def test_unauthenticated_request_returns_401(client):
    response = client.post(
        "/api/v1/organizations/00000000-0000-0000-0000-000000000000/customer-requests", json={}
    )
    assert response.status_code == 401


def test_owner_can_create_a_request(client, app):
    csrf_token = _register_and_login(client, "owner@example.com")
    org = _create_org(client, csrf_token)
    customer_id = _make_customer(app, org["id"])

    response = _create_request(client, csrf_token, org["id"], customer_id=customer_id, title="Can't log in")

    assert response.status_code == 201
    body = response.get_json()["data"]
    assert body["title"] == "Can't log in"
    assert body["customer_id"] == customer_id
    assert body["status"] == "new"
    assert body["priority"] == "medium"
    assert body["assignee_membership_id"] is None


@pytest.mark.parametrize("role", [MembershipRole.MANAGER, MembershipRole.CUSTOMER_SUPPORT])
def test_roles_with_customer_request_manage_can_create_a_request(client, app, role):
    csrf_token = _register_and_login(client, f"owner-{role.value}@example.com")
    org = _create_org(client, csrf_token)
    customer_id = _make_customer(app, org["id"])
    other_email = f"{role.value}@example.com"
    other_csrf = _register_and_login(client, other_email)
    _give_role(app, org["id"], other_email, role)

    response = _create_request(client, other_csrf, org["id"], customer_id=customer_id)

    assert response.status_code == 201


@pytest.mark.parametrize("role", [MembershipRole.EMPLOYEE, MembershipRole.ACCOUNTANT])
def test_roles_without_full_scope_cannot_create_a_request(client, app, role):
    csrf_token = _register_and_login(client, f"owner2-{role.value}@example.com")
    org = _create_org(client, csrf_token)
    customer_id = _make_customer(app, org["id"])
    other_email = f"{role.value}2@example.com"
    other_csrf = _register_and_login(client, other_email)
    _give_role(app, org["id"], other_email, role)

    response = _create_request(client, other_csrf, org["id"], customer_id=customer_id)

    assert response.status_code == 403


def test_create_without_csrf_token_returns_403(client, app):
    csrf_token = _register_and_login(client, "owner3@example.com")
    org = _create_org(client, csrf_token)
    customer_id = _make_customer(app, org["id"])

    response = client.post(
        f"/api/v1/organizations/{org['id']}/customer-requests",
        json={"customer_id": customer_id, "title": "Can't log in"},
    )

    assert response.status_code == 403


def test_create_in_an_organization_the_caller_does_not_belong_to_returns_404(client, app):
    csrf_token = _register_and_login(client, "owner4@example.com")
    org = _create_org(client, csrf_token)
    customer_id = _make_customer(app, org["id"])
    outsider_csrf = _register_and_login(client, "outsider@example.com")

    response = _create_request(client, outsider_csrf, org["id"], customer_id=customer_id)

    assert response.status_code == 404


def test_create_requires_a_title(client, app):
    csrf_token = _register_and_login(client, "owner5@example.com")
    org = _create_org(client, csrf_token)
    customer_id = _make_customer(app, org["id"])

    response = client.post(
        f"/api/v1/organizations/{org['id']}/customer-requests",
        json={"customer_id": customer_id},
        headers={"X-CSRF-Token": csrf_token},
    )

    assert response.status_code == 422


def test_create_rejects_a_blank_title(client, app):
    csrf_token = _register_and_login(client, "owner6@example.com")
    org = _create_org(client, csrf_token)
    customer_id = _make_customer(app, org["id"])

    response = _create_request(client, csrf_token, org["id"], customer_id=customer_id, title="   ")

    assert response.status_code == 422


def test_create_requires_a_customer_id(client):
    csrf_token = _register_and_login(client, "owner7@example.com")
    org = _create_org(client, csrf_token)

    response = client.post(
        f"/api/v1/organizations/{org['id']}/customer-requests",
        json={"title": "Can't log in"},
        headers={"X-CSRF-Token": csrf_token},
    )

    assert response.status_code == 422


def test_create_rejects_an_unknown_customer_id(client):
    csrf_token = _register_and_login(client, "owner8@example.com")
    org = _create_org(client, csrf_token)

    response = _create_request(
        client, csrf_token, org["id"], customer_id="00000000-0000-0000-0000-000000000000"
    )

    assert response.status_code == 422
    assert response.get_json()["error"]["code"] == "INVALID_CUSTOMER"


def test_create_rejects_a_cross_org_customer_id(client, app):
    owner_a_csrf = _register_and_login(client, "owner9a@example.com")
    org_a = _create_org(client, owner_a_csrf, name="Org A")
    owner_b_csrf = _register_and_login(client, "owner9b@example.com")
    org_b = _create_org(client, owner_b_csrf, name="Org B")
    foreign_customer_id = _make_customer(app, org_b["id"])
    owner_a_csrf = _login(client, "owner9a@example.com")

    response = _create_request(client, owner_a_csrf, org_a["id"], customer_id=foreign_customer_id)

    assert response.status_code == 422
    assert response.get_json()["error"]["code"] == "INVALID_CUSTOMER"


def test_create_rejects_an_archived_customer_id(client, app):
    csrf_token = _register_and_login(client, "owner10@example.com")
    org = _create_org(client, csrf_token)
    archived_customer_id = _make_customer(app, org["id"], status=CustomerStatus.ARCHIVED)

    response = _create_request(client, csrf_token, org["id"], customer_id=archived_customer_id)

    assert response.status_code == 422
    assert response.get_json()["error"]["code"] == "INVALID_CUSTOMER"


def test_create_with_all_fields(client, app):
    csrf_token = _register_and_login(client, "owner11@example.com")
    org = _create_org(client, csrf_token)
    customer_id = _make_customer(app, org["id"])

    response = _create_request(
        client,
        csrf_token,
        org["id"],
        customer_id=customer_id,
        title="Can't log in",
        description="Customer locked out",
        category="technical",
        priority="high",
        due_date="2026-01-10",
    )

    assert response.status_code == 201
    body = response.get_json()["data"]
    assert body["description"] == "Customer locked out"
    assert body["category"] == "technical"
    assert body["priority"] == "high"
    assert body["due_date"] == "2026-01-10"


def test_create_rejects_unknown_fields(client, app):
    csrf_token = _register_and_login(client, "owner12@example.com")
    org = _create_org(client, csrf_token)
    customer_id = _make_customer(app, org["id"])

    response = _create_request(
        client, csrf_token, org["id"], customer_id=customer_id, assignee_membership_id="00000000-0000-0000-0000-000000000000"
    )

    assert response.status_code == 422


def test_create_sets_creator_to_the_caller_regardless_of_body(client, app):
    csrf_token = _register_and_login(client, "owner13@example.com")
    org = _create_org(client, csrf_token)
    customer_id = _make_customer(app, org["id"])

    response = _create_request(client, csrf_token, org["id"], customer_id=customer_id)
    assert response.status_code == 201
    request_id = response.get_json()["data"]["id"]

    with app.app_context():
        from app.models import CustomerRequest

        customer_request = db.session.get(CustomerRequest, request_id)
        user = db.session.query(User).filter_by(email="owner13@example.com").one()
        creator_membership = (
            db.session.query(Membership)
            .filter_by(user_id=user.id, organization_id=customer_request.organization_id)
            .one()
        )
        assert str(customer_request.creator_membership_id) == str(creator_membership.id)
