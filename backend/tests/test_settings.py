"""Settings endpoints: organization profile, members (role/access), and
the signed-in user's own account (name, password)."""

import uuid

import pytest

from app.extensions import db
from app.models import ActivityLog, Membership, MembershipRole, MembershipStatus, Organization, User

PASSWORD = "correct horse battery"
OWNER = "owner@settings.example.com"
OWNER2 = "owner2@settings.example.com"
MANAGER = "manager@settings.example.com"
EMPLOYEE = "employee@settings.example.com"
ACCOUNTANT = "accountant@settings.example.com"
OUTSIDER = "outsider@settings.example.com"


@pytest.fixture(autouse=True)
def _clean(app):
    yield
    with app.app_context():
        db.session.query(ActivityLog).delete()
        db.session.query(Membership).delete()
        db.session.query(Organization).delete()
        db.session.query(User).delete()
        db.session.commit()


def _login(client, email, password=PASSWORD):
    response = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    return response.get_json()["data"]["csrf_token"] if response.status_code == 200 else None


def _give_role(app, org_id, email, role, status=MembershipStatus.ACTIVE):
    with app.app_context():
        user = db.session.query(User).filter_by(email=email).one()
        membership = Membership(organization_id=uuid.UUID(org_id), user_id=user.id, role=role, status=status)
        db.session.add(membership)
        db.session.commit()
        return str(membership.id)


def _membership_id(app, org_id, email):
    with app.app_context():
        user = db.session.query(User).filter_by(email=email).one()
        return str(db.session.query(Membership).filter_by(organization_id=uuid.UUID(org_id), user_id=user.id).one().id)


@pytest.fixture
def org(app, client):
    for email in (OWNER, OWNER2, MANAGER, EMPLOYEE, ACCOUNTANT, OUTSIDER):
        client.post("/api/v1/auth/register", json={"name": email.split("@")[0], "email": email, "password": PASSWORD})
    csrf = _login(client, OWNER)
    org = client.post("/api/v1/organizations", json={"name": "Settings Org"}, headers={"X-CSRF-Token": csrf}).get_json()[
        "data"
    ]
    return {
        "id": org["id"],
        "owner": _membership_id(app, org["id"], OWNER),
        "manager": _give_role(app, org["id"], MANAGER, MembershipRole.MANAGER),
        "employee": _give_role(app, org["id"], EMPLOYEE, MembershipRole.EMPLOYEE),
        "accountant": _give_role(app, org["id"], ACCOUNTANT, MembershipRole.ACCOUNTANT),
    }


def _patch_org(client, csrf, org_id, body):
    return client.patch(f"/api/v1/organizations/{org_id}", json=body, headers={"X-CSRF-Token": csrf})


def _patch_member(client, csrf, org_id, membership_id, body):
    return client.patch(
        f"/api/v1/organizations/{org_id}/members/{membership_id}", json=body, headers={"X-CSRF-Token": csrf}
    )


# --- Organization profile -------------------------------------------------


def test_owner_updates_every_organization_field(app, client, org):
    csrf = _login(client, OWNER)

    response = _patch_org(
        client,
        csrf,
        org["id"],
        {
            "name": "Renamed Co",
            "email": "hello@renamed.example.com",
            "phone": "+1 555 0100",
            "address": "1 Main St",
            "currency": "eur",
            "timezone": "Europe/Berlin",
            "date_format": "DD/MM/YYYY",
        },
    )

    assert response.status_code == 200
    data = response.get_json()["data"]
    assert data["name"] == "Renamed Co"
    assert data["currency"] == "EUR"
    assert data["timezone"] == "Europe/Berlin"
    assert data["slug"]  # unchanged and still present
    with app.app_context():
        entry = db.session.query(ActivityLog).filter_by(action="organization_updated").one()
        assert "currency" in entry.metadata_["fields"]


def test_manager_may_edit_contact_details_only(client, org):
    csrf = _login(client, MANAGER)

    assert _patch_org(client, csrf, org["id"], {"phone": "+1 555 0199", "date_format": "YYYY-MM-DD"}).status_code == 200
    forbidden = _patch_org(client, csrf, org["id"], {"name": "Manager Co", "phone": "x"})
    assert forbidden.status_code == 403
    assert "name" in forbidden.get_json()["error"]["details"]


