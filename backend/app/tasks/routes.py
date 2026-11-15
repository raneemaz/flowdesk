from flask import Blueprint, g, jsonify, request
from pydantic import ValidationError

from app.auth.decorators import csrf_protect, login_required
from app.authz.decorators import require_permission
from app.authz.permissions import Permission
from app.errors import APIError, validation_error_details
from app.tasks.schemas import (
    AssignTaskRequest,
    CreateTaskCommentRequest,
    CreateTaskRequest,
    ListTaskCommentsQuery,
    ListTasksQuery,
    UpdateTaskRequest,
    UpdateTaskStatusRequest,
)
from app.tasks.service import (
    assign_task,
    create_task,
    create_task_comment,
    get_task,
    list_task_comments,
    list_tasks,
    update_task,
    update_task_status,
)

tasks_bp = Blueprint("tasks", __name__)


@tasks_bp.route("/organizations/<uuid:organization_id>/tasks", methods=["POST"])
@login_required
@csrf_protect
@require_permission(Permission.TASK_CREATE_ASSIGN)
def post_tasks(organization_id):
    payload = request.get_json(silent=True)
    if payload is None:
        raise APIError("Request body must be valid JSON.", status_code=400, code="BAD_REQUEST")

    try:
        data = CreateTaskRequest.model_validate(payload)
    except ValidationError as exc:
        raise APIError(
            "Validation failed", status_code=422, code="VALIDATION_ERROR", details=validation_error_details(exc)
        )

    task = create_task(
        organization_id,
        g.current_membership.id,
        title=data.title,
        description=data.description,
        priority=data.priority,
        department_id=data.department_id,
        start_date=data.start_date,
        due_date=data.due_date,
        estimated_hours=data.estimated_hours,
    )

    body = {"success": True, "message": "Task created", "data": task.to_public_dict()}
    return jsonify(body), 201


@tasks_bp.route("/organizations/<uuid:organization_id>/tasks", methods=["GET"])
@login_required
@require_permission(Permission.TASK_VIEW_UPDATE)
def get_tasks(organization_id):
    try:
        query = ListTasksQuery.model_validate(request.args.to_dict())
    except ValidationError as exc:
        raise APIError(
            "Validation failed", status_code=422, code="VALIDATION_ERROR", details=validation_error_details(exc)
        )

    tasks, total = list_tasks(
        organization_id,
        scope=g.permission_scope,
        caller_membership_id=g.current_membership.id,
        assignee_membership_id=query.assignee_membership_id,
        department_id=query.department_id,
        priority=query.priority,
        status=query.status,
        due_date_from=query.due_date_from,
        due_date_to=query.due_date_to,
        created_from=query.created_from,
        created_to=query.created_to,
        page=query.page,
        per_page=query.per_page,
    )
    total_pages = (total + query.per_page - 1) // query.per_page if total else 0

    body = {
        "success": True,
        "message": "Tasks retrieved",
        "data": [task.to_public_dict() for task in tasks],
        "meta": {"page": query.page, "per_page": query.per_page, "total": total, "total_pages": total_pages},
    }
    return jsonify(body), 200


@tasks_bp.route("/organizations/<uuid:organization_id>/tasks/<uuid:task_id>", methods=["GET"])
@login_required
@require_permission(Permission.TASK_VIEW_UPDATE)
def get_task_detail(organization_id, task_id):
    task = get_task(organization_id, task_id, scope=g.permission_scope, caller_membership_id=g.current_membership.id)

    body = {"success": True, "message": "Task retrieved", "data": task.to_public_dict()}
    return jsonify(body), 200


