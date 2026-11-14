import enum
import uuid

from sqlalchemy import Enum, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship, validates

from app.extensions import db
from app.models.base import TimestampMixin, UUIDPrimaryKeyMixin


class DepartmentStatus(str, enum.Enum):
    """Judgment call (not in Section 35): mirrors the two-state
    active/inactive pattern FD-021's own task description uses
    ("deactivate") rather than User/Membership's three-state
    active/inactive/suspended - there's no "suspended department"
    concept anywhere in the spec."""

    ACTIVE = "active"
    INACTIVE = "inactive"


class Department(UUIDPrimaryKeyMixin, TimestampMixin, db.Model):
    """FD-019. Fields per spec Section 10.1's Department entity
    (id, organization_id, name, description, manager, status).

    manager_membership_id intentionally has no ORM relationship()
    attribute, no uniqueness constraint on name, and - unlike
    organization_id - no DB-level guarantee that the referenced
    membership belongs to *this* department's organization (a cross-
    table invariant a plain FK can't express without also letting that
    FK's ON DELETE action null out organization_id, which must stay
    required). Spec Section 10.3 rule #2 ("validated in application
    logic and enforced with foreign keys/constraints") is satisfied by
    both halves together: the FK's referential integrity here, same-
    organization validation in FD-021's service layer (which doesn't
    exist yet - this task is the model only), mirroring how
    Invitation.inviter_id (FD-016) is a loose historical reference with
    no relationship() of its own.
    """

    __tablename__ = "departments"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Nullable: FR-008 lists "assign ... managers" as its own action,
    # separate from "create" - a department can exist before one is
    # assigned. SET NULL (not CASCADE/RESTRICT), same reasoning as
    # Invitation.inviter_id: a department is organization history and
    # must outlive a manager's membership row if that's ever hard-
    # deleted (no such endpoint exists yet, but the schema shouldn't
    # assume one never will - and CASCADE here would delete the whole
    # department just because its manager left, which FR-008's "assign
    # managers" implies is just a field update, not a structural one).
    manager_membership_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("memberships.id", ondelete="SET NULL"), nullable=True, index=True
    )
    status: Mapped[DepartmentStatus] = mapped_column(
        Enum(
            DepartmentStatus,
            name="department_status",
            native_enum=True,
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=False,
        default=DepartmentStatus.ACTIVE,
        server_default=DepartmentStatus.ACTIVE.value,
    )

    organization = relationship("Organization", back_populates="departments")
    # No cascade/passive_deletes here, unlike Organization.departments -
    # deleting a department must not delete its employees' profiles, it
    # only clears their department_id (FD-020's FK is ON DELETE SET
    # NULL). This relationship is read-only browsing convenience.
    employee_profiles = relationship("EmployeeProfile", back_populates="department")

    @validates("name")
    def _normalize_name(self, key, value):
        normalized = (value or "").strip()
        if not normalized:
            raise ValueError("name must not be empty")
        return normalized

    def to_public_dict(self) -> dict:
        return {
            "id": str(self.id),
            "organization_id": str(self.organization_id),
            "name": self.name,
            "description": self.description,
            "manager_membership_id": str(self.manager_membership_id) if self.manager_membership_id else None,
            "status": self.status.value,
            "created_at": self.created_at.isoformat(),
        }

    def __repr__(self) -> str:
        return f"<Department org={self.organization_id} name={self.name!r} status={self.status.value}>"
