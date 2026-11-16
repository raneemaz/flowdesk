from flask import Blueprint, jsonify, request
from pydantic import ValidationError

from app.auth.decorators import csrf_protect, login_required
from app.authz.decorators import require_permission
from app.authz.permissions import Permission
from app.customers.schemas import CreateCustomerRequest, ListCustomersQuery, UpdateCustomerRequest
from app.customers.service import (
    archive_customer,
    create_customer,
    get_customer_or_404,
    list_customers,
    update_customer,
)
from app.errors import APIError, validation_error_details

customers_bp = Blueprint("customers", __name__)


@customers_bp.route("/organizations/<uuid:organization_id>/customers", methods=["POST"])
@login_required
@csrf_protect
@require_permission(Permission.CUSTOMER_MANAGE)
def post_customers(organization_id):
    payload = request.get_json(silent=True)
    if payload is None:
        raise APIError("Request body must be valid JSON.", status_code=400, code="BAD_REQUEST")

    try:
        data = CreateCustomerRequest.model_validate(payload)
    except ValidationError as exc:
        raise APIError(
            "Validation failed", status_code=422, code="VALIDATION_ERROR", details=validation_error_details(exc)
        )

    customer = create_customer(
        organization_id,
        name=data.name,
        email=data.email,
        phone=data.phone,
        company=data.company,
        address=data.address,
        notes=data.notes,
    )

    body = {"success": True, "message": "Customer created", "data": customer.to_public_dict()}
    return jsonify(body), 201


@customers_bp.route("/organizations/<uuid:organization_id>/customers", methods=["GET"])
@login_required
@require_permission(Permission.CUSTOMER_MANAGE)
def get_customers(organization_id):
    try:
        query = ListCustomersQuery.model_validate(request.args.to_dict())
    except ValidationError as exc:
        raise APIError(
            "Validation failed", status_code=422, code="VALIDATION_ERROR", details=validation_error_details(exc)
        )

    customers, total = list_customers(
        organization_id, search=query.search, status=query.status, page=query.page, per_page=query.per_page
    )
    total_pages = (total + query.per_page - 1) // query.per_page if total else 0

    body = {
        "success": True,
        "message": "Customers retrieved",
        "data": [customer.to_public_dict() for customer in customers],
        "meta": {"page": query.page, "per_page": query.per_page, "total": total, "total_pages": total_pages},
    }
    return jsonify(body), 200


@customers_bp.route("/organizations/<uuid:organization_id>/customers/<uuid:customer_id>", methods=["GET"])
@login_required
@require_permission(Permission.CUSTOMER_MANAGE)
def get_customer_detail(organization_id, customer_id):
    customer = get_customer_or_404(organization_id, customer_id)

    body = {"success": True, "message": "Customer retrieved", "data": customer.to_public_dict()}
    return jsonify(body), 200


@customers_bp.route("/organizations/<uuid:organization_id>/customers/<uuid:customer_id>", methods=["PATCH"])
@login_required
@csrf_protect
@require_permission(Permission.CUSTOMER_MANAGE)
def patch_customer(organization_id, customer_id):
    payload = request.get_json(silent=True)
    if payload is None:
        raise APIError("Request body must be valid JSON.", status_code=400, code="BAD_REQUEST")

    try:
        data = UpdateCustomerRequest.model_validate(payload)
    except ValidationError as exc:
        raise APIError(
            "Validation failed", status_code=422, code="VALIDATION_ERROR", details=validation_error_details(exc)
        )

    customer = update_customer(organization_id, customer_id, data.model_dump(exclude_unset=True))

    body = {"success": True, "message": "Customer updated", "data": customer.to_public_dict()}
    return jsonify(body), 200


@customers_bp.route("/organizations/<uuid:organization_id>/customers/<uuid:customer_id>", methods=["DELETE"])
@login_required
@csrf_protect
@require_permission(Permission.CUSTOMER_MANAGE)
def delete_customer(organization_id, customer_id):
    customer = archive_customer(organization_id, customer_id)

    body = {"success": True, "message": "Customer archived", "data": customer.to_public_dict()}
    return jsonify(body), 200