@tasks_bp.route("/organizations/<uuid:organization_id>/tasks/<uuid:task_id>", methods=["PATCH"])
@login_required
@csrf_protect
@require_permission(Permission.TASK_CREATE_ASSIGN)
def patch_task(organization_id, task_id):
    payload = request.get_json(silent=True)
    if payload is None:
        raise APIError("Request body must be valid JSON.", status_code=400, code="BAD_REQUEST")

    try:
        data = UpdateTaskRequest.model_validate(payload)
    except ValidationError as exc:
        raise APIError(
            "Validation failed", status_code=422, code="VALIDATION_ERROR", details=validation_error_details(exc)
        )

    task = update_task(
        organization_id,
        task_id,
        data.model_dump(exclude_unset=True),
        actor_membership_id=g.current_membership.id,
    )

    body = {"success": True, "message": "Task updated", "data": task.to_public_dict()}
    return jsonify(body), 200


@tasks_bp.route("/organizations/<uuid:organization_id>/tasks/<uuid:task_id>/assign", methods=["PATCH"])
@login_required
@csrf_protect
@require_permission(Permission.TASK_CREATE_ASSIGN)
def patch_task_assign(organization_id, task_id):
    payload = request.get_json(silent=True)
    if payload is None:
        raise APIError("Request body must be valid JSON.", status_code=400, code="BAD_REQUEST")

    try:
        data = AssignTaskRequest.model_validate(payload)
    except ValidationError as exc:
        raise APIError(
            "Validation failed", status_code=422, code="VALIDATION_ERROR", details=validation_error_details(exc)
        )

    task = assign_task(
        organization_id,
        task_id,
        actor_membership_id=g.current_membership.id,
        assignee_membership_id=data.assignee_membership_id,
    )

    body = {"success": True, "message": "Task assignee updated", "data": task.to_public_dict()}
    return jsonify(body), 200


@tasks_bp.route("/organizations/<uuid:organization_id>/tasks/<uuid:task_id>/status", methods=["PATCH"])
@login_required
@csrf_protect
@require_permission(Permission.TASK_VIEW_UPDATE)
def patch_task_status(organization_id, task_id):
    payload = request.get_json(silent=True)
    if payload is None:
        raise APIError("Request body must be valid JSON.", status_code=400, code="BAD_REQUEST")

    try:
        data = UpdateTaskStatusRequest.model_validate(payload)
    except ValidationError as exc:
        raise APIError(
            "Validation failed", status_code=422, code="VALIDATION_ERROR", details=validation_error_details(exc)
        )

    task = update_task_status(
        organization_id,
        task_id,
        scope=g.permission_scope,
        caller_membership_id=g.current_membership.id,
        actor_membership_id=g.current_membership.id,
        new_status=data.status,
    )

    body = {"success": True, "message": "Task status updated", "data": task.to_public_dict()}
    return jsonify(body), 200


@tasks_bp.route("/organizations/<uuid:organization_id>/tasks/<uuid:task_id>/comments", methods=["POST"])
@login_required
@csrf_protect
@require_permission(Permission.TASK_VIEW_UPDATE)
def post_task_comments(organization_id, task_id):
    payload = request.get_json(silent=True)
    if payload is None:
        raise APIError("Request body must be valid JSON.", status_code=400, code="BAD_REQUEST")

    try:
        data = CreateTaskCommentRequest.model_validate(payload)
    except ValidationError as exc:
        raise APIError(
            "Validation failed", status_code=422, code="VALIDATION_ERROR", details=validation_error_details(exc)
        )

    comment = create_task_comment(
        organization_id,
        task_id,
        scope=g.permission_scope,
        caller_membership_id=g.current_membership.id,
        author_membership_id=g.current_membership.id,
        body=data.body,
    )

    body = {"success": True, "message": "Comment created", "data": comment.to_public_dict()}
    return jsonify(body), 201


@tasks_bp.route("/organizations/<uuid:organization_id>/tasks/<uuid:task_id>/comments", methods=["GET"])
@login_required
@require_permission(Permission.TASK_VIEW_UPDATE)
def get_task_comments(organization_id, task_id):
    try:
        query = ListTaskCommentsQuery.model_validate(request.args.to_dict())
    except ValidationError as exc:
        raise APIError(
            "Validation failed", status_code=422, code="VALIDATION_ERROR", details=validation_error_details(exc)
        )

    comments, total = list_task_comments(
        organization_id,
        task_id,
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
