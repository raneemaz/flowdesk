import uuid
from decimal import Decimal

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models import (
    Customer,
    Invoice,
    InvoiceLineItem,
    InvoiceStatus,
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


def test_invoice_gets_a_uuid_primary_key_on_insert(db_session):
    user = _make_user()
    org = _make_org()
    db_session.add_all([user, org])
    db_session.flush()
    creator = _make_membership(org, user)
    customer = _make_customer(org)
    db_session.add_all([creator, customer])
    db_session.flush()

    invoice = Invoice(
        organization_id=org.id, customer_id=customer.id, invoice_number="INV-0001", currency="USD", created_by=creator.id
    )
    db_session.add(invoice)
    db_session.commit()

    assert isinstance(invoice.id, uuid.UUID)


def test_invoice_status_defaults_to_draft(db_session):
    user = _make_user()
    org = _make_org()
    db_session.add_all([user, org])
    db_session.flush()
    creator = _make_membership(org, user)
    customer = _make_customer(org)
    db_session.add_all([creator, customer])
    db_session.flush()

    invoice = Invoice(
        organization_id=org.id, customer_id=customer.id, invoice_number="INV-0001", currency="USD", created_by=creator.id
    )
    db_session.add(invoice)
    db_session.commit()

    assert invoice.status == InvoiceStatus.DRAFT


def test_invoice_status_is_stored_as_a_lowercase_value(db_session):
    user = _make_user()
    org = _make_org()
    db_session.add_all([user, org])
    db_session.flush()
    creator = _make_membership(org, user)
    customer = _make_customer(org)
    db_session.add_all([creator, customer])
    db_session.flush()

    invoice = Invoice(
        organization_id=org.id, customer_id=customer.id, invoice_number="INV-0001", currency="USD", created_by=creator.id
    )
    db_session.add(invoice)
    db_session.commit()

    (status_raw,) = db_session.execute(
        text("SELECT status::text FROM invoices WHERE id = :id"), {"id": invoice.id}
    ).one()
    assert status_raw == "draft"


def test_invoice_money_fields_default_to_zero(db_session):
    user = _make_user()
    org = _make_org()
    db_session.add_all([user, org])
    db_session.flush()
    creator = _make_membership(org, user)
    customer = _make_customer(org)
    db_session.add_all([creator, customer])
    db_session.flush()

    invoice = Invoice(
        organization_id=org.id, customer_id=customer.id, invoice_number="INV-0001", currency="USD", created_by=creator.id
    )
    db_session.add(invoice)
    db_session.commit()
    db_session.refresh(invoice)

    assert invoice.subtotal == Decimal("0.00")
    assert invoice.tax_total == Decimal("0.00")
    assert invoice.discount_total == Decimal("0.00")
    assert invoice.total == Decimal("0.00")


def test_invoice_hours_store_exact_decimal_values(db_session):
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
        subtotal=Decimal("1234.56"),
        total=Decimal("1234.56"),
    )
    db_session.add(invoice)
    db_session.commit()
    db_session.refresh(invoice)

    assert invoice.subtotal == Decimal("1234.56")
    assert invoice.total == Decimal("1234.56")


def test_invoice_number_must_not_be_blank(db_session):
    user = _make_user()
    org = _make_org()
    db_session.add_all([user, org])
    db_session.flush()
    creator = _make_membership(org, user)
    customer = _make_customer(org)
    db_session.add_all([creator, customer])
    db_session.flush()

    with pytest.raises(ValueError):
        Invoice(organization_id=org.id, customer_id=customer.id, invoice_number="   ", currency="USD", created_by=creator.id)


def test_invoice_number_is_unique_per_organization(db_session):
    user = _make_user()
    org = _make_org()
    db_session.add_all([user, org])
    db_session.flush()
    creator = _make_membership(org, user)
    customer = _make_customer(org)
    db_session.add_all([creator, customer])
    db_session.flush()
    db_session.add(
        Invoice(organization_id=org.id, customer_id=customer.id, invoice_number="INV-0001", currency="USD", created_by=creator.id)
    )
    db_session.commit()

    db_session.add(
        Invoice(organization_id=org.id, customer_id=customer.id, invoice_number="INV-0001", currency="USD", created_by=creator.id)
    )
    with pytest.raises(IntegrityError):
        db_session.commit()


