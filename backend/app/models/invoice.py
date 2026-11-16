import enum
import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import Date, Enum, ForeignKey, ForeignKeyConstraint, Numeric, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship, validates

from app.extensions import db
from app.models.base import TimestampMixin, UUIDPrimaryKeyMixin


class InvoiceStatus(str, enum.Enum):
    """FR-025's six statuses, listed verbatim. Transition enforcement
    itself (which moves are legal, and the "once issued, financial
    details are never silently overwritten" rule - spec's own
    "Important invoice rule") is FD-042's job - this model only defines
    the values the column can hold, the same split Task/TaskStatus
    (FD-025/FD-028) and CustomerRequest/RequestStatus (FD-036/FD-037)
    already established. No separate "voided"/"credited" value and no
    CreditNote entity - Section 35 open decision #7 (void-only vs.
    credit-note corrections) is left to FD-042's editing policy;
    Section 10.1's own entity list names no CreditNote entity for V1,
    and FR-025 already includes `cancelled` as its own terminal value."""

    DRAFT = "draft"
    SENT = "sent"
    PARTIALLY_PAID = "partially_paid"
    PAID = "paid"
    OVERDUE = "overdue"
    CANCELLED = "cancelled"


class Invoice(UUIDPrimaryKeyMixin, TimestampMixin, db.Model):
    """FD-040. Fields per spec Section 10.1's Invoice entity and
    FR-023. Model only, like FD-025/FD-034/FD-036 before it -
    calculations (FD-041), the status lifecycle and controlled editing
    (FD-042), and payments (FD-043) are separate future tasks.

    `currency` - Section 35 open decision #5 (single-currency-per-org
    vs. multi-currency invoices) is NOT resolved here: the column
    exists either way (FR-023 lists it as its own field, mirroring
    `Organization.currency`'s own `String(3)` shape), and which policy
    actually gets *enforced* is a FD-041/FD-042 service-layer concern,
    not a schema one. No default at the model level, unlike
    `Organization.currency` - an invoice is never created directly from
    a bare form the way an organization is; the service layer that
    eventually creates one (FD-041) always supplies a value explicitly
    (e.g. defaulting to the organization's own currency), the same
    "always explicitly supplied" treatment `Task.title` gets.

    `subtotal`/`tax_total`/`discount_total`/`total` default to `0.00`
    (`NOT NULL`, never `NULL` - a money field always has a concrete
    value, per spec Section 10.3 rule #4) rather than being left to the
    caller, since a Draft invoice can legitimately exist with no line
    items yet; FD-041's calculation logic is what keeps these in sync
    with `InvoiceLineItem` rows afterward. The *rounding/computation
    rule itself* (Section 35 open decision #6) is entirely FD-041's
    job - this task only picks `Numeric(12, 2)` as the column's own
    precision/scale, a schema-level judgment call, not the policy
    decision.

    `invoice_number` is unique **per organization** (this task's own
    title), not globally - a composite `UniqueConstraint(organization_id,
    invoice_number)`, mirroring `memberships`'s own org-scoped
    uniqueness pattern (FD-012). No generation scheme is implemented
    here (e.g. "INV-2026-0001") - that belongs to whichever future task
    actually creates invoices.

    `customer_id` and `created_by` are both DB-enforced to the correct
    organization via composite FKs, identical technique and RESTRICT
    reasoning to `CustomerRequest.customer_id`/`creator_membership_id`
    (FD-036) - financial history is explicitly named in spec Section
    10.3 rule #5 ("never cascade-delete financial or audit history
    without an approved retention policy") as needing exactly this
    protection, even more so than a support request.
    """

    __tablename__ = "invoices"
    __table_args__ = (
        UniqueConstraint("id", "organization_id", name="uq_invoices_id_organization_id"),
        UniqueConstraint("organization_id", "invoice_number", name="uq_invoices_organization_id_invoice_number"),
        ForeignKeyConstraint(
            ["created_by", "organization_id"],
            ["memberships.id", "memberships.organization_id"],
            name="fk_invoices_created_by_organization_id",
        ),
        ForeignKeyConstraint(
            ["customer_id", "organization_id"],
            ["customers.id", "customers.organization_id"],
            name="fk_invoices_customer_id_organization_id",
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # NOT NULL, no ORM-column-level FK (the composite ForeignKeyConstraint
    # above covers it) - see the class docstring for why RESTRICT.
    customer_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False, index=True)
    invoice_number: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    status: Mapped[InvoiceStatus] = mapped_column(
        Enum(
            InvoiceStatus,
            name="invoice_status",
            native_enum=True,
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=False,
        default=InvoiceStatus.DRAFT,
        server_default=InvoiceStatus.DRAFT.value,
        index=True,
    )
    # Nullable - a Draft invoice may not have a fixed issue/due date
    # yet (set once it's actually sent, FD-042's job), same treatment
    # Task.start_date/due_date already get.
    issue_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    subtotal: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=Decimal("0.00"), server_default="0.00")
    tax_total: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=Decimal("0.00"), server_default="0.00")
    discount_total: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), nullable=False, default=Decimal("0.00"), server_default="0.00"
    )
    total: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=Decimal("0.00"), server_default="0.00")
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    payment_terms: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # NOT NULL, no ORM-column-level FK (the composite ForeignKeyConstraint
    # above covers it) - who created an invoice is audit-relevant
    # financial history (Section 10.3 rule #5), same RESTRICT reasoning
    # as Task.creator_membership_id.
    created_by: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False, index=True)

    organization = relationship("Organization", back_populates="invoices")
    customer = relationship("Customer", back_populates="invoices", foreign_keys=[customer_id])
    creator = relationship("Membership", foreign_keys=[created_by])
    line_items = relationship(
        "InvoiceLineItem", back_populates="invoice", cascade="all, delete-orphan", passive_deletes=True
    )
    payments = relationship("Payment", back_populates="invoice", cascade="all, delete-orphan", passive_deletes=True)

    @validates("invoice_number")
    def _normalize_invoice_number(self, key, value):
        normalized = (value or "").strip()
        if not normalized:
            raise ValueError("invoice_number must not be empty")
        return normalized

    def to_public_dict(self) -> dict:
        return {
            "id": str(self.id),
            "organization_id": str(self.organization_id),
            "customer_id": str(self.customer_id),
            "invoice_number": self.invoice_number,
            "status": self.status.value,
            "issue_date": self.issue_date.isoformat() if self.issue_date else None,
            "due_date": self.due_date.isoformat() if self.due_date else None,
            "currency": self.currency,
            "subtotal": str(self.subtotal),
            "tax_total": str(self.tax_total),
            "discount_total": str(self.discount_total),
            "total": str(self.total),
            "notes": self.notes,
            "payment_terms": self.payment_terms,
            "created_by": str(self.created_by),
            "created_at": self.created_at.isoformat(),
        }

    def __repr__(self) -> str:
        return f"<Invoice org={self.organization_id} number={self.invoice_number!r} status={self.status.value}>"


