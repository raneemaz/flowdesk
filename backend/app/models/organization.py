from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship, validates

from app.extensions import db
from app.models.base import TimestampMixin, UUIDPrimaryKeyMixin


class Organization(UUIDPrimaryKeyMixin, TimestampMixin, db.Model):
    """A business workspace. Required-field policy per Section 35 open
    decision #1: name and slug are always required; currency and
    timezone are required but default to USD/UTC so creation is never
    blocked by them; everything else is optional and fillable later in
    settings (logo, contact info, date format)."""

    __tablename__ = "organizations"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    # Auto-generation from name (with collision handling) is FD-013's
    # job (business logic for creating an org) - this model only
    # enforces the column's own data-integrity invariants: normalized
    # format and uniqueness.
    slug: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    logo: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    address: Mapped[str | None] = mapped_column(Text, nullable=True)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="USD", server_default="USD")
    timezone: Mapped[str] = mapped_column(String(64), nullable=False, default="UTC", server_default="UTC")
    date_format: Mapped[str | None] = mapped_column(String(32), nullable=True)

    # passive_deletes=True: let the DB's ON DELETE CASCADE (migration)
    # handle removing memberships when an org is deleted, instead of
    # SQLAlchemy loading every child row first just to delete it one by
    # one. cascade="all, delete-orphan" still applies for explicit
    # in-session manipulation (e.g. removing an item from the list).
    memberships = relationship(
        "Membership", back_populates="organization", cascade="all, delete-orphan", passive_deletes=True
    )
    invitations = relationship(
        "Invitation", back_populates="organization", cascade="all, delete-orphan", passive_deletes=True
    )
    departments = relationship(
        "Department", back_populates="organization", cascade="all, delete-orphan", passive_deletes=True
    )
    employee_profiles = relationship(
        "EmployeeProfile", back_populates="organization", cascade="all, delete-orphan", passive_deletes=True
    )
    tasks = relationship("Task", back_populates="organization", cascade="all, delete-orphan", passive_deletes=True)
    customers = relationship(
        "Customer", back_populates="organization", cascade="all, delete-orphan", passive_deletes=True
    )
    customer_requests = relationship(
        "CustomerRequest", back_populates="organization", cascade="all, delete-orphan", passive_deletes=True
    )
    invoices = relationship(
        "Invoice", back_populates="organization", cascade="all, delete-orphan", passive_deletes=True
    )

    @validates("name")
    def _normalize_name(self, key, value):
        normalized = (value or "").strip()
        if not normalized:
            raise ValueError("name must not be empty")
        return normalized

    @validates("slug")
    def _normalize_slug(self, key, value):
        normalized = (value or "").strip().lower()
        if not normalized:
            raise ValueError("slug must not be empty")
        if not all(c.isalnum() or c == "-" for c in normalized):
            raise ValueError("slug may only contain lowercase letters, digits, and hyphens")
        return normalized

    @validates("currency")
    def _normalize_currency(self, key, value):
        normalized = (value or "").strip().upper()
        if len(normalized) != 3:
            raise ValueError("currency must be a 3-letter ISO 4217 code")
        return normalized

    def to_public_dict(self) -> dict:
        return {
            "id": str(self.id),
            "name": self.name,
            "slug": self.slug,
            "logo": self.logo,
            "email": self.email,
            "phone": self.phone,
            "address": self.address,
            "currency": self.currency,
            "timezone": self.timezone,
            "date_format": self.date_format,
            "created_at": self.created_at.isoformat(),
        }

    def __repr__(self) -> str:
        return f"<Organization {self.slug}>"
