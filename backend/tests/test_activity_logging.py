import uuid
from decimal import Decimal

import pytest

from app.activity.service import list_activity, log_activity
from app.authz.permissions import PermissionScope
from app.extensions import db
from app.models import (
    ActivityLog,
    Customer,
    CustomerRequest,
    CustomerStatus,
    EmployeeProfile,
    Invitation,
    Invoice,
    InvoiceLineItem,
    Membership,
    MembershipRole,
    MembershipStatus,
    Organization,
    Payment,
    RequestStatus,
    Task,
    TaskHistory,
    TaskStatus,
    User,
)


@pytest.fixture(autouse=True)
def _clean(app):
    yield
    with app.app_context():
        db.session.query(ActivityLog).delete()
        db.session.query(Payment).delete()
        db.session.query(InvoiceLineItem).delete()
        db.session.query(Invoice).delete()
        db.session.query(TaskHistory).delete()
        db.session.query(Task).delete()
        db.session.query(CustomerRequest).delete()
        db.session.query(Customer).delete()
        db.session.query(Invitation).delete()
        db.session.query(EmployeeProfile).delete()
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


def _make_customer(app, organization_id, name="Jane Customer", status=CustomerStatus.ACTIVE):
    with app.app_context():
        customer = Customer(organization_id=uuid.UUID(organization_id), name=name, status=status)
        db.session.add(customer)
        db.session.commit()
        return str(customer.id)


def _logs(app, organization_id):
    with app.app_context():
        return db.session.query(ActivityLog).filter_by(organization_id=uuid.UUID(organization_id)).all()


# --- log_activity / list_activity (service-level) --------------------------


def test_log_activity_adds_but_does_not_commit(app):
    with app.app_context():
        org = Organization(name="Org", slug="org-svc")
        db.session.add(org)
        db.session.commit()

        entry = log_activity(org.id, None, "task_created", "task", uuid.uuid4(), metadata={"title": "x"})
        assert entry in db.session.new or entry in db.session
        db.session.rollback()
        assert db.session.query(ActivityLog).count() == 0


def _make_org_and_membership(email="svc@example.com", role=MembershipRole.OWNER):
    org = Organization(name="Org", slug=f"org-{uuid.uuid4().hex[:8]}")
    db.session.add(org)
    db.session.commit()
    user = User(name="Svc User", email=email)
    user.set_password("correct horse battery")
    db.session.add(user)
    db.session.commit()
    membership = Membership(organization_id=org.id, user_id=user.id, role=role, status=MembershipStatus.ACTIVE)
    db.session.add(membership)
    db.session.commit()
    return org, membership


def test_list_activity_full_scope_sees_every_entity_type(app):
    with app.app_context():
        org, membership = _make_org_and_membership("fullA@example.com")

        log_activity(org.id, membership.id, "task_created", "task", uuid.uuid4())
        log_activity(org.id, membership.id, "invoice_created", "invoice", uuid.uuid4())
        db.session.commit()

        entries, total = list_activity(
            org.id, scope=PermissionScope.FULL, caller_role=MembershipRole.OWNER, caller_membership_id=membership.id, page=1, per_page=20
        )
        assert total == 2
        assert len(entries) == 2


def test_list_activity_own_scope_filters_to_caller_as_actor(app):
    with app.app_context():
        org, membership_a = _make_org_and_membership("ownA@example.com")
        user_b = User(name="User B", email="ownB@example.com")
        user_b.set_password("correct horse battery")
        db.session.add(user_b)
        db.session.commit()
        membership_b = Membership(
            organization_id=org.id, user_id=user_b.id, role=MembershipRole.EMPLOYEE, status=MembershipStatus.ACTIVE
        )
        db.session.add(membership_b)
        db.session.commit()

        log_activity(org.id, membership_a.id, "task_created", "task", uuid.uuid4())
        log_activity(org.id, membership_b.id, "task_created", "task", uuid.uuid4())
        db.session.commit()

        entries, total = list_activity(
            org.id,
            scope=PermissionScope.OWN,
            caller_role=MembershipRole.EMPLOYEE,
            caller_membership_id=membership_a.id,
            page=1,
            per_page=20,
        )
        assert total == 1
        assert entries[0].actor_membership_id == membership_a.id


