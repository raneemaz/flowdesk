import pytest

from app.extensions import db
from app.models import Invitation, Membership, MembershipRole, MembershipStatus, Organization, User


@pytest.fixture(autouse=True)
def _clean(app):
    yield
    with app.app_context():
        db.session.query(Invitation).delete()
        db.session.query(Membership).delete()
        db.session.query(Organization).delete()
        db.session.query(User).delete()
        db.session.commit()


def _register_and_login(client, email, password="correct horse battery"):
    client.post("/api/v1/auth/register", json={"name": "Test User", "email": email, "password": password})
    login_response = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    return login_response.get_json()["data"]["csrf_token"]


def _create_org(client, csrf_token, name="Org One"):
    return client.post("/api/v1/organizations", json={"name": name}, headers={"X-CSRF-Token": csrf_token}).get_json()[
        "data"
    ]


def _give_role(app, organization_id, email, role, status=MembershipStatus.ACTIVE):
    with app.app_context():
        user = db.session.query(User).filter_by(email=email).one()
        membership = Membership(organization_id=organization_id, user_id=user.id, role=role, status=status)
        db.session.add(membership)
        db.session.commit()


def _invite(client, csrf_token, org_id, email="invitee@example.com", role="employee"):
    return client.post(
        f"/api/v1/organizations/{org_id}/invitations",
        json={"email": email, "role": role},
        headers={"X-CSRF-Token": csrf_token},
    ).get_json()["data"]


class TestList:
    def test_unauthenticated_returns_401(self, client, app):
        response = client.get("/api/v1/organizations/00000000-0000-0000-0000-000000000000/invitations")
        assert response.status_code == 401

    def test_non_member_gets_404(self, client, app):
        owner_csrf = _register_and_login(client, "owner@example.com")
        org = _create_org(client, owner_csrf)
        client.post("/api/v1/auth/logout", headers={"X-CSRF-Token": owner_csrf})

        _register_and_login(client, "stranger@example.com")

        response = client.get(f"/api/v1/organizations/{org['id']}/invitations")
        assert response.status_code == 404

    def test_owner_sees_pending_invitations(self, client, app):
        csrf_token = _register_and_login(client, "owner2@example.com")
        org = _create_org(client, csrf_token)
        _invite(client, csrf_token, org["id"], email="a@example.com")
        _invite(client, csrf_token, org["id"], email="b@example.com")

        response = client.get(f"/api/v1/organizations/{org['id']}/invitations")

        assert response.status_code == 200
        emails = {invitation["email"] for invitation in response.get_json()["data"]}
        assert emails == {"a@example.com", "b@example.com"}

    def test_employee_with_no_permission_gets_403(self, client, app):
        owner_csrf = _register_and_login(client, "owner3@example.com")
        org = _create_org(client, owner_csrf)
        client.post("/api/v1/auth/logout", headers={"X-CSRF-Token": owner_csrf})

        _register_and_login(client, "employee@example.com")
        _give_role(app, org["id"], "employee@example.com", MembershipRole.EMPLOYEE)

        response = client.get(f"/api/v1/organizations/{org['id']}/invitations")

        assert response.status_code == 403

    def test_list_never_includes_another_organizations_invitations(self, client, app):
        owner_csrf = _register_and_login(client, "owner4@example.com")
        org_a = _create_org(client, owner_csrf, "Org A")
        _invite(client, owner_csrf, org_a["id"], email="only-in-a@example.com")

        owner2_csrf = _register_and_login(client, "owner5@example.com")
        org_b = _create_org(client, owner2_csrf, "Org B")
        _invite(client, owner2_csrf, org_b["id"], email="only-in-b@example.com")

        response = client.get(f"/api/v1/organizations/{org_b['id']}/invitations")

        emails = {invitation["email"] for invitation in response.get_json()["data"]}
        assert emails == {"only-in-b@example.com"}


class TestCancel:
    def test_unauthenticated_returns_401(self, client, app):
        response = client.delete(
            "/api/v1/organizations/00000000-0000-0000-0000-000000000000/invitations/00000000-0000-0000-0000-000000000000"
        )
        assert response.status_code == 401

    def test_owner_can_cancel_a_pending_invitation(self, client, app):
        csrf_token = _register_and_login(client, "owner6@example.com")
        org = _create_org(client, csrf_token)
        invitation = _invite(client, csrf_token, org["id"])

        response = client.delete(
            f"/api/v1/organizations/{org['id']}/invitations/{invitation['id']}",
            headers={"X-CSRF-Token": csrf_token},
        )

        assert response.status_code == 200
        assert response.get_json()["data"]["status"] == "cancelled"

    def test_cancelling_without_csrf_returns_403(self, client, app):
        csrf_token = _register_and_login(client, "owner7@example.com")
        org = _create_org(client, csrf_token)
        invitation = _invite(client, csrf_token, org["id"])

        response = client.delete(f"/api/v1/organizations/{org['id']}/invitations/{invitation['id']}")

        assert response.status_code == 403

    def test_cancelling_a_nonexistent_invitation_returns_404(self, client, app):
        csrf_token = _register_and_login(client, "owner8@example.com")
        org = _create_org(client, csrf_token)

        response = client.delete(
            f"/api/v1/organizations/{org['id']}/invitations/00000000-0000-0000-0000-000000000000",
            headers={"X-CSRF-Token": csrf_token},
        )

        assert response.status_code == 404

    def test_cancelling_an_already_cancelled_invitation_returns_409(self, client, app):
        csrf_token = _register_and_login(client, "owner9@example.com")
        org = _create_org(client, csrf_token)
        invitation = _invite(client, csrf_token, org["id"])
        client.delete(
            f"/api/v1/organizations/{org['id']}/invitations/{invitation['id']}", headers={"X-CSRF-Token": csrf_token}
        )

        response = client.delete(
            f"/api/v1/organizations/{org['id']}/invitations/{invitation['id']}", headers={"X-CSRF-Token": csrf_token}
        )

        assert response.status_code == 409
        assert response.get_json()["error"]["code"] == "INVITATION_NOT_PENDING"

    def test_manager_cannot_cancel_an_invitation_for_a_manager_role(self, client, app):
        owner_csrf = _register_and_login(client, "owner10@example.com")
        org = _create_org(client, owner_csrf)
        invitation = _invite(client, owner_csrf, org["id"], email="future-manager@example.com", role="manager")

        manager_csrf = _register_and_login(client, "manager@example.com")
        _give_role(app, org["id"], "manager@example.com", MembershipRole.MANAGER)

        response = client.delete(
            f"/api/v1/organizations/{org['id']}/invitations/{invitation['id']}",
            headers={"X-CSRF-Token": manager_csrf},
        )

        assert response.status_code == 403

    def test_cancelling_an_invitation_from_a_different_organization_returns_404(self, client, app):
        owner_csrf = _register_and_login(client, "owner11@example.com")
        org_a = _create_org(client, owner_csrf, "Org A")
        invitation = _invite(client, owner_csrf, org_a["id"])

        owner2_csrf = _register_and_login(client, "owner12@example.com")
        org_b = _create_org(client, owner2_csrf, "Org B")

        response = client.delete(
            f"/api/v1/organizations/{org_b['id']}/invitations/{invitation['id']}",
            headers={"X-CSRF-Token": owner2_csrf},
        )

        assert response.status_code == 404