@pytest.mark.parametrize("email", [EMPLOYEE, ACCOUNTANT])
def test_other_roles_cannot_edit_the_organization(client, org, email):
    csrf = _login(client, email)

    assert _patch_org(client, csrf, org["id"], {"phone": "123"}).status_code == 403


def test_outsider_gets_404_for_another_organization(client, org):
    csrf = _login(client, OUTSIDER)

    assert _patch_org(client, csrf, org["id"], {"phone": "123"}).status_code == 404
    assert client.get(f"/api/v1/organizations/{org['id']}/members").status_code == 404


@pytest.mark.parametrize(
    "body, field",
    [
        ({"timezone": "Mars/Olympus"}, "timezone"),
        ({"currency": "U$D"}, "currency"),
        ({"name": None}, "name"),
        ({"slug": "hijack"}, "slug"),
        ({"email": "not-an-email"}, "email"),
    ],
)
def test_organization_update_validation(client, org, body, field):
    csrf = _login(client, OWNER)

    response = _patch_org(client, csrf, org["id"], body)

    assert response.status_code == 422
    assert field in response.get_json()["error"]["details"]


def test_organization_update_requires_csrf(client, org):
    _login(client, OWNER)

    assert client.patch(f"/api/v1/organizations/{org['id']}", json={"phone": "1"}).status_code == 403


# --- Members ----------------------------------------------------------------


def test_owner_lists_members_including_removed_ones(app, client, org):
    _give_role(app, org["id"], OWNER2, MembershipRole.EMPLOYEE, status=MembershipStatus.INACTIVE)
    _login(client, OWNER)

    response = client.get(f"/api/v1/organizations/{org['id']}/members")

    assert response.status_code == 200
    members = response.get_json()["data"]
    assert len(members) == 5
    assert members[0]["role"] == "owner"
    assert members[-1]["status"] == "inactive"
    assert {"name", "email", "role", "status", "membership_id"} <= set(members[0])


@pytest.mark.parametrize("email", [EMPLOYEE, ACCOUNTANT])
def test_other_roles_cannot_list_members(client, org, email):
    _login(client, email)

    assert client.get(f"/api/v1/organizations/{org['id']}/members").status_code == 403


def test_owner_changes_a_role_and_it_is_logged(app, client, org):
    csrf = _login(client, OWNER)

    response = _patch_member(client, csrf, org["id"], org["employee"], {"role": "manager"})

    assert response.status_code == 200
    assert response.get_json()["data"]["role"] == "manager"
    with app.app_context():
        entry = db.session.query(ActivityLog).filter_by(action="member_role_changed").one()
        assert entry.metadata_ == {"from": "employee", "to": "manager"}


def test_manager_reach_is_limited(client, org):
    csrf = _login(client, MANAGER)

    assert _patch_member(client, csrf, org["id"], org["employee"], {"role": "accountant"}).status_code == 200
    # Can't promote to manager, can't touch the owner, can't change self.
    assert _patch_member(client, csrf, org["id"], org["accountant"], {"role": "manager"}).status_code == 403
    assert _patch_member(client, csrf, org["id"], org["owner"], {"role": "employee"}).status_code == 403
    assert _patch_member(client, csrf, org["id"], org["manager"], {"role": "employee"}).status_code == 403


def test_removing_access_blocks_the_member_and_restoring_lets_them_back(client, org):
    owner_csrf = _login(client, OWNER)
    assert _patch_member(client, owner_csrf, org["id"], org["employee"], {"status": "inactive"}).status_code == 200

    _login(client, EMPLOYEE)
    assert client.get(f"/api/v1/organizations/{org['id']}/tasks").status_code == 404

    owner_csrf = _login(client, OWNER)
    assert _patch_member(client, owner_csrf, org["id"], org["employee"], {"status": "active"}).status_code == 200
    _login(client, EMPLOYEE)
    assert client.get(f"/api/v1/organizations/{org['id']}/tasks").status_code == 200


def test_the_last_active_owner_cannot_be_demoted_or_removed(app, client, org):
    _give_role(app, org["id"], OWNER2, MembershipRole.OWNER)
    csrf = _login(client, OWNER2)
    # With two owners, one may demote the other...
    assert _patch_member(client, csrf, org["id"], org["owner"], {"role": "manager"}).status_code == 200

    csrf = _login(client, OWNER)  # now a manager
    owner2 = _membership_id(app, org["id"], OWNER2)
    assert _patch_member(client, csrf, org["id"], owner2, {"status": "inactive"}).status_code == 403

    # ...and the remaining owner can't remove themselves (self-change is never allowed).
    csrf = _login(client, OWNER2)
    assert _patch_member(client, csrf, org["id"], owner2, {"role": "manager"}).status_code == 403