def test_invoice_number_can_repeat_across_different_organizations(db_session):
    user_a = _make_user(email="a@example.com")
    user_b = _make_user(email="b@example.com")
    org_a = _make_org(name="Org A", slug="org-a-invoice-number")
    org_b = _make_org(name="Org B", slug="org-b-invoice-number")
    db_session.add_all([user_a, user_b, org_a, org_b])
    db_session.flush()
    creator_a = _make_membership(org_a, user_a)
    creator_b = _make_membership(org_b, user_b)
    customer_a = _make_customer(org_a)
    customer_b = _make_customer(org_b)
    db_session.add_all([creator_a, creator_b, customer_a, customer_b])
    db_session.flush()
    db_session.add(
        Invoice(organization_id=org_a.id, customer_id=customer_a.id, invoice_number="INV-0001", currency="USD", created_by=creator_a.id)
    )
    db_session.add(
        Invoice(organization_id=org_b.id, customer_id=customer_b.id, invoice_number="INV-0001", currency="USD", created_by=creator_b.id)
    )

    db_session.commit()  # no IntegrityError - same number, different orgs


def test_invoice_requires_a_real_organization(db_session):
    user = _make_user()
    org = _make_org()
    db_session.add_all([user, org])
    db_session.flush()
    creator = _make_membership(org, user)
    customer = _make_customer(org)
    db_session.add_all([creator, customer])
    db_session.flush()

    invoice = Invoice(
        organization_id=uuid.uuid4(), customer_id=customer.id, invoice_number="INV-0001", currency="USD", created_by=creator.id
    )
    db_session.add(invoice)

    with pytest.raises(IntegrityError):
        db_session.commit()


def test_invoice_creator_must_be_a_real_membership(db_session):
    org = _make_org()
    db_session.add(org)
    db_session.flush()
    customer = _make_customer(org)
    db_session.add(customer)
    db_session.flush()

    invoice = Invoice(
        organization_id=org.id, customer_id=customer.id, invoice_number="INV-0001", currency="USD", created_by=uuid.uuid4()
    )
    db_session.add(invoice)

    with pytest.raises(IntegrityError):
        db_session.commit()


def test_invoice_requires_a_real_customer(db_session):
    user = _make_user()
    org = _make_org()
    db_session.add_all([user, org])
    db_session.flush()
    creator = _make_membership(org, user)
    db_session.add(creator)
    db_session.flush()

    invoice = Invoice(
        organization_id=org.id, customer_id=uuid.uuid4(), invoice_number="INV-0001", currency="USD", created_by=creator.id
    )
    db_session.add(invoice)

    with pytest.raises(IntegrityError):
        db_session.commit()


def test_invoice_creator_organization_id_must_match_its_memberships_organization(db_session):
    user = _make_user()
    org_a = _make_org(name="Org A", slug="org-a-invoice-creator")
    org_b = _make_org(name="Org B", slug="org-b-invoice-creator")
    db_session.add_all([user, org_a, org_b])
    db_session.flush()
    creator_in_org_a = _make_membership(org_a, user)
    customer_in_org_b = _make_customer(org_b)
    db_session.add_all([creator_in_org_a, customer_in_org_b])
    db_session.flush()

    invoice = Invoice(
        organization_id=org_b.id,
        customer_id=customer_in_org_b.id,
        invoice_number="INV-0001",
        currency="USD",
        created_by=creator_in_org_a.id,
    )
    db_session.add(invoice)

    with pytest.raises(IntegrityError):
        db_session.commit()


def test_invoice_customer_organization_id_must_match_its_customers_organization(db_session):
    """The composite FK's real payoff, mirroring CustomerRequest.customer_id's
    own test (FD-036): a customer_id from a different organization than
    the invoice's own organization_id is rejected at the DB level."""
    user = _make_user()
    org_a = _make_org(name="Org A", slug="org-a-invoice-customer")
    org_b = _make_org(name="Org B", slug="org-b-invoice-customer")
    db_session.add_all([user, org_a, org_b])
    db_session.flush()
    creator_in_org_a = _make_membership(org_a, user)
    customer_in_org_b = _make_customer(org_b)
    db_session.add_all([creator_in_org_a, customer_in_org_b])
    db_session.flush()

    invoice = Invoice(
        organization_id=org_a.id,
        customer_id=customer_in_org_b.id,
        invoice_number="INV-0001",
        currency="USD",
        created_by=creator_in_org_a.id,
    )
    db_session.add(invoice)

    with pytest.raises(IntegrityError):
        db_session.commit()


def test_deleting_the_creators_membership_is_blocked_while_it_still_has_invoices(db_session):
    user = _make_user()
    org = _make_org()
    db_session.add_all([user, org])
    db_session.flush()
    creator = _make_membership(org, user)
    customer = _make_customer(org)
    db_session.add_all([creator, customer])
    db_session.flush()
    db_session.add(
        Invoice(organization_id=org.id, customer_id=customer.id, invoice_number="INV-0001", currency="USD", created_by=creator.id)
    )
    db_session.commit()

    db_session.delete(creator)
    with pytest.raises(IntegrityError):
        db_session.commit()


