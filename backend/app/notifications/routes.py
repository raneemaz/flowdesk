"""FD-048. Unlike every other organization-scoped resource in this
codebase, these routes don't use `require_permission` - there is no
`Permission` for notifications (Section 7.2's baseline matrix has no
row for this entity), so there's nothing for that decorator to check.
Access is ownership-based instead: `get_active_membership_or_404`
still confirms the caller is an active member of `organization_id`
(a missing/cross-tenant/inactive membership is 404, same as every
other org-scoped route), but every query below is then always scoped
to that membership's own `id` as `recipient_membership_id` - the same
"authenticated + no further role gate, but still filtered to the
caller's own records" shape `GET /organizations` already uses for
listing the caller's own memberships.

The mark-read endpoints use `PATCH`, not the spec outline's literal
`POST` (Section 11.1) - a judgment call for internal consistency: every
other "change the state of an existing resource, idempotently" endpoint
in this codebase (tasks' assign/status, invoices' issue/cancel,
employees' profile update) uses `PATCH`, and following the spec's
literal verb here would be the one exception for no functional
difference."""

from flask import Blueprint, g, jsonify, request
from pydantic import ValidationError

from app.auth.decorators import csrf_protect, login_required
from app.authz.service import get_active_membership_or_404
from app.errors import APIError, validation_error_details
from app.notifications.schemas import ListNotificationsQuery
from app.notifications.service import list_notifications, mark_all_notifications_read, mark_notification_read

notifications_bp = Blueprint("notifications", __name__)


@notifications_bp.route("/organizations/<uuid:organization_id>/notifications", methods=["GET"])
@login_required
def get_notifications(organization_id):
    membership = get_active_membership_or_404(g.current_user, organization_id)

    try:
        query = ListNotificationsQuery.model_validate(request.args.to_dict())
    except ValidationError as exc:
        raise APIError(
            "Validation failed", status_code=422, code="VALIDATION_ERROR", details=validation_error_details(exc)
        )

    entries, total = list_notifications(
        organization_id,
        membership.id,
        unread_only=query.unread_only,
        page=query.page,
        per_page=query.per_page,
    )
    total_pages = (total + query.per_page - 1) // query.per_page if total else 0

    body = {
        "success": True,
        "message": "Notifications retrieved",
        "data": [entry.to_public_dict() for entry in entries],
        "meta": {"page": query.page, "per_page": query.per_page, "total": total, "total_pages": total_pages},
    }
    return jsonify(body), 200


@notifications_bp.route("/organizations/<uuid:organization_id>/notifications/<uuid:notification_id>/read", methods=["PATCH"])
@login_required
@csrf_protect
def patch_notification_read(organization_id, notification_id):
    membership = get_active_membership_or_404(g.current_user, organization_id)
    notification = mark_notification_read(organization_id, membership.id, notification_id)

    body = {"success": True, "message": "Notification marked read", "data": notification.to_public_dict()}
    return jsonify(body), 200


@notifications_bp.route("/organizations/<uuid:organization_id>/notifications/read-all", methods=["PATCH"])
@login_required
@csrf_protect
def patch_notifications_read_all(organization_id):
    membership = get_active_membership_or_404(g.current_user, organization_id)
    updated_count = mark_all_notifications_read(organization_id, membership.id)

    body = {
        "success": True,
        "message": "Notifications marked read",
        "data": {"updated_count": updated_count},
    }
    return jsonify(body), 200
