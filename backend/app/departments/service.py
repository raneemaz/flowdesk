import uuid

from app.errors import APIError
from app.extensions import db
from app.models import Department, DepartmentStatus, Membership, MembershipStatus


def _validate_manager_membership(organization_id: uuid.UUID, manager_membership_id: uuid.UUID | None) -> None:
    """manager_membership_id, if given, must resolve to a real, ACTIVE
    membership in *this* organization. This is exactly the check
    Department.manager_membership_id's own docstring (FD-019) named as
    deferred to "a future service layer" - the model's composite-FK
    approach (used for EmployeeProfile.membership_id, FD-020) isn't
    available here because it would need ON DELETE SET NULL, which
    conflicts with organization_id staying required (see that
    docstring). This is where that gap actually gets closed."""
    if manager_membership_id is None:
        return

    membership = (
        db.session.query(Membership)
        .filter_by(id=manager_membership_id, organization_id=organization_id)
        .first()
    )
    if membership is None or membership.status != MembershipStatus.ACTIVE:
        raise APIError(
            "manager_membership_id must reference an active membership in this organization.",
            status_code=422,
            code="INVALID_MANAGER_MEMBERSHIP",
            details={"manager_membership_id": "must reference an active membership in this organization"},
        )


def _set_name(department: Department, name: str) -> None:
    # Department.name's own @validates strips and rejects a blank
    # result (e.g. a whitespace-only string, which passes pydantic's
    # min_length=1 but not this) - converted to a 422 here rather than
    # letting the bare ValueError escape as an unhandled 500.
    try:
        department.name = name
    except ValueError as exc:
        raise APIError(str(exc), status_code=422, code="VALIDATION_ERROR", details={"name": str(exc)})


def create_department(
    organization_id: uuid.UUID,
    *,
    name: str,
    description: str | None,
    manager_membership_id: uuid.UUID | None,
) -> Department:
    _validate_manager_membership(organization_id, manager_membership_id)

    department = Department(organization_id=organization_id, description=description)
    _set_name(department, name)
    department.manager_membership_id = manager_membership_id

    db.session.add(department)
    db.session.commit()
    return department


def list_departments(organization_id: uuid.UUID) -> list[Department]:
    # Every status included (active and inactive) - deactivation never
    # hides history, same convention as membership/invitation listing.
    return (
        db.session.query(Department).filter_by(organization_id=organization_id).order_by(Department.name.asc()).all()
    )


def get_department_or_404(organization_id: uuid.UUID, department_id: uuid.UUID) -> Department:
    department = db.session.query(Department).filter_by(id=department_id, organization_id=organization_id).first()
    if department is None:
        raise APIError("Not found.", status_code=404, code="NOT_FOUND")
    return department


def update_department(organization_id: uuid.UUID, department_id: uuid.UUID, fields: dict) -> Department:
    """`fields` is the caller's `UpdateDepartmentRequest.model_dump(exclude_unset=True)`
    - only keys actually present in the request body are applied."""
    department = get_department_or_404(organization_id, department_id)

    if "manager_membership_id" in fields:
        _validate_manager_membership(organization_id, fields["manager_membership_id"])

    if "name" in fields:
        _set_name(department, fields["name"])
    if "description" in fields:
        department.description = fields["description"]
    if "manager_membership_id" in fields:
        department.manager_membership_id = fields["manager_membership_id"]
    if "status" in fields:
        department.status = fields["status"]

    db.session.commit()
    return department


def deactivate_department(organization_id: uuid.UUID, department_id: uuid.UUID) -> Department:
    """The DELETE endpoint's action - soft, never a real row delete
    (spec Section 10.3 rule #5, and this task's own "safe-deletion
    policy" wording): sets status to inactive so the department (and
    every historical EmployeeProfile.department_id reference to it)
    survives. Idempotent - deactivating an already-inactive department
    is a no-op success, not an error, matching DELETE's own idempotent
    semantics."""
    department = get_department_or_404(organization_id, department_id)
    if department.status != DepartmentStatus.INACTIVE:
        department.status = DepartmentStatus.INACTIVE
        db.session.commit()
    return department
