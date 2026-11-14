"""Object-level RBAC checks (FD-015) - the "object-level checks" half of
the backlog line, complementing the role/permission gate in
app.authz.decorators. These are what stop a user from gaining access by
changing an ID in a URL, body, or query string (spec Section 7.3)."""

import uuid

from app.authz.permissions import Permission, PermissionScope, ROLE_PERMISSIONS
from app.errors import APIError
from app.extensions import db
from app.models import Membership, MembershipRole, MembershipStatus, User


def get_active_membership_or_404(user: User, organization_id: uuid.UUID) -> Membership:
    """The single place that answers "is this user currently a member of
    this organization?". A missing membership and a non-active one are
    deliberately indistinguishable to the caller - both return 404,
    never 403, matching the project's documented convention that
    cross-tenant/inaccessible records never confirm their own existence
    (docs/API.md). This also means an organization a user *used to*
    belong to behaves exactly like one they never did, once removed or
    deactivated - no information about history leaks through this
    check.
    """
    try:
        organization_id = uuid.UUID(str(organization_id))
    except (ValueError, AttributeError, TypeError):
        # A malformed organization_id can never be a real membership's
        # key - treat it exactly like "no membership found" rather than
        # letting it reach the DB as a bad filter value (which would
        # raise and surface as an undifferentiated 500, not this
        # function's intended, uniform 404). Keeps every "doesn't
        # resolve to an active membership" case - missing, cross-tenant,
        # inactive, or malformed - identical to the caller.
        raise APIError("Not found.", status_code=404, code="NOT_FOUND")

    membership = db.session.query(Membership).filter_by(organization_id=organization_id, user_id=user.id).first()
    if membership is None or membership.status != MembershipStatus.ACTIVE:
        raise APIError("Not found.", status_code=404, code="NOT_FOUND")
    return membership


def check_scope_allows(
    scope: PermissionScope,
    *,
    caller_id: uuid.UUID,
    owner_id: uuid.UUID | None = None,
    assignee_id: uuid.UUID | None = None,
) -> bool:
    """Whether a granted scope covers one specific record.

    FULL/LIMITED are gate-level grants the calling route/service must
    still apply its own field- or query-level restriction for - this
    function only encodes the *reach* a scope has over records, not
    which fields a LIMITED scope may see (that's resource-specific and
    decided when that resource is built). NONE never legitimately
    reaches here - app.authz.decorators.require_permission already
    rejects NONE with a 403 before any view runs, so a NONE scope
    arriving here indicates a bug in the caller, not a real
    authorization case.
    """
    if scope == PermissionScope.NONE:
        return False
    if scope in (PermissionScope.FULL, PermissionScope.LIMITED):
        return True
    if scope == PermissionScope.OWN:
        return owner_id is not None and owner_id == caller_id
    if scope == PermissionScope.ASSIGNED:
        return assignee_id is not None and assignee_id == caller_id
    raise ValueError(f"Unhandled PermissionScope: {scope!r}")  # pragma: no cover


# The set of roles a Manager's LIMITED MEMBERSHIP_MANAGE scope reaches -
# shared between can_assign_role (changing an existing member's role)
# and can_invite_with_role (FD-016: inviting a new member with a role).
_MANAGER_ASSIGNABLE_ROLES = {MembershipRole.EMPLOYEE, MembershipRole.ACCOUNTANT, MembershipRole.CUSTOMER_SUPPORT}


def can_invite_with_role(actor_membership: Membership, role: MembershipRole) -> bool:
    """Whether `actor_membership`'s role may send an invitation for
    `role` (FD-016). Governed by the same MEMBERSHIP_MANAGE scope as
    can_assign_role, applied to the role being offered rather than an
    existing target membership:
    - FULL (Owner): may invite any role.
    - LIMITED (Manager, "as granted"): may only invite
      Employee/Accountant/CustomerSupport - can never invite a new
      Owner or Manager.
    - NONE: may never invite anyone.
    """
    scope = ROLE_PERMISSIONS[actor_membership.role][Permission.MEMBERSHIP_MANAGE]
    if scope == PermissionScope.FULL:
        return True
    if scope == PermissionScope.LIMITED:
        return role in _MANAGER_ASSIGNABLE_ROLES
    return False


def can_assign_role(actor_membership: Membership, target_membership: Membership, new_role: MembershipRole) -> bool:
    """Section 13's mandatory security scenario ("Employee tries to
    change their own role -> 403") generalizes to every role here: no
    one may change their own role, no matter how much
    membership-management power they otherwise have - self-escalation
    (or a self-demotion that could leave an organization ownerless) is
    never allowed through this path.

    Beyond that, reach is governed by MEMBERSHIP_MANAGE's scope for the
    actor's role (see app.authz.permissions.ROLE_PERMISSIONS):
    - FULL (Owner): may assign any role to any other member.
    - LIMITED (Manager, "as granted"): may only act on a target whose
      *current* role is Employee/Accountant/CustomerSupport, and may
      only assign a *new* role from that same set - can never touch, or
      create, an Owner or another Manager.
    - NONE: may never change anyone's role.

    Defends itself against a cross-tenant mix-up rather than trusting
    the caller to have already matched both memberships to the same
    organization (found by tenant-security-reviewer during FD-015's own
    review: a route that fetches the actor correctly from the URL's
    organization_id but the target by a bare membership_id from the
    request body - an easy mistake - would otherwise let a Manager in
    one org silently change a member's role in a *different* org, since
    nothing here previously checked that both memberships even belong
    to the same organization).
    """
    if target_membership.organization_id != actor_membership.organization_id:
        return False
    if target_membership.user_id == actor_membership.user_id:
        return False

    scope = ROLE_PERMISSIONS[actor_membership.role][Permission.MEMBERSHIP_MANAGE]
    if scope == PermissionScope.FULL:
        return True
    if scope == PermissionScope.LIMITED:
        return target_membership.role in _MANAGER_ASSIGNABLE_ROLES and new_role in _MANAGER_ASSIGNABLE_ROLES
    return False
