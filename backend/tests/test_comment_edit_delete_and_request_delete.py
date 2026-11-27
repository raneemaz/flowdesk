"""Editing/deleting comments (tasks and customer requests) and permanently
deleting a customer request."""

import time
import uuid

import pytest

from app.extensions import db
from app.models import (
    ActivityLog,
    Customer,
    CustomerRequest,
    Membership,
    MembershipRole,
    MembershipStatus,
    Notification,
    Organization,
    RequestComment,
    RequestHistory,
    Task,
    TaskComment,
    TaskHistory,
    User,
)

PASSWORD = "correct horse battery"
OWNER = "owner@comments.example.com"
MANAGER = "manager@comments.example.com"
EMPLOYEE = "employee@comments.example.com"
SUPPORT = "support@comments.example.com"
OUTSIDER = "outsider@comments.example.com"


@pytest.fixture(autouse=True)
def _clean(app):
    yield
    with app.app_context():
        for model in (
            Notification,
            ActivityLog,
            RequestComment,
            RequestHistory,
            CustomerRequest,
            Customer,
            TaskComment,
            TaskHistory,
            Task,
            Membership,
            Organization,
            User,
        ):
            db.session.query(model).delete()
        db.session.commit()


def _login(client, email):
    return client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD}).get_json()["data"]["csrf_token"]


def _give_role(app, org_id, email, role):
    with app.app_context():
        user = db.session.query(User).filter_by(email=email).one()
        membership = Membership(
            organization_id=uuid.UUID(org_id), user_id=user.id, role=role, status=MembershipStatus.ACTIVE
        )
        db.session.add(membership)
        db.session.commit()
        return str(membership.id)


@pytest.fixture
def world(app, client):
    for email in (OWNER, MANAGER, EMPLOYEE, SUPPORT, OUTSIDER):
        client.post("/api/v1/auth/register", json={"name": email.split("@")[0], "email": email, "password": PASSWORD})
    csrf = _login(client, OWNER)
    h = {"X-CSRF-Token": csrf}
    org_id = client.post("/api/v1/organizations", json={"name": "Comments Org"}, headers=h).get_json()["data"]["id"]
    _give_role(app, org_id, MANAGER, MembershipRole.MANAGER)
    employee_id = _give_role(app, org_id, EMPLOYEE, MembershipRole.EMPLOYEE)
    _give_role(app, org_id, SUPPORT, MembershipRole.CUSTOMER_SUPPORT)
    base = f"/api/v1/organizations/{org_id}"

    task = client.post(f"{base}/tasks", json={"title": "Task with comments"}, headers=h).get_json()["data"]
    client.patch(f"{base}/tasks/{task['id']}/assign", json={"assignee_membership_id": employee_id}, headers=h)
    customer = client.post(f"{base}/customers", json={"name": "Northwind"}, headers=h).get_json()["data"]
    req = client.post(
        f"{base}/customer-requests", json={"customer_id": customer["id"], "title": "Checkout broken"}, headers=h
    ).get_json()["data"]
    client.patch(f"{base}/customer-requests/{req['id']}/assign", json={"assignee_membership_id": employee_id}, headers=h)

    # The employee (assignee) writes one comment on each.
    ecsrf = _login(client, EMPLOYEE)
    task_comment = client.post(
        f"{base}/tasks/{task['id']}/comments", json={"body": "Employee note"}, headers={"X-CSRF-Token": ecsrf}
    ).get_json()["data"]
    request_comment = client.post(
        f"{base}/customer-requests/{req['id']}/comments", json={"body": "Called them"}, headers={"X-CSRF-Token": ecsrf}
    ).get_json()["data"]
    return {
        "base": base,
        "org_id": org_id,
        "task_comment_url": f"{base}/tasks/{task['id']}/comments/{task_comment['id']}",
        "request_comment_url": f"{base}/customer-requests/{req['id']}/comments/{request_comment['id']}",
        "request_url": f"{base}/customer-requests/{req['id']}",
        "request_id": req["id"],
    }


COMMENT_KINDS = ["task_comment_url", "request_comment_url"]


@pytest.mark.parametrize("kind", COMMENT_KINDS)
def test_author_edits_their_comment_and_it_is_marked_edited(client, world, kind):
    csrf = _login(client, EMPLOYEE)
    time.sleep(1.1)  # so updated_at is clearly later than created_at

    response = client.patch(world[kind], json={"body": "  Fixed typo  "}, headers={"X-CSRF-Token": csrf})

    assert response.status_code == 200
    data = response.get_json()["data"]
    assert data["body"] == "Fixed typo"
    assert data["edited_at"] is not None


