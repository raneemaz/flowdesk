"""FD-022: the employee directory list endpoint's service layer.

Read-only and membership-centric - lists every *active* Membership in
the organization, not just ones with an EmployeeProfile row. Nothing
in the backlog so far auto-creates an EmployeeProfile when a Membership
is created (FD-020 was model-only; profile management is FD-023), so
requiring one would make every organization's directory empty until
some other, not-yet-built mechanism populates it. job_title/department/
manager/employment-status are simply `None` for a membership with no
profile yet - an honest "not set up", never a fabricated default (e.g.
"active"), which would also make pagination/filtering by `status`
silently wrong (a default applied only in Python, after the DB already
decided which page of rows to return, wouldn't match what was actually
filtered).

Search matches the member's name only, deliberately never their email -
even for a FULL-scope (Owner/Manager) caller. The real reason is scope-
independent: a LIMITED-scope caller (Employee/Accountant/CustomerSupport,
spec Section 7.2 footnote 3) never sees email in the response at all,
but if `search` matched it anyway, `?search=someone@example.com`
returning a hit would still confirm that address exists in the org - an
oracle the response body itself was built specifically to prevent.
"""

import uuid

from sqlalchemy.orm import joinedload

from app.activity.service import log_activity
from app.authz.permissions import PermissionScope
from app.errors import APIError
from app.extensions import db
from app.models import (
    Department,
    DepartmentStatus,
    EmployeeProfile,
    EmployeeStatus,
    Membership,
    MembershipRole,
    MembershipStatus,
    User,
)


def _base_query(
    organization_id: uuid.UUID,
    *,
    search: str | None,
    department_id: uuid.UUID | None,
    role: MembershipRole | None,
    status: EmployeeStatus | None,
):
    query = (
        db.session.query(Membership)
        .join(Membership.user)
        .filter(Membership.organization_id == organization_id, Membership.status == MembershipStatus.ACTIVE)
    )
    if search:
        query = query.filter(User.name.ilike(f"%{search}%"))
    if role is not None:
        query = query.filter(Membership.role == role)
    if department_id is not None or status is not None:
        query = query.outerjoin(EmployeeProfile, Membership.id == EmployeeProfile.membership_id)
        if department_id is not None:
            query = query.filter(EmployeeProfile.department_id == department_id)
        if status is not None:
            query = query.filter(EmployeeProfile.status == status)
    return query


def _resolve_manager_names(organization_id: uuid.UUID, manager_membership_ids: set[uuid.UUID]) -> dict[str, str]:
    """Defensive: only resolves a manager's name when that manager's
    own membership is confirmed to belong to *this* organization.
    EmployeeProfile.manager_membership_id has no cross-org DB or
    service-layer validation yet (FD-020's docstring defers that to a
    future write endpoint, FD-023 - this task is read-only), so without
    this check a cross-org reference set by some future bug would leak
    another organization's member's name into this response instead of
    just showing manager: null."""
    if not manager_membership_ids:
        return {}
    rows = (
        db.session.query(Membership.id, User.name)
        .join(Membership.user)
        .filter(Membership.organization_id == organization_id, Membership.id.in_(manager_membership_ids))
        .all()
    )
    return {str(membership_id): name for membership_id, name in rows}


def _resolve_departments(organization_id: uuid.UUID, department_ids: set[uuid.UUID]) -> dict[str, dict]:
    """Same defense as _resolve_manager_names, for the same reason:
    EmployeeProfile.department_id (FD-020's docstring) has no cross-org
    validation yet either, so a department is only shown once its own
    organization_id is confirmed to match - never trusting the ORM
    relationship traversal (profile.department) directly, which would
    follow the FK wherever it actually points."""
    if not department_ids:
        return {}
    rows = (
        db.session.query(Department.id, Department.name)
        .filter(Department.organization_id == organization_id, Department.id.in_(department_ids))
        .all()
    )
    return {str(department_id): {"id": str(department_id), "name": name} for department_id, name in rows}


