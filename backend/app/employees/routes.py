from flask import Blueprint, g, jsonify, request
from pydantic import ValidationError

from app.auth.decorators import login_required
from app.authz.decorators import require_permission
from app.authz.permissions import Permission
from app.employees.schemas import ListEmployeesQuery
from app.employees.service import list_employees
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
