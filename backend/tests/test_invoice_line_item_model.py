import uuid
from decimal import Decimal

import pytest
from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models import Customer, Invoice, InvoiceLineItem, Membership, MembershipRole, Organization, User


@pytest.fixture
def db_session(app):
    with app.app_context():
        yield db.session
        db.session.rollback()
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


def _make_customer(org):
    return Customer(organization_id=org.id, name="Jane Customer")


def _make_invoice(org, customer, creator, number="INV-0001"):
    return Invoice(organization_id=org.id, customer_id=customer.id, invoice_number=number, currency="USD", created_by=creator.id)


def test_line_item_gets_a_uuid_primary_key_on_insert(db_session):
    user = _make_user()
    org = _make_org()
    db_session.add_all([user, org])
    db_session.flush()
    creator = _make_membership(org, user)
    customer = _make_customer(org)
    db_session.add_all([creator, customer])
    db_session.flush()
    invoice = _make_invoice(org, customer, creator)
    db_session.add(invoice)
    db_session.commit()

    item = InvoiceLineItem(
        organization_id=org.id,
        invoice_id=invoice.id,
        description="Consulting",
        quantity=Decimal("2.00"),
        unit_price=Decimal("150.00"),
        line_total=Decimal("300.00"),
    )
    db_session.add(item)
    db_session.commit()

    assert isinstance(item.id, uuid.UUID)


def test_line_item_tax_rate_is_optional(db_session):
    user = _make_user()
    org = _make_org()
    db_session.add_all([user, org])
    db_session.flush()
    creator = _make_membership(org, user)
    customer = _make_customer(org)
    db_session.add_all([creator, customer])
    db_session.flush()
    invoice = _make_invoice(org, customer, creator)
    db_session.add(invoice)
    db_session.commit()

    item = InvoiceLineItem(
        organization_id=org.id,
        invoice_id=invoice.id,
        description="Consulting",
        quantity=Decimal("1.00"),
        unit_price=Decimal("100.00"),
        line_total=Decimal("100.00"),
    )
    db_session.add(item)
    db_session.commit()

    assert item.tax_rate is None


def test_line_item_stores_exact_decimal_values(db_session):
    user = _make_user()
    org = _make_org()
    db_session.add_all([user, org])
    db_session.flush()
    creator = _make_membership(org, user)
    customer = _make_customer(org)
    db_session.add_all([creator, customer])
    db_session.flush()
    invoice = _make_invoice(org, customer, creator)
    db_session.add(invoice)
    db_session.commit()

    item = InvoiceLineItem(
        organization_id=org.id,
        invoice_id=invoice.id,
        description="Consulting",
        quantity=Decimal("2.50"),
        unit_price=Decimal("99.99"),
        tax_rate=Decimal("8.25"),
        line_total=Decimal("249.98"),
    )
    db_session.add(item)
    db_session.commit()
    db_session.refresh(item)

    assert item.quantity == Decimal("2.50")
    assert item.unit_price == Decimal("99.99")
    assert item.tax_rate == Decimal("8.25")
    assert item.line_total == Decimal("249.98")


def test_line_item_description_must_not_be_blank(db_session):
    with pytest.raises(ValueError):
        InvoiceLineItem(
            organization_id=uuid.uuid4(),
            invoice_id=uuid.uuid4(),
            description="   ",
            quantity=Decimal("1.00"),
            unit_price=Decimal("1.00"),
            line_total=Decimal("1.00"),
        )


def test_line_item_requires_a_real_invoice(db_session):
    org = _make_org()
    db_session.add(org)
    db_session.flush()

    item = InvoiceLineItem(
        organization_id=org.id,
        invoice_id=uuid.uuid4(),
        description="Consulting",
        quantity=Decimal("1.00"),
        unit_price=Decimal("1.00"),
        line_total=Decimal("1.00"),
    )
    db_session.add(item)

    with pytest.raises(IntegrityError):
        db_session.commit()