def _serialize(
    membership: Membership, scope: PermissionScope, manager_names: dict[str, str], departments: dict[str, dict]
) -> dict:
    user = membership.user
    profile = membership.employee_profile

    base = {
        "membership_id": str(membership.id),
        "name": user.name,
        "role": membership.role.value,
        "status": profile.status.value if profile else None,
    }
    if scope != PermissionScope.FULL:
        return base

    department = None
    if profile and profile.department_id:
        department = departments.get(str(profile.department_id))

    manager = None
    if profile and profile.manager_membership_id:
        manager_name = manager_names.get(str(profile.manager_membership_id))
        if manager_name is not None:
            manager = {"membership_id": str(profile.manager_membership_id), "name": manager_name}

    return {
        **base,
        "email": user.email,
        "job_title": profile.job_title if profile else None,
        "department": department,
        "manager": manager,
        "joined_at": membership.joined_at.isoformat(),
    }


def list_employees(
    organization_id: uuid.UUID,
    *,
    scope: PermissionScope,
    search: str | None,
    department_id: uuid.UUID | None,
    role: MembershipRole | None,
    status: EmployeeStatus | None,
    page: int,
    per_page: int,
) -> tuple[list[dict], int]:
    base_query = _base_query(
        organization_id, search=search, department_id=department_id, role=role, status=status
    )

    total = base_query.count()

    rows = (
        base_query.options(joinedload(Membership.user), joinedload(Membership.employee_profile))
        .order_by(User.name.asc())
        .offset((page - 1) * per_page)
        .limit(per_page)
        .all()
    )

    manager_ids = {
        row.employee_profile.manager_membership_id
        for row in rows
        if row.employee_profile is not None and row.employee_profile.manager_membership_id is not None
    }
    manager_names = _resolve_manager_names(organization_id, manager_ids)

    department_ids = {
        row.employee_profile.department_id
        for row in rows
        if row.employee_profile is not None and row.employee_profile.department_id is not None
    }
    departments = _resolve_departments(organization_id, department_ids)

    employees = [_serialize(row, scope, manager_names, departments) for row in rows]
    return employees, total


def get_target_membership_or_404(organization_id: uuid.UUID, membership_id: uuid.UUID) -> Membership:
    """FD-023: the single place that resolves a *target* employee's
    Membership for both GET (single-profile view) and PATCH (profile/
    status edit). Same 404 convention as app.authz.service's
    get_active_membership_or_404 - missing, cross-organization, and
    inactive are all indistinguishable, never a 403 that would confirm
    the row exists under a different organization."""
    membership = (
        db.session.query(Membership)
        .options(joinedload(Membership.user), joinedload(Membership.employee_profile))
        .filter(
            Membership.id == membership_id,
            Membership.organization_id == organization_id,
            Membership.status == MembershipStatus.ACTIVE,
        )
        .first()
    )
    if membership is None:
        raise APIError("Not found.", status_code=404, code="NOT_FOUND")
    return membership


def get_employee(organization_id: uuid.UUID, membership: Membership, *, scope: PermissionScope) -> dict:
    """Single-record counterpart to list_employees - reuses the exact
    same cross-org-safe _resolve_manager_names/_resolve_departments
    lookups and _serialize scope-filtering, so this path can't drift
    from the directory's own leak prevention (FD-022's
    tenant-security-reviewer finding applies here too)."""
    profile = membership.employee_profile
    manager_ids = {profile.manager_membership_id} if profile and profile.manager_membership_id else set()
    department_ids = {profile.department_id} if profile and profile.department_id else set()
    manager_names = _resolve_manager_names(organization_id, manager_ids)
    departments = _resolve_departments(organization_id, department_ids)
    return _serialize(membership, scope, manager_names, departments)


