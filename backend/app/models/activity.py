import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.extensions import db
from app.models.base import UUIDPrimaryKeyMixin


class ActivityLog(UUIDPrimaryKeyMixin, db.Model):
    """FD-047. Fields per spec Section 10.1's ActivityLog entity and
    FR-036/FR-037. Deliberately does NOT use `TimestampMixin` - same
    "chronological, append-only" reasoning `TaskHistory`/`RequestHistory`
    already established (FD-025/FD-036): an `updated_at` column would
    imply a logged event can be edited after the fact, which defeats
    the point of an audit trail (FR-037: "immutable through the normal
    application interface" - there is no update/delete route for this
    table anywhere in this codebase).

    `action`/`entity_type` are plain strings, not closed enums - same
    "no implied fixed set" reasoning `TaskHistory.event_type` already
    used: this task wires logging into the specific trigger points
    FR-036 names (see `app.activity.service.log_activity`'s own
    docstring for the exact list, including the one named event -
    "role-changed" - that has no existing trigger point to hook into
    at all, since no task has ever built a "change an existing
    member's role" feature), but nothing stops a later task from
    defining new action/entity_type values without a migration.

    `entity_id` has no foreign key - unlike every other
    actor/parent reference in this codebase, it's genuinely
    polymorphic (a task's id, an invoice's id, a membership's id, ...
    depending on `entity_type`), so there's no single target table a
    real FK constraint could point at.

    `actor_membership_id` is a simple FK (nullable, `ON DELETE SET
    NULL`), not the composite same-organization-enforcing FK pattern
    `Invoice.created_by`/`Payment.recorded_by` use - mirrors
    `TaskHistory.actor_membership_id`/`RequestHistory.actor_membership_id`'s
    own precedent exactly (audit-trail actor references in this
    codebase have consistently used the simpler form, unlike
    financial-record actor references).

    `metadata` is the spec's own field name (FR-036: "... each with
    actor, action, entity, entity ID, timestamp, organization,
    metadata"), but `metadata` is reserved on `db.Model` (SQLAlchemy's
    own `MetaData` collection) - mapped here as the Python attribute
    `metadata_` while keeping the actual column name `metadata`, so
    the API/database still speak the spec's own vocabulary.
    **"Safe metadata only" (this task's own title) is a calling
    discipline, not something this column enforces at runtime** - every
    call site in `app.activity.service` is responsible for only ever
    passing safe, descriptive values (e.g. a title, an amount, a
    status) and never a password, token, or raw request body; there is
    no other field in this codebase whose safety is runtime-validated
    either (e.g. `TaskComment.body` isn't scanned for PII).
    """

    __tablename__ = "activity_logs"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    actor_membership_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("memberships.id", ondelete="SET NULL"), nullable=True, index=True
    )
    action: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    entity_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    entity_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False, index=True)
    metadata_: Mapped[dict | None] = mapped_column("metadata", JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )

    def to_public_dict(self) -> dict:
        return {
            "id": str(self.id),
            "organization_id": str(self.organization_id),
            "actor_membership_id": str(self.actor_membership_id) if self.actor_membership_id else None,
            "action": self.action,
            "entity_type": self.entity_type,
            "entity_id": str(self.entity_id),
            "metadata": self.metadata_,
            "created_at": self.created_at.isoformat(),
        }

    def __repr__(self) -> str:
        return f"<ActivityLog org={self.organization_id} action={self.action!r} entity={self.entity_type}:{self.entity_id}>"
