import re
from datetime import datetime, timedelta, timezone

import pytest

from app.email import client as email_client
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


@pytest.fixture
def sent_emails(monkeypatch):
    """Captures every email the test sends, the same way a real invitee
    would read their inbox - the raw token is deliberately not in any
    API response (see app/invitations/service.py), only in the emailed
    link, so this is the only legitimate way to retrieve it for a test."""
    captured = []

    def _fake_send_email(*, to, subject, body):
        captured.append({"to": to, "subject": subject, "body": body})

    monkeypatch.setattr(email_client, "send_email", _fake_send_email)
    return captured


def _register_and_login(client, email, password="correct horse battery"):
    client.post("/api/v1/auth/register", json={"name": "Test User", "email": email, "password": password})
    login_response = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    return login_response.get_json()["data"]["csrf_token"]


def _create_org(client, csrf_token, name="Org One"):
    return client.post("/api/v1/organizations", json={"name": name}, headers={"X-CSRF-Token": csrf_token}).get_json()[
        "data"
    ]


def _invite(client, csrf_token, org_id, email, role="employee"):
    return client.post(
        f"/api/v1/organizations/{org_id}/invitations",
        json={"email": email, "role": role},
        headers={"X-CSRF-Token": csrf_token},
    ).get_json()["data"]


def _extract_token(email_body: str) -> str:
    match = re.search(r"token=([\w\-\.]+)", email_body)
    assert match, f"no token found in email body: {email_body!r}"
    return match.group(1)


def _accept(client, csrf_token, token):
    return client.post(
        "/api/v1/invitations/accept", json={"token": token}, headers={"X-CSRF-Token": csrf_token}
    )


def test_unauthenticated_accept_returns_401(client, app):
    response = client.post("/api/v1/invitations/accept", json={"token": "whatever"})
    assert response.status_code == 401


def test_invitee_can_accept_and_becomes_an_active_member(client, app, sent_emails):
    owner_csrf = _register_and_login(client, "owner@example.com")
    org = _create_org(client, owner_csrf)
    _invite(client, owner_csrf, org["id"], email="invitee@example.com", role="employee")
    token = _extract_token(sent_emails[0]["body"])

    invitee_csrf = _register_and_login(client, "invitee@example.com")
    response = _accept(client, invitee_csrf, token)

    assert response.status_code == 200
    body = response.get_json()["data"]
    assert body["role"] == "employee"
    assert body["status"] == "active"
    assert body["organization"]["id"] == org["id"]


def test_accept_marks_the_invitation_accepted(client, app, sent_emails):
    owner_csrf = _register_and_login(client, "owner2@example.com")
    org = _create_org(client, owner_csrf)
    invitation = _invite(client, owner_csrf, org["id"], email="invitee2@example.com")
    token = _extract_token(sent_emails[0]["body"])

    invitee_csrf = _register_and_login(client, "invitee2@example.com")
    _accept(client, invitee_csrf, token)

    with app.app_context():
        stored = db.session.get(Invitation, invitation["id"])
        assert stored.status == "accepted"


def test_unknown_token_returns_404(client, app):
    csrf_token = _register_and_login(client, "someone@example.com")

    response = _accept(client, csrf_token, "not-a-real-token")

    assert response.status_code == 404
    assert response.get_json()["error"]["code"] == "INVITATION_NOT_FOUND"


def test_accepting_with_a_different_email_than_invited_returns_403(client, app, sent_emails):
    owner_csrf = _register_and_login(client, "owner3@example.com")
    org = _create_org(client, owner_csrf)
    _invite(client, owner_csrf, org["id"], email="intended@example.com")
    token = _extract_token(sent_emails[0]["body"])

    wrong_csrf = _register_and_login(client, "wrong-person@example.com")
    response = _accept(client, wrong_csrf, token)

    assert response.status_code == 403
    assert response.get_json()["error"]["code"] == "INVITATION_EMAIL_MISMATCH"


