"""Organization settings: the organization's own profile and its members'
roles/access - the backend half of the Settings page.

Reach rules reuse what app/authz already defines rather than inventing
new ones: ORGANIZATION_SETTINGS_MANAGE's scopes for the profile, and
can_assign_role for every member change.
"""

import uuid
from zoneinfo import available_timezones

from sqlalchemy.orm import joinedload

from app.activity.service import log_activity
from app.authz.permissions import PermissionScope
from app.authz.service import can_assign_role
from app.errors import APIError
from app.extensions import db
from app.models import Membership, MembershipRole, MembershipStatus, Organization

# What a Manager's LIMITED ORGANIZATION_SETTINGS_MANAGE scope may change
# (app/authz/permissions.py's own comment on that scope). Name, currency
# and timezone are identity/financial-impacting, so Owner-only.
MANAGER_EDITABLE_FIELDS = {"logo", "email", "phone", "address", "date_format"}
# NOT NULL columns: an explicit null for these is a validation error.
_REQUIRED_FIELDS = {"name", "currency", "timezone"}


def _validation_error(details: dict) -> APIError:
    return APIError("Validation failed", status_code=422, code="VALIDATION_ERROR", details=details)


def update_organization(actor_membership: Membership, scope: PermissionScope, fields: dict) -> Organization:
    if scope == PermissionScope.LIMITED:
        forbidden = sorted(set(fields) - MANAGER_EDITABLE_FIELDS)
        if forbidden:
            raise APIError(
                "Only the owner can change the organization's name, currency or timezone.",
                status_code=403,
                code="FORBIDDEN",
                details={field: "Owner only." for field in forbidden},
            )

    missing = sorted(field for field in _REQUIRED_FIELDS if field in fields and fields[field] is None)
    if missing:
        raise _validation_error({field: "This field is required." for field in missing})
    if fields.get("timezone") is not None and fields["timezone"] not in available_timezones():
        raise _validation_error({"timezone": "Unknown timezone."})
    if fields.get("currency") is not None and not fields["currency"].isalpha():
        raise _validation_error({"currency": "Use a 3-letter currency code, such as USD."})

    organization = actor_membership.organization
    changed = []
    for field, value in fields.items():
        before = getattr(organization, field)
        setattr(organization, field, value)  # model validators normalize (e.g. currency upper-case)
        if getattr(organization, field) != before:
            changed.append(field)
    if changed:
        log_activity(
            organization.id,
            actor_membership.id,
            "organization_updated",
            "organization",
            organization.id,
            metadata={"fields": sorted(changed)},
        )
    db.session.commit()
    return organization


def list_members(organization_id: uuid.UUID) -> list[Membership]:
    """Every membership - removed ones included, so they can be restored -
    active before removed, owners first, then by join date."""
    memberships = (
        db.session.query(Membership)
        .options(joinedload(Membership.user))
        .filter(Membership.organization_id == organization_id)
        .order_by(Membership.joined_at.asc())
        .all()
    )
    return sorted(memberships, key=lambda m: (m.status != MembershipStatus.ACTIVE, m.role != MembershipRole.OWNER))


def serialize_member(membership: Membership) -> dict:
    return {
        "membership_id": str(membership.id),
        "user_id": str(membership.user_id),
        "name": membership.user.name,
        "email": membership.user.email,
        "role": membership.role.value,
        "status": membership.status.value,
        "joined_at": membership.joined_at.isoformat(),
    }


def update_member(
    actor_membership: Membership,
    membership_id: uuid.UUID,
    role: MembershipRole | None,
    status: MembershipStatus | None,
) -> Membership:
    """Role changes and access removal/restoration share one reach rule,
    can_assign_role: never yourself; a Manager only among Employee/
    Accountant/Customer Support. Removing access sets the membership
    inactive (get_active_membership_or_404 then refuses every request
    they make in this organization) - nothing they created is deleted,
    and it can be restored. The organization always keeps at least one
    active Owner."""
    if role is None and status is None:
        raise _validation_error({"role": "Send a role, a status, or both."})

    target = (
        db.session.query(Membership)
        .filter_by(id=membership_id, organization_id=actor_membership.organization_id)
        .first()
    )
    if target is None:
        raise APIError("Not found.", status_code=404, code="NOT_FOUND")

    new_role = role if role is not None else target.role
    if not can_assign_role(actor_membership, target, new_role):
        raise APIError("You can't change this member's role or access.", status_code=403, code="FORBIDDEN")

    new_status = status if status is not None else target.status
    loses_active_owner = (
        target.role == MembershipRole.OWNER
        and target.status == MembershipStatus.ACTIVE
        and (new_role != MembershipRole.OWNER or new_status != MembershipStatus.ACTIVE)
    )
    if loses_active_owner:
        other_active_owners = (
            db.session.query(Membership)
            .filter(
                Membership.organization_id == target.organization_id,
                Membership.role == MembershipRole.OWNER,
                Membership.status == MembershipStatus.ACTIVE,
                Membership.id != target.id,
            )
            .count()
        )
        if other_active_owners == 0:
            raise APIError("The organization must keep at least one active owner.", status_code=409, code="LAST_OWNER")

    if new_role != target.role:
        log_activity(
            target.organization_id,
            actor_membership.id,
            "member_role_changed",
            "membership",
            target.id,
            metadata={"from": target.role.value, "to": new_role.value},
        )
        target.role = new_role
    if new_status != target.status:
        log_activity(
            target.organization_id,
            actor_membership.id,
            "member_access_restored" if new_status == MembershipStatus.ACTIVE else "member_access_removed",
            "membership",
            target.id,
            metadata={"status": new_status.value},
        )
        target.status = new_status
    db.session.commit()
    return target
