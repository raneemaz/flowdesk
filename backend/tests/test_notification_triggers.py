import uuid

import pytest

from app.extensions import db
from app.models import (
    Customer,
    CustomerRequest,
    CustomerStatus,
    Invoice,
    InvoiceLineItem,
    Membership,
    MembershipRole,
    MembershipStatus,
    Notification,
    Organization,
    Payment,
    RequestHistory,
    RequestStatus,
    Task,
    TaskHistory,
    User,
)


@pytest.fixture(autouse=True)
def _clean(app):
    yield
    with app.app_context():
        db.session.query(Notification).delete()
        db.session.query(Payment).delete()
        db.session.query(InvoiceLineItem).delete()
        db.session.query(Invoice).delete()
        db.session.query(TaskHistory).delete()
        db.session.query(Task).delete()
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
    return client.post("/api/v1/organizations", json={"name": name}, headers={"X-CSRF-Token": csrf_token}).get_json()[
        "data"
    ]


def _give_role(app, organization_id, email, role, status=MembershipStatus.ACTIVE):
    with app.app_context():
        user = db.session.query(User).filter_by(email=email.lower()).one()
        membership = Membership(organization_id=organization_id, user_id=user.id, role=role, status=status)
        db.session.add(membership)
        db.session.commit()
        return str(membership.id)


def _membership_id(app, organization_id, email):
    with app.app_context():
        user = db.session.query(User).filter_by(email=email.lower()).one()
        membership = (
            db.session.query(Membership).filter_by(organization_id=uuid.UUID(organization_id), user_id=user.id).one()
        )
        return str(membership.id)


def _make_customer(app, organization_id, name="Jane Customer"):
    with app.app_context():
        customer = Customer(organization_id=uuid.UUID(organization_id), name=name, status=CustomerStatus.ACTIVE)
        db.session.add(customer)
        db.session.commit()
        return str(customer.id)


def _notifications_for(app, recipient_membership_id):
    with app.app_context():
        return (
            db.session.query(Notification)
            .filter_by(recipient_membership_id=uuid.UUID(recipient_membership_id))
            .all()
        )


# --- task_assigned ----------------------------------------------------


def test_assigning_a_task_notifies_the_new_assignee(client, app):
    csrf_token = _register_and_login(client, "notiftrig-owner1@example.com")
    org = _create_org(client, csrf_token)
    _register_and_login(client, "notiftrig-emp1@example.com", name="Employee")
    employee_id = _give_role(app, org["id"], "notiftrig-emp1@example.com", MembershipRole.EMPLOYEE)
    csrf_token = _login(client, "notiftrig-owner1@example.com")
    task_id = client.post(
        f"/api/v1/organizations/{org['id']}/tasks", json={"title": "Do it"}, headers={"X-CSRF-Token": csrf_token}
    ).get_json()["data"]["id"]

    response = client.patch(
        f"/api/v1/organizations/{org['id']}/tasks/{task_id}/assign",
        json={"assignee_membership_id": employee_id},
        headers={"X-CSRF-Token": csrf_token},
    )
    assert response.status_code == 200

    notifications = _notifications_for(app, employee_id)
    assert len(notifications) == 1
    assert notifications[0].type == "task_assigned"
    assert notifications[0].entity_type == "task"
    assert str(notifications[0].entity_id) == task_id


def test_assigning_a_task_to_yourself_does_not_notify_yourself(client, app):
    csrf_token = _register_and_login(client, "notiftrig-owner1b@example.com")
    org = _create_org(client, csrf_token)
    owner_id = _membership_id(app, org["id"], "notiftrig-owner1b@example.com")
    task_id = client.post(
        f"/api/v1/organizations/{org['id']}/tasks", json={"title": "Do it"}, headers={"X-CSRF-Token": csrf_token}
    ).get_json()["data"]["id"]

    client.patch(
        f"/api/v1/organizations/{org['id']}/tasks/{task_id}/assign",
        json={"assignee_membership_id": owner_id},
        headers={"X-CSRF-Token": csrf_token},
    )

    assert _notifications_for(app, owner_id) == []


