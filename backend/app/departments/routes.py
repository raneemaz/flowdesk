from flask import Blueprint, jsonify, request
from pydantic import ValidationError

from app.auth.decorators import csrf_protect, login_required
from app.authz.decorators import require_permission
from app.authz.permissions import Permission
from app.departments.schemas import CreateDepartmentRequest, UpdateDepartmentRequest
from app.departments.service import (
    create_department,
    deactivate_department,
    list_departments,
    update_department,
)
from app.errors import APIError, validation_error_details

departments_bp = Blueprint("departments", __name__)


@departments_bp.route("/organizations/<uuid:organization_id>/departments", methods=["POST"])
@login_required
@csrf_protect
@require_permission(Permission.DEPARTMENT_MANAGE)
def post_departments(organization_id):
    payload = request.get_json(silent=True)
    if payload is None:
        raise APIError("Request body must be valid JSON.", status_code=400, code="BAD_REQUEST")

    try:
        data = CreateDepartmentRequest.model_validate(payload)
    except ValidationError as exc:
        raise APIError(
            "Validation failed", status_code=422, code="VALIDATION_ERROR", details=validation_error_details(exc)
        )

    department = create_department(
        organization_id,
        name=data.name,
        description=data.description,
        manager_membership_id=data.manager_membership_id,
    )

    body = {"success": True, "message": "Department created", "data": department.to_public_dict()}
    return jsonify(body), 201


@departments_bp.route("/organizations/<uuid:organization_id>/departments", methods=["GET"])
@login_required
@require_permission(Permission.DEPARTMENT_MANAGE)
def get_departments(organization_id):
    departments = list_departments(organization_id)

    body = {
        "success": True,
        "message": "Departments retrieved",
        "data": [department.to_public_dict() for department in departments],
    }
    return jsonify(body), 200


@departments_bp.route("/organizations/<uuid:organization_id>/departments/<uuid:department_id>", methods=["PATCH"])
@login_required
@csrf_protect
@require_permission(Permission.DEPARTMENT_MANAGE)
def patch_department(organization_id, department_id):
    payload = request.get_json(silent=True)
    if payload is None:
        raise APIError("Request body must be valid JSON.", status_code=400, code="BAD_REQUEST")

    try:
        data = UpdateDepartmentRequest.model_validate(payload)
    except ValidationError as exc:
        raise APIError(
            "Validation failed", status_code=422, code="VALIDATION_ERROR", details=validation_error_details(exc)
        )

    department = update_department(organization_id, department_id, data.model_dump(exclude_unset=True))

    body = {"success": True, "message": "Department updated", "data": department.to_public_dict()}
    return jsonify(body), 200


@departments_bp.route("/organizations/<uuid:organization_id>/departments/<uuid:department_id>", methods=["DELETE"])
@login_required
@csrf_protect
@require_permission(Permission.DEPARTMENT_MANAGE)
def delete_department(organization_id, department_id):
    department = deactivate_department(organization_id, department_id)

    body = {"success": True, "message": "Department deactivated", "data": department.to_public_dict()}
    return jsonify(body), 200
