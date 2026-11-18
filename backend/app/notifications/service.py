"""FD-048: notification infrastructure - a shared service other domain
modules will call (FR-038), plus its own read/mark-read side (FR-039).

`create_notification` is deliberately **not called anywhere yet** -
this task is infrastructure only. FR-038's actual trigger list (task
assigned, deadline approaching/overdue, comment added, request
assigned/status changed, invoice paid, invitation received) is
FD-049's job to wire in, once it can depend on this module existing.

Unlike `app.activity.service.list_activity`, there is no role/scope
parameter here - see `app.models.notification.Notification`'s own
docstring for why: Section 7.2's baseline permission matrix has no
notification row at all, so access is purely ownership-based (the
caller's own `recipient_membership_id`), never role-filtered.
"""

import uuid
from datetime import datetime, timezone

from app.errors import APIError
from app.extensions import db
from app.models import Notification


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
