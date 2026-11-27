import enum
import uuid
from datetime import date, datetime, timezone, timedelta
from decimal import Decimal

from sqlalchemy import Date, DateTime, Enum, ForeignKey, ForeignKeyConstraint, Numeric, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship, validates

from app.extensions import db
from app.models.base import TimestampMixin, UUIDPrimaryKeyMixin



# Clock difference between created_at and updated_at that still counts as
# "never edited" (both are set in the same insert).
_EDIT_GRACE = timedelta(seconds=1)

class TaskStatus(str, enum.Enum):
    """FR-012's workflow: To Do -> In Progress -> Under Review ->
    Completed, with Cancelled as a terminal state reachable from any
    non-terminal status. Transition enforcement itself (which moves are
    legal from which status) is FD-028's job - this model only defines
    the five values the column can hold."""

    TODO = "to_do"
    IN_PROGRESS = "in_progress"
    UNDER_REVIEW = "under_review"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class TaskPriority(str, enum.Enum):
    """Judgment call (not in Section 35): FR-010/FR-014 just say
    "priority" with no values enumerated anywhere in the spec. Low/
    Medium/High/Urgent is the conventional four-level scheme mainstream
    task trackers (Jira, Linear, Asana) use - distinct from this
    *backlog's own* P0-P3 task-priority column (spec Section 20), an
    unrelated concept that happens to share the word "priority"."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    URGENT = "urgent"


class Task(UUIDPrimaryKeyMixin, TimestampMixin, db.Model):
    """FD-025. Fields per spec Section 10.1's Task entity (id,
    organization_id, title, description, status, priority, creator,
    assignee, department, start/due date, est./actual hours). No
    `attachments` column - Section 10.1's separate Attachment entity
    ("metadata for uploaded files, linked to its entity") is its
    documented home, and no backlog task builds that entity yet; an ad
    hoc column here would duplicate a mechanism this project hasn't
    committed to the shape of yet. Model only, like FD-019/FD-020
    before it - creation/retrieval, assignment, status workflow,
    editing, comments, and history are FD-026 through FD-031, not this
    task.
    """

    __tablename__ = "tasks"
    __table_args__ = (
        # Lets TaskComment/TaskHistory DB-enforce their own
        # organization_id against *this* task's, the same technique
        # memberships.uq_memberships_id_organization_id (FD-020)
        # established for EmployeeProfile.
        UniqueConstraint("id", "organization_id", name="uq_tasks_id_organization_id"),
        # Safe to make composite (no ON DELETE clause given, so it
        # defaults to RESTRICT, never SET NULL): creator_membership_id
        # is NOT NULL, and RESTRICT never needs to null out
        # organization_id the way a SET NULL composite FK would, so
        # there's no conflict with organization_id staying required.
        # This is the one task reference that gets genuine DB-enforced
        # same-organization integrity, unlike assignee_membership_id/
        # department_id below - see their own comments for why those
        # two can't use this technique.
        ForeignKeyConstraint(
            ["creator_membership_id", "organization_id"],
            ["memberships.id", "memberships.organization_id"],
            name="fk_tasks_creator_membership_id_organization_id_memberships",
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[TaskStatus] = mapped_column(
        Enum(
            TaskStatus,
            name="task_status",
            native_enum=True,
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=False,
        default=TaskStatus.TODO,
        server_default=TaskStatus.TODO.value,
        index=True,
    )
    priority: Mapped[TaskPriority] = mapped_column(
        Enum(
            TaskPriority,
            name="task_priority",
            native_enum=True,
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=False,
        default=TaskPriority.MEDIUM,
        server_default=TaskPriority.MEDIUM.value,
        index=True,
    )
    # NOT NULL, no ORM-column-level FK (the composite ForeignKeyConstraint
    # above covers it) - who created a task is audit-relevant history
    # (spec Section 10.3 rule #5) and must never silently disappear or
    # drag the task down with it.
    creator_membership_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False, index=True)
    # Nullable + SET NULL: FR-011 treats "assign" as its own action
    # separate from creation (a task can exist unassigned), and
    # reassigning/unassigning must only clear this field, never cascade
    # into deleting the task. Simple (non-composite) FK - same
    # SET-NULL-conflicts-with-required-organization_id reasoning as
    # Department.manager_membership_id (FD-019) and
    # EmployeeProfile.manager_membership_id (FD-020); same-organization
    # validation is deferred to a future service layer (FD-026/FD-027).
    # No ORM relationship() attribute either, for the same reason those
    # two don't have one - don't trust the ORM traversal for a
    # reference the DB can't itself guarantee is same-organization (the
    # lesson FD-022's tenant-security-reviewer finding already taught
    # this codebase once).
    assignee_membership_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("memberships.id", ondelete="SET NULL"), nullable=True, index=True
    )
    # Nullable + SET NULL, simple FK, no relationship() - identical
    # reasoning to assignee_membership_id above, mirroring
    # EmployeeProfile.department_id (FD-020) exactly.
    department_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("departments.id", ondelete="SET NULL"), nullable=True, index=True
    )
    start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    # Numeric, not Float (spec Section 10.3 rule #4, applied here too
    # even though hours aren't money - exact fractional hours, e.g.
    # 2.5, without binary-float rounding drift once these get summed
    # for analytics later). Up to 9999.99 hours.
    estimated_hours: Mapped[Decimal | None] = mapped_column(Numeric(6, 2), nullable=True)
    actual_hours: Mapped[Decimal | None] = mapped_column(Numeric(6, 2), nullable=True)

    organization = relationship("Organization", back_populates="tasks")
    creator = relationship("Membership", foreign_keys=[creator_membership_id])
    comments = relationship("TaskComment", back_populates="task", cascade="all, delete-orphan", passive_deletes=True)
    history = relationship(
        "TaskHistory",
        back_populates="task",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="TaskHistory.created_at",
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
            "title": self.title,
            "description": self.description,
            "status": self.status.value,
            "priority": self.priority.value,
            "creator_membership_id": str(self.creator_membership_id),
            "assignee_membership_id": str(self.assignee_membership_id) if self.assignee_membership_id else None,
            "department_id": str(self.department_id) if self.department_id else None,
            "start_date": self.start_date.isoformat() if self.start_date else None,
            "due_date": self.due_date.isoformat() if self.due_date else None,
            "estimated_hours": str(self.estimated_hours) if self.estimated_hours is not None else None,
            "actual_hours": str(self.actual_hours) if self.actual_hours is not None else None,
            "created_at": self.created_at.isoformat(),
        }

    def __repr__(self) -> str:
        return f"<Task org={self.organization_id} title={self.title!r} status={self.status.value}>"


class TaskComment(UUIDPrimaryKeyMixin, TimestampMixin, db.Model):
    """FD-025. Fields per spec Section 10.1's TaskComment entity (id,
    task_id, author_id, body, created_at) - access control and
    attachment support are FD-030's job (comments), not this
    model-only task.
    """

    __tablename__ = "task_comments"
    __table_args__ = (
        # Dual-FK pattern, mirroring EmployeeProfile.organization_id
        # (FD-020) exactly: organization_id is both directly FK'd to
        # organizations.id below *and* composite-FK'd to tasks.(id,
        # organization_id) here, so two separate ON DELETE CASCADE
        # paths converge on this table (organizations -> task_comments
        # directly, and organizations -> tasks -> task_comments) - both
        # safe together, same reasoning EmployeeProfile's docstring
        # already covers.
        ForeignKeyConstraint(
            ["task_id", "organization_id"],
            ["tasks.id", "tasks.organization_id"],
            name="fk_task_comments_task_id_organization_id_tasks",
            ondelete="CASCADE",
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    task_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False, index=True)
    # Nullable + SET NULL, simple FK, no relationship() - a comment is
    # organization/task history and must outlive its author's
    # membership row if that's ever hard-deleted, same reasoning as
    # Invitation.inviter_id (FD-016) and Department.manager_membership_id
    # (FD-019).
    author_membership_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("memberships.id", ondelete="SET NULL"), nullable=True, index=True
    )
    body: Mapped[str] = mapped_column(Text, nullable=False)

    task = relationship("Task", back_populates="comments", foreign_keys=[task_id])

    @validates("body")
    def _normalize_body(self, key, value):
        normalized = (value or "").strip()
        if not normalized:
            raise ValueError("body must not be empty")
        return normalized

    def to_public_dict(self) -> dict:
        return {
            "id": str(self.id),
            "task_id": str(self.task_id),
            "author_membership_id": str(self.author_membership_id) if self.author_membership_id else None,
            "body": self.body,
            "created_at": self.created_at.isoformat(),
            # Set only once the body has been edited (comments change no
            # other way); a fresh comment's updated_at equals created_at.
            "edited_at": self.updated_at.isoformat() if self.updated_at - self.created_at > _EDIT_GRACE else None,
        }

    def __repr__(self) -> str:
        return f"<TaskComment task={self.task_id} author={self.author_membership_id}>"


class TaskHistory(UUIDPrimaryKeyMixin, db.Model):
    """FD-025. Fields per spec Section 10.1's TaskHistory entity (id,
    task_id, actor_id, event_type, previous_value, new_value,
    created_at). Deliberately does NOT use TimestampMixin - FD-031's
    own task title calls this "chronological, append-only": an
    `updated_at` column would imply history rows can be edited after
    the fact, which defeats the point of an audit trail. `created_at`
    is declared directly instead, the same inline style
    Membership.joined_at (FD-012) already uses for a single immutable
    timestamp.

    `event_type` is a plain String, not a closed Enum - FD-027/FD-028/
    FD-029/FD-031 (assignment, status workflow, editing, and history
    recording itself) haven't been built yet and are what will actually
    define the set of events this column holds (e.g. "status_changed",
    "reassigned", "priority_changed"); inventing that taxonomy now, in
    a model-only task, risks guessing wrong and needing an enum
    migration later. Same reasoning for previous_value/new_value being
    free-form Text rather than typed columns - different event types
    will need different shapes of "what changed", determined when those
    future tasks actually define what they record.
    """

    __tablename__ = "task_histories"
    __table_args__ = (
        # Same dual-FK/composite-FK pattern as TaskComment above.
        ForeignKeyConstraint(
            ["task_id", "organization_id"],
            ["tasks.id", "tasks.organization_id"],
            name="fk_task_histories_task_id_organization_id_tasks",
            ondelete="CASCADE",
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    task_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False, index=True)
    # Nullable + SET NULL, simple FK, no relationship() - same
    # reasoning as TaskComment.author_membership_id: a history entry is
    # audit trail and must outlive the actor's membership row.
    actor_membership_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("memberships.id", ondelete="SET NULL"), nullable=True, index=True
    )
    event_type: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    previous_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    new_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )

    task = relationship("Task", back_populates="history", foreign_keys=[task_id])

    def to_public_dict(self) -> dict:
        return {
            "id": str(self.id),
            "task_id": str(self.task_id),
            "actor_membership_id": str(self.actor_membership_id) if self.actor_membership_id else None,
            "event_type": self.event_type,
            "previous_value": self.previous_value,
            "new_value": self.new_value,
            "created_at": self.created_at.isoformat(),
        }

    def __repr__(self) -> str:
        return f"<TaskHistory task={self.task_id} event={self.event_type!r}>"
