"""FD-047: centralized activity logging - a shared service other
domain modules call (FR-036), plus its own read side (FR-037:
"immutable through the normal application interface" - there is no
corresponding write endpoint; every row is written as a side effect
of the business action it describes).

`log_activity` is wired into the specific trigger points FR-036 names:
employee invited (`app.invitations.service.create_invitation`), task
created/assigned/completed (`app.tasks.service.create_task`/
`assign_task`/`update_task_status`), request created/resolved
(`app.customer_requests.service.create_request`/`update_request_status`),
invoice created (`app.invoices.service.create_invoice`), payment
recorded (`app.payments.service.record_payment`), and employee
deactivated (`app.employees.service.update_employee_profile`).

**One named event - "role-changed" - is deliberately NOT wired**,
because it has no trigger point to hook into: no task in this backlog
has ever built a "change an existing member's role" feature
(`app.authz.service.can_assign_role` exists, defined ahead of that
future feature at FD-015 time per that module's own docstring, but
nothing calls it). This is an honest scope gap, not a guess - adding a
whole new membership-role-change feature just to have something to
log would be scope creep well beyond "implement centralized activity
logging."

Every call site is responsible for passing only safe, descriptive
`metadata` (a title, an amount, a status, an id) - never a password,
raw token, or full request body. See `app.models.activity.ActivityLog`'s
own docstring for why this is a calling discipline, not a runtime-
enforced filter.
"""

import uuid

from app.extensions import db
from app.models import ActivityLog, MembershipRole
from app.authz.permissions import PermissionScope

# ACTIVITY_HISTORY_VIEW's own per-role reach, already finalized at
# FD-015 time (app/authz/permissions.py's own comments): Owner/Manager
# get `full` (no filter); Employee gets `own` (only entries they
# themselves are the actor of); Accountant and CustomerSupport both
# get `limited`, but with two *different* meanings - "activity entries
# tied to invoices/payments/financial records only" vs. "...tied to
# customers/requests only" - so `limited` alone (just the resolved
# PermissionScope) isn't enough to know which filter applies; the
# caller's actual role disambiguates it.
_FINANCIAL_ENTITY_TYPES = ("invoice", "payment")
_CUSTOMER_ENTITY_TYPES = ("customer", "customer_request")


def log_activity(
    organization_id: uuid.UUID,
    actor_membership_id: uuid.UUID | None,
    action: str,
    entity_type: str,
    entity_id: uuid.UUID,
    metadata: dict | None = None,
) -> ActivityLog:
    """Adds an `ActivityLog` row to the session - does **not** commit.
    Every call site adds this alongside the business change it
    describes and commits both together in one transaction (NFR-006's
    "financial operations use database transactions" extended here to
    audit consistency too: a crash between the business write and its
    log entry must never leave one without the other)."""
    entry = ActivityLog(
        organization_id=organization_id,
        actor_membership_id=actor_membership_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        metadata_=metadata,
    )
    db.session.add(entry)
    return entry


def list_activity(
    organization_id: uuid.UUID,
    *,
    scope: PermissionScope,
    caller_role: MembershipRole,
    caller_membership_id: uuid.UUID,
    page: int,
    per_page: int,
) -> tuple[list[ActivityLog], int]:
    """`scope` is `g.permission_scope` (already resolved by
    `require_permission`); `caller_role` disambiguates `limited`'s two
    different meanings - see this module's own docstring above."""
    query = db.session.query(ActivityLog).filter(ActivityLog.organization_id == organization_id)

    if scope == PermissionScope.OWN:
        query = query.filter(ActivityLog.actor_membership_id == caller_membership_id)
    elif scope == PermissionScope.LIMITED:
        if caller_role == MembershipRole.ACCOUNTANT:
            query = query.filter(ActivityLog.entity_type.in_(_FINANCIAL_ENTITY_TYPES))
        elif caller_role == MembershipRole.CUSTOMER_SUPPORT:
            query = query.filter(ActivityLog.entity_type.in_(_CUSTOMER_ENTITY_TYPES))
        else:
            # No other role is ever granted `limited` for this
            # permission today (app/authz/permissions.py) - matches
            # nothing rather than guessing, so a future role added
            # here without updating this function fails closed (an
            # empty result), not open (everything).
            query = query.filter(False)
    # `full` (Owner/Manager): no filter - every entry in the org.

    total = query.count()
    entries = query.order_by(ActivityLog.created_at.desc()).offset((page - 1) * per_page).limit(per_page).all()
    return entries, total
