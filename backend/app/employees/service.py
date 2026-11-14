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

from app.authz.permissions import PermissionScope
from app.extensions import db
from app.models import Department, EmployeeProfile, EmployeeStatus, Membership, MembershipRole, MembershipStatus, User


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
