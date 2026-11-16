import uuid

import pytest

from app.extensions import db
from app.models import (
    Customer,
    CustomerRequest,
    Membership,
    MembershipRole,
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


def _make_request(app, organization_id, customer_id, creator_membership_id, status=RequestStatus.NEW, **kwargs):
    with app.app_context():
        customer_request = CustomerRequest(
            organization_id=uuid.UUID(organization_id),
            customer_id=uuid.UUID(customer_id),
            creator_membership_id=uuid.UUID(creator_membership_id),
            title=kwargs.pop("title", "Request"),
            status=status,
            **kwargs,
        )
        db.session.add(customer_request)
        db.session.commit()
        return str(customer_request.id)


def _set_status(client, csrf_token, org_id, request_id, status, resolution_notes=None):
    body = {"status": status}
    if resolution_notes is not None:
        body["resolution_notes"] = resolution_notes
    return client.patch(
        f"/api/v1/organizations/{org_id}/customer-requests/{request_id}/status",
        json=body,
        headers={"X-CSRF-Token": csrf_token},
    )


def test_unauthenticated_request_returns_401(client):
    response = client.patch(
        "/api/v1/organizations/00000000-0000-0000-0000-000000000000/customer-requests/"
        "00000000-0000-0000-0000-000000000000/status",
        json={"status": "assigned"},
    )
    assert response.status_code == 401


@pytest.mark.parametrize(
    "from_status,to_status,needs_assignee",
    [
        (RequestStatus.NEW, "assigned", True),
        (RequestStatus.ASSIGNED, "in_progress", False),
        (RequestStatus.IN_PROGRESS, "waiting_for_customer", False),
        (RequestStatus.WAITING_FOR_CUSTOMER, "resolved", False),
        (RequestStatus.RESOLVED, "closed", False),
    ],
)
def test_owner_can_make_every_legal_transition(client, app, from_status, to_status, needs_assignee):
    csrf_token = _register_and_login(client, f"owner-{from_status.value}-{to_status}@example.com")
    org = _create_org(client, csrf_token)
    owner_id = _membership_id(app, org["id"], f"owner-{from_status.value}-{to_status}@example.com")
    customer_id = _make_customer(app, org["id"])
    kwargs = {"assignee_membership_id": uuid.UUID(owner_id)} if needs_assignee else {}
    request_id = _make_request(app, org["id"], customer_id, owner_id, status=from_status, **kwargs)

    response = _set_status(client, csrf_token, org["id"], request_id, to_status)

    assert response.status_code == 200
    assert response.get_json()["data"]["status"] == to_status


@pytest.mark.parametrize(
    "from_status,to_status",
    [
        (RequestStatus.NEW, "in_progress"),
        (RequestStatus.ASSIGNED, "resolved"),
        (RequestStatus.ASSIGNED, "closed"),
        (RequestStatus.WAITING_FOR_CUSTOMER, "closed"),
    ],
)
def test_rejects_skipping_a_stage(client, app, from_status, to_status):
    csrf_token = _register_and_login(client, f"owner-skip-{from_status.value}-{to_status}@example.com")
    org = _create_org(client, csrf_token)
    owner_id = _membership_id(app, org["id"], f"owner-skip-{from_status.value}-{to_status}@example.com")
    customer_id = _make_customer(app, org["id"])
    request_id = _make_request(app, org["id"], customer_id, owner_id, status=from_status)

    response = _set_status(client, csrf_token, org["id"], request_id, to_status)

    assert response.status_code == 422
    assert response.get_json()["error"]["code"] == "INVALID_STATUS_TRANSITION"


def test_closed_is_terminal(client, app):
    csrf_token = _register_and_login(client, "owner-terminal@example.com")
    org = _create_org(client, csrf_token)
    owner_id = _membership_id(app, org["id"], "owner-terminal@example.com")
    customer_id = _make_customer(app, org["id"])
    request_id = _make_request(app, org["id"], customer_id, owner_id, status=RequestStatus.CLOSED)

    response = _set_status(client, csrf_token, org["id"], request_id, "resolved")

    assert response.status_code == 422


def test_cannot_mark_assigned_without_an_assignee(client, app):
    csrf_token = _register_and_login(client, "owner-noassignee@example.com")
    org = _create_org(client, csrf_token)
    owner_id = _membership_id(app, org["id"], "owner-noassignee@example.com")
    customer_id = _make_customer(app, org["id"])
    request_id = _make_request(app, org["id"], customer_id, owner_id, status=RequestStatus.NEW)

    response = _set_status(client, csrf_token, org["id"], request_id, "assigned")

    assert response.status_code == 422
    assert response.get_json()["error"]["code"] == "INVALID_STATUS_TRANSITION"


def test_employee_can_make_forward_progress_moves_on_their_own_request(client, app):
    csrf_token = _register_and_login(client, "owner2@example.com")
    org = _create_org(client, csrf_token)
    owner_id = _membership_id(app, org["id"], "owner2@example.com")
    customer_id = _make_customer(app, org["id"])
    employee_csrf = _register_and_login(client, "employee2@example.com")
    employee_id = _give_role(app, org["id"], "employee2@example.com", MembershipRole.EMPLOYEE)
    request_id = _make_request(
        app,
        org["id"],
        customer_id,
        owner_id,
        status=RequestStatus.ASSIGNED,
        assignee_membership_id=uuid.UUID(employee_id),
    )

    response = _set_status(client, employee_csrf, org["id"], request_id, "in_progress")

    assert response.status_code == 200
    assert response.get_json()["data"]["status"] == "in_progress"


def test_employee_cannot_resolve_a_request(client, app):
    csrf_token = _register_and_login(client, "owner3@example.com")
    org = _create_org(client, csrf_token)
    owner_id = _membership_id(app, org["id"], "owner3@example.com")
    customer_id = _make_customer(app, org["id"])
    employee_csrf = _register_and_login(client, "employee3@example.com")
    employee_id = _give_role(app, org["id"], "employee3@example.com", MembershipRole.EMPLOYEE)
    request_id = _make_request(
        app,
        org["id"],
        customer_id,
        owner_id,
        status=RequestStatus.WAITING_FOR_CUSTOMER,
        assignee_membership_id=uuid.UUID(employee_id),
    )

    response = _set_status(client, employee_csrf, org["id"], request_id, "resolved")

    assert response.status_code == 403


def test_employee_cannot_close_a_request(client, app):
    csrf_token = _register_and_login(client, "owner4@example.com")
    org = _create_org(client, csrf_token)
    owner_id = _membership_id(app, org["id"], "owner4@example.com")
    customer_id = _make_customer(app, org["id"])
    employee_csrf = _register_and_login(client, "employee4@example.com")
    employee_id = _give_role(app, org["id"], "employee4@example.com", MembershipRole.EMPLOYEE)
    request_id = _make_request(
        app,
        org["id"],
        customer_id,
        owner_id,
        status=RequestStatus.RESOLVED,
        assignee_membership_id=uuid.UUID(employee_id),
    )

    response = _set_status(client, employee_csrf, org["id"], request_id, "closed")

    assert response.status_code == 403


def test_employee_cannot_act_on_a_request_not_assigned_to_them(client, app):
    csrf_token = _register_and_login(client, "owner5@example.com")
    org = _create_org(client, csrf_token)
    owner_id = _membership_id(app, org["id"], "owner5@example.com")
    customer_id = _make_customer(app, org["id"])
    employee_csrf = _register_and_login(client, "employee5@example.com")
    _give_role(app, org["id"], "employee5@example.com", MembershipRole.EMPLOYEE)
    request_id = _make_request(app, org["id"], customer_id, owner_id, status=RequestStatus.ASSIGNED)

    response = _set_status(client, employee_csrf, org["id"], request_id, "in_progress")

    assert response.status_code == 403


def test_accountant_cannot_change_status(client, app):
    csrf_token = _register_and_login(client, "owner6@example.com")
    org = _create_org(client, csrf_token)
    owner_id = _membership_id(app, org["id"], "owner6@example.com")
    customer_id = _make_customer(app, org["id"])
    accountant_csrf = _register_and_login(client, "accountant6@example.com")
    _give_role(app, org["id"], "accountant6@example.com", MembershipRole.ACCOUNTANT)
    request_id = _make_request(app, org["id"], customer_id, owner_id)

    response = _set_status(client, accountant_csrf, org["id"], request_id, "assigned")

    assert response.status_code == 403


def test_status_change_can_set_resolution_notes(client, app):
    csrf_token = _register_and_login(client, "owner7@example.com")
    org = _create_org(client, csrf_token)
    owner_id = _membership_id(app, org["id"], "owner7@example.com")
    customer_id = _make_customer(app, org["id"])
    request_id = _make_request(app, org["id"], customer_id, owner_id, status=RequestStatus.RESOLVED)

    response = _set_status(client, csrf_token, org["id"], request_id, "closed", resolution_notes="Fixed via reset.")

    assert response.status_code == 200
    assert response.get_json()["data"]["resolution_notes"] == "Fixed via reset."


def test_resolution_notes_can_be_set_without_a_status_change(client, app):
    csrf_token = _register_and_login(client, "owner8@example.com")
    org = _create_org(client, csrf_token)
    owner_id = _membership_id(app, org["id"], "owner8@example.com")
    customer_id = _make_customer(app, org["id"])
    request_id = _make_request(app, org["id"], customer_id, owner_id, status=RequestStatus.IN_PROGRESS)

    response = _set_status(client, csrf_token, org["id"], request_id, "in_progress", resolution_notes="Investigating.")

    assert response.status_code == 200
    assert response.get_json()["data"]["resolution_notes"] == "Investigating."
    assert response.get_json()["data"]["status"] == "in_progress"


def test_same_status_is_a_noop_and_writes_no_history(client, app):
    csrf_token = _register_and_login(client, "owner9@example.com")
    org = _create_org(client, csrf_token)
    owner_id = _membership_id(app, org["id"], "owner9@example.com")
    customer_id = _make_customer(app, org["id"])
    request_id = _make_request(app, org["id"], customer_id, owner_id, status=RequestStatus.IN_PROGRESS)

    response = _set_status(client, csrf_token, org["id"], request_id, "in_progress")

    assert response.status_code == 200
    with app.app_context():
        assert db.session.query(RequestHistory).filter_by(request_id=uuid.UUID(request_id)).count() == 0


def test_status_change_without_csrf_returns_403(client, app):
    csrf_token = _register_and_login(client, "owner10@example.com")
    org = _create_org(client, csrf_token)
    owner_id = _membership_id(app, org["id"], "owner10@example.com")
    customer_id = _make_customer(app, org["id"])
    request_id = _make_request(app, org["id"], customer_id, owner_id)

    response = client.patch(
        f"/api/v1/organizations/{org['id']}/customer-requests/{request_id}/status", json={"status": "assigned"}
    )

    assert response.status_code == 403


def test_status_change_nonexistent_request_returns_404(client):
    csrf_token = _register_and_login(client, "owner11@example.com")
    org = _create_org(client, csrf_token)

    response = _set_status(client, csrf_token, org["id"], "00000000-0000-0000-0000-000000000000", "assigned")

    assert response.status_code == 404


def test_status_change_rejects_an_unknown_status_value(client, app):
    csrf_token = _register_and_login(client, "owner12@example.com")
    org = _create_org(client, csrf_token)
    owner_id = _membership_id(app, org["id"], "owner12@example.com")
    customer_id = _make_customer(app, org["id"])
    request_id = _make_request(app, org["id"], customer_id, owner_id)

    response = client.patch(
        f"/api/v1/organizations/{org['id']}/customer-requests/{request_id}/status",
        json={"status": "archived"},
        headers={"X-CSRF-Token": csrf_token},
    )

    assert response.status_code == 422