def test_reassigning_to_the_same_assignee_does_not_notify_again(client, app):
    csrf_token = _register_and_login(client, "notiftrig-owner1c@example.com")
    org = _create_org(client, csrf_token)
    _register_and_login(client, "notiftrig-emp1c@example.com", name="Employee")
    employee_id = _give_role(app, org["id"], "notiftrig-emp1c@example.com", MembershipRole.EMPLOYEE)
    csrf_token = _login(client, "notiftrig-owner1c@example.com")
    task_id = client.post(
        f"/api/v1/organizations/{org['id']}/tasks", json={"title": "Do it"}, headers={"X-CSRF-Token": csrf_token}
    ).get_json()["data"]["id"]
    client.patch(
        f"/api/v1/organizations/{org['id']}/tasks/{task_id}/assign",
        json={"assignee_membership_id": employee_id},
        headers={"X-CSRF-Token": csrf_token},
    )

    response = client.patch(
        f"/api/v1/organizations/{org['id']}/tasks/{task_id}/assign",
        json={"assignee_membership_id": employee_id},
        headers={"X-CSRF-Token": csrf_token},
    )
    assert response.status_code == 200

    assert len(_notifications_for(app, employee_id)) == 1


# --- task_comment_added -------------------------------------------------


def test_commenting_on_an_assigned_task_notifies_the_assignee(client, app):
    csrf_token = _register_and_login(client, "notiftrig-owner2@example.com")
    org = _create_org(client, csrf_token)
    _register_and_login(client, "notiftrig-emp2@example.com", name="Employee")
    employee_id = _give_role(app, org["id"], "notiftrig-emp2@example.com", MembershipRole.EMPLOYEE)
    csrf_token = _login(client, "notiftrig-owner2@example.com")
    task_id = client.post(
        f"/api/v1/organizations/{org['id']}/tasks", json={"title": "Do it"}, headers={"X-CSRF-Token": csrf_token}
    ).get_json()["data"]["id"]
    client.patch(
        f"/api/v1/organizations/{org['id']}/tasks/{task_id}/assign",
        json={"assignee_membership_id": employee_id},
        headers={"X-CSRF-Token": csrf_token},
    )

    response = client.post(
        f"/api/v1/organizations/{org['id']}/tasks/{task_id}/comments",
        json={"body": "How's it going?"},
        headers={"X-CSRF-Token": csrf_token},
    )
    assert response.status_code == 201

    notifications = [n for n in _notifications_for(app, employee_id) if n.type == "task_comment_added"]
    assert len(notifications) == 1


def test_commenting_on_your_own_assigned_task_does_not_notify_yourself(client, app):
    csrf_token = _register_and_login(client, "notiftrig-owner2b@example.com")
    org = _create_org(client, csrf_token)
    owner_id = _membership_id(app, org["id"], "notiftrig-owner2b@example.com")
    task_id = client.post(
        f"/api/v1/organizations/{org['id']}/tasks", json={"title": "Do it"}, headers={"X-CSRF-Token": csrf_token}
    ).get_json()["data"]["id"]
    client.patch(
        f"/api/v1/organizations/{org['id']}/tasks/{task_id}/assign",
        json={"assignee_membership_id": owner_id},
        headers={"X-CSRF-Token": csrf_token},
    )

    client.post(
        f"/api/v1/organizations/{org['id']}/tasks/{task_id}/comments",
        json={"body": "Note to self"},
        headers={"X-CSRF-Token": csrf_token},
    )

    comment_notifications = [n for n in _notifications_for(app, owner_id) if n.type == "task_comment_added"]
    assert comment_notifications == []


# --- request_assigned / request_status_changed / request_comment_added --


def test_assigning_a_request_notifies_the_new_assignee(client, app):
    csrf_token = _register_and_login(client, "notiftrig-owner3@example.com")
    org = _create_org(client, csrf_token)
    _register_and_login(client, "notiftrig-emp3@example.com", name="Employee")
    employee_id = _give_role(app, org["id"], "notiftrig-emp3@example.com", MembershipRole.EMPLOYEE)
    csrf_token = _login(client, "notiftrig-owner3@example.com")
    customer_id = _make_customer(app, org["id"])
    request_id = client.post(
        f"/api/v1/organizations/{org['id']}/customer-requests",
        json={"title": "Help", "customer_id": customer_id},
        headers={"X-CSRF-Token": csrf_token},
    ).get_json()["data"]["id"]

    response = client.patch(
        f"/api/v1/organizations/{org['id']}/customer-requests/{request_id}/assign",
        json={"assignee_membership_id": employee_id},
        headers={"X-CSRF-Token": csrf_token},
    )
    assert response.status_code == 200

    notifications = [n for n in _notifications_for(app, employee_id) if n.type == "request_assigned"]
    assert len(notifications) == 1
    assert notifications[0].entity_type == "customer_request"


