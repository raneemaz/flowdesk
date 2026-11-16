from decimal import Decimal

import pytest

from app.errors import APIError
from app.extensions import db
from app.invoices.service import build_line_item, compute_line_total, recalculate_invoice
from app.models import (
    Customer,
    DiscountType,
    Invoice,
    InvoiceLineItem,
    Membership,
    MembershipRole,
    Organization,
    Payment,
    User,
)


@pytest.fixture
def db_session(app):
    with app.app_context():
        yield db.session
        db.session.rollback()
        db.session.query(Payment).delete()
        db.session.query(InvoiceLineItem).delete()
        db.session.query(Invoice).delete()
        db.session.query(Customer).delete()
        db.session.query(Membership).delete()
        db.session.query(Organization).delete()
        db.session.query(User).delete()
        db.session.commit()


def _make_user(email="creator@example.com"):
    user = User(name="A Creator", email=email)
    user.set_password("correct horse battery staple")
    return user


def _make_org(name="Acme Inc", slug="acme-inc"):
    return Organization(name=name, slug=slug)


def _make_membership(org, user, role=MembershipRole.OWNER):
    return Membership(organization_id=org.id, user_id=user.id, role=role)


def _make_customer(org, name="Jane Customer"):
    return Customer(organization_id=org.id, name=name)


def _make_invoice(db_session, discount_type=DiscountType.FLAT, discount_value=Decimal("0.00")):
    user = _make_user()
    org = _make_org()
    db_session.add_all([user, org])
    db_session.flush()
    creator = _make_membership(org, user)
    customer = _make_customer(org)
    db_session.add_all([creator, customer])
    db_session.flush()
    invoice = Invoice(
        organization_id=org.id,
        customer_id=customer.id,
        invoice_number="INV-0001",
        currency="USD",
        created_by=creator.id,
        discount_type=discount_type,
        discount_value=discount_value,
    )
    db_session.add(invoice)
    db_session.flush()
    return invoice


def _add_line_item(db_session, invoice, *, quantity, unit_price, tax_rate=None):
    item = build_line_item(
        invoice.organization_id,
        invoice.id,
        description="Widget",
        quantity=Decimal(quantity),
        unit_price=Decimal(unit_price),
        tax_rate=Decimal(tax_rate) if tax_rate is not None else None,
    )
    db_session.add(item)
    db_session.flush()
    db_session.refresh(invoice)
    return item


def test_compute_line_total_rounds_half_up_to_the_cent():
    assert compute_line_total(Decimal("3"), Decimal("10.005")) == Decimal("30.02")


def test_recalculate_invoice_sums_line_totals_into_subtotal(db_session):
    invoice = _make_invoice(db_session)
    _add_line_item(db_session, invoice, quantity="2", unit_price="10.00")
    _add_line_item(db_session, invoice, quantity="1", unit_price="5.50")

    recalculate_invoice(invoice)

    assert invoice.subtotal == Decimal("25.50")
    assert invoice.total == Decimal("25.50")


def test_recalculate_invoice_with_no_line_items_is_all_zero(db_session):
    invoice = _make_invoice(db_session)

    recalculate_invoice(invoice)

    assert invoice.subtotal == Decimal("0.00")
    assert invoice.tax_total == Decimal("0.00")
    assert invoice.discount_total == Decimal("0.00")
    assert invoice.total == Decimal("0.00")


def test_recalculate_invoice_sums_tax_at_full_precision_before_rounding_once(db_session):
    """The user's explicit locked-in rule: per-line tax amounts are
    summed at full decimal precision, and only the final sum is
    rounded once - never each line rounded individually first. These
    three lines each produce a tax fraction that rounds UP on its own
    (0.125 -> 0.13), but the true sum (0.375) rounds DOWN to 0.38 only
    if summed unrounded first; per-line rounding would instead give
    0.13 * 3 = 0.39. Picking amounts where the two policies disagree
    proves the right one is implemented."""
    invoice = _make_invoice(db_session)
    _add_line_item(db_session, invoice, quantity="1", unit_price="12.50", tax_rate="1")
    _add_line_item(db_session, invoice, quantity="1", unit_price="12.50", tax_rate="1")
    _add_line_item(db_session, invoice, quantity="1", unit_price="12.50", tax_rate="1")

    recalculate_invoice(invoice)

    assert invoice.subtotal == Decimal("37.50")
    assert invoice.tax_total == Decimal("0.38")
    assert invoice.total == Decimal("37.88")


def test_recalculate_invoice_skips_tax_for_line_items_with_no_tax_rate(db_session):
    invoice = _make_invoice(db_session)
    _add_line_item(db_session, invoice, quantity="1", unit_price="100.00", tax_rate=None)

    recalculate_invoice(invoice)

    assert invoice.tax_total == Decimal("0.00")


def test_recalculate_invoice_applies_a_flat_discount(db_session):
    invoice = _make_invoice(db_session, discount_type=DiscountType.FLAT, discount_value=Decimal("15.00"))
    _add_line_item(db_session, invoice, quantity="1", unit_price="100.00")

    recalculate_invoice(invoice)

    assert invoice.discount_total == Decimal("15.00")
    assert invoice.total == Decimal("85.00")


def test_recalculate_invoice_applies_a_percentage_discount_of_subtotal(db_session):
    invoice = _make_invoice(db_session, discount_type=DiscountType.PERCENTAGE, discount_value=Decimal("10.00"))
    _add_line_item(db_session, invoice, quantity="1", unit_price="100.00")

    recalculate_invoice(invoice)

    assert invoice.discount_total == Decimal("10.00")
    assert invoice.total == Decimal("90.00")


def test_recalculate_invoice_rejects_a_discount_that_would_make_the_total_negative(db_session):
    invoice = _make_invoice(db_session, discount_type=DiscountType.FLAT, discount_value=Decimal("500.00"))
    _add_line_item(db_session, invoice, quantity="1", unit_price="100.00")

    with pytest.raises(APIError) as exc_info:
        recalculate_invoice(invoice)

    assert exc_info.value.status_code == 422
    assert exc_info.value.code == "NEGATIVE_TOTAL"


def test_recalculate_invoice_rejects_a_negative_discount_value(db_session):
    """A negative discount_value would otherwise silently *increase*
    the total instead of discounting it (subtotal - (-50.00) > subtotal),
    since the total-negative check alone can't catch it."""
    invoice = _make_invoice(db_session, discount_type=DiscountType.FLAT, discount_value=Decimal("-50.00"))
    _add_line_item(db_session, invoice, quantity="1", unit_price="100.00")

    with pytest.raises(APIError) as exc_info:
        recalculate_invoice(invoice)

    assert exc_info.value.status_code == 422
    assert exc_info.value.code == "INVALID_DISCOUNT"


def test_build_line_item_computes_line_total_from_quantity_and_unit_price(db_session):
    invoice = _make_invoice(db_session)

    item = build_line_item(
        invoice.organization_id,
        invoice.id,
        description="Consulting hours",
        quantity=Decimal("3"),
        unit_price=Decimal("50.00"),
        tax_rate=None,
    )

    assert item.line_total == Decimal("150.00")