def test_accepting_twice_returns_409_already_accepted(client, app, sent_emails):
    owner_csrf = _register_and_login(client, "owner4@example.com")
    org = _create_org(client, owner_csrf)
    _invite(client, owner_csrf, org["id"], email="invitee4@example.com")
    token = _extract_token(sent_emails[0]["body"])

    invitee_csrf = _register_and_login(client, "invitee4@example.com")
    _accept(client, invitee_csrf, token)

    response = _accept(client, invitee_csrf, token)

    assert response.status_code == 409
    assert response.get_json()["error"]["code"] == "INVITATION_ALREADY_ACCEPTED"


def test_accepting_a_cancelled_invitation_returns_409(client, app, sent_emails):
    owner_csrf = _register_and_login(client, "owner5@example.com")
    org = _create_org(client, owner_csrf)
    invitation = _invite(client, owner_csrf, org["id"], email="invitee5@example.com")
    token = _extract_token(sent_emails[0]["body"])
    client.delete(
        f"/api/v1/organizations/{org['id']}/invitations/{invitation['id']}", headers={"X-CSRF-Token": owner_csrf}
    )

    invitee_csrf = _register_and_login(client, "invitee5@example.com")
    response = _accept(client, invitee_csrf, token)

    assert response.status_code == 409
    assert response.get_json()["error"]["code"] == "INVITATION_CANCELLED"


def test_accept_without_csrf_returns_403(client, app, sent_emails):
    owner_csrf = _register_and_login(client, "owner6@example.com")
    org = _create_org(client, owner_csrf)
    _invite(client, owner_csrf, org["id"], email="invitee6@example.com")
    token = _extract_token(sent_emails[0]["body"])

    invitee_csrf = _register_and_login(client, "invitee6@example.com")
    response = client.post("/api/v1/invitations/accept", json={"token": token})

    assert response.status_code == 403


def test_accepting_an_expired_invitation_returns_409(client, app, sent_emails):
    """Section 13's mandatory scenario: 'User accesses an expired
    invitation -> Rejected'. test_invitation_model.py already checks the
    derived status property in isolation; this exercises the real route
    end to end (flagged as a coverage gap by tenant-security-reviewer
    during FD-016's own review)."""
    owner_csrf = _register_and_login(client, "owner8@example.com")
    org = _create_org(client, owner_csrf)
    invitation = _invite(client, owner_csrf, org["id"], email="invitee8@example.com")
    token = _extract_token(sent_emails[0]["body"])

    with app.app_context():
        stored = db.session.get(Invitation, invitation["id"])
        stored.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        db.session.commit()

    invitee_csrf = _register_and_login(client, "invitee8@example.com")
    response = _accept(client, invitee_csrf, token)

    assert response.status_code == 409
    assert response.get_json()["error"]["code"] == "INVITATION_EXPIRED"


def test_accepting_while_already_an_active_member_returns_409(client, app, sent_emails):
    """Distinct from create_invitation's own ALREADY_A_MEMBER check
    (which blocks *issuing* a duplicate invite): here the invitation was
    issued while the invitee was NOT yet a member, and they became one
    through some other means before accepting it - the accept path's
    own _has_active_membership check must still catch it (flagged by
    tenant-security-reviewer as an untested branch)."""
    owner_csrf = _register_and_login(client, "owner9@example.com")
    org = _create_org(client, owner_csrf)
    invitation = _invite(client, owner_csrf, org["id"], email="invitee9@example.com")
    token = _extract_token(sent_emails[0]["body"])

    invitee_csrf = _register_and_login(client, "invitee9@example.com")
    with app.app_context():
        user = db.session.query(User).filter_by(email="invitee9@example.com").one()
        db.session.add(
            Membership(organization_id=org["id"], user_id=user.id, role=MembershipRole.EMPLOYEE)
        )
        db.session.commit()

    response = _accept(client, invitee_csrf, token)

    assert response.status_code == 409
    assert response.get_json()["error"]["code"] == "ALREADY_A_MEMBER"


def test_accepting_grants_exactly_the_invited_role(client, app, sent_emails):
    owner_csrf = _register_and_login(client, "owner7@example.com")
    org = _create_org(client, owner_csrf)
    _invite(client, owner_csrf, org["id"], email="future-accountant@example.com", role="accountant")
    token = _extract_token(sent_emails[0]["body"])

    invitee_csrf = _register_and_login(client, "future-accountant@example.com")
    response = _accept(client, invitee_csrf, token)

    assert response.get_json()["data"]["role"] == "accountant"
