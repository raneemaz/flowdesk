"""FD-048/FD-049: notification infrastructure (FR-038/FR-039) plus
FD-049's actual event wiring.

`create_notification`/`create_notifications_for_roles` are called from
the specific trigger points FR-038 names: task assigned
(`app.tasks.service.assign_task`), task/request comment added
(`app.tasks.service.create_task_comment`/
`app.customer_requests.service.create_request_comment`), request
assigned/status changed (`app.customer_requests.service.assign_request`/
`update_request_status`), and invoice paid
(`app.payments.service.record_payment`, fanned out to every active
Owner/Accountant - FR-038's own "(authorized users)", matching
`INVOICE_PAYMENT_MANAGE`/`FINANCIAL_REPORTS_VIEW`'s existing
Owner+Accountant-only grant).

**Two named triggers are deliberately NOT wired**, each a structural
gap rather than a guess:
- **"invitation received"** - `Notification.recipient_membership_id`
  is required (FD-048), but an invitee has no `Membership` row at all
  until they accept - there is no valid recipient to attach this
  notification to yet. FR-039's own "in-app first; email is a later
  extension" wording already has a fallback here anyway: FD-016's
  `create_invitation` already sends a best-effort email.
- **"deadline approaching/overdue"** - this is a *time-based* trigger,
  not an *event-based* one (this task's own title), and no scheduled-
  job infrastructure exists anywhere in this codebase yet - Section 14
  introduces Celery+Redis only once FD-059 actually needs it, far
  later in the backlog, and FD-049's own dependency list names no
  scheduler task. Building one now would be scope creep well beyond
  "event-based notifications."

**"No duplicate delivery"** (this task's own acceptance criterion) is
satisfied by never creating a notification unless the call site's own
already-established idempotency/no-op guard says a real change
happened: `assign_task`/`assign_request`'s existing "same assignee is
a no-op" check, `update_request_status`'s existing "same status is a
no-op" check, and `record_payment`'s existing idempotent-replay path
(the notification call sits right alongside `log_activity`'s own call,
inside the same `try` block, before the one commit - never reached on
a replay). A trigger also never notifies the actor about their own
action (self-notification is skipped at every call site).

Unlike `app.activity.service.list_activity`, there is no role/scope
parameter on the read side - see `app.models.notification.Notification`'s
own docstring for why: Section 7.2's baseline permission matrix has no
notification row at all, so access is purely ownership-based (the
caller's own `recipient_membership_id`), never role-filtered.
"""

import uuid
from datetime import datetime, timezone

from app.errors import APIError
from app.extensions import db
from app.models import Membership, MembershipRole, MembershipStatus, Notification


def create_notification(
    organization_id: uuid.UUID,
    recipient_membership_id: uuid.UUID,
    notification_type: str,
    title: str,
    body: str,
    entity_type: str,
    entity_id: uuid.UUID,
) -> Notification:
    """Adds a `Notification` row to the session - does **not** commit.
    Mirrors `app.activity.service.log_activity`'s own convention: the
    future caller (FD-049) adds this alongside the business change it
    describes and commits both together in one transaction, so a crash
    between the two can never leave one without the other."""
    notification = Notification(
        organization_id=organization_id,
        recipient_membership_id=recipient_membership_id,
        type=notification_type,
        title=title,
        body=body,
        entity_type=entity_type,
        entity_id=entity_id,
    )
    db.session.add(notification)
    return notification


def create_notifications_for_roles(
    organization_id: uuid.UUID,
    roles: tuple,
    notification_type: str,
    title: str,
    body: str,
    entity_type: str,
    entity_id: uuid.UUID,
    *,
    exclude_membership_id: uuid.UUID | None = None,
) -> list[Notification]:
    """Fans a single event out to every active membership in
    `organization_id` holding any of `roles` - FR-038's "invoice paid
    (authorized users)" is the one trigger with more than one
    recipient. `exclude_membership_id` skips the actor (e.g. an
    Accountant recording their own payment doesn't get notified about
    it). Adds every row to the session - does **not** commit, same
    convention as `create_notification`."""
    memberships = (
        db.session.query(Membership)
        .filter(
            Membership.organization_id == organization_id,
            Membership.status == MembershipStatus.ACTIVE,
            Membership.role.in_(roles),
        )
        .all()
    )
    return [
        create_notification(organization_id, membership.id, notification_type, title, body, entity_type, entity_id)
        for membership in memberships
        if membership.id != exclude_membership_id
    ]


def list_notifications(
    organization_id: uuid.UUID,
    recipient_membership_id: uuid.UUID,
    *,
    unread_only: bool,
    page: int,
    per_page: int,
) -> tuple[list[Notification], int]:
    """Always scoped to the caller's own `recipient_membership_id` -
    there is no role/scope that ever widens this to other members'
    notifications, not even Owner/Manager (no admin override exists in
    the spec for this entity)."""
    query = db.session.query(Notification).filter_by(
        organization_id=organization_id, recipient_membership_id=recipient_membership_id
    )
    if unread_only:
        query = query.filter(Notification.read_at.is_(None))

    total = query.count()
    entries = query.order_by(Notification.created_at.desc()).offset((page - 1) * per_page).limit(per_page).all()
    return entries, total


def _get_own_notification_or_404(
    organization_id: uuid.UUID, recipient_membership_id: uuid.UUID, notification_id: uuid.UUID
) -> Notification:
    """A notification that exists but belongs to a different recipient
    is 404, not 403 - same "never confirm existence of something the
    caller has zero reach over" convention as every other cross-tenant
    case in this codebase (docs/API.md), extended here to cross-recipient
    too, since nobody (not even Owner/Manager) has reach over another
    member's own notifications."""
    notification = (
        db.session.query(Notification)
        .filter_by(id=notification_id, organization_id=organization_id, recipient_membership_id=recipient_membership_id)
        .first()
    )
    if notification is None:
        raise APIError("Not found.", status_code=404, code="NOT_FOUND")
    return notification


def mark_notification_read(
    organization_id: uuid.UUID, recipient_membership_id: uuid.UUID, notification_id: uuid.UUID
) -> Notification:
    """Idempotent: marking an already-read notification read again is a
    no-op (no redundant `updated_at` bump), same convention
    `app.tasks.service.assign_task`/`update_task_status` already
    established for "requesting the state something already has"."""
    notification = _get_own_notification_or_404(organization_id, recipient_membership_id, notification_id)
    if notification.read_at is None:
        notification.read_at = datetime.now(timezone.utc)
        db.session.commit()
    return notification


def mark_all_notifications_read(organization_id: uuid.UUID, recipient_membership_id: uuid.UUID) -> int:
    """Bulk UPDATE (not a Python loop over rows) - same convention
    `app.invoices.service._refresh_overdue_invoices` (FD-042) already
    established for "flip a flag on every matching row in one
    statement". Returns the number of rows actually flipped (0 if
    everything was already read)."""
    updated_count = (
        db.session.query(Notification)
        .filter(
            Notification.organization_id == organization_id,
            Notification.recipient_membership_id == recipient_membership_id,
            Notification.read_at.is_(None),
        )
        .update({"read_at": datetime.now(timezone.utc)}, synchronize_session=False)
    )
    db.session.commit()
    return updated_count
