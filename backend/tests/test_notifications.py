import uuid

import pytest

from app.extensions import db
from app.models import Membership, MembershipRole, MembershipStatus, Notification, Organization, User
from app.notifications.service import (
    create_notification,
    list_notifications,
    mark_all_notifications_read,
    mark_notification_read,
)


@pytest.fixture(autouse=True)
def _clean(app):
    yield
    with app.app_context():
        db.session.query(Notification).delete()
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


def _make_notification(app, organization_id, recipient_membership_id, notification_type="task_assigned", **kwargs):
    with app.app_context():
        notification = create_notification(
            uuid.UUID(organization_id),
            uuid.UUID(recipient_membership_id),
            notification_type,
            kwargs.pop("title", "You were assigned a task"),
            kwargs.pop("body", "Task X was assigned to you."),
            kwargs.pop("entity_type", "task"),
            kwargs.pop("entity_id", uuid.uuid4()),
        )
        db.session.commit()
        return str(notification.id)


# --- Service-level -----------------------------------------------------


def test_create_notification_adds_but_does_not_commit(app):
    with app.app_context():
        org = Organization(name="Org", slug="org-notif-svc")
        user = User(name="U", email="svc-create@example.com")
        user.set_password("correct horse battery")
        db.session.add_all([org, user])
        db.session.commit()
        membership = Membership(organization_id=org.id, user_id=user.id, role=MembershipRole.OWNER, status=MembershipStatus.ACTIVE)
        db.session.add(membership)
        db.session.commit()

        entry = create_notification(org.id, membership.id, "task_assigned", "Title", "Body", "task", uuid.uuid4())
        assert entry in db.session.new or entry in db.session
        db.session.rollback()
        assert db.session.query(Notification).count() == 0


def test_list_notifications_is_scoped_to_the_recipient(app):
    with app.app_context():
        org = Organization(name="Org", slug="org-notif-scope")
        user_a = User(name="A", email="recip-a@example.com")
        user_a.set_password("correct horse battery")
        user_b = User(name="B", email="recip-b@example.com")
        user_b.set_password("correct horse battery")
        db.session.add_all([org, user_a, user_b])
        db.session.commit()
        membership_a = Membership(organization_id=org.id, user_id=user_a.id, role=MembershipRole.EMPLOYEE, status=MembershipStatus.ACTIVE)
        membership_b = Membership(organization_id=org.id, user_id=user_b.id, role=MembershipRole.EMPLOYEE, status=MembershipStatus.ACTIVE)
        db.session.add_all([membership_a, membership_b])
        db.session.commit()

        create_notification(org.id, membership_a.id, "task_assigned", "T", "B", "task", uuid.uuid4())
        create_notification(org.id, membership_b.id, "task_assigned", "T", "B", "task", uuid.uuid4())
        db.session.commit()

        entries, total = list_notifications(org.id, membership_a.id, unread_only=False, page=1, per_page=20)
        assert total == 1
        assert entries[0].recipient_membership_id == membership_a.id


def test_list_notifications_unread_only_filter(app):
    with app.app_context():
        org = Organization(name="Org", slug="org-notif-unread")
        user = User(name="U", email="unread@example.com")
        user.set_password("correct horse battery")
        db.session.add_all([org, user])
        db.session.commit()
        membership = Membership(organization_id=org.id, user_id=user.id, role=MembershipRole.EMPLOYEE, status=MembershipStatus.ACTIVE)
        db.session.add(membership)
        db.session.commit()

        n1 = create_notification(org.id, membership.id, "task_assigned", "T1", "B", "task", uuid.uuid4())
        create_notification(org.id, membership.id, "task_assigned", "T2", "B", "task", uuid.uuid4())
        db.session.commit()
        mark_notification_read(org.id, membership.id, n1.id)

        entries, total = list_notifications(org.id, membership.id, unread_only=True, page=1, per_page=20)
        assert total == 1
        assert entries[0].title == "T2"


def test_mark_notification_read_is_idempotent(app):
    with app.app_context():
        org = Organization(name="Org", slug="org-notif-idem")
        user = User(name="U", email="idem@example.com")
        user.set_password("correct horse battery")
        db.session.add_all([org, user])
        db.session.commit()
        membership = Membership(organization_id=org.id, user_id=user.id, role=MembershipRole.EMPLOYEE, status=MembershipStatus.ACTIVE)
        db.session.add(membership)
        db.session.commit()
        notification = create_notification(org.id, membership.id, "task_assigned", "T", "B", "task", uuid.uuid4())
        db.session.commit()

        first = mark_notification_read(org.id, membership.id, notification.id)
        first_read_at = first.read_at
        second = mark_notification_read(org.id, membership.id, notification.id)

        assert second.read_at == first_read_at


