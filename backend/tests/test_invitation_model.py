from datetime import datetime, timedelta, timezone

import pytest

from app.extensions import db
from app.models import Invitation, MembershipRole, Organization


@pytest.fixture(autouse=True)
def _clean(app):
    yield
    with app.app_context():
        db.session.query(Invitation).delete()
        db.session.query(Organization).delete()
        db.session.commit()


def _make_org(app):
    with app.app_context():
        organization = Organization(name="Org", slug="org")
        db.session.add(organization)
        db.session.commit()
        return organization.id


def _make_invitation(app, organization_id, **overrides):
    defaults = dict(
        organization_id=organization_id,
        email="Invitee@Example.com",
        role=MembershipRole.EMPLOYEE,
        token_hash="a" * 64,
        expires_at=datetime.now(timezone.utc) + timedelta(days=7),
    )
    defaults.update(overrides)
    with app.app_context():
        invitation = Invitation(**defaults)
        db.session.add(invitation)
        db.session.commit()
        return invitation.id


def test_email_is_normalized_to_lowercase_and_trimmed(app):
    org_id = _make_org(app)
    invitation_id = _make_invitation(app, org_id, email="  Invitee@Example.com  ")

    with app.app_context():
        invitation = db.session.get(Invitation, invitation_id)
        assert invitation.email == "invitee@example.com"


def test_status_is_pending_by_default(app):
    org_id = _make_org(app)
    invitation_id = _make_invitation(app, org_id)

    with app.app_context():
        invitation = db.session.get(Invitation, invitation_id)
        assert invitation.status == "pending"


def test_status_is_expired_once_past_expiry(app):
    org_id = _make_org(app)
    invitation_id = _make_invitation(
        app, org_id, expires_at=datetime.now(timezone.utc) - timedelta(seconds=1)
    )

    with app.app_context():
        invitation = db.session.get(Invitation, invitation_id)
        assert invitation.status == "expired"


def test_status_is_accepted_once_accepted_at_is_set(app):
    org_id = _make_org(app)
    invitation_id = _make_invitation(app, org_id, accepted_at=datetime.now(timezone.utc))

    with app.app_context():
        invitation = db.session.get(Invitation, invitation_id)
        assert invitation.status == "accepted"


def test_status_is_cancelled_once_cancelled_at_is_set_even_if_also_accepted(app):
    """cancelled_at takes priority - a cancelled invitation should never
    read as accepted no matter what other timestamp got set."""
    org_id = _make_org(app)
    invitation_id = _make_invitation(
        app, org_id, accepted_at=datetime.now(timezone.utc), cancelled_at=datetime.now(timezone.utc)
    )

    with app.app_context():
        invitation = db.session.get(Invitation, invitation_id)
        assert invitation.status == "cancelled"


def test_to_public_dict_never_includes_the_token_hash(app):
    org_id = _make_org(app)
    invitation_id = _make_invitation(app, org_id)

    with app.app_context():
        invitation = db.session.get(Invitation, invitation_id)
        body = invitation.to_public_dict()
        assert "token_hash" not in body
        assert "token" not in body
        assert body["role"] == "employee"
        assert body["status"] == "pending"