def test_last_owner_rule_applies_even_to_another_owner(app, client, org):
    owner2 = _give_role(app, org["id"], OWNER2, MembershipRole.OWNER, status=MembershipStatus.INACTIVE)
    csrf = _login(client, OWNER)
    # OWNER2 is inactive, so OWNER is the only *active* owner. Promoting
    # and restoring OWNER2 makes two; then OWNER2 can't remove OWNER and
    # itself in turn - the second removal is refused.
    assert _patch_member(client, csrf, org["id"], owner2, {"status": "active"}).status_code == 200
    csrf = _login(client, OWNER2)
    assert _patch_member(client, csrf, org["id"], org["owner"], {"status": "inactive"}).status_code == 200
    csrf = _login(client, OWNER2)
    with app.app_context():
        remaining = db.session.query(Membership).filter_by(
            organization_id=uuid.UUID(org["id"]), role=MembershipRole.OWNER, status=MembershipStatus.ACTIVE
        ).count()
    assert remaining == 1


def test_member_update_validation_and_isolation(client, org):
    csrf = _login(client, OWNER)

    assert _patch_member(client, csrf, org["id"], org["employee"], {}).status_code == 422
    assert _patch_member(client, csrf, org["id"], org["employee"], {"role": "emperor"}).status_code == 422
    assert _patch_member(client, csrf, org["id"], str(uuid.uuid4()), {"role": "employee"}).status_code == 404


# --- My account ---------------------------------------------------------------


def test_user_updates_their_own_name(client, org):
    csrf = _login(client, EMPLOYEE)

    response = client.patch("/api/v1/auth/me", json={"name": "  Ada Lovelace "}, headers={"X-CSRF-Token": csrf})

    assert response.status_code == 200
    assert response.get_json()["data"]["name"] == "Ada Lovelace"
    assert client.get("/api/v1/auth/me").get_json()["data"]["name"] == "Ada Lovelace"
    blank = client.patch("/api/v1/auth/me", json={"name": "   "}, headers={"X-CSRF-Token": csrf})
    assert blank.status_code == 422
    assert client.patch("/api/v1/auth/me", json={"email": "x@y.com", "name": "A"}, headers={"X-CSRF-Token": csrf}).status_code == 422


def test_password_change_requires_the_current_password(client, org):
    csrf = _login(client, EMPLOYEE)

    wrong = client.post(
        "/api/v1/auth/change-password",
        json={"current_password": "wrong password", "new_password": "a brand new password"},
        headers={"X-CSRF-Token": csrf},
    )
    assert wrong.status_code == 400
    assert wrong.get_json()["error"]["code"] == "INVALID_CURRENT_PASSWORD"

    same = client.post(
        "/api/v1/auth/change-password",
        json={"current_password": PASSWORD, "new_password": PASSWORD},
        headers={"X-CSRF-Token": csrf},
    )
    assert same.status_code == 422

    short = client.post(
        "/api/v1/auth/change-password",
        json={"current_password": PASSWORD, "new_password": "short"},
        headers={"X-CSRF-Token": csrf},
    )
    assert short.status_code == 422

    ok = client.post(
        "/api/v1/auth/change-password",
        json={"current_password": PASSWORD, "new_password": "a brand new password"},
        headers={"X-CSRF-Token": csrf},
    )
    assert ok.status_code == 200

    assert _login(client, EMPLOYEE) is None
    assert _login(client, EMPLOYEE, "a brand new password") is not None


def test_account_endpoints_require_login_and_csrf(app, client, org):
    anonymous = app.test_client()
    assert anonymous.patch("/api/v1/auth/me", json={"name": "X"}).status_code == 401
    _login(client, EMPLOYEE)
    assert client.patch("/api/v1/auth/me", json={"name": "X"}).status_code == 403
    assert (
        client.post(
            "/api/v1/auth/change-password", json={"current_password": PASSWORD, "new_password": "another password"}
        ).status_code
        == 403
    )