class InvoiceLineItem(UUIDPrimaryKeyMixin, TimestampMixin, db.Model):
    """FD-040. Fields per spec Section 10.1's InvoiceLineItem entity and
    FR-024. `quantity`/`unit_price`/`line_total` have no default - a
    line item's whole reason to exist is to carry a priced amount, so
    the service layer that creates one (FD-041) always supplies these
    explicitly (the computed `line_total`, in particular, is never left
    for the DB to infer). `tax_rate` is the one field FR-024 itself
    marks "(opt.)" - nullable, a percentage value (e.g. `8.25` meaning
    8.25%), with the actual tax computation itself deferred to FD-041.
    """

    __tablename__ = "invoice_line_items"
    __table_args__ = (
        # Same dual-FK pattern as RequestComment/RequestHistory (FD-036):
        # organization_id is both directly FK'd to organizations.id
        # below *and* composite-FK'd to invoices.(id, organization_id)
        # here, so two separate ON DELETE CASCADE paths converge safely.
        ForeignKeyConstraint(
            ["invoice_id", "organization_id"],
            ["invoices.id", "invoices.organization_id"],
            name="fk_invoice_line_items_invoice_id_organization_id",
            ondelete="CASCADE",
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    invoice_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False, index=True)
    description: Mapped[str] = mapped_column(String(500), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    tax_rate: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)
    line_total: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)

    invoice = relationship("Invoice", back_populates="line_items", foreign_keys=[invoice_id])

    @validates("description")
    def _normalize_description(self, key, value):
        normalized = (value or "").strip()
        if not normalized:
            raise ValueError("description must not be empty")
        return normalized

    def to_public_dict(self) -> dict:
        return {
            "id": str(self.id),
            "invoice_id": str(self.invoice_id),
            "description": self.description,
            "quantity": str(self.quantity),
            "unit_price": str(self.unit_price),
            "tax_rate": str(self.tax_rate) if self.tax_rate is not None else None,
            "line_total": str(self.line_total),
            "created_at": self.created_at.isoformat(),
        }

    def __repr__(self) -> str:
        return f"<InvoiceLineItem invoice={self.invoice_id} description={self.description!r}>"