def _validate_department(organization_id: uuid.UUID, department_id: uuid.UUID | None) -> None:
    """department_id, if given, must resolve to a real, *active*
    Department in this organization - mirrors
    app.departments.service._validate_manager_membership's pattern
    (same deferred-to-the-service-layer gap EmployeeProfile.department_id's
    own docstring names). Requiring `active` (not just "exists in this
    org") blocks a *new* assignment into a deactivated department,
    though deactivating a department afterwards still never un-assigns
    the employees already pointed at it - FR-009/FD-021's "deactivation
    never hides history" is about the past, not about accepting new
    assignments into a department that's no longer in use."""
    if department_id is None:
        return

    department = db.session.query(Department).filter_by(id=department_id, organization_id=organization_id).first()
    if department is None or department.status != DepartmentStatus.ACTIVE:
        raise APIError(
            "department_id must reference an active department in this organization.",
            status_code=422,
            code="INVALID_DEPARTMENT",
            details={"department_id": "must reference an active department in this organization"},
        )


def _validate_manager_membership(
    organization_id: uuid.UUID, manager_membership_id: uuid.UUID | None, *, target_membership_id: uuid.UUID
) -> None:
    """manager_membership_id, if given, must resolve to a real, active
    Membership in this organization, and can't be the employee's own
    membership_id - an employee can't be their own manager."""
    if manager_membership_id is None:
        return

    if manager_membership_id == target_membership_id:
        raise APIError(
            "An employee cannot be their own manager.",
            status_code=422,
            code="INVALID_MANAGER_MEMBERSHIP",
            details={"manager_membership_id": "cannot be the employee's own membership_id"},
        )

    membership = (
        db.session.query(Membership).filter_by(id=manager_membership_id, organization_id=organization_id).first()
    )
    if membership is None or membership.status != MembershipStatus.ACTIVE:
        raise APIError(
            "manager_membership_id must reference an active membership in this organization.",
            status_code=422,
            code="INVALID_MANAGER_MEMBERSHIP",
            details={"manager_membership_id": "must reference an active membership in this organization"},
        )


def _get_or_create_profile(organization_id: uuid.UUID, membership_id: uuid.UUID) -> EmployeeProfile:
    """Nothing else creates an EmployeeProfile row yet (FD-022's own
    module docstring) - this PATCH endpoint is that first write path, so
    it upserts rather than requiring a separate POST a caller would have
    to remember to call first."""
    profile = (
        db.session.query(EmployeeProfile)
        .filter_by(organization_id=organization_id, membership_id=membership_id)
        .first()
    )
    if profile is None:
        profile = EmployeeProfile(organization_id=organization_id, membership_id=membership_id)
        db.session.add(profile)
    return profile


def update_employee_profile(
    organization_id: uuid.UUID, membership_id: uuid.UUID, fields: dict, *, actor_membership_id: uuid.UUID
) -> EmployeeProfile:
    """`fields` is the caller's `UpdateEmployeeProfileRequest.model_dump(exclude_unset=True)`
    - only keys actually present in the request body are applied."""
    if "department_id" in fields:
        _validate_department(organization_id, fields["department_id"])
    if "manager_membership_id" in fields:
        _validate_manager_membership(
            organization_id, fields["manager_membership_id"], target_membership_id=membership_id
        )

    profile = _get_or_create_profile(organization_id, membership_id)
    previous_status = profile.status

    if "job_title" in fields:
        profile.job_title = fields["job_title"]
    if "department_id" in fields:
        profile.department_id = fields["department_id"]
    if "manager_membership_id" in fields:
        profile.manager_membership_id = fields["manager_membership_id"]
    if "status" in fields:
        profile.status = fields["status"]

    # FR-036's "employee deactivated" - only on a genuine transition
    # *into* inactive, not a no-op PATCH that merely re-sends the
    # already-inactive status (same idempotent-logging convention
    # app.tasks.service.update_task_status already established).
    if "status" in fields and profile.status == EmployeeStatus.INACTIVE and previous_status != EmployeeStatus.INACTIVE:
        log_activity(
            organization_id, actor_membership_id, "employee_deactivated", "membership", membership_id, metadata=None
        )

    db.session.commit()
    return profile
