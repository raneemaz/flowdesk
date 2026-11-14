import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, Enum, String, UniqueConstraint
from sqlalchemy import ForeignKey
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship, validates

from app.extensions import db
from app.models.base import TimestampMixin, UUIDPrimaryKeyMixin
from app.models.membership import MembershipRole


class Invitation(UUIDPrimaryKeyMixin, TimestampMixin, db.Model):
    """FD-016. Fields per spec Section 10.1's Invitation entity, plus
    `cancelled_at` (a judgment call, not in that field list - symmetric
    with `accepted_at` so cancellation doesn't need a separate status
    enum column; `status` below is derived, never stored, so it can
    never drift out of sync with the timestamps that actually define it).
    """

    __tablename__ = "invitations"
    __table_args__ = (UniqueConstraint("token_hash", name="uq_invitations_token_hash"),)

    organization_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    email: Mapped[str] = mapped_column(String(320), nullable=False, index=True)
    role: Mapped[MembershipRole] = mapped_column(
        Enum(
            MembershipRole,
            name="membership_role",
            native_enum=True,
            # The type already exists (created by the memberships
            # table, FD-012) - the generated migration must not try to
            # CREATE or DROP it again; checked and fixed by hand below,
            # the same review step FD-008 established for enum columns.
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=False,
    )
    # SHA-256 hex digest of the raw token - never the raw token itself.
    # Deliberately NOT Argon2id (that's for passwords, which are
    # verified one guess at a time against a known user; a token lookup
    # needs to find the matching row by hash directly, which requires a
    # deterministic digest to index on - the raw token's own 256 bits of
    # randomness is what makes it unguessable, not a slow hash).
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # SET NULL, not CASCADE: an invitation is organization history: it
    # must outlive the inviter's own User row if that's ever deleted
    # (no such endpoint exists yet, but the schema shouldn't assume one
    # never will).
    inviter_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )

    organization = relationship("Organization", back_populates="invitations")

    @validates("email")
    def _normalize_email(self, key, value):
        normalized = (value or "").strip().lower()
        if not normalized:
            raise ValueError("email must not be empty")
        return normalized

    @property
    def status(self) -> str:
        if self.cancelled_at is not None:
            return "cancelled"
        if self.accepted_at is not None:
            return "accepted"
        if self.expires_at <= datetime.now(timezone.utc):
            return "expired"
        return "pending"

    def to_public_dict(self) -> dict:
        return {
            "id": str(self.id),
            "email": self.email,
            "role": self.role.value,
            "status": self.status,
            "expires_at": self.expires_at.isoformat(),
            "accepted_at": self.accepted_at.isoformat() if self.accepted_at else None,
            "cancelled_at": self.cancelled_at.isoformat() if self.cancelled_at else None,
            "inviter_id": str(self.inviter_id) if self.inviter_id else None,
            "created_at": self.created_at.isoformat(),
        }

    def __repr__(self) -> str:
        return f"<Invitation org={self.organization_id} email={self.email} status={self.status}>"
