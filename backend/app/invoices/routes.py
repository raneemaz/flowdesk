from flask import Blueprint, g, jsonify, request
from pydantic import ValidationError

from app.auth.decorators import csrf_protect, login_required
from app.authz.decorators import require_permission
from app.authz.permissions import Permission
from app.errors import APIError, validation_error_details
from app.invoices.schemas import (
    CreateInvoiceRequest,
    FinancialSummaryQuery,
    ListInvoicesQuery,
    UpdateInvoiceRequest,
)
from app.invoices.service import (
    cancel_invoice,
    create_invoice,
    get_financial_summary,
    get_invoice,
    issue_invoice,
    list_invoices,
    update_invoice,
)

invoices_bp = Blueprint("invoices", __name__)


@invoices_bp.route("/organizations/<uuid:organization_id>/invoices", methods=["POST"])
@login_required
@csrf_protect
@require_permission(Permission.INVOICE_PAYMENT_MANAGE)
def post_invoices(organization_id):
    payload = request.get_json(silent=True)
    if payload is None:
        raise APIError("Request body must be valid JSON.", status_code=400, code="BAD_REQUEST")

    try:
        data = CreateInvoiceRequest.model_validate(payload)
    except ValidationError as exc:
        raise APIError(
            "Validation failed", status_code=422, code="VALIDATION_ERROR", details=validation_error_details(exc)
        )

    invoice = create_invoice(
        organization_id,
        g.current_membership.id,
        customer_id=data.customer_id,
        currency=data.currency,
        issue_date=data.issue_date,
        due_date=data.due_date,
        notes=data.notes,
        payment_terms=data.payment_terms,
        discount_type=data.discount_type,
        discount_value=data.discount_value,
        line_items=[item.model_dump() for item in data.line_items],
    )

    body = {"success": True, "message": "Invoice created", "data": invoice.to_public_dict()}
    return jsonify(body), 201


@invoices_bp.route("/organizations/<uuid:organization_id>/invoices", methods=["GET"])
@login_required
@require_permission(Permission.INVOICE_PAYMENT_MANAGE)
def get_invoices(organization_id):
    try:
        query = ListInvoicesQuery.model_validate(request.args.to_dict())
    except ValidationError as exc:
        raise APIError(
            "Validation failed", status_code=422, code="VALIDATION_ERROR", details=validation_error_details(exc)
        )

    invoices, total = list_invoices(
        organization_id,
        organization_timezone=g.current_membership.organization.timezone,
        customer_id=query.customer_id,
        status=query.status,
        due_date_from=query.due_date_from,
        due_date_to=query.due_date_to,
        page=query.page,
        per_page=query.per_page,
    )
    total_pages = (total + query.per_page - 1) // query.per_page if total else 0

    body = {
        "success": True,
        "message": "Invoices retrieved",
        "data": [invoice.to_public_dict() for invoice in invoices],
        "meta": {"page": query.page, "per_page": query.per_page, "total": total, "total_pages": total_pages},
    }
    return jsonify(body), 200


@invoices_bp.route("/organizations/<uuid:organization_id>/invoices/financial-summary", methods=["GET"])
@login_required
@require_permission(Permission.FINANCIAL_REPORTS_VIEW)
def get_invoices_financial_summary(organization_id):
    try:
        query = FinancialSummaryQuery.model_validate(request.args.to_dict())
    except ValidationError as exc:
        raise APIError(
            "Validation failed", status_code=422, code="VALIDATION_ERROR", details=validation_error_details(exc)
        )

    summary = get_financial_summary(
        organization_id,
        g.current_membership.organization.timezone,
        period_start=query.period_start,
        period_end=query.period_end,
    )

    body = {
        "success": True,
        "message": "Financial summary retrieved",
        "data": {
            "total_invoiced": str(summary["total_invoiced"]),
            "total_collected": str(summary["total_collected"]),
            "outstanding_balance": str(summary["outstanding_balance"]),
            "overdue_invoice_count": summary["overdue_invoice_count"],
            "period_start": summary["period_start"].isoformat(),
            "period_end": summary["period_end"].isoformat(),
            "monthly_revenue_collected": str(summary["monthly_revenue_collected"]),
            "recent_payments": [payment.to_public_dict() for payment in summary["recent_payments"]],
        },
    }
    return jsonify(body), 200


@invoices_bp.route("/organizations/<uuid:organization_id>/invoices/<uuid:invoice_id>", methods=["GET"])
@login_required
@require_permission(Permission.INVOICE_PAYMENT_MANAGE)
def get_invoice_detail(organization_id, invoice_id):
    invoice = get_invoice(organization_id, invoice_id, g.current_membership.organization.timezone)

    body = {"success": True, "message": "Invoice retrieved", "data": invoice.to_public_dict()}
    return jsonify(body), 200


@invoices_bp.route("/organizations/<uuid:organization_id>/invoices/<uuid:invoice_id>", methods=["PATCH"])
@login_required
@csrf_protect
@require_permission(Permission.INVOICE_PAYMENT_MANAGE)
def patch_invoice(organization_id, invoice_id):
    payload = request.get_json(silent=True)
    if payload is None:
        raise APIError("Request body must be valid JSON.", status_code=400, code="BAD_REQUEST")

    try:
        data = UpdateInvoiceRequest.model_validate(payload)
    except ValidationError as exc:
        raise APIError(
            "Validation failed", status_code=422, code="VALIDATION_ERROR", details=validation_error_details(exc)
        )

    fields = data.model_dump(exclude_unset=True)
    invoice = update_invoice(organization_id, invoice_id, fields)

    body = {"success": True, "message": "Invoice updated", "data": invoice.to_public_dict()}
    return jsonify(body), 200


@invoices_bp.route("/organizations/<uuid:organization_id>/invoices/<uuid:invoice_id>/issue", methods=["PATCH"])
@login_required
@csrf_protect
@require_permission(Permission.INVOICE_PAYMENT_MANAGE)
def patch_invoice_issue(organization_id, invoice_id):
    invoice = issue_invoice(organization_id, invoice_id)

    body = {"success": True, "message": "Invoice issued", "data": invoice.to_public_dict()}
    return jsonify(body), 200


@invoices_bp.route("/organizations/<uuid:organization_id>/invoices/<uuid:invoice_id>/cancel", methods=["PATCH"])
@login_required
@csrf_protect
@require_permission(Permission.INVOICE_PAYMENT_MANAGE)
def patch_invoice_cancel(organization_id, invoice_id):
    invoice = cancel_invoice(organization_id, invoice_id)

    body = {"success": True, "message": "Invoice cancelled", "data": invoice.to_public_dict()}
    return jsonify(body), 200
