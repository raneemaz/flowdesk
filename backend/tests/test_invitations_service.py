import pytest

from app.email.client import EmailDeliveryError
from app.extensions import db
from app.invitations.service import create_invitation
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


def _make_owner_membership(app, email="owner@example.com"):
    with app.app_context():
        organization = Organization(name="Org", slug="org")
        user = User(name="Owner", email=email)
        user.set_password("correct horse battery")
        db.session.add_all([organization, user])
        db.session.flush()
        membership = Membership(organization_id=organization.id, user_id=user.id, role=MembershipRole.OWNER)
        db.session.add(membership)
        db.session.commit()
        return membership.id, organization.id


def test_a_failed_email_send_does_not_roll_back_the_invitation(app):
    """A flaky/unreachable mail server must never erase the
    organization's real intent to invite this person - see Section 14's
    'a failed [external] call must never corrupt business data', applied
    here to email instead of the AI provider it was written for."""
    membership_id, organization_id = _make_owner_membership(app)

    def _failing_send(*, to, subject, body):
        raise EmailDeliveryError("smtp server unreachable")

    with app.app_context():
        membership = db.session.get(Membership, membership_id)
        organization = db.session.get(Organization, organization_id)

        invitation, email_delivery = create_invitation(
            membership, organization, "invitee@example.com", MembershipRole.EMPLOYEE, send_email_fn=_failing_send
        )

        assert email_delivery == "failed"
        # Still persisted and still pending - not rolled back.
        reloaded = db.session.get(Invitation, invitation.id)
        assert reloaded is not None
        assert reloaded.status == "pending"


def test_a_successful_email_send_is_reported_as_sent(app):
    membership_id, organization_id = _make_owner_membership(app, email="owner2@example.com")
    sent = []

    def _capturing_send(*, to, subject, body):
        sent.append((to, subject, body))

    with app.app_context():
        membership = db.session.get(Membership, membership_id)
        organization = db.session.get(Organization, organization_id)

        invitation, email_delivery = create_invitation(
            membership, organization, "invitee2@example.com", MembershipRole.EMPLOYEE, send_email_fn=_capturing_send
        )

        assert email_delivery == "sent"
        assert sent[0][0] == "invitee2@example.com"
        assert "token=" in sent[0][2]
