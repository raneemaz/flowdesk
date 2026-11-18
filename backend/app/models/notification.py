import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, ForeignKeyConstraint, String, Text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.extensions import db
from app.models.base import TimestampMixin, UUIDPrimaryKeyMixin


class Notification(UUIDPrimaryKeyMixin, TimestampMixin, db.Model):
    """FD-048. Fields per spec Section 10.1's Notification entity, plus
    `read_at` doing the same "nullable timestamp as a state flag" job
    `Invitation.accepted_at`/`cancelled_at` already established in this
    codebase - unread is simply `read_at IS NULL`, not a separate
    boolean that could drift out of sync with when it actually happened.
    Uses `TimestampMixin` (unlike the append-only `ActivityLog`/
    `TaskHistory`) because marking a notification read is a real update
    to this row, not a new historical fact - `updated_at` is kept as
    the standard bookkeeping column but, like `Invitation`, not
    surfaced in `to_public_dict()` since the spec's own field list for
    this entity doesn't include it.

    The spec names this column `recipient_id`, renamed here to
    `recipient_membership_id` - every actor/recipient reference in this
    codebase is to a `Membership`, never directly to a `User` (a person
    can hold a different role, or no access at all, in a different
    organization), and the `_membership_id` suffix is this codebase's
    own established naming convention for that (`creator_membership_id`,
    `actor_membership_id`, etc.).

    `recipient_membership_id` is **required** (unlike `ActivityLog.actor_membership_id`,
    nullable) - a notification with no recipient is meaningless, so
    there's no "system action" case to accommodate here the way an
    audit-log entry might have one. It uses the exact composite
    same-organization-enforcing FK technique `EmployeeProfile.membership_id`
    (FD-020) established for a required membership reference,
    `ON DELETE CASCADE` for the same reason that one gave: a
    notification has no life independent of the membership it was sent
    to, unlike `Task.creator_membership_id`'s `RESTRICT` (a task must
    outlive its creator leaving).

    `entity_type`/`entity_id` mirror `ActivityLog`'s own polymorphic
    reference pattern exactly (no FK on `entity_id` - its target table
    depends on `entity_type`) - FD-049 is what will actually populate
    these as it wires real trigger points in.

    **FD-048 is infrastructure only** - nothing in this task calls
    `app.notifications.service.create_notification()` from any business
    event. FR-038's own trigger list (task assigned, deadline
    approaching/overdue, comment added, request assigned/status
    changed, invoice paid, invitation received) is FD-049's job to wire
    in, once its own dependencies (FD-027/028/037/043, all already
    Done) are joined by this task's read-side infrastructure.

    No `require_permission`-gated `Permission` exists for this entity,
    unlike every other organization-scoped resource in this codebase -
    checked against spec Section 7.2's own baseline permission matrix,
    which has no notification row at all. Access here is purely
    ownership-based ("the caller is this row's own recipient"), the
    same ungated-but-still-member-checked shape `GET /organizations`
    already uses for "list the caller's own memberships" - see
    `app.notifications.routes`'s own docstring.
    """

    __tablename__ = "notifications"
    __table_args__ = (
        # Named shorter than the auto-generated
        # `fk_notifications_recipient_membership_id_organization_id_memberships`
        # would be (68 chars) - Postgres identifiers cap at 63.
        ForeignKeyConstraint(
            ["recipient_membership_id", "organization_id"],
            ["memberships.id", "memberships.organization_id"],
            name="fk_notifications_recipient_membership_org_memberships",
            ondelete="CASCADE",
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    recipient_membership_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False, index=True)
    type: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    entity_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    entity_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False, index=True)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)

    def to_public_dict(self) -> dict:
        return {
            "id": str(self.id),
            "organization_id": str(self.organization_id),
            "recipient_membership_id": str(self.recipient_membership_id),
            "type": self.type,
            "title": self.title,
            "body": self.body,
            "entity_type": self.entity_type,
            "entity_id": str(self.entity_id),
            "read_at": self.read_at.isoformat() if self.read_at else None,
            "created_at": self.created_at.isoformat(),
        }

    def __repr__(self) -> str:
        return f"<Notification recipient={self.recipient_membership_id} type={self.type!r}>"
