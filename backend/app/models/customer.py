import enum
import uuid

from sqlalchemy import Enum, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship, validates

from app.extensions import db
from app.models.base import TimestampMixin, UUIDPrimaryKeyMixin


class CustomerStatus(str, enum.Enum):
    """Judgment call (not in Section 35): mirrors Department's own
    two-state active/inactive pattern (FD-019), but named to match this
    task's own vocabulary - Section 26's acceptance criterion and
    FD-035's task title both say "archive", never "deactivate"."""

    ACTIVE = "active"
    ARCHIVED = "archived"


class Customer(UUIDPrimaryKeyMixin, TimestampMixin, db.Model):
    """FD-034. Fields per spec Section 10.1's Customer entity (id,
    organization_id, name, email, phone, company, address, notes,
    status) and FR-017 ("name, email, phone, company (opt.), address
    (opt.), notes, created date").

    Required-vs-optional (not in Section 35, a plain schema judgment
    call like TaskPriority's own four-level scheme): FR-017 marks only
    `company` and `address` "(opt.)", but a small business's real-world
    customer records routinely have only a phone number, or only an
    email, on file - there's no login/identity concept riding on this
    data the way there is for `User.email`. Only `name` is required and
    non-blank-validated, the same bar every other named entity in this
    codebase holds (`User.name`, `Department.name`, `Task.title`); the
    rest are nullable with no uniqueness constraint (a shared household/
    business email or phone across two customer records is plausible
    and not this model's problem to prevent).

    `status` (active/archived) exists now, even though archiving itself
    is FD-035's job, for the same reason `Department.status` and
    `EmployeeProfile.status` were added by their own model-only tasks -
    Section 26's own acceptance criterion ("archived customers stay
    linked to historical requests/invoices") requires the column to
    exist before FD-036's CustomerRequest/Invoice can reference it.

    `UniqueConstraint("id", "organization_id", ...)`: the same forward-
    looking composite key `Task` (FD-025) and `EmployeeProfile`
    (FD-020) each established before *their* first org-scoped child
    table existed - FD-036 (CustomerRequest) will need to compose a
    same-organization-enforcing FK against this pair exactly the way
    `TaskComment`/`TaskHistory` do against `Task`.

    No `attachments` column, same documented gap as `Task` (FD-025) -
    Section 10.1's separate `Attachment` entity is the intended home,
    and no backlog task builds it yet.
    """

    __tablename__ = "customers"
    __table_args__ = (UniqueConstraint("id", "organization_id", name="uq_customers_id_organization_id"),)

    organization_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    # Same length as User.email (FD-008) for consistency, though this
    # column carries no uniqueness/login semantics of its own.
    email: Mapped[str | None] = mapped_column(String(320), nullable=True, index=True)
    phone: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)
    company: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    # Text, not indexed - free-form fields FD-035's search isn't
    # expected to target, same treatment as Organization.address and
    # Department.description elsewhere in this codebase.
    address: Mapped[str | None] = mapped_column(Text, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[CustomerStatus] = mapped_column(
        Enum(
            CustomerStatus,
            name="customer_status",
            native_enum=True,
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=False,
        default=CustomerStatus.ACTIVE,
        server_default=CustomerStatus.ACTIVE.value,
    )

    organization = relationship("Organization", back_populates="customers")
    # No cascade/passive_deletes here, unlike Organization.customers -
    # a customers row is never hard-deleted by this app (only archived,
    # FD-035), and CustomerRequest.customer_id's own composite FK is
    # RESTRICT (see that model's docstring), so this stays a read-only
    # browsing convenience, the same style Department.employee_profiles
    # (FD-019) already established.
    requests = relationship("CustomerRequest", back_populates="customer", foreign_keys="CustomerRequest.customer_id")
    # Same reasoning as `requests` above - Invoice.customer_id's own
    # composite FK is RESTRICT (see that model's docstring), so this
    # too stays a read-only browsing convenience, never a cascade path.
    invoices = relationship("Invoice", back_populates="customer", foreign_keys="Invoice.customer_id")

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
            "email": self.email,
            "phone": self.phone,
            "company": self.company,
            "address": self.address,
            "notes": self.notes,
            "status": self.status.value,
            "created_at": self.created_at.isoformat(),
        }

    def __repr__(self) -> str:
        return f"<Customer org={self.organization_id} name={self.name!r} status={self.status.value}>"