def test_request_status_change_notifies_the_assignee(client, app):
    csrf_token = _register_and_login(client, "notiftrig-owner4@example.com")
    org = _create_org(client, csrf_token)
    owner_id = _membership_id(app, org["id"], "notiftrig-owner4@example.com")
    _register_and_login(client, "notiftrig-emp4@example.com", name="Employee")
    employee_id = _give_role(app, org["id"], "notiftrig-emp4@example.com", MembershipRole.EMPLOYEE)
    customer_id = _make_customer(app, org["id"])
    with app.app_context():
        request_row = CustomerRequest(
            organization_id=uuid.UUID(org["id"]),
            customer_id=uuid.UUID(customer_id),
            creator_membership_id=uuid.UUID(owner_id),
            assignee_membership_id=uuid.UUID(employee_id),
            title="Help",
            status=RequestStatus.ASSIGNED,
        )
        db.session.add(request_row)
        db.session.commit()
        request_id = str(request_row.id)
    csrf_token = _login(client, "notiftrig-owner4@example.com")

    response = client.patch(
        f"/api/v1/organizations/{org['id']}/customer-requests/{request_id}/status",
        json={"status": "in_progress"},
        headers={"X-CSRF-Token": csrf_token},
    )
    assert response.status_code == 200

    notifications = [n for n in _notifications_for(app, employee_id) if n.type == "request_status_changed"]
    assert len(notifications) == 1


def test_commenting_on_an_assigned_request_notifies_the_assignee(client, app):
    csrf_token = _register_and_login(client, "notiftrig-owner5@example.com")
    org = _create_org(client, csrf_token)
    owner_id = _membership_id(app, org["id"], "notiftrig-owner5@example.com")
    _register_and_login(client, "notiftrig-emp5@example.com", name="Employee")
    employee_id = _give_role(app, org["id"], "notiftrig-emp5@example.com", MembershipRole.EMPLOYEE)
    customer_id = _make_customer(app, org["id"])
    with app.app_context():
        request_row = CustomerRequest(
            organization_id=uuid.UUID(org["id"]),
            customer_id=uuid.UUID(customer_id),
            creator_membership_id=uuid.UUID(owner_id),
            assignee_membership_id=uuid.UUID(employee_id),
            title="Help",
            status=RequestStatus.ASSIGNED,
        )
        db.session.add(request_row)
        db.session.commit()
        request_id = str(request_row.id)
    csrf_token = _login(client, "notiftrig-owner5@example.com")

    response = client.post(
        f"/api/v1/organizations/{org['id']}/customer-requests/{request_id}/comments",
        json={"body": "Any update?"},
        headers={"X-CSRF-Token": csrf_token},
    )
    assert response.status_code == 201

    notifications = [n for n in _notifications_for(app, employee_id) if n.type == "request_comment_added"]
    assert len(notifications) == 1


# --- invoice_paid --------------------------------------------------------


def _create_and_issue_invoice(client, csrf_token, org_id, customer_id, unit_price="100.00"):
    invoice = client.post(
        f"/api/v1/organizations/{org_id}/invoices",
        json={
            "customer_id": customer_id,
            "currency": "USD",
            "line_items": [{"description": "Widget", "quantity": "1", "unit_price": unit_price}],
        },
        headers={"X-CSRF-Token": csrf_token},
    ).get_json()["data"]
    client.patch(f"/api/v1/organizations/{org_id}/invoices/{invoice['id']}/issue", headers={"X-CSRF-Token": csrf_token})
    return invoice


