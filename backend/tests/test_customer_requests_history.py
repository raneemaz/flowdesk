import uuid

import pytest

from app.extensions import db
from app.models import Customer, CustomerRequest, Membership, MembershipRole, Organization, RequestHistory, User


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


def _make_history(app, organization_id, request_id, actor_membership_id, event_type, previous_value=None, new_value=None):
    with app.app_context():
        entry = RequestHistory(
            organization_id=uuid.UUID(organization_id),
            request_id=uuid.UUID(request_id),
            actor_membership_id=uuid.UUID(actor_membership_id) if actor_membership_id else None,
            event_type=event_type,
            previous_value=previous_value,
            new_value=new_value,
        )
        db.session.add(entry)
        db.session.commit()
        return str(entry.id)


def _get_history(client, org_id, request_id, **params):
    return client.get(f"/api/v1/organizations/{org_id}/customer-requests/{request_id}/history", query_string=params)


def test_unauthenticated_request_returns_401(client):
    response = client.get(
        "/api/v1/organizations/00000000-0000-0000-0000-000000000000/customer-requests/"
        "00000000-0000-0000-0000-000000000000/history"
    )
    assert response.status_code == 401


def test_owner_can_view_history(client, app):
    csrf_token = _register_and_login(client, "owner@example.com")
    org = _create_org(client, csrf_token)
    owner_id = _membership_id(app, org["id"], "owner@example.com")
    customer_id = _make_customer(app, org["id"])
    request_id = _make_request(app, org["id"], customer_id, owner_id)
    _make_history(app, org["id"], request_id, owner_id, "status_changed", "new", "assigned")

    response = _get_history(client, org["id"], request_id)

    assert response.status_code == 200
    body = response.get_json()["data"]
    assert len(body) == 1
    assert body[0]["event_type"] == "status_changed"
    assert body[0]["previous_value"] == "new"
    assert body[0]["new_value"] == "assigned"
    assert body[0]["actor_membership_id"] == owner_id


def test_assignee_can_view_history_of_their_own_request(client, app):
    csrf_token = _register_and_login(client, "owner2@example.com")
    org = _create_org(client, csrf_token)
    owner_id = _membership_id(app, org["id"], "owner2@example.com")
    customer_id = _make_customer(app, org["id"])
    _register_and_login(client, "employee2@example.com", name="Employee Two")
    employee_id = _give_role(app, org["id"], "employee2@example.com", MembershipRole.EMPLOYEE)
    request_id = _make_request(
        app, org["id"], customer_id, owner_id, assignee_membership_id=uuid.UUID(employee_id)
    )
    _make_history(app, org["id"], request_id, owner_id, "assignee_changed", None, employee_id)
    employee_csrf = _login(client, "employee2@example.com")

    response = _get_history(client, org["id"], request_id)

    assert response.status_code == 200
    assert len(response.get_json()["data"]) == 1


def test_employee_cannot_view_history_of_a_request_not_assigned_to_them(client, app):
    csrf_token = _register_and_login(client, "owner3@example.com")
    org = _create_org(client, csrf_token)
    owner_id = _membership_id(app, org["id"], "owner3@example.com")
    customer_id = _make_customer(app, org["id"])
    _register_and_login(client, "employee3@example.com", name="Employee Three")
    _give_role(app, org["id"], "employee3@example.com", MembershipRole.EMPLOYEE)
    request_id = _make_request(app, org["id"], customer_id, owner_id)
    employee_csrf = _login(client, "employee3@example.com")

    response = _get_history(client, org["id"], request_id)

    assert response.status_code == 403


def test_accountant_cannot_view_history(client, app):
    csrf_token = _register_and_login(client, "owner4@example.com")
    org = _create_org(client, csrf_token)
    owner_id = _membership_id(app, org["id"], "owner4@example.com")
    customer_id = _make_customer(app, org["id"])
    request_id = _make_request(app, org["id"], customer_id, owner_id)
    accountant_csrf = _register_and_login(client, "accountant4@example.com")
    _give_role(app, org["id"], "accountant4@example.com", MembershipRole.ACCOUNTANT)

    response = _get_history(client, org["id"], request_id)

    assert response.status_code == 403


def test_history_nonexistent_request_returns_404(client):
    csrf_token = _register_and_login(client, "owner5@example.com")
    org = _create_org(client, csrf_token)

    response = _get_history(client, org["id"], str(uuid.uuid4()))

    assert response.status_code == 404


