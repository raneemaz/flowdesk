from flask import Blueprint, g, jsonify, request
from pydantic import ValidationError

from app.auth.decorators import csrf_protect, login_required
from app.authz.decorators import require_permission
from app.authz.permissions import Permission
from app.errors import APIError, validation_error_details
from app.payments.schemas import CreatePaymentRequest, ListPaymentsQuery
from app.payments.service import get_invoice_balance, list_payments, record_payment

payments_bp = Blueprint("payments", __name__)


def _payment_response(payment, *, message, status_code):
    amount_paid, balance_due = get_invoice_balance(payment.invoice)
    body = {
        "success": True,
        "message": message,
        "data": {
            "payment": payment.to_public_dict(),
            "invoice": payment.invoice.to_public_dict(),
            "amount_paid": str(amount_paid),
            "balance_due": str(balance_due),
        },
    }
    return jsonify(body), status_code


@payments_bp.route("/organizations/<uuid:organization_id>/invoices/<uuid:invoice_id>/payments", methods=["POST"])
@login_required
@csrf_protect
@require_permission(Permission.INVOICE_PAYMENT_MANAGE)
def post_invoice_payments(organization_id, invoice_id):
    payload = request.get_json(silent=True)
    if payload is None:
        raise APIError("Request body must be valid JSON.", status_code=400, code="BAD_REQUEST")

    try:
        data = CreatePaymentRequest.model_validate(payload)
    except ValidationError as exc:
        raise APIError(
            "Validation failed", status_code=422, code="VALIDATION_ERROR", details=validation_error_details(exc)
        )

    payment, created = record_payment(
        organization_id,
        invoice_id,
        g.current_membership.id,
        amount=data.amount,
        payment_date=data.payment_date,
        method=data.method,
        reference=data.reference,
        notes=data.notes,
        idempotency_key=data.idempotency_key,
    )

    if created:
        return _payment_response(payment, message="Payment recorded", status_code=201)
    return _payment_response(payment, message="Payment already recorded", status_code=200)


@payments_bp.route("/organizations/<uuid:organization_id>/invoices/<uuid:invoice_id>/payments", methods=["GET"])
@login_required
@require_permission(Permission.INVOICE_PAYMENT_MANAGE)
def get_invoice_payments(organization_id, invoice_id):
    try:
        query = ListPaymentsQuery.model_validate(request.args.to_dict())
    except ValidationError as exc:
        raise APIError(
            "Validation failed", status_code=422, code="VALIDATION_ERROR", details=validation_error_details(exc)
        )

    payments, total = list_payments(organization_id, invoice_id, page=query.page, per_page=query.per_page)
    total_pages = (total + query.per_page - 1) // query.per_page if total else 0

    body = {
        "success": True,
        "message": "Payments retrieved",
        "data": [payment.to_public_dict() for payment in payments],
        "meta": {"page": query.page, "per_page": query.per_page, "total": total, "total_pages": total_pages},
    }
    return jsonify(body), 200