def test_mark_notification_read_for_another_recipient_raises_404(app):
    from app.errors import APIError

    with app.app_context():
        org = Organization(name="Org", slug="org-notif-cross")
        user_a = User(name="A", email="cross-a@example.com")
        user_a.set_password("correct horse battery")
        user_b = User(name="B", email="cross-b@example.com")
        user_b.set_password("correct horse battery")
        db.session.add_all([org, user_a, user_b])
        db.session.commit()
        membership_a = Membership(organization_id=org.id, user_id=user_a.id, role=MembershipRole.EMPLOYEE, status=MembershipStatus.ACTIVE)
        membership_b = Membership(organization_id=org.id, user_id=user_b.id, role=MembershipRole.EMPLOYEE, status=MembershipStatus.ACTIVE)
        db.session.add_all([membership_a, membership_b])
        db.session.commit()
        notification = create_notification(org.id, membership_a.id, "task_assigned", "T", "B", "task", uuid.uuid4())
        db.session.commit()

        with pytest.raises(APIError) as exc_info:
            mark_notification_read(org.id, membership_b.id, notification.id)
        assert exc_info.value.status_code == 404


def test_mark_all_notifications_read_only_affects_the_caller(app):
    with app.app_context():
        org = Organization(name="Org", slug="org-notif-markall")
        user_a = User(name="A", email="markall-a@example.com")
        user_a.set_password("correct horse battery")
        user_b = User(name="B", email="markall-b@example.com")
        user_b.set_password("correct horse battery")
        db.session.add_all([org, user_a, user_b])
        db.session.commit()
        membership_a = Membership(organization_id=org.id, user_id=user_a.id, role=MembershipRole.EMPLOYEE, status=MembershipStatus.ACTIVE)
        membership_b = Membership(organization_id=org.id, user_id=user_b.id, role=MembershipRole.EMPLOYEE, status=MembershipStatus.ACTIVE)
        db.session.add_all([membership_a, membership_b])
        db.session.commit()
        create_notification(org.id, membership_a.id, "task_assigned", "T1", "B", "task", uuid.uuid4())
        create_notification(org.id, membership_a.id, "task_assigned", "T2", "B", "task", uuid.uuid4())
        create_notification(org.id, membership_b.id, "task_assigned", "T3", "B", "task", uuid.uuid4())
        db.session.commit()

        updated_count = mark_all_notifications_read(org.id, membership_a.id)

        assert updated_count == 2
        unread_b, total_b = list_notifications(org.id, membership_b.id, unread_only=True, page=1, per_page=20)
        assert total_b == 1


def test_mark_all_notifications_read_when_nothing_is_unread_returns_zero(app):
    with app.app_context():
        org = Organization(name="Org", slug="org-notif-markall-zero")
        user = User(name="U", email="markall-zero@example.com")
        user.set_password("correct horse battery")
        db.session.add_all([org, user])
        db.session.commit()
        membership = Membership(organization_id=org.id, user_id=user.id, role=MembershipRole.EMPLOYEE, status=MembershipStatus.ACTIVE)
        db.session.add(membership)
        db.session.commit()

        updated_count = mark_all_notifications_read(org.id, membership.id)

        assert updated_count == 0


# --- GET /organizations/{id}/notifications ------------------------------


def test_unauthenticated_request_returns_401(client):
    response = client.get("/api/v1/organizations/00000000-0000-0000-0000-000000000000/notifications")
    assert response.status_code == 401


def test_a_non_member_cannot_view_a_foreign_organizations_notifications(client, app):
    owner_a_csrf = _register_and_login(client, "notif-ownera@example.com")
    org_a = _create_org(client, owner_a_csrf, name="Org A")
    owner_b_csrf = _register_and_login(client, "notif-ownerb@example.com")
    _create_org(client, owner_b_csrf, name="Org B")

    response = client.get(f"/api/v1/organizations/{org_a['id']}/notifications", headers={"X-CSRF-Token": owner_b_csrf})

    assert response.status_code == 404


def test_caller_sees_only_their_own_notifications(client, app):
    csrf_token = _register_and_login(client, "notif-owner1@example.com")
    org = _create_org(client, csrf_token)
    owner_id = _membership_id(app, org["id"], "notif-owner1@example.com")
    _register_and_login(client, "notif-emp1@example.com", name="Employee")
    employee_id = _give_role(app, org["id"], "notif-emp1@example.com", MembershipRole.EMPLOYEE)
    _make_notification(app, org["id"], owner_id)
    _make_notification(app, org["id"], employee_id)
    owner_csrf = _login(client, "notif-owner1@example.com")

    response = client.get(f"/api/v1/organizations/{org['id']}/notifications", headers={"X-CSRF-Token": owner_csrf})

    assert response.status_code == 200
    body = response.get_json()
    assert body["meta"]["total"] == 1
    assert body["data"][0]["recipient_membership_id"] == owner_id