def test_history_cross_org_request_returns_404(client, app):
    owner_a_csrf = _register_and_login(client, "owner6a@example.com")
    org_a = _create_org(client, owner_a_csrf, name="Org A")
    owner_b_csrf = _register_and_login(client, "owner6b@example.com")
    org_b = _create_org(client, owner_b_csrf, name="Org B")
    owner_b_id = _membership_id(app, org_b["id"], "owner6b@example.com")
    customer_b = _make_customer(app, org_b["id"])
    request_in_org_b = _make_request(app, org_b["id"], customer_b, owner_b_id)
    _login(client, "owner6a@example.com")

    response = _get_history(client, org_a["id"], request_in_org_b)

    assert response.status_code == 404


def test_history_is_chronological(client, app):
    csrf_token = _register_and_login(client, "owner7@example.com")
    org = _create_org(client, csrf_token)
    owner_id = _membership_id(app, org["id"], "owner7@example.com")
    customer_id = _make_customer(app, org["id"])
    request_id = _make_request(app, org["id"], customer_id, owner_id)
    first_id = _make_history(app, org["id"], request_id, owner_id, "assignee_changed", None, owner_id)
    with app.app_context():
        entry = db.session.get(RequestHistory, uuid.UUID(first_id))
        entry.created_at = entry.created_at.replace(year=entry.created_at.year - 1)
        db.session.commit()
    _make_history(app, org["id"], request_id, owner_id, "status_changed", "new", "assigned")

    response = _get_history(client, org["id"], request_id)

    assert response.status_code == 200
    body = response.get_json()["data"]
    assert [e["event_type"] for e in body] == ["assignee_changed", "status_changed"]


def test_pagination_meta(client, app):
    csrf_token = _register_and_login(client, "owner8@example.com")
    org = _create_org(client, csrf_token)
    owner_id = _membership_id(app, org["id"], "owner8@example.com")
    customer_id = _make_customer(app, org["id"])
    request_id = _make_request(app, org["id"], customer_id, owner_id)
    for i in range(3):
        _make_history(app, org["id"], request_id, owner_id, "resolution_notes_changed", f"note{i}", f"note{i + 1}")

    response = _get_history(client, org["id"], request_id, per_page=2, page=1)

    assert response.status_code == 200
    body = response.get_json()
    assert len(body["data"]) == 2
    assert body["meta"] == {"page": 1, "per_page": 2, "total": 3, "total_pages": 2}


def test_history_rejects_unknown_query_param(client, app):
    csrf_token = _register_and_login(client, "owner9@example.com")
    org = _create_org(client, csrf_token)
    owner_id = _membership_id(app, org["id"], "owner9@example.com")
    customer_id = _make_customer(app, org["id"])
    request_id = _make_request(app, org["id"], customer_id, owner_id)

    response = _get_history(client, org["id"], request_id, event_type="status_changed")

    assert response.status_code == 422


def test_history_reflects_real_assign_and_status_actions(client, app):
    """End-to-end: the /assign and /status endpoints (FD-037) write the
    rows this endpoint reads back. /assign on a still-new request
    writes both assignee_changed and its own auto-advance
    status_changed (new -> assigned); the follow-up /status call
    (assigned -> in_progress) writes a second status_changed."""
    csrf_token = _register_and_login(client, "owner10@example.com")
    org = _create_org(client, csrf_token)
    owner_id = _membership_id(app, org["id"], "owner10@example.com")
    customer_id = _make_customer(app, org["id"])
    request_id = _make_request(app, org["id"], customer_id, owner_id)
    _register_and_login(client, "employee10@example.com", name="Employee Ten")
    employee_id = _give_role(app, org["id"], "employee10@example.com", MembershipRole.EMPLOYEE)
    owner_csrf = _login(client, "owner10@example.com")

    client.patch(
        f"/api/v1/organizations/{org['id']}/customer-requests/{request_id}/assign",
        json={"assignee_membership_id": employee_id},
        headers={"X-CSRF-Token": owner_csrf},
    )
    client.patch(
        f"/api/v1/organizations/{org['id']}/customer-requests/{request_id}/status",
        json={"status": "in_progress"},
        headers={"X-CSRF-Token": owner_csrf},
    )

    response = _get_history(client, org["id"], request_id)

    assert response.status_code == 200
    body = response.get_json()["data"]
    assert [e["event_type"] for e in body] == ["assignee_changed", "status_changed", "status_changed"]
    assert response.get_json()["meta"]["total"] == 3
