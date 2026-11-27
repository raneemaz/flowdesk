import enum
import uuid
from datetime import date, datetime, timezone, timedelta

from sqlalchemy import Date, DateTime, Enum, ForeignKey, ForeignKeyConstraint, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship, validates

from app.extensions import db
from app.models.base import TimestampMixin, UUIDPrimaryKeyMixin



# Clock difference between created_at and updated_at that still counts as
# "never edited" (both are set in the same insert).
_EDIT_GRACE = timedelta(seconds=1)

class RequestStatus(str, enum.Enum):
    """FR-019's workflow: New -> Assigned -> In Progress -> Waiting for
    Customer -> Resolved -> Closed. Transition enforcement itself (which
    moves are legal from which status) is FD-037's job - this model
    only defines the six values the column can hold, the same split
    Task/TaskStatus (FD-025/FD-028) already established."""

    NEW = "new"
    ASSIGNED = "assigned"
    IN_PROGRESS = "in_progress"
    WAITING_FOR_CUSTOMER = "waiting_for_customer"
    RESOLVED = "resolved"
    CLOSED = "closed"


class RequestPriority(str, enum.Enum):
    """Judgment call (not in Section 35), same reasoning as
    Task/TaskPriority (FD-025): FR-018 just says "priority" with no
    values enumerated anywhere in the spec. Kept as its own enum
    (`request_priority`, not a reuse of `task_priority`) even though
    the four values are identical - this codebase's own convention is
    one enum type per model, the same way CustomerStatus (FD-034) is
    distinct from DepartmentStatus despite both being simple two-value
    status columns."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    URGENT = "urgent"


class CustomerRequest(UUIDPrimaryKeyMixin, TimestampMixin, db.Model):
    """FD-036. Fields per spec Section 10.1's CustomerRequest entity
    (id, organization_id, customer_id, title, description, category,
    status, priority, assignee, creator, due date, resolution notes)
    and FR-018. Model only, like FD-025 (Task) before it -
    workflow enforcement, assignment, and comments/history recording
    are FD-037/FD-038, separate future tasks.

    No `department_id` - unlike Task, FR-018 never lists a department
    field for a request, so none is added here (not every field Task
    happens to have belongs on every org-scoped entity).

    `category` is a plain nullable string, not an enum - unlike
    priority/status, the spec never even implies a fixed set (FR-018
    just says "category"), and FlowDesk is explicitly meant to be
    generic across industries (Section 1), so hardcoding e.g.
    "billing"/"technical" would bake in one business's taxonomy as
    everyone's default. Indexed anyway, alongside status/priority/
    due_date - a filterable facet, not free-form prose like
    title/description/resolution_notes (which aren't).
    """

    __tablename__ = "customer_requests"
    __table_args__ = (
        # Lets RequestComment/RequestHistory DB-enforce their own
        # organization_id against *this* request's, the same technique
        # Task (FD-025) established for TaskComment/TaskHistory.
        UniqueConstraint("id", "organization_id", name="uq_customer_requests_id_organization_id"),
        # Composite, mirroring Task.creator_membership_id's own FK
        # exactly (FD-025): creator_membership_id is NOT NULL, so
        # RESTRICT (no ON DELETE clause given) never needs to null out
        # organization_id. Who created a request is audit-relevant
        # history (spec Section 10.3 rule #5) and must never silently
        # disappear or drag the request down with it.
        ForeignKeyConstraint(
            ["creator_membership_id", "organization_id"],
            ["memberships.id", "memberships.organization_id"],
            # Shortened from the "..._memberships" suffix the analogous
            # Task/EmployeeProfile constraints use (FD-020/FD-025) -
            # "customer_requests" alone already pushes this past
            # Postgres's 63-byte identifier limit; the referenced table
            # is still obvious from the FK's own target columns.
            name="fk_customer_requests_creator_membership_id_organization_id",
        ),
        # Composite, same technique: customer_id is NOT NULL (every
        # request belongs to exactly one customer - the entire point of
        # this entity), so RESTRICT is the only sound choice - CASCADE
        # would silently delete request history the moment a customer
        # row was removed (spec Section 10.3 rule #5's "never
        # cascade-delete... audit history"), and SET NULL isn't
        # possible for a NOT NULL column (nor would "no customer" make
        # sense for a *customer* request). In practice a `customers`
        # row is never hard-deleted by this app (FD-035's DELETE only
        # archives it), so this mostly guards a hypothetical direct
        # deletion, not a real flow - but Section 26's own acceptance
        # criterion ("archived customers stay linked to historical
        # requests") is exactly what this constraint protects.
        ForeignKeyConstraint(
            ["customer_id", "organization_id"],
            ["customers.id", "customers.organization_id"],
            name="fk_customer_requests_customer_id_organization_id_customers",
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # NOT NULL, no ORM-column-level FK (the composite ForeignKeyConstraint
    # above covers it) - see its own comment for why RESTRICT.
    customer_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    category: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    status: Mapped[RequestStatus] = mapped_column(
        Enum(
            RequestStatus,
            name="request_status",
            native_enum=True,
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=False,
        default=RequestStatus.NEW,
        server_default=RequestStatus.NEW.value,
        index=True,
    )
    priority: Mapped[RequestPriority] = mapped_column(
        Enum(
            RequestPriority,
            name="request_priority",
            native_enum=True,
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=False,
        default=RequestPriority.MEDIUM,
        server_default=RequestPriority.MEDIUM.value,
        index=True,
    )
    # NOT NULL, no ORM-column-level FK (the composite ForeignKeyConstraint
    # above covers it) - same reasoning as Task.creator_membership_id.
    creator_membership_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False, index=True)
    # Nullable + SET NULL, simple (non-composite) FK, no relationship() -
    # identical reasoning to Task.assignee_membership_id (FD-025): a
    # request can exist unassigned (FR-020's "assignment" is its own
    # action, FD-037's job), reassigning/unassigning must only clear
    # this field, and same-organization validation for it is deferred
    # to that future service layer rather than DB-enforced here.
    assignee_membership_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("memberships.id", ondelete="SET NULL"), nullable=True, index=True
    )
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    resolution_notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    organization = relationship("Organization", back_populates="customer_requests")
    customer = relationship("Customer", back_populates="requests", foreign_keys=[customer_id])
    creator = relationship("Membership", foreign_keys=[creator_membership_id])
    comments = relationship(
        "RequestComment", back_populates="request", cascade="all, delete-orphan", passive_deletes=True
    )
    history = relationship(
        "RequestHistory",
        back_populates="request",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="RequestHistory.created_at",
    )

    @validates("title")
    def _normalize_title(self, key, value):
        normalized = (value or "").strip()
        if not normalized:
            raise ValueError("title must not be empty")
        return normalized

    def to_public_dict(self) -> dict:
        return {
            "id": str(self.id),
            "organization_id": str(self.organization_id),
            "customer_id": str(self.customer_id),
            "title": self.title,
            "description": self.description,
            "category": self.category,
            "status": self.status.value,
            "priority": self.priority.value,
            "creator_membership_id": str(self.creator_membership_id),
            "assignee_membership_id": str(self.assignee_membership_id) if self.assignee_membership_id else None,
            "due_date": self.due_date.isoformat() if self.due_date else None,
            "resolution_notes": self.resolution_notes,
            "created_at": self.created_at.isoformat(),
        }

    def __repr__(self) -> str:
        return f"<CustomerRequest org={self.organization_id} title={self.title!r} status={self.status.value}>"


class RequestComment(UUIDPrimaryKeyMixin, TimestampMixin, db.Model):
    """FD-036. Fields per spec Section 10.1's RequestComment entity
    ("linked to request; actor, event_type, timestamps" - read together
    with FR-021, this is the same id/request_id/author_id/body/
    created_at shape TaskComment (FD-025) already has). Access
    restriction ("internal comments never customer-exposed") is
    FD-038's job, not this model-only task - there's no customer-portal
    concept anywhere in this backlog for a comment to ever be exposed
    *to* in the first place, so every comment here is implicitly
    internal; no `is_internal` column is needed to distinguish a kind
    that doesn't exist yet.
    """

    __tablename__ = "request_comments"
    __table_args__ = (
        # Same dual-FK pattern as TaskComment (FD-025): organization_id
        # is both directly FK'd to organizations.id below *and*
        # composite-FK'd to customer_requests.(id, organization_id)
        # here, so two separate ON DELETE CASCADE paths converge on
        # this table safely together.
        ForeignKeyConstraint(
            ["request_id", "organization_id"],
            ["customer_requests.id", "customer_requests.organization_id"],
            # Shortened, same reasoning as CustomerRequest's own
            # creator_membership_id constraint above - the full
            # "..._customer_requests" suffix exceeds Postgres's 63-byte
            # identifier limit once combined with this table's own
            # ("request_comments") name.
            name="fk_request_comments_request_id_organization_id",
            ondelete="CASCADE",
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    request_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False, index=True)
    # Nullable + SET NULL, simple FK, no relationship() - a comment is
    # history and must outlive its author's membership row, same
    # reasoning as TaskComment.author_membership_id.
    author_membership_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("memberships.id", ondelete="SET NULL"), nullable=True, index=True
    )
    body: Mapped[str] = mapped_column(Text, nullable=False)

    request = relationship("CustomerRequest", back_populates="comments", foreign_keys=[request_id])

    @validates("body")
    def _normalize_body(self, key, value):
        normalized = (value or "").strip()
        if not normalized:
            raise ValueError("body must not be empty")
        return normalized

    def to_public_dict(self) -> dict:
        return {
            "id": str(self.id),
            "request_id": str(self.request_id),
            "author_membership_id": str(self.author_membership_id) if self.author_membership_id else None,
            "body": self.body,
            "created_at": self.created_at.isoformat(),
            # Set only once the body has been edited (comments change no
            # other way); a fresh comment's updated_at equals created_at.
            "edited_at": self.updated_at.isoformat() if self.updated_at - self.created_at > _EDIT_GRACE else None,
        }

    def __repr__(self) -> str:
        return f"<RequestComment request={self.request_id} author={self.author_membership_id}>"


class RequestHistory(UUIDPrimaryKeyMixin, db.Model):
    """FD-036. Fields per spec Section 10.1's RequestHistory entity,
    the same shape as TaskHistory (FD-025). Deliberately does NOT use
    TimestampMixin - "append-only" (FR-021's "history" wording) implies
    no `updated_at` the same way TaskHistory's own docstring already
    argues; `created_at` is declared directly instead.

    `event_type` is a plain String, not a closed Enum - FD-037/FD-038
    (workflow, assignment, and history recording itself) haven't been
    built yet and are what will actually define the set of events this
    column holds; inventing that taxonomy now, in a model-only task,
    risks guessing wrong. Same reasoning for previous_value/new_value
    being free-form Text rather than typed columns.
    """

    __tablename__ = "request_histories"
    __table_args__ = (
        # Same dual-FK/composite-FK pattern as RequestComment above.
        ForeignKeyConstraint(
            ["request_id", "organization_id"],
            ["customer_requests.id", "customer_requests.organization_id"],
            # Shortened, same reasoning as RequestComment's own
            # constraint above.
            name="fk_request_histories_request_id_organization_id",
            ondelete="CASCADE",
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    request_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False, index=True)
    # Nullable + SET NULL, simple FK, no relationship() - same
    # reasoning as RequestComment.author_membership_id: a history entry
    # is audit trail and must outlive the actor's membership row.
    actor_membership_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("memberships.id", ondelete="SET NULL"), nullable=True, index=True
    )
    event_type: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    previous_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    new_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )

    request = relationship("CustomerRequest", back_populates="history", foreign_keys=[request_id])

    def to_public_dict(self) -> dict:
        return {
            "id": str(self.id),
            "request_id": str(self.request_id),
            "actor_membership_id": str(self.actor_membership_id) if self.actor_membership_id else None,
            "event_type": self.event_type,
            "previous_value": self.previous_value,
            "new_value": self.new_value,
            "created_at": self.created_at.isoformat(),
        }

    def __repr__(self) -> str:
        return f"<RequestHistory request={self.request_id} event={self.event_type!r}>"
