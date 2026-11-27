from flask import Blueprint, g, jsonify, request
from pydantic import ValidationError

from app.auth.decorators import csrf_protect, login_required
from app.authz.decorators import require_permission
from app.authz.permissions import Permission
from app.customer_requests.schemas import (
    AssignCustomerRequestRequest,
    CreateCustomerRequestRequest,
    CreateRequestCommentRequest,
    ListCustomerRequestsQuery,
    ListRequestCommentsQuery,
    ListRequestHistoryQuery,
    UpdateCustomerRequestStatusRequest,
)
from app.customer_requests.service import (
    assign_request,
    delete_request,
    delete_request_comment,
    edit_request_comment,
    create_request,
    create_request_comment,
    get_request,
    list_request_comments,
    list_request_history,
    list_requests,
    update_request_status,
)
from app.errors import APIError, validation_error_details

customer_requests_bp = Blueprint("customer_requests", __name__)


@customer_requests_bp.route("/organizations/<uuid:organization_id>/customer-requests", methods=["POST"])
@login_required
@csrf_protect
@require_permission(Permission.CUSTOMER_REQUEST_MANAGE)
def post_customer_requests(organization_id):
    payload = request.get_json(silent=True)
    if payload is None:
        raise APIError("Request body must be valid JSON.", status_code=400, code="BAD_REQUEST")

    try:
        data = CreateCustomerRequestRequest.model_validate(payload)
    except ValidationError as exc:
        raise APIError(
            "Validation failed", status_code=422, code="VALIDATION_ERROR", details=validation_error_details(exc)
        )

    customer_request = create_request(
        organization_id,
        g.current_membership.id,
        scope=g.permission_scope,
        customer_id=data.customer_id,
        title=data.title,
        description=data.description,
        category=data.category,
        priority=data.priority,
        due_date=data.due_date,
    )

    body = {"success": True, "message": "Customer request created", "data": customer_request.to_public_dict()}
    return jsonify(body), 201


@customer_requests_bp.route("/organizations/<uuid:organization_id>/customer-requests", methods=["GET"])
@login_required
@require_permission(Permission.CUSTOMER_REQUEST_MANAGE)
def get_customer_requests(organization_id):
    try:
        query = ListCustomerRequestsQuery.model_validate(request.args.to_dict())
    except ValidationError as exc:
        raise APIError(
            "Validation failed", status_code=422, code="VALIDATION_ERROR", details=validation_error_details(exc)
        )

    requests, total = list_requests(
        organization_id,
        scope=g.permission_scope,
        caller_membership_id=g.current_membership.id,
        customer_id=query.customer_id,
        assignee_membership_id=query.assignee_membership_id,
        category=query.category,
        priority=query.priority,
        status=query.status,
        due_date_from=query.due_date_from,
        due_date_to=query.due_date_to,
        page=query.page,
        per_page=query.per_page,
    )
    total_pages = (total + query.per_page - 1) // query.per_page if total else 0

    body = {
        "success": True,
        "message": "Customer requests retrieved",
        "data": [customer_request.to_public_dict() for customer_request in requests],
        "meta": {"page": query.page, "per_page": query.per_page, "total": total, "total_pages": total_pages},
    }
    return jsonify(body), 200


@customer_requests_bp.route(
    "/organizations/<uuid:organization_id>/customer-requests/<uuid:request_id>", methods=["GET"]
)
@login_required
@require_permission(Permission.CUSTOMER_REQUEST_MANAGE)
def get_customer_request_detail(organization_id, request_id):
    customer_request = get_request(
        organization_id, request_id, scope=g.permission_scope, caller_membership_id=g.current_membership.id
    )

    body = {"success": True, "message": "Customer request retrieved", "data": customer_request.to_public_dict()}
    return jsonify(body), 200


@customer_requests_bp.route(
    "/organizations/<uuid:organization_id>/customer-requests/<uuid:request_id>/assign", methods=["PATCH"]
)
@login_required
@csrf_protect
@require_permission(Permission.CUSTOMER_REQUEST_MANAGE)
def patch_customer_request_assign(organization_id, request_id):
    payload = request.get_json(silent=True)
    if payload is None:
        raise APIError("Request body must be valid JSON.", status_code=400, code="BAD_REQUEST")

    try:
        data = AssignCustomerRequestRequest.model_validate(payload)
    except ValidationError as exc:
        raise APIError(
            "Validation failed", status_code=422, code="VALIDATION_ERROR", details=validation_error_details(exc)
        )

    customer_request = assign_request(
        organization_id,
        request_id,
        scope=g.permission_scope,
        actor_membership_id=g.current_membership.id,
        assignee_membership_id=data.assignee_membership_id,
    )

    body = {"success": True, "message": "Customer request assignee updated", "data": customer_request.to_public_dict()}
    return jsonify(body), 200


@customer_requests_bp.route(
    "/organizations/<uuid:organization_id>/customer-requests/<uuid:request_id>/status", methods=["PATCH"]
)
@login_required
@csrf_protect
@require_permission(Permission.CUSTOMER_REQUEST_MANAGE)
def patch_customer_request_status(organization_id, request_id):
    payload = request.get_json(silent=True)
    if payload is None:
        raise APIError("Request body must be valid JSON.", status_code=400, code="BAD_REQUEST")

    try:
        data = UpdateCustomerRequestStatusRequest.model_validate(payload)
    except ValidationError as exc:
        raise APIError(
            "Validation failed", status_code=422, code="VALIDATION_ERROR", details=validation_error_details(exc)
        )

    customer_request = update_request_status(
        organization_id,
        request_id,
        scope=g.permission_scope,
        caller_membership_id=g.current_membership.id,
        actor_membership_id=g.current_membership.id,
        new_status=data.status,
        resolution_notes=data.resolution_notes,
    )

    body = {"success": True, "message": "Customer request status updated", "data": customer_request.to_public_dict()}
    return jsonify(body), 200