def test_list_activity_limited_accountant_sees_only_financial_entity_types(app):
    with app.app_context():
        org = Organization(name="Org", slug="org-ltd-acct")
        db.session.add(org)
        db.session.commit()

        log_activity(org.id, None, "invoice_created", "invoice", uuid.uuid4())
        log_activity(org.id, None, "payment_recorded", "payment", uuid.uuid4())
        log_activity(org.id, None, "task_created", "task", uuid.uuid4())
        log_activity(org.id, None, "request_created", "customer_request", uuid.uuid4())
        db.session.commit()

        entries, total = list_activity(
            org.id,
            scope=PermissionScope.LIMITED,
            caller_role=MembershipRole.ACCOUNTANT,
            caller_membership_id=uuid.uuid4(),
            page=1,
            per_page=20,
        )
        assert total == 2
        assert {e.entity_type for e in entries} == {"invoice", "payment"}


def test_list_activity_limited_customer_support_sees_only_customer_entity_types(app):
    with app.app_context():
        org = Organization(name="Org", slug="org-ltd-cs")
        db.session.add(org)
        db.session.commit()

        log_activity(org.id, None, "request_created", "customer_request", uuid.uuid4())
        log_activity(org.id, None, "invoice_created", "invoice", uuid.uuid4())
        db.session.commit()

        entries, total = list_activity(
            org.id,
            scope=PermissionScope.LIMITED,
            caller_role=MembershipRole.CUSTOMER_SUPPORT,
            caller_membership_id=uuid.uuid4(),
            page=1,
            per_page=20,
        )
        assert total == 1
        assert entries[0].entity_type == "customer_request"


def test_list_activity_limited_with_an_unmatched_role_fails_closed(app):
    with app.app_context():
        org = Organization(name="Org", slug="org-ltd-fail")
        db.session.add(org)
        db.session.commit()

        log_activity(org.id, None, "task_created", "task", uuid.uuid4())
        db.session.commit()

        entries, total = list_activity(
            org.id,
            scope=PermissionScope.LIMITED,
            caller_role=MembershipRole.EMPLOYEE,
            caller_membership_id=uuid.uuid4(),
            page=1,
            per_page=20,
        )
        assert total == 0
        assert entries == []


def test_list_activity_is_scoped_to_the_organization(app):
    with app.app_context():
        org_a = Organization(name="Org A", slug="org-a-iso")
        org_b = Organization(name="Org B", slug="org-b-iso")
        db.session.add_all([org_a, org_b])
        db.session.commit()

        log_activity(org_a.id, None, "task_created", "task", uuid.uuid4())
        log_activity(org_b.id, None, "task_created", "task", uuid.uuid4())
        db.session.commit()

        entries, total = list_activity(
            org_a.id, scope=PermissionScope.FULL, caller_role=MembershipRole.OWNER, caller_membership_id=uuid.uuid4(), page=1, per_page=20
        )
        assert total == 1


# --- Trigger points ---------------------------------------------------------


def test_inviting_an_employee_logs_employee_invited(client, app):
    csrf_token = _register_and_login(client, "owner1@example.com")
    org = _create_org(client, csrf_token)

    response = client.post(
        f"/api/v1/organizations/{org['id']}/invitations",
        json={"email": "invitee1@example.com", "role": "employee"},
        headers={"X-CSRF-Token": csrf_token},
    )
    assert response.status_code == 201

    logs = _logs(app, org["id"])
    assert len(logs) == 1
    assert logs[0].action == "employee_invited"
    assert logs[0].entity_type == "invitation"
    assert logs[0].metadata_["email"] == "invitee1@example.com"


def test_creating_a_task_logs_task_created(client, app):
    csrf_token = _register_and_login(client, "owner2@example.com")
    org = _create_org(client, csrf_token)

    response = client.post(
        f"/api/v1/organizations/{org['id']}/tasks",
        json={"title": "Do the thing"},
        headers={"X-CSRF-Token": csrf_token},
    )
    assert response.status_code == 201
    task_id = response.get_json()["data"]["id"]

    logs = _logs(app, org["id"])
    assert len(logs) == 1
    assert logs[0].action == "task_created"
    assert logs[0].entity_type == "task"
    assert str(logs[0].entity_id) == task_id