def test_unread_only_filter_on_the_list_endpoint(client, app):
    csrf_token = _register_and_login(client, "notif-owner2@example.com")
    org = _create_org(client, csrf_token)
    owner_id = _membership_id(app, org["id"], "notif-owner2@example.com")
    read_id = _make_notification(app, org["id"], owner_id, title="Read one")
    _make_notification(app, org["id"], owner_id, title="Unread one")
    client.patch(
        f"/api/v1/organizations/{org['id']}/notifications/{read_id}/read", headers={"X-CSRF-Token": csrf_token}
    )

    response = client.get(
        f"/api/v1/organizations/{org['id']}/notifications?unread_only=true", headers={"X-CSRF-Token": csrf_token}
    )

    assert response.status_code == 200
    body = response.get_json()
    assert body["meta"]["total"] == 1
    assert body["data"][0]["title"] == "Unread one"


def test_notifications_pagination(client, app):
    csrf_token = _register_and_login(client, "notif-owner3@example.com")
    org = _create_org(client, csrf_token)
    owner_id = _membership_id(app, org["id"], "notif-owner3@example.com")
    for i in range(3):
        _make_notification(app, org["id"], owner_id, title=f"N{i}")

    response = client.get(
        f"/api/v1/organizations/{org['id']}/notifications?page=1&per_page=2", headers={"X-CSRF-Token": csrf_token}
    )

    assert response.status_code == 200
    body = response.get_json()
    assert len(body["data"]) == 2
    assert body["meta"]["total"] == 3
    assert body["meta"]["total_pages"] == 2


# --- PATCH .../notifications/{id}/read -----------------------------------


def test_mark_read_requires_csrf_token(client, app):
    csrf_token = _register_and_login(client, "notif-owner4@example.com")
    org = _create_org(client, csrf_token)
    owner_id = _membership_id(app, org["id"], "notif-owner4@example.com")
    notification_id = _make_notification(app, org["id"], owner_id)

    response = client.patch(f"/api/v1/organizations/{org['id']}/notifications/{notification_id}/read")

    assert response.status_code == 403


def test_owner_can_mark_their_own_notification_read(client, app):
    csrf_token = _register_and_login(client, "notif-owner5@example.com")
    org = _create_org(client, csrf_token)
    owner_id = _membership_id(app, org["id"], "notif-owner5@example.com")
    notification_id = _make_notification(app, org["id"], owner_id)

    response = client.patch(
        f"/api/v1/organizations/{org['id']}/notifications/{notification_id}/read",
        headers={"X-CSRF-Token": csrf_token},
    )

    assert response.status_code == 200
    body = response.get_json()["data"]
    assert body["read_at"] is not None


def test_marking_a_nonexistent_notification_read_returns_404(client, app):
    csrf_token = _register_and_login(client, "notif-owner6@example.com")
    org = _create_org(client, csrf_token)

    response = client.patch(
        f"/api/v1/organizations/{org['id']}/notifications/{uuid.uuid4()}/read",
        headers={"X-CSRF-Token": csrf_token},
    )

    assert response.status_code == 404


def test_marking_another_members_notification_read_returns_404(client, app):
    csrf_token = _register_and_login(client, "notif-owner7@example.com")
    org = _create_org(client, csrf_token)
    owner_id = _membership_id(app, org["id"], "notif-owner7@example.com")
    _register_and_login(client, "notif-emp7@example.com", name="Employee")
    employee_id = _give_role(app, org["id"], "notif-emp7@example.com", MembershipRole.EMPLOYEE)
    notification_id = _make_notification(app, org["id"], owner_id)
    employee_csrf = _login(client, "notif-emp7@example.com")

    response = client.patch(
        f"/api/v1/organizations/{org['id']}/notifications/{notification_id}/read",
        headers={"X-CSRF-Token": employee_csrf},
    )

    assert response.status_code == 404


# --- PATCH .../notifications/read-all ------------------------------------


def test_mark_all_read_only_affects_the_caller_via_the_api(client, app):
    csrf_token = _register_and_login(client, "notif-owner8@example.com")
    org = _create_org(client, csrf_token)
    owner_id = _membership_id(app, org["id"], "notif-owner8@example.com")
    _register_and_login(client, "notif-emp8@example.com", name="Employee")
    employee_id = _give_role(app, org["id"], "notif-emp8@example.com", MembershipRole.EMPLOYEE)
    _make_notification(app, org["id"], owner_id)
    _make_notification(app, org["id"], owner_id)
    _make_notification(app, org["id"], employee_id)
    owner_csrf = _login(client, "notif-owner8@example.com")

    response = client.patch(
        f"/api/v1/organizations/{org['id']}/notifications/read-all", headers={"X-CSRF-Token": owner_csrf}
    )

    assert response.status_code == 200
    assert response.get_json()["data"]["updated_count"] == 2

    employee_csrf = _login(client, "notif-emp8@example.com")
    unread_response = client.get(
        f"/api/v1/organizations/{org['id']}/notifications?unread_only=true", headers={"X-CSRF-Token": employee_csrf}
    )
    assert unread_response.get_json()["meta"]["total"] == 1