@pytest.mark.parametrize("kind", COMMENT_KINDS)
@pytest.mark.parametrize("email", [OWNER, MANAGER])
def test_nobody_else_can_edit_a_comment(client, world, kind, email):
    csrf = _login(client, email)

    response = client.patch(world[kind], json={"body": "Rewritten"}, headers={"X-CSRF-Token": csrf})

    assert response.status_code == 403


@pytest.mark.parametrize("kind", COMMENT_KINDS)
def test_blank_edit_is_rejected(client, world, kind):
    csrf = _login(client, EMPLOYEE)

    assert client.patch(world[kind], json={"body": "   "}, headers={"X-CSRF-Token": csrf}).status_code == 422


@pytest.mark.parametrize("kind", COMMENT_KINDS)
@pytest.mark.parametrize("email", [EMPLOYEE, OWNER, MANAGER])
def test_author_and_moderators_can_delete_a_comment(app, client, world, kind, email):
    csrf = _login(client, email)

    response = client.delete(world[kind], headers={"X-CSRF-Token": csrf})

    assert response.status_code == 200
    assert client.delete(world[kind], headers={"X-CSRF-Token": csrf}).status_code == 404


def test_customer_support_cannot_delete_someone_elses_request_comment(client, world):
    csrf = _login(client, SUPPORT)

    assert client.delete(world["request_comment_url"], headers={"X-CSRF-Token": csrf}).status_code == 403


@pytest.mark.parametrize("kind", COMMENT_KINDS)
def test_outsiders_and_csrf(client, world, kind):
    csrf = _login(client, OUTSIDER)
    assert client.delete(world[kind], headers={"X-CSRF-Token": csrf}).status_code == 404
    assert client.patch(world[kind], json={"body": "x"}, headers={"X-CSRF-Token": csrf}).status_code == 404

    _login(client, EMPLOYEE)
    assert client.delete(world[kind]).status_code == 403


def test_comment_id_must_belong_to_that_parent(client, world):
    csrf = _login(client, EMPLOYEE)
    # A task comment's id used under the request URL is not found.
    task_comment_id = world["task_comment_url"].rsplit("/", 1)[-1]
    wrong = f"{world['request_url']}/comments/{task_comment_id}"

    assert client.patch(wrong, json={"body": "x"}, headers={"X-CSRF-Token": csrf}).status_code == 404


@pytest.mark.parametrize("email", [OWNER, MANAGER])
def test_owner_and_manager_delete_a_request_permanently(app, client, world, email):
    csrf = _login(client, email)
    request_uuid = uuid.UUID(world["request_id"])
    with app.app_context():
        assert db.session.query(Notification).filter_by(entity_type="customer_request", entity_id=request_uuid).count() >= 1

    response = client.delete(world["request_url"], headers={"X-CSRF-Token": csrf})

    assert response.status_code == 200
    assert client.get(world["request_url"]).status_code == 404
    with app.app_context():
        assert db.session.get(CustomerRequest, request_uuid) is None
        assert db.session.query(RequestComment).filter_by(request_id=request_uuid).count() == 0
        assert db.session.query(RequestHistory).filter_by(request_id=request_uuid).count() == 0
        assert db.session.query(Notification).filter_by(entity_type="customer_request", entity_id=request_uuid).count() == 0
        entry = db.session.query(ActivityLog).filter_by(action="request_deleted", entity_id=request_uuid).one()
        assert entry.metadata_["title"] == "Checkout broken"


@pytest.mark.parametrize("email", [EMPLOYEE, SUPPORT])
def test_other_roles_cannot_delete_requests(app, client, world, email):
    csrf = _login(client, email)

    assert client.delete(world["request_url"], headers={"X-CSRF-Token": csrf}).status_code == 403
    with app.app_context():
        assert db.session.get(CustomerRequest, uuid.UUID(world["request_id"])) is not None


def test_request_delete_isolation_and_csrf(app, client, world):
    csrf = _login(client, OUTSIDER)
    assert client.delete(world["request_url"], headers={"X-CSRF-Token": csrf}).status_code == 404
    _login(client, OWNER)
    assert client.delete(world["request_url"]).status_code == 403
    with app.app_context():
        assert db.session.get(CustomerRequest, uuid.UUID(world["request_id"])) is not None