def test_assigning_a_task_logs_task_assigned(client, app):
    csrf_token = _register_and_login(client, "owner3@example.com")
    org = _create_org(client, csrf_token)
    owner_id = _membership_id(app, org["id"], "owner3@example.com")
    task_id = client.post(
        f"/api/v1/organizations/{org['id']}/tasks", json={"title": "Task"}, headers={"X-CSRF-Token": csrf_token}
    ).get_json()["data"]["id"]
    _register_and_login(client, "employee3@example.com", name="Employee Three")
    employee_id = _give_role(app, org["id"], "employee3@example.com", MembershipRole.EMPLOYEE)
    owner_csrf = _login(client, "owner3@example.com")

    response = client.patch(
        f"/api/v1/organizations/{org['id']}/tasks/{task_id}/assign",
        json={"assignee_membership_id": employee_id},
        headers={"X-CSRF-Token": owner_csrf},
    )
    assert response.status_code == 200

    logs = [log for log in _logs(app, org["id"]) if log.action == "task_assigned"]
    assert len(logs) == 1
    assert logs[0].entity_type == "task"
    assert str(logs[0].actor_membership_id) == owner_id


def test_unassigning_a_task_does_not_log_task_assigned(client, app):
    csrf_token = _register_and_login(client, "owner3u@example.com")
    org = _create_org(client, csrf_token)
    _register_and_login(client, "employee3u@example.com", name="Employee")
    employee_id = _give_role(app, org["id"], "employee3u@example.com", MembershipRole.EMPLOYEE)
    owner_csrf = _login(client, "owner3u@example.com")
    task_id = client.post(
        f"/api/v1/organizations/{org['id']}/tasks",
        json={"title": "Task"},
        headers={"X-CSRF-Token": owner_csrf},
    ).get_json()["data"]["id"]
    client.patch(
        f"/api/v1/organizations/{org['id']}/tasks/{task_id}/assign",
        json={"assignee_membership_id": employee_id},
        headers={"X-CSRF-Token": owner_csrf},
    )

    response = client.patch(
        f"/api/v1/organizations/{org['id']}/tasks/{task_id}/assign",
        json={"assignee_membership_id": None},
        headers={"X-CSRF-Token": owner_csrf},
    )
    assert response.status_code == 200

    assigned_logs = [log for log in _logs(app, org["id"]) if log.action == "task_assigned"]
    assert len(assigned_logs) == 1  # only the original assignment, not the unassignment


def test_completing_a_task_logs_task_completed(client, app):
    csrf_token = _register_and_login(client, "owner4@example.com")
    org = _create_org(client, csrf_token)
    task_id = client.post(
        f"/api/v1/organizations/{org['id']}/tasks", json={"title": "Task"}, headers={"X-CSRF-Token": csrf_token}
    ).get_json()["data"]["id"]
    client.patch(
        f"/api/v1/organizations/{org['id']}/tasks/{task_id}/status",
        json={"status": "in_progress"},
        headers={"X-CSRF-Token": csrf_token},
    )
    client.patch(
        f"/api/v1/organizations/{org['id']}/tasks/{task_id}/status",
        json={"status": "under_review"},
        headers={"X-CSRF-Token": csrf_token},
    )

    response = client.patch(
        f"/api/v1/organizations/{org['id']}/tasks/{task_id}/status",
        json={"status": "completed"},
        headers={"X-CSRF-Token": csrf_token},
    )
    assert response.status_code == 200

    completed_logs = [log for log in _logs(app, org["id"]) if log.action == "task_completed"]
    assert len(completed_logs) == 1
    assert completed_logs[0].entity_type == "task"


def test_intermediate_status_changes_do_not_log_task_completed(client, app):
    csrf_token = _register_and_login(client, "owner4b@example.com")
    org = _create_org(client, csrf_token)
    task_id = client.post(
        f"/api/v1/organizations/{org['id']}/tasks", json={"title": "Task"}, headers={"X-CSRF-Token": csrf_token}
    ).get_json()["data"]["id"]

    response = client.patch(
        f"/api/v1/organizations/{org['id']}/tasks/{task_id}/status",
        json={"status": "in_progress"},
        headers={"X-CSRF-Token": csrf_token},
    )
    assert response.status_code == 200

    completed_logs = [log for log in _logs(app, org["id"]) if log.action == "task_completed"]
    assert len(completed_logs) == 0