def test_fully_paying_an_invoice_notifies_owner_and_accountant_not_the_recorder(client, app):
    csrf_token = _register_and_login(client, "notiftrig-owner6@example.com")
    org = _create_org(client, csrf_token)
    owner_id = _membership_id(app, org["id"], "notiftrig-owner6@example.com")
    _register_and_login(client, "notiftrig-acct6@example.com", name="Accountant")
    accountant_id = _give_role(app, org["id"], "notiftrig-acct6@example.com", MembershipRole.ACCOUNTANT)
    _register_and_login(client, "notiftrig-emp6@example.com", name="Employee")
    _give_role(app, org["id"], "notiftrig-emp6@example.com", MembershipRole.EMPLOYEE)
    csrf_token = _login(client, "notiftrig-owner6@example.com")
    customer_id = _make_customer(app, org["id"])
    invoice = _create_and_issue_invoice(client, csrf_token, org["id"], customer_id)

    response = client.post(
        f"/api/v1/organizations/{org['id']}/invoices/{invoice['id']}/payments",
        json={"amount": "100.00", "payment_date": "2026-01-15", "method": "bank_transfer", "idempotency_key": "key-1"},
        headers={"X-CSRF-Token": csrf_token},
    )
    assert response.status_code == 201

    owner_notifications = [n for n in _notifications_for(app, owner_id) if n.type == "invoice_paid"]
    accountant_notifications = [n for n in _notifications_for(app, accountant_id) if n.type == "invoice_paid"]
    assert owner_notifications == []  # owner recorded it themselves - no self-notification
    assert len(accountant_notifications) == 1
    assert accountant_notifications[0].entity_type == "invoice"


def test_partial_payment_does_not_trigger_invoice_paid_notification(client, app):
    csrf_token = _register_and_login(client, "notiftrig-owner7@example.com")
    org = _create_org(client, csrf_token)
    owner_id = _membership_id(app, org["id"], "notiftrig-owner7@example.com")
    customer_id = _make_customer(app, org["id"])
    invoice = _create_and_issue_invoice(client, csrf_token, org["id"], customer_id)

    client.post(
        f"/api/v1/organizations/{org['id']}/invoices/{invoice['id']}/payments",
        json={"amount": "40.00", "payment_date": "2026-01-15", "method": "bank_transfer", "idempotency_key": "key-2"},
        headers={"X-CSRF-Token": csrf_token},
    )

    assert [n for n in _notifications_for(app, owner_id) if n.type == "invoice_paid"] == []


def test_inactive_accountant_is_excluded_from_the_payment_fan_out(client, app):
    csrf_token = _register_and_login(client, "notiftrig-owner7b@example.com")
    org = _create_org(client, csrf_token)
    _register_and_login(client, "notiftrig-acct7b@example.com", name="Inactive Accountant")
    inactive_accountant_id = _give_role(
        app, org["id"], "notiftrig-acct7b@example.com", MembershipRole.ACCOUNTANT, status=MembershipStatus.INACTIVE
    )
    csrf_token = _login(client, "notiftrig-owner7b@example.com")
    customer_id = _make_customer(app, org["id"])
    invoice = _create_and_issue_invoice(client, csrf_token, org["id"], customer_id)

    response = client.post(
        f"/api/v1/organizations/{org['id']}/invoices/{invoice['id']}/payments",
        json={"amount": "100.00", "payment_date": "2026-01-15", "method": "bank_transfer", "idempotency_key": "key-3"},
        headers={"X-CSRF-Token": csrf_token},
    )
    assert response.status_code == 201

    assert _notifications_for(app, inactive_accountant_id) == []


def test_idempotent_payment_replay_does_not_notify_twice(client, app):
    csrf_token = _register_and_login(client, "notiftrig-owner8@example.com")
    org = _create_org(client, csrf_token)
    _register_and_login(client, "notiftrig-acct8@example.com", name="Accountant")
    accountant_id = _give_role(app, org["id"], "notiftrig-acct8@example.com", MembershipRole.ACCOUNTANT)
    csrf_token = _login(client, "notiftrig-owner8@example.com")
    customer_id = _make_customer(app, org["id"])
    invoice = _create_and_issue_invoice(client, csrf_token, org["id"], customer_id)
    body = {"amount": "100.00", "payment_date": "2026-01-15", "method": "bank_transfer", "idempotency_key": "key-replay"}
    client.post(
        f"/api/v1/organizations/{org['id']}/invoices/{invoice['id']}/payments", json=body, headers={"X-CSRF-Token": csrf_token}
    )

    response = client.post(
        f"/api/v1/organizations/{org['id']}/invoices/{invoice['id']}/payments", json=body, headers={"X-CSRF-Token": csrf_token}
    )
    assert response.status_code == 200

    notifications = [n for n in _notifications_for(app, accountant_id) if n.type == "invoice_paid"]
    assert len(notifications) == 1
