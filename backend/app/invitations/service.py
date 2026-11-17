import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from flask import current_app
from sqlalchemy.exc import IntegrityError

from app.activity.service import log_activity
from app.authz.service import can_invite_with_role
from app.email import client as email_client
from app.email.client import EmailDeliveryError
from app.errors import APIError
from app.extensions import db
from app.models import Invitation, Membership, MembershipRole, MembershipStatus, Organization, User


def _hash_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def _normalize_email(email: str) -> str:
    return email.strip().lower()


def _has_active_membership(organization_id, user_id) -> bool:
    return (
        db.session.query(Membership)
        .filter_by(organization_id=organization_id, user_id=user_id, status=MembershipStatus.ACTIVE)
        .first()
        is not None
    )


def create_invitation(
    actor_membership: Membership,
    organization: Organization,
    email: str,
    role: MembershipRole,
    send_email_fn=None,
) -> tuple[Invitation, str]:
    """Creates and (best-effort) emails an invitation. Returns
    (invitation, "sent" | "failed") - a failed send never rolls back the
    invitation row: the organization's intent to invite this person is
    real business data independent of whether the mail server happened
    to be reachable just now (same principle as Section 14's "a failed
    [external] call must never corrupt business data"). The raw token is
    deliberately not returned to the caller - see app/email/client.py's
    module docstring and this task's completion report for why real
    email delivery means the API response itself shouldn't also carry
    the secret.

    `send_email_fn` defaults to None rather than binding
    email_client.send_email directly as the parameter default - a
    default value is evaluated once at function-definition time, which
    would make it impossible for tests to monkeypatch
    app.email.client.send_email and have it take effect here. Resolving
    it inside the function body (just below) keeps every call site that
    doesn't pass its own stub using whatever send_email currently is.
    """
    if not can_invite_with_role(actor_membership, role):
        raise APIError("You do not have permission to invite this role.", status_code=403, code="FORBIDDEN")

    normalized_email = _normalize_email(email)

    existing_user = db.session.query(User).filter_by(email=normalized_email).first()
    if existing_user is not None and _has_active_membership(organization.id, existing_user.id):
        raise APIError("This person is already a member of the organization.", status_code=409, code="ALREADY_A_MEMBER")

    # Check-then-insert, not race-closed like email/slug uniqueness
    # elsewhere in this project - documented, minor limitation: two
    # concurrent invite requests for the same email could both succeed,
    # leaving a harmless duplicate pending invitation rather than a
    # security issue (whichever is accepted first succeeds normally;
    # the other remains cancellable).
    now = datetime.now(timezone.utc)
    existing_pending = (
        db.session.query(Invitation)
        .filter_by(organization_id=organization.id, email=normalized_email, accepted_at=None, cancelled_at=None)
        .filter(Invitation.expires_at > now)
        .first()
    )
    if existing_pending is not None:
        raise APIError(
            "An invitation is already pending for this email.", status_code=409, code="INVITATION_ALREADY_PENDING"
        )

    raw_token = secrets.token_urlsafe(32)
    expiry_days = current_app.config["INVITATION_EXPIRY_DAYS"]

    invitation = Invitation(
        organization_id=organization.id,
        email=normalized_email,
        role=role,
        token_hash=_hash_token(raw_token),
        expires_at=now + timedelta(days=expiry_days),
        inviter_id=actor_membership.user_id,
    )
    db.session.add(invitation)
    db.session.flush()
    log_activity(
        organization.id,
        actor_membership.id,
        "employee_invited",
        "invitation",
        invitation.id,
        metadata={"email": normalized_email, "role": role.value},
    )
    db.session.commit()

    invite_link = f"{current_app.config['FRONTEND_URL']}/invitations/accept?token={raw_token}"
    subject = f"You're invited to join {organization.name} on FlowDesk"
    body = (
        f"You've been invited to join {organization.name} on FlowDesk as {role.value}.\n\n"
        f"Accept your invitation: {invite_link}\n\n"
        f"This link expires on {invitation.expires_at.isoformat()}."
    )

    sender = send_email_fn or email_client.send_email
    try:
        sender(to=normalized_email, subject=subject, body=body)
        email_delivery = "sent"
    except EmailDeliveryError:
        current_app.logger.warning("Failed to send invitation email to %s", normalized_email, exc_info=True)
        email_delivery = "failed"

    return invitation, email_delivery


def list_invitations(organization_id) -> list[Invitation]:
    return (
        db.session.query(Invitation)
        .filter_by(organization_id=organization_id)
        .order_by(Invitation.created_at.desc())
        .all()
    )


def cancel_invitation(actor_membership: Membership, organization_id, invitation_id) -> Invitation:
    invitation = db.session.query(Invitation).filter_by(id=invitation_id, organization_id=organization_id).first()
    if invitation is None:
        raise APIError("Not found.", status_code=404, code="NOT_FOUND")

    if not can_invite_with_role(actor_membership, invitation.role):
        raise APIError("You do not have permission to cancel this invitation.", status_code=403, code="FORBIDDEN")

    if invitation.status != "pending":
        raise APIError("This invitation is no longer pending.", status_code=409, code="INVITATION_NOT_PENDING")

    invitation.cancelled_at = datetime.now(timezone.utc)
    db.session.commit()
    return invitation


_TERMINAL_STATUS_CODES = {
    "cancelled": "INVITATION_CANCELLED",
    "accepted": "INVITATION_ALREADY_ACCEPTED",
    "expired": "INVITATION_EXPIRED",
}


def accept_invitation(user: User, raw_token: str) -> Membership:
    token_hash = _hash_token(raw_token)
    invitation = db.session.query(Invitation).filter_by(token_hash=token_hash).first()
    if invitation is None:
        raise APIError("Invitation not found.", status_code=404, code="INVITATION_NOT_FOUND")

    # Checked before the lifecycle-status check below (tenant-security-
    # reviewer's note during FD-016's own review): a caller who isn't
    # the invited person shouldn't learn anything about the
    # invitation's state - whether it's expired, already accepted, or
    # cancelled - before being told they're simply the wrong recipient.
    if user.email != invitation.email:
        raise APIError(
            "This invitation was issued to a different email address.",
            status_code=403,
            code="INVITATION_EMAIL_MISMATCH",
        )

    status = invitation.status
    if status != "pending":
        raise APIError(
            "This invitation can no longer be accepted.",
            status_code=409,
            code=_TERMINAL_STATUS_CODES[status],
        )

    if _has_active_membership(invitation.organization_id, user.id):
        raise APIError("You are already a member of this organization.", status_code=409, code="ALREADY_A_MEMBER")

    membership = Membership(
        organization_id=invitation.organization_id,
        user_id=user.id,
        role=invitation.role,
        status=MembershipStatus.ACTIVE,
    )
    db.session.add(membership)
    invitation.accepted_at = datetime.now(timezone.utc)

    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        raise APIError("You are already a member of this organization.", status_code=409, code="ALREADY_A_MEMBER")

    return membership