def test_creating_a_customer_request_logs_request_created(client, app):
    csrf_token = _register_and_login(client, "owner5@example.com")
    org = _create_org(client, csrf_token)
    customer_id = _make_customer(app, org["id"])

    response = client.post(
        f"/api/v1/organizations/{org['id']}/customer-requests",
        json={"title": "Can't log in", "customer_id": customer_id},
        headers={"X-CSRF-Token": csrf_token},
    )
    assert response.status_code == 201

    logs = _logs(app, org["id"])
    assert len(logs) == 1
    assert logs[0].action == "request_created"
    assert logs[0].entity_type == "customer_request"


def test_resolving_a_customer_request_logs_request_resolved(client, app):
    csrf_token = _register_and_login(client, "owner6@example.com")
    org = _create_org(client, csrf_token)
    owner_id = _membership_id(app, org["id"], "owner6@example.com")
    customer_id = _make_customer(app, org["id"])
    with app.app_context():
        request_row = CustomerRequest(
            organization_id=uuid.UUID(org["id"]),
            customer_id=uuid.UUID(customer_id),
            creator_membership_id=uuid.UUID(owner_id),
            assignee_membership_id=uuid.UUID(owner_id),
            title="Request",
            status=RequestStatus.WAITING_FOR_CUSTOMER,
        )
        db.session.add(request_row)
        db.session.commit()
        request_id = str(request_row.id)

    response = client.patch(
        f"/api/v1/organizations/{org['id']}/customer-requests/{request_id}/status",
        json={"status": "resolved"},
        headers={"X-CSRF-Token": csrf_token},
    )
    assert response.status_code == 200

    logs = [log for log in _logs(app, org["id"]) if log.action == "request_resolved"]
    assert len(logs) == 1
    assert logs[0].entity_type == "customer_request"
    assert str(logs[0].entity_id) == request_id


def test_creating_an_invoice_logs_invoice_created(client, app):
    csrf_token = _register_and_login(client, "owner7@example.com")
    org = _create_org(client, csrf_token)
    customer_id = _make_customer(app, org["id"])

    response = client.post(
        f"/api/v1/organizations/{org['id']}/invoices",
        json={"customer_id": customer_id, "currency": "USD"},
        headers={"X-CSRF-Token": csrf_token},
    )
    assert response.status_code == 201
    invoice_id = response.get_json()["data"]["id"]

    logs = _logs(app, org["id"])
    assert len(logs) == 1
    assert logs[0].action == "invoice_created"
    assert logs[0].entity_type == "invoice"
    assert str(logs[0].entity_id) == invoice_id


def test_recording_a_payment_logs_payment_recorded(client, app):
    csrf_token = _register_and_login(client, "owner8@example.com")
    org = _create_org(client, csrf_token)
    customer_id = _make_customer(app, org["id"])
    invoice = client.post(
        f"/api/v1/organizations/{org['id']}/invoices",
        json={
            "customer_id": customer_id,
            "currency": "USD",
            "line_items": [{"description": "Widget", "quantity": "1", "unit_price": "100.00"}],
        },
        headers={"X-CSRF-Token": csrf_token},
    ).get_json()["data"]
    client.patch(f"/api/v1/organizations/{org['id']}/invoices/{invoice['id']}/issue", headers={"X-CSRF-Token": csrf_token})

    response = client.post(
        f"/api/v1/organizations/{org['id']}/invoices/{invoice['id']}/payments",
        json={"amount": "100.00", "payment_date": "2026-01-15", "method": "bank_transfer", "idempotency_key": "key-1"},
        headers={"X-CSRF-Token": csrf_token},
    )
    assert response.status_code == 201

    logs = [log for log in _logs(app, org["id"]) if log.action == "payment_recorded"]
    assert len(logs) == 1
    assert logs[0].entity_type == "payment"


