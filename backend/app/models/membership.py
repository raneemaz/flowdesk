import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, Enum, ForeignKey, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.extensions import db
from app.models.base import TimestampMixin, UUIDPrimaryKeyMixin


class MembershipRole(str, enum.Enum):
    """Section 7.1's five roles."""

    OWNER = "owner"
    MANAGER = "manager"
    EMPLOYEE = "employee"
    ACCOUNTANT = "accountant"
    CUSTOMER_SUPPORT = "customer_support"


class MembershipStatus(str, enum.Enum):
    """Judgment call (not in Section 35): a Membership row represents an
    already-accepted relationship to an organization, so it doesn't need
    an 'invited' state - that lives on the separate Invitation entity
    (FD-016), not yet built. Mirrors User.status (FD-008) for
    consistency: active/inactive/suspended."""

    ACTIVE = "active"
    INACTIVE = "inactive"
    SUSPENDED = "suspended"


class Membership(UUIDPrimaryKeyMixin, TimestampMixin, db.Model):
    __tablename__ = "memberships"
    __table_args__ = (UniqueConstraint("organization_id", "user_id", name="uq_memberships_organization_id_user_id"),)

    organization_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    role: Mapped[MembershipRole] = mapped_column(
        Enum(
            MembershipRole,
            name="membership_role",
            native_enum=True,
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=False,
    )
    status: Mapped[MembershipStatus] = mapped_column(
        Enum(
            MembershipStatus,
            name="membership_status",
            native_enum=True,
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=False,
        default=MembershipStatus.ACTIVE,
    )
    joined_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )

    organization = relationship("Organization", back_populates="memberships")
    user = relationship("User", back_populates="memberships")

    def __repr__(self) -> str:
        return f"<Membership org={self.organization_id} user={self.user_id} role={self.role.value}>"
