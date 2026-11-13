import pytest
from flask import g, jsonify

from app.auth.decorators import login_required
from app.authz.decorators import require_permission
from app.authz.permissions import Permission
from app.extensions import db
from app.models import Membership, MembershipRole, MembershipStatus, Organization, User

# This module registers its own throwaway routes directly on the `app`
# fixture (function-scoped - a fresh Flask app per test) to exercise
# require_permission end-to-end via real HTTP requests, without
# inventing a permanent business endpoint that FD-015 isn't scoped to
# build.


@pytest.fixture(autouse=True)
def _clean(app):
    yield
    with app.app_context():
        db.session.query(Membership).delete()
        db.session.query(Organization).delete()
        db.session.query(User).delete()
        db.session.commit()


@pytest.fixture
def client(app):
    @app.route("/api/v1/_test/orgs/<uuid:organization_id>/departments", methods=["GET"])
    @login_required
    @require_permission(Permission.DEPARTMENT_MANAGE)
    def _departments_probe(organization_id):
        return (
            jsonify(
                {
                    "success": True,
                    "message": "ok",
                    "data": {
                        "scope": g.permission_scope.value,
                        "role": g.current_membership.role.value,
                    },
                }
            ),
            200,
        )

    @app.route("/api/v1/_test/orgs/<uuid:organization_id>/tasks", methods=["GET"])
    @login_required
    @require_permission(Permission.TASK_VIEW_UPDATE)
    def _tasks_probe(organization_id):
        return (
            jsonify({"success": True, "message": "ok", "data": {"scope": g.permission_scope.value}}),
            200,
        )

    # Deliberately uses a plain string URL segment (no <uuid:...>
    # converter) to exercise require_permission/get_active_membership_or_404's
    # own defense against a malformed organization_id, for a future
    # route that might declare its URL rule this way.
    @app.route("/api/v1/_test/orgs-raw/<organization_id>/departments", methods=["GET"])
    @login_required
    @require_permission(Permission.DEPARTMENT_MANAGE)
    def _departments_probe_raw(organization_id):
        return jsonify({"success": True, "message": "ok", "data": {}}), 200

    return app.test_client()


def _register_and_login(client, email, password="correct horse battery"):
    client.post("/api/v1/auth/register", json={"name": "Test User", "email": email, "password": password})
    login_response = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    return login_response.get_json()["data"]["user"]["id"]


def _make_org(app, name, slug):
    with app.app_context():
        organization = Organization(name=name, slug=slug)
        db.session.add(organization)
        db.session.commit()
        return str(organization.id)


def _make_membership(app, organization_id, user_id, role, status=MembershipStatus.ACTIVE):
    with app.app_context():
        membership = Membership(organization_id=organization_id, user_id=user_id, role=role, status=status)
        db.session.add(membership)
        db.session.commit()


def test_no_session_returns_401(client, app):
    org_id = _make_org(app, "Org", "org")

    response = client.get(f"/api/v1/_test/orgs/{org_id}/departments")

    assert response.status_code == 401


def test_no_membership_in_the_organization_returns_404(client, app):
    user_id = _register_and_login(client, "nomember@example.com")
    org_id = _make_org(app, "Org", "org")

    response = client.get(f"/api/v1/_test/orgs/{org_id}/departments")

    assert response.status_code == 404


def test_membership_in_a_different_organization_returns_404(client, app):
    user_id = _register_and_login(client, "crosstenant@example.com")
    own_org_id = _make_org(app, "Own Org", "own-org")
    other_org_id = _make_org(app, "Other Org", "other-org")
    _make_membership(app, own_org_id, user_id, MembershipRole.OWNER)

    response = client.get(f"/api/v1/_test/orgs/{other_org_id}/departments")

    assert response.status_code == 404


def test_inactive_membership_returns_404_not_403(client, app):
    user_id = _register_and_login(client, "inactive@example.com")
    org_id = _make_org(app, "Org", "org")
    _make_membership(app, org_id, user_id, MembershipRole.OWNER, status=MembershipStatus.INACTIVE)

    response = client.get(f"/api/v1/_test/orgs/{org_id}/departments")

    assert response.status_code == 404


def test_role_with_no_scope_for_the_permission_returns_403(client, app):
    user_id = _register_and_login(client, "employee@example.com")
    org_id = _make_org(app, "Org", "org")
    _make_membership(app, org_id, user_id, MembershipRole.EMPLOYEE)

    response = client.get(f"/api/v1/_test/orgs/{org_id}/departments")

    assert response.status_code == 403
    assert response.get_json()["error"]["code"] == "FORBIDDEN"


def test_role_with_full_scope_is_granted_and_exposes_the_scope(client, app):
    user_id = _register_and_login(client, "owner@example.com")
    org_id = _make_org(app, "Org", "org")
    _make_membership(app, org_id, user_id, MembershipRole.OWNER)

    response = client.get(f"/api/v1/_test/orgs/{org_id}/departments")

    assert response.status_code == 200
    data = response.get_json()["data"]
    assert data["scope"] == "full"
    assert data["role"] == "owner"


def test_role_with_assigned_scope_is_granted_and_exposes_that_scope(client, app):
    user_id = _register_and_login(client, "employee2@example.com")
    org_id = _make_org(app, "Org", "org")
    _make_membership(app, org_id, user_id, MembershipRole.EMPLOYEE)

    response = client.get(f"/api/v1/_test/orgs/{org_id}/tasks")

    assert response.status_code == 200
    assert response.get_json()["data"]["scope"] == "assigned"


def test_malformed_organization_id_returns_404_not_500(client, app):
    """Regression for tenant-security-reviewer's finding during FD-015's
    own review: a route without a <uuid:...> URL converter must still
    get a uniform 404 for a bad organization_id, not an unhandled DB
    error surfacing as a generic 500."""
    _register_and_login(client, "malformed-route@example.com")

    response = client.get("/api/v1/_test/orgs-raw/not-a-real-uuid/departments")

    assert response.status_code == 404


def test_suspended_membership_returns_404(client, app):
    user_id = _register_and_login(client, "suspended@example.com")
    org_id = _make_org(app, "Org", "org")
    _make_membership(app, org_id, user_id, MembershipRole.MANAGER, status=MembershipStatus.SUSPENDED)

    response = client.get(f"/api/v1/_test/orgs/{org_id}/departments")

    assert response.status_code == 404
