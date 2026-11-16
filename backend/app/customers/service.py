"""FD-035: customer CRUD, search, pagination, and archiving.

`Permission.CUSTOMER_MANAGE` (FD-015) is only ever `full` or `none`
across every role (see app/authz/permissions.py's ROLE_PERMISSIONS) -
unlike `TASK_VIEW_UPDATE`'s `assigned` scope, there's no per-record
reach restriction to apply here: `require_permission` alone (never
`none` reaches a view) is the whole authorization story for this
module, same as app/departments/.
"""

import uuid

from sqlalchemy import or_

from app.errors import APIError
from app.extensions import db
from app.models import Customer, CustomerStatus


def _set_name(customer: Customer, name: str) -> None:
    # Customer.name's own @validates strips and rejects a blank result
    # (e.g. a whitespace-only string, which passes pydantic's
    # min_length=1 but not this) - converted to a 422 here rather than
    # letting the bare ValueError escape as an unhandled 500, same
    # pattern app.departments.service._set_name already established.
    try:
        customer.name = name
    except ValueError as exc:
        raise APIError(str(exc), status_code=422, code="VALIDATION_ERROR", details={"name": str(exc)})


def create_customer(
    organization_id: uuid.UUID,
    *,
    name: str,
    email: str | None,
    phone: str | None,
    company: str | None,
    address: str | None,
    notes: str | None,
) -> Customer:
    customer = Customer(
        organization_id=organization_id,
        email=email,
        phone=phone,
        company=company,
        address=address,
        notes=notes,
    )
    _set_name(customer, name)

    db.session.add(customer)
    db.session.commit()
    return customer


def _apply_search(query, search: str | None):
    # Matches name/email/phone/company - exactly the four columns
    # FD-034's model docstring indexed for this. Unlike the employee
    # directory's name-only search (FD-022's own documented reasoning:
    # avoiding an email-existence oracle for a LIMITED-scope caller),
    # CUSTOMER_MANAGE has no LIMITED scope at all - any caller who can
    # list customers already sees every field on every row, so there's
    # no narrower-scope caller for a matched-but-hidden field to leak
    # information to.
    if not search:
        return query
    pattern = f"%{search}%"
    return query.filter(
        or_(
            Customer.name.ilike(pattern),
            Customer.email.ilike(pattern),
            Customer.phone.ilike(pattern),
            Customer.company.ilike(pattern),
        )
    )


def list_customers(
    organization_id: uuid.UUID,
    *,
    search: str | None,
    status: CustomerStatus | None,
    page: int,
    per_page: int,
) -> tuple[list[Customer], int]:
    # Every status included by default (active and archived) -
    # archiving never hides history (Section 26's own acceptance
    # criterion), same convention app.departments.service.list_departments
    # and the employee directory's own default-unfiltered `status`
    # already established. `status` narrows it down when given.
    query = db.session.query(Customer).filter(Customer.organization_id == organization_id)
    query = _apply_search(query, search)
    if status is not None:
        query = query.filter(Customer.status == status)

    total = query.count()
    customers = query.order_by(Customer.name.asc()).offset((page - 1) * per_page).limit(per_page).all()
    return customers, total


def get_customer_or_404(organization_id: uuid.UUID, customer_id: uuid.UUID) -> Customer:
    customer = db.session.query(Customer).filter_by(id=customer_id, organization_id=organization_id).first()
    if customer is None:
        raise APIError("Not found.", status_code=404, code="NOT_FOUND")
    return customer


# Order matters, same reasoning as app.tasks.service's _EDITABLE_FIELDS:
# name is listed first so a blank-title-style rejection (the one field
# whose model-level @validates can raise) happens before any other
# field in the same request gets mutated.
_EDITABLE_FIELDS = ("email", "phone", "company", "address", "notes", "status")


def update_customer(organization_id: uuid.UUID, customer_id: uuid.UUID, fields: dict) -> Customer:
    """`fields` is the caller's `UpdateCustomerRequest.model_dump(exclude_unset=True)`
    - only keys actually present in the request body are applied."""
    customer = get_customer_or_404(organization_id, customer_id)

    if "name" in fields:
        _set_name(customer, fields["name"])
    for field in _EDITABLE_FIELDS:
        if field in fields:
            setattr(customer, field, fields[field])

    db.session.commit()
    return customer


def archive_customer(organization_id: uuid.UUID, customer_id: uuid.UUID) -> Customer:
    """The DELETE endpoint's action - soft, never a real row delete
    (spec Section 10.3 rule #5, and Section 26's "archived customers
    stay linked to historical requests/invoices"): sets status to
    archived so the customer (and every future CustomerRequest/Invoice
    referencing it, FD-036+) survives. Idempotent - archiving an
    already-archived customer is a no-op success, not an error, same
    convention app.departments.service.deactivate_department already
    established for DELETE's own idempotent semantics. A caller can
    reverse this via PATCH {"status": "active"} - there's no separate
    "unarchive" endpoint, same as Department's own status field."""
    customer = get_customer_or_404(organization_id, customer_id)
    if customer.status != CustomerStatus.ARCHIVED:
        customer.status = CustomerStatus.ARCHIVED
        db.session.commit()
    return customer