def test_line_item_organization_id_must_match_its_invoices_organization(db_session):
    user = _make_user()
    org_a = _make_org(name="Org A", slug="org-a-line-item-mismatch")
    org_b = _make_org(name="Org B", slug="org-b-line-item-mismatch")
    db_session.add_all([user, org_a, org_b])
    db_session.flush()
    creator = _make_membership(org_a, user)
    customer = _make_customer(org_a)
    db_session.add_all([creator, customer])
    db_session.flush()
    invoice_in_org_a = _make_invoice(org_a, customer, creator)
    db_session.add(invoice_in_org_a)
    db_session.commit()

    item = InvoiceLineItem(
        organization_id=org_b.id,
        invoice_id=invoice_in_org_a.id,
        description="Consulting",
        quantity=Decimal("1.00"),
        unit_price=Decimal("1.00"),
        line_total=Decimal("1.00"),
    )
    db_session.add(item)

    with pytest.raises(IntegrityError):
        db_session.commit()


def test_deleting_an_invoice_cascades_to_its_line_items(db_session):
    user = _make_user()
    org = _make_org()
    db_session.add_all([user, org])
    db_session.flush()
    creator = _make_membership(org, user)
    customer = _make_customer(org)
    db_session.add_all([creator, customer])
    db_session.flush()
    invoice = _make_invoice(org, customer, creator)
    db_session.add(invoice)
    db_session.commit()
    db_session.add(
        InvoiceLineItem(
            organization_id=org.id,
            invoice_id=invoice.id,
            description="Consulting",
            quantity=Decimal("1.00"),
            unit_price=Decimal("1.00"),
            line_total=Decimal("1.00"),
        )
    )
    db_session.commit()

    db_session.delete(invoice)
    db_session.commit()

    assert db_session.query(InvoiceLineItem).count() == 0


def test_deleting_an_organization_cascades_to_its_invoice_line_items(db_session):
    user = _make_user()
    org = _make_org()
    db_session.add_all([user, org])
    db_session.flush()
    creator = _make_membership(org, user)
    customer = _make_customer(org)
    db_session.add_all([creator, customer])
    db_session.flush()
    invoice = _make_invoice(org, customer, creator)
    db_session.add(invoice)
    db_session.commit()
    db_session.add(
        InvoiceLineItem(
            organization_id=org.id,
            invoice_id=invoice.id,
            description="Consulting",
            quantity=Decimal("1.00"),
            unit_price=Decimal("1.00"),
            line_total=Decimal("1.00"),
        )
    )
    db_session.commit()

    db_session.delete(org)
    db_session.commit()

    assert db_session.query(InvoiceLineItem).count() == 0


def test_invoice_relationship_exposes_its_line_items(db_session):
    user = _make_user()
    org = _make_org()
    db_session.add_all([user, org])
    db_session.flush()
    creator = _make_membership(org, user)
    customer = _make_customer(org)
    db_session.add_all([creator, customer])
    db_session.flush()
    invoice = _make_invoice(org, customer, creator)
    db_session.add(invoice)
    db_session.commit()
    db_session.add(
        InvoiceLineItem(
            organization_id=org.id,
            invoice_id=invoice.id,
            description="Consulting",
            quantity=Decimal("1.00"),
            unit_price=Decimal("1.00"),
            line_total=Decimal("1.00"),
        )
    )
    db_session.commit()
    db_session.refresh(invoice)

    assert len(invoice.line_items) == 1
    assert invoice.line_items[0].description == "Consulting"


def test_line_item_to_public_dict_shape(db_session):
    user = _make_user()
    org = _make_org()
    db_session.add_all([user, org])
    db_session.flush()
    creator = _make_membership(org, user)
    customer = _make_customer(org)
    db_session.add_all([creator, customer])
    db_session.flush()
    invoice = _make_invoice(org, customer, creator)
    db_session.add(invoice)
    db_session.commit()
    item = InvoiceLineItem(
        organization_id=org.id,
        invoice_id=invoice.id,
        description="Consulting",
        quantity=Decimal("2.00"),
        unit_price=Decimal("150.00"),
        tax_rate=Decimal("8.25"),
        line_total=Decimal("300.00"),
    )
    db_session.add(item)
    db_session.commit()

    body = item.to_public_dict()

    assert body == {
        "id": str(item.id),
        "invoice_id": str(invoice.id),
        "description": "Consulting",
        "quantity": "2.00",
        "unit_price": "150.00",
        "tax_rate": "8.25",
        "line_total": "300.00",
        "created_at": item.created_at.isoformat(),
    }