@customer_requests_bp.route(
    "/organizations/<uuid:organization_id>/customer-requests/<uuid:request_id>/comments", methods=["POST"]
)
@login_required
@csrf_protect
@require_permission(Permission.CUSTOMER_REQUEST_MANAGE)
def post_customer_request_comments(organization_id, request_id):
    payload = request.get_json(silent=True)
    if payload is None:
        raise APIError("Request body must be valid JSON.", status_code=400, code="BAD_REQUEST")

    try:
        data = CreateRequestCommentRequest.model_validate(payload)
    except ValidationError as exc:
        raise APIError(
            "Validation failed", status_code=422, code="VALIDATION_ERROR", details=validation_error_details(exc)
        )

    comment = create_request_comment(
        organization_id,
        request_id,
        scope=g.permission_scope,
        caller_membership_id=g.current_membership.id,
        author_membership_id=g.current_membership.id,
        body=data.body,
    )

    body = {"success": True, "message": "Comment created", "data": comment.to_public_dict()}
    return jsonify(body), 201


@customer_requests_bp.route(
    "/organizations/<uuid:organization_id>/customer-requests/<uuid:request_id>/comments", methods=["GET"]
)
@login_required
@require_permission(Permission.CUSTOMER_REQUEST_MANAGE)
def get_customer_request_comments(organization_id, request_id):
    try:
        query = ListRequestCommentsQuery.model_validate(request.args.to_dict())
    except ValidationError as exc:
        raise APIError(
            "Validation failed", status_code=422, code="VALIDATION_ERROR", details=validation_error_details(exc)
        )

    comments, total = list_request_comments(
        organization_id,
        request_id,
        scope=g.permission_scope,
        caller_membership_id=g.current_membership.id,
        page=query.page,
        per_page=query.per_page,
    )
    total_pages = (total + query.per_page - 1) // query.per_page if total else 0

    body = {
        "success": True,
        "message": "Comments retrieved",
        "data": [comment.to_public_dict() for comment in comments],
        "meta": {"page": query.page, "per_page": query.per_page, "total": total, "total_pages": total_pages},
    }
    return jsonify(body), 200


@customer_requests_bp.route(
    "/organizations/<uuid:organization_id>/customer-requests/<uuid:request_id>/history", methods=["GET"]
)
@login_required
@require_permission(Permission.CUSTOMER_REQUEST_MANAGE)
def get_customer_request_history(organization_id, request_id):
    try:
        query = ListRequestHistoryQuery.model_validate(request.args.to_dict())
    except ValidationError as exc:
        raise APIError(
            "Validation failed", status_code=422, code="VALIDATION_ERROR", details=validation_error_details(exc)
        )

    entries, total = list_request_history(
        organization_id,
        request_id,
        scope=g.permission_scope,
        caller_membership_id=g.current_membership.id,
        page=query.page,
        per_page=query.per_page,
    )
    total_pages = (total + query.per_page - 1) // query.per_page if total else 0

    body = {
        "success": True,
        "message": "History retrieved",
        "data": [entry.to_public_dict() for entry in entries],
        "meta": {"page": query.page, "per_page": query.per_page, "total": total, "total_pages": total_pages},
    }
    return jsonify(body), 200


@customer_requests_bp.route(
    "/organizations/<uuid:organization_id>/customer-requests/<uuid:request_id>", methods=["DELETE"]
)
@login_required
@csrf_protect
@require_permission(Permission.CUSTOMER_REQUEST_MANAGE)
def remove_customer_request(organization_id, request_id):
    """Owner/Manager only (checked in delete_request). Permanent."""
    delete_request(organization_id, request_id, actor=g.current_membership)
    return jsonify({"success": True, "message": "Request deleted", "data": None}), 200


@customer_requests_bp.route(
    "/organizations/<uuid:organization_id>/customer-requests/<uuid:request_id>/comments/<uuid:comment_id>",
    methods=["PATCH"],
)
@login_required
@csrf_protect
@require_permission(Permission.CUSTOMER_REQUEST_MANAGE)
def patch_request_comment(organization_id, request_id, comment_id):
    payload = request.get_json(silent=True)
    if payload is None:
        raise APIError("Request body must be valid JSON.", status_code=400, code="BAD_REQUEST")
    try:
        data = CreateRequestCommentRequest.model_validate(payload)
    except ValidationError as exc:
        raise APIError(
            "Validation failed", status_code=422, code="VALIDATION_ERROR", details=validation_error_details(exc)
        )
    comment = edit_request_comment(
        organization_id, request_id, comment_id, scope=g.permission_scope, actor=g.current_membership, body=data.body
    )
    return jsonify({"success": True, "message": "Comment updated", "data": comment.to_public_dict()}), 200


@customer_requests_bp.route(
    "/organizations/<uuid:organization_id>/customer-requests/<uuid:request_id>/comments/<uuid:comment_id>",
    methods=["DELETE"],
)
@login_required
@csrf_protect
@require_permission(Permission.CUSTOMER_REQUEST_MANAGE)
def remove_request_comment(organization_id, request_id, comment_id):
    delete_request_comment(
        organization_id, request_id, comment_id, scope=g.permission_scope, actor=g.current_membership
    )
    return jsonify({"success": True, "message": "Comment deleted", "data": None}), 200