def test_deleting_the_customer_is_blocked_while_it_still_has_invoices(db_session):
    """The customer_id composite FK's RESTRICT, mirroring CustomerRequest's
    own equivalent test - financial history must never silently
    disappear (spec Section 10.3 rule #5, explicit about financial
    records)."""
    user = _make_user()
    org = _make_org()
    db_session.add_all([user, org])
    db_session.flush()
    creator = _make_membership(org, user)
    customer = _make_customer(org)
    db_session.add_all([creator, customer])
    db_session.flush()
    db_session.add(
        Invoice(organization_id=org.id, customer_id=customer.id, invoice_number="INV-0001", currency="USD", created_by=creator.id)
    )
    db_session.commit()

    db_session.delete(customer)
    with pytest.raises(IntegrityError):
        db_session.commit()


def test_deleting_an_organization_cascades_to_its_invoices(db_session):
    user = _make_user()
    org = _make_org()
    db_session.add_all([user, org])
    db_session.flush()
    creator = _make_membership(org, user)
    customer = _make_customer(org)
    db_session.add_all([creator, customer])
    db_session.flush()
    db_session.add(
        Invoice(organization_id=org.id, customer_id=customer.id, invoice_number="INV-0001", currency="USD", created_by=creator.id)
    )
    db_session.commit()

    db_session.delete(org)
    db_session.commit()

    assert db_session.query(Invoice).count() == 0


def test_deleting_one_organizations_invoices_does_not_touch_another_organizations(db_session):
    user_a = _make_user(email="user-a@example.com")
    user_b = _make_user(email="user-b@example.com")
    org_a = _make_org(name="Org A", slug="org-a-invoice-isolation")
    org_b = _make_org(name="Org B", slug="org-b-invoice-isolation")
    db_session.add_all([user_a, user_b, org_a, org_b])
    db_session.flush()
    creator_a = _make_membership(org_a, user_a)
    creator_b = _make_membership(org_b, user_b)
    customer_a = _make_customer(org_a, name="Org A customer")
    customer_b = _make_customer(org_b, name="Org B customer")
    db_session.add_all([creator_a, creator_b, customer_a, customer_b])
    db_session.flush()
    db_session.add(
        Invoice(organization_id=org_a.id, customer_id=customer_a.id, invoice_number="A-1", currency="USD", created_by=creator_a.id)
    )
    invoice_b = Invoice(
        organization_id=org_b.id, customer_id=customer_b.id, invoice_number="B-1", currency="USD", created_by=creator_b.id
    )
    db_session.add(invoice_b)
    db_session.commit()
    invoice_b_id = invoice_b.id

    db_session.delete(org_a)
    db_session.commit()

    survivor = db_session.get(Invoice, invoice_b_id)
    assert survivor is not None
    assert survivor.organization_id == org_b.id
    assert db_session.query(Invoice).filter_by(organization_id=org_a.id).count() == 0


def test_invoice_to_public_dict_shape(db_session):
    user = _make_user()
    org = _make_org()
    db_session.add_all([user, org])
    db_session.flush()
    creator = _make_membership(org, user)
    customer = _make_customer(org)
    db_session.add_all([creator, customer])
    db_session.flush()
    invoice = Invoice(
        organization_id=org.id, customer_id=customer.id, invoice_number="INV-0001", currency="USD", created_by=creator.id
    )
    db_session.add(invoice)
    db_session.commit()
    db_session.refresh(invoice)

    body = invoice.to_public_dict()

    assert body == {
        "id": str(invoice.id),
        "organization_id": str(org.id),
        "customer_id": str(customer.id),
        "invoice_number": "INV-0001",
        "status": "draft",
        "issue_date": None,
        "due_date": None,
        "currency": "USD",
        "subtotal": "0.00",
        "tax_total": "0.00",
        "discount_type": "flat",
        "discount_value": "0.00",
        "discount_total": "0.00",
        "total": "0.00",
        "notes": None,
        "payment_terms": None,
        "created_by": str(creator.id),
        "created_at": invoice.created_at.isoformat(),
    }


def test_customer_relationship_exposes_its_invoices(db_session):
    user = _make_user()
    org = _make_org()
    db_session.add_all([user, org])
    db_session.flush()
    creator = _make_membership(org, user)
    customer = _make_customer(org)
    db_session.add_all([creator, customer])
    db_session.flush()
    invoice = Invoice(
        organization_id=org.id, customer_id=customer.id, invoice_number="INV-0001", currency="USD", created_by=creator.id
    )
    db_session.add(invoice)
    db_session.commit()
    db_session.refresh(customer)

    assert len(customer.invoices) == 1
    assert customer.invoices[0].id == invoice.id
