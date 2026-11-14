from flask import Blueprint, g, jsonify, request
from pydantic import ValidationError

from app.auth.decorators import csrf_protect, login_required
from app.authz.decorators import require_permission
from app.authz.permissions import Permission, PermissionScope
from app.authz.service import can_manage_employee_profile
from app.employees.schemas import ListEmployeesQuery, UpdateEmployeeProfileRequest
from app.employees.service import get_employee, get_target_membership_or_404, list_employees, update_employee_profile
from app.errors import APIError, validation_error_details

employees_bp = Blueprint("employees", __name__)


@employees_bp.route("/organizations/<uuid:organization_id>/employees", methods=["GET"])
@login_required
@require_permission(Permission.EMPLOYEE_DIRECTORY_VIEW)
def get_employees(organization_id):
    try:
        query = ListEmployeesQuery.model_validate(request.args.to_dict())
    except ValidationError as exc:
        raise APIError(
            "Validation failed", status_code=422, code="VALIDATION_ERROR", details=validation_error_details(exc)
        )

    employees, total = list_employees(
        organization_id,
        scope=g.permission_scope,
        search=query.search,
        department_id=query.department_id,
        role=query.role,
        status=query.status,
        page=query.page,
        per_page=query.per_page,
    )
    total_pages = (total + query.per_page - 1) // query.per_page if total else 0

    body = {
        "success": True,
        "message": "Employees retrieved",
        "data": employees,
        "meta": {"page": query.page, "per_page": query.per_page, "total": total, "total_pages": total_pages},
    }
    return jsonify(body), 200


@employees_bp.route("/organizations/<uuid:organization_id>/employees/<uuid:membership_id>", methods=["GET"])
@login_required
@require_permission(Permission.EMPLOYEE_DIRECTORY_VIEW)
def get_employee_profile(organization_id, membership_id):
    """FD-023. Reuses the list endpoint's own EMPLOYEE_DIRECTORY_VIEW
    gate (never `none`) rather than a new permission - viewing one
    employee isn't a different capability from viewing many. The one
    difference from the list: a caller viewing their *own* profile
    always gets the `full` field set, regardless of their directory
    scope - this is their own data, so it grants no new access to
    anyone else's."""
    target_membership = get_target_membership_or_404(organization_id, membership_id)

    is_self = target_membership.id == g.current_membership.id
    effective_scope = PermissionScope.FULL if (g.permission_scope == PermissionScope.FULL or is_self) else g.permission_scope

    employee = get_employee(organization_id, target_membership, scope=effective_scope)

    body = {"success": True, "message": "Employee retrieved", "data": employee}
    return jsonify(body), 200


@employees_bp.route("/organizations/<uuid:organization_id>/employees/<uuid:membership_id>", methods=["PATCH"])
@login_required
@csrf_protect
@require_permission(Permission.EMPLOYEE_MANAGE)
def patch_employee_profile(organization_id, membership_id):
    """FD-023. require_permission only confirms the caller's role has
    *some* EMPLOYEE_MANAGE reach (not `none`) - can_manage_employee_profile
    is the object-level check that confirms it reaches *this specific*
    target (e.g. a Manager can't edit an Owner's or another Manager's
    profile)."""
    target_membership = get_target_membership_or_404(organization_id, membership_id)

    if not can_manage_employee_profile(g.current_membership, target_membership):
        raise APIError("You do not have permission to do this.", status_code=403, code="FORBIDDEN")

    payload = request.get_json(silent=True)
    if payload is None:
        raise APIError("Request body must be valid JSON.", status_code=400, code="BAD_REQUEST")

    try:
        data = UpdateEmployeeProfileRequest.model_validate(payload)
    except ValidationError as exc:
        raise APIError(
            "Validation failed", status_code=422, code="VALIDATION_ERROR", details=validation_error_details(exc)
        )

    profile = update_employee_profile(organization_id, membership_id, data.model_dump(exclude_unset=True))

    body = {"success": True, "message": "Employee profile updated", "data": profile.to_public_dict()}
    return jsonify(body), 200