class Payment(UUIDPrimaryKeyMixin, TimestampMixin, db.Model):
    """FD-040. Fields per spec Section 10.1's Payment entity and
    FR-026. "Payments are separate records, never edits to the original
    total" (the spec's own "Important invoice rule") - recording and
    validating a payment (amount never exceeding the outstanding
    balance, idempotency) is FD-043's job; this task only defines the
    columns.

    `method` is a plain string, not a closed enum - FR-026 never
    enumerates payment methods anywhere, the same "no implied fixed
    set, and FlowDesk is meant to be generic across industries"
    reasoning `CustomerRequest.category` (FD-036) already used.
    """

    __tablename__ = "payments"
    __table_args__ = (
        # Same dual-FK pattern as InvoiceLineItem above.
        ForeignKeyConstraint(
            ["invoice_id", "organization_id"],
            ["invoices.id", "invoices.organization_id"],
            name="fk_payments_invoice_id_organization_id",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["recorded_by", "organization_id"],
            ["memberships.id", "memberships.organization_id"],
            name="fk_payments_recorded_by_organization_id",
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    invoice_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False, index=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    payment_date: Mapped[date] = mapped_column(Date, nullable=False)
    method: Mapped[str] = mapped_column(String(50), nullable=False)
    reference: Mapped[str | None] = mapped_column(String(255), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    # NOT NULL, no ORM-column-level FK (the composite ForeignKeyConstraint
    # above covers it) - who recorded a payment is audit-relevant
    # financial history (Section 10.3 rule #5), same RESTRICT reasoning
    # as Invoice.created_by.
    recorded_by: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False, index=True)

    invoice = relationship("Invoice", back_populates="payments", foreign_keys=[invoice_id])
    recorder = relationship("Membership", foreign_keys=[recorded_by])

    @validates("method")
    def _normalize_method(self, key, value):
        normalized = (value or "").strip()
        if not normalized:
            raise ValueError("method must not be empty")
        return normalized

    def to_public_dict(self) -> dict:
        return {
            "id": str(self.id),
            "invoice_id": str(self.invoice_id),
            "amount": str(self.amount),
            "payment_date": self.payment_date.isoformat(),
            "method": self.method,
            "reference": self.reference,
            "notes": self.notes,
            "recorded_by": str(self.recorded_by),
            "created_at": self.created_at.isoformat(),
        }

    def __repr__(self) -> str:
        return f"<Payment invoice={self.invoice_id} amount={self.amount}>"