def test_an_idempotent_payment_replay_does_not_log_a_second_time(client, app):
    csrf_token = _register_and_login(client, "owner8b@example.com")
    org = _create_org(client, csrf_token)
    customer_id = _make_customer(app, org["id"])
    invoice = client.post(
        f"/api/v1/organizations/{org['id']}/invoices",
        json={
            "customer_id": customer_id,
            "currency": "USD",
            "line_items": [{"description": "Widget", "quantity": "1", "unit_price": "100.00"}],
        },
        headers={"X-CSRF-Token": csrf_token},
    ).get_json()["data"]
    client.patch(f"/api/v1/organizations/{org['id']}/invoices/{invoice['id']}/issue", headers={"X-CSRF-Token": csrf_token})
    body = {"amount": "40.00", "payment_date": "2026-01-15", "method": "bank_transfer", "idempotency_key": "key-replay"}
    client.post(
        f"/api/v1/organizations/{org['id']}/invoices/{invoice['id']}/payments", json=body, headers={"X-CSRF-Token": csrf_token}
    )

    response = client.post(
        f"/api/v1/organizations/{org['id']}/invoices/{invoice['id']}/payments", json=body, headers={"X-CSRF-Token": csrf_token}
    )
    assert response.status_code == 200

    logs = [log for log in _logs(app, org["id"]) if log.action == "payment_recorded"]
    assert len(logs) == 1


def test_deactivating_an_employee_logs_employee_deactivated(client, app):
    csrf_token = _register_and_login(client, "owner9@example.com")
    org = _create_org(client, csrf_token)
    owner_id = _membership_id(app, org["id"], "owner9@example.com")
    _register_and_login(client, "employee9@example.com", name="Employee Nine")
    employee_id = _give_role(app, org["id"], "employee9@example.com", MembershipRole.EMPLOYEE)
    owner_csrf = _login(client, "owner9@example.com")

    response = client.patch(
        f"/api/v1/organizations/{org['id']}/employees/{employee_id}",
        json={"status": "inactive"},
        headers={"X-CSRF-Token": owner_csrf},
    )
    assert response.status_code == 200

    logs = [log for log in _logs(app, org["id"]) if log.action == "employee_deactivated"]
    assert len(logs) == 1
    assert logs[0].entity_type == "membership"
    assert str(logs[0].entity_id) == employee_id
    assert str(logs[0].actor_membership_id) == owner_id


def test_redundant_deactivation_does_not_log_twice(client, app):
    csrf_token = _register_and_login(client, "owner9b@example.com")
    org = _create_org(client, csrf_token)
    _register_and_login(client, "employee9b@example.com", name="Employee")
    employee_id = _give_role(app, org["id"], "employee9b@example.com", MembershipRole.EMPLOYEE)
    owner_csrf = _login(client, "owner9b@example.com")
    client.patch(
        f"/api/v1/organizations/{org['id']}/employees/{employee_id}",
        json={"status": "inactive"},
        headers={"X-CSRF-Token": owner_csrf},
    )

    response = client.patch(
        f"/api/v1/organizations/{org['id']}/employees/{employee_id}",
        json={"status": "inactive"},
        headers={"X-CSRF-Token": owner_csrf},
    )
    assert response.status_code == 200

    logs = [log for log in _logs(app, org["id"]) if log.action == "employee_deactivated"]
    assert len(logs) == 1


# --- GET /organizations/{id}/activity ---------------------------------------


def test_unauthenticated_request_returns_401(client):
    response = client.get("/api/v1/organizations/00000000-0000-0000-0000-000000000000/activity")
    assert response.status_code == 401


def test_owner_sees_every_activity_entry(client, app):
    csrf_token = _register_and_login(client, "ownerA@example.com")
    org = _create_org(client, csrf_token)
    with app.app_context():
        log_activity(uuid.UUID(org["id"]), None, "task_created", "task", uuid.uuid4())
        log_activity(uuid.UUID(org["id"]), None, "invoice_created", "invoice", uuid.uuid4())
        db.session.commit()

    response = client.get(f"/api/v1/organizations/{org['id']}/activity", headers={"X-CSRF-Token": csrf_token})

    assert response.status_code == 200
    body = response.get_json()
    assert body["meta"]["total"] == 2
    assert len(body["data"]) == 2


def test_employee_sees_only_their_own_actions(client, app):
    csrf_token = _register_and_login(client, "ownerB@example.com")
    org = _create_org(client, csrf_token)
    _register_and_login(client, "employeeB@example.com", name="Employee B")
    employee_id = _give_role(app, org["id"], "employeeB@example.com", MembershipRole.EMPLOYEE)
    with app.app_context():
        log_activity(uuid.UUID(org["id"]), uuid.UUID(employee_id), "task_created", "task", uuid.uuid4())
        log_activity(uuid.UUID(org["id"]), None, "task_created", "task", uuid.uuid4())
        db.session.commit()
    employee_csrf = _login(client, "employeeB@example.com")

    response = client.get(f"/api/v1/organizations/{org['id']}/activity", headers={"X-CSRF-Token": employee_csrf})

    assert response.status_code == 200
    body = response.get_json()
    assert body["meta"]["total"] == 1
    assert body["data"][0]["actor_membership_id"] == employee_id


