import enum
import uuid

from sqlalchemy import Enum, ForeignKey, ForeignKeyConstraint, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.extensions import db
from app.models.base import TimestampMixin, UUIDPrimaryKeyMixin


class EmployeeStatus(str, enum.Enum):
    """FR-009 lists Active/Inactive/Invited/Suspended, but "Invited" is
    handled the same way MembershipStatus (FD-012) already resolved the
    identical tension: an EmployeeProfile requires a real membership_id,
    and nothing is "invited" yet at the point a Membership (and
    therefore an EmployeeProfile) exists - that state lives entirely on
    the separate Invitation entity (FD-016), with no corresponding row
    here. Only the other three apply to an actual EmployeeProfile row."""

    ACTIVE = "active"
    INACTIVE = "inactive"
    SUSPENDED = "suspended"


class EmployeeProfile(UUIDPrimaryKeyMixin, TimestampMixin, db.Model):
    """FD-020. Fields per spec Section 10.1's EmployeeProfile entity
    (id, organization_id, membership_id, department_id, job_title,
    employment status), plus manager_membership_id - the task's own
    title ("linked to membership, department, manager") names a
    distinct per-employee "reports to" reference, separate from (though
    often equal to) their department's own manager_membership_id
    (Department, FD-019): FR-006 lists "manager" as its own employee-
    directory column alongside "department", implying an employee's
    manager isn't always strictly derived from whoever heads their
    department.

    `status` here is deliberately independent of Membership.status: the
    membership field governs org access (can this person log in at
    all - app/authz), this one governs current employment (can this
    person be newly assigned work - FD-023's "deactivation doesn't
    break history"). They usually move together but aren't the same
    concept, and the spec lists "employment status" as EmployeeProfile's
    own column, not a reuse of Membership's.

    No `photo` field: Section 10.1's field list for this entity doesn't
    include one, and the spec's generic Attachment entity ("metadata
    for uploaded files, linked to its entity") is the documented home
    for file-backed data like an avatar - adding an ad hoc URL column
    here would duplicate that future mechanism.
    """

    __tablename__ = "employee_profiles"
    __table_args__ = (
        UniqueConstraint("membership_id", name="uq_employee_profiles_membership_id"),
        # Composite FK (not just FK(membership_id) alone): this is the
        # one place in FD-019/FD-020 where a composite FK is actually
        # safe - CASCADE (not SET NULL) is the right action here, since
        # an EmployeeProfile has no identity independent of its
        # Membership, and CASCADE never needs to null out a NOT NULL
        # column the way SET NULL would. This DB-enforces "this profile's
        # organization_id always equals its membership's organization_id"
        # directly, which Department.manager_membership_id (FD-019)
        # couldn't do for the SET NULL fields below without conflicting
        # with organization_id staying required (see that model's
        # docstring) - department_id and manager_membership_id still
        # can't be composite-FK'd for that same reason, so same-org
        # validation for *those* two stays deferred to FD-022/FD-023's
        # future service layer, exactly like Department.manager_membership_id.
        ForeignKeyConstraint(
            ["membership_id", "organization_id"],
            ["memberships.id", "memberships.organization_id"],
            name="fk_employee_profiles_membership_id_organization_id_memberships",
            ondelete="CASCADE",
        ),
    )

    # Also directly FK'd to organizations.id (ON DELETE CASCADE), like
    # every other org-scoped table in this codebase, in addition to
    # participating in the composite FK below - a column can belong to
    # more than one FK constraint, and this keeps organization_id's own
    # referential integrity independent of the membership_id path.
    organization_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    membership_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False, index=True)
    # Simple (non-composite) FK, SET NULL: see the class docstring and
    # Department.manager_membership_id (FD-019) for why same-organization
    # validation for this column is deferred to a future service layer
    # rather than DB-enforced here.
    department_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("departments.id", ondelete="SET NULL"), nullable=True, index=True
    )
    manager_membership_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("memberships.id", ondelete="SET NULL"), nullable=True, index=True
    )
    job_title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[EmployeeStatus] = mapped_column(
        Enum(
            EmployeeStatus,
            name="employee_status",
            native_enum=True,
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=False,
        default=EmployeeStatus.ACTIVE,
        server_default=EmployeeStatus.ACTIVE.value,
    )

    organization = relationship("Organization", back_populates="employee_profiles")
    membership = relationship("Membership", back_populates="employee_profile", foreign_keys=[membership_id])
    department = relationship("Department", back_populates="employee_profiles")

    def to_public_dict(self) -> dict:
        return {
            "id": str(self.id),
            "organization_id": str(self.organization_id),
            "membership_id": str(self.membership_id),
            "department_id": str(self.department_id) if self.department_id else None,
            "manager_membership_id": str(self.manager_membership_id) if self.manager_membership_id else None,
            "job_title": self.job_title,
            "status": self.status.value,
            "created_at": self.created_at.isoformat(),
        }

    def __repr__(self) -> str:
        return f"<EmployeeProfile org={self.organization_id} membership={self.membership_id} status={self.status.value}>"
