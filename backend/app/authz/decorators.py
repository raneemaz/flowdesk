"""The role/permission gate half of FD-015's RBAC (object-level checks
live in app.authz.service, used both by this decorator and directly by
later resource-specific services/routes).

Must sit *inside* app.auth.decorators.login_required (i.e. run after
it) - it needs g.current_user already populated."""

from functools import wraps

from flask import g

from app.authz.permissions import Permission, PermissionScope, ROLE_PERMISSIONS
from app.authz.service import get_active_membership_or_404
from app.errors import APIError


def require_permission(permission: Permission):
    """Gates a view on the caller having some access to `permission`
    inside the organization named by the view's own `organization_id`
    URL parameter. Every endpoint this guards must declare that URL
    segment (e.g. `/organizations/<uuid:organization_id>/departments`) -
    there is no other source of "which organization" this decorator
    will trust, since a value read from the request body or query
    string could be forged to probe a different organization.

    On success, sets:
    - g.current_membership - the caller's Membership row for this org
    - g.permission_scope - the PermissionScope granted (FULL/LIMITED/
      OWN/ASSIGNED), so the view/service layer can apply the right
      per-record filtering. NONE never reaches the view - it's rejected
      here with a 403 instead.

    A missing or non-active membership (including a genuinely
    cross-tenant request) is rejected with a 404 by
    get_active_membership_or_404, before role is even considered - see
    that function's docstring for why 404 rather than 403.
    """

    def decorator(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            organization_id = kwargs.get("organization_id")
            if organization_id is None:
                raise RuntimeError(
                    "require_permission requires the view to accept an 'organization_id' URL parameter."
                )

            membership = get_active_membership_or_404(g.current_user, organization_id)
            scope = ROLE_PERMISSIONS[membership.role][permission]
            if scope == PermissionScope.NONE:
                raise APIError("You do not have permission to do this.", status_code=403, code="FORBIDDEN")

            g.current_membership = membership
            g.permission_scope = scope
            return view(*args, **kwargs)

        return wrapped

    return decorator