def test_accountant_sees_only_financial_entity_types(client, app):
    csrf_token = _register_and_login(client, "ownerC@example.com")
    org = _create_org(client, csrf_token)
    _register_and_login(client, "accountantC@example.com", name="Accountant C")
    _give_role(app, org["id"], "accountantC@example.com", MembershipRole.ACCOUNTANT)
    with app.app_context():
        log_activity(uuid.UUID(org["id"]), None, "invoice_created", "invoice", uuid.uuid4())
        log_activity(uuid.UUID(org["id"]), None, "task_created", "task", uuid.uuid4())
        db.session.commit()
    accountant_csrf = _login(client, "accountantC@example.com")

    response = client.get(f"/api/v1/organizations/{org['id']}/activity", headers={"X-CSRF-Token": accountant_csrf})

    assert response.status_code == 200
    body = response.get_json()
    assert body["meta"]["total"] == 1
    assert body["data"][0]["entity_type"] == "invoice"


def test_customer_support_sees_only_customer_entity_types(client, app):
    csrf_token = _register_and_login(client, "ownerD@example.com")
    org = _create_org(client, csrf_token)
    _register_and_login(client, "supportD@example.com", name="Support D")
    _give_role(app, org["id"], "supportD@example.com", MembershipRole.CUSTOMER_SUPPORT)
    with app.app_context():
        log_activity(uuid.UUID(org["id"]), None, "request_created", "customer_request", uuid.uuid4())
        log_activity(uuid.UUID(org["id"]), None, "invoice_created", "invoice", uuid.uuid4())
        db.session.commit()
    support_csrf = _login(client, "supportD@example.com")

    response = client.get(f"/api/v1/organizations/{org['id']}/activity", headers={"X-CSRF-Token": support_csrf})

    assert response.status_code == 200
    body = response.get_json()
    assert body["meta"]["total"] == 1
    assert body["data"][0]["entity_type"] == "customer_request"


def test_activity_is_isolated_by_organization(client, app):
    owner_a_csrf = _register_and_login(client, "ownerEa@example.com")
    org_a = _create_org(client, owner_a_csrf, name="Org A")
    owner_b_csrf = _register_and_login(client, "ownerEb@example.com")
    org_b = _create_org(client, owner_b_csrf, name="Org B")
    with app.app_context():
        log_activity(uuid.UUID(org_a["id"]), None, "task_created", "task", uuid.uuid4())
        log_activity(uuid.UUID(org_b["id"]), None, "task_created", "task", uuid.uuid4())
        db.session.commit()
    owner_a_csrf = _login(client, "ownerEa@example.com")

    response = client.get(f"/api/v1/organizations/{org_a['id']}/activity", headers={"X-CSRF-Token": owner_a_csrf})

    assert response.status_code == 200
    assert response.get_json()["meta"]["total"] == 1


def test_a_non_member_cannot_view_a_foreign_organizations_activity(client, app):
    owner_a_csrf = _register_and_login(client, "ownerFa@example.com")
    org_a = _create_org(client, owner_a_csrf, name="Org A")
    owner_b_csrf = _register_and_login(client, "ownerFb@example.com")
    _create_org(client, owner_b_csrf, name="Org B")

    response = client.get(f"/api/v1/organizations/{org_a['id']}/activity", headers={"X-CSRF-Token": owner_b_csrf})

    assert response.status_code == 404


def test_activity_pagination(client, app):
    csrf_token = _register_and_login(client, "ownerG@example.com")
    org = _create_org(client, csrf_token)
    with app.app_context():
        for _ in range(3):
            log_activity(uuid.UUID(org["id"]), None, "task_created", "task", uuid.uuid4())
        db.session.commit()

    response = client.get(
        f"/api/v1/organizations/{org['id']}/activity?page=1&per_page=2", headers={"X-CSRF-Token": csrf_token}
    )

    assert response.status_code == 200
    body = response.get_json()
    assert len(body["data"]) == 2
    assert body["meta"]["total"] == 3
    assert body["meta"]["total_pages"] == 2
