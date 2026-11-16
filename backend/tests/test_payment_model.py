import uuid
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models import Customer, Invoice, Membership, MembershipRole, Organization, Payment, User


@pytest.fixture
def db_session(app):
    with app.app_context():
        yield db.session
        db.session.rollback()
        db.session.query(Payment).delete()
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


def test_payment_gets_a_uuid_primary_key_on_insert(db_session):
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

    payment = Payment(
        organization_id=org.id,
        invoice_id=invoice.id,
        amount=Decimal("100.00"),
        payment_date=date(2026, 1, 1),
        method="bank_transfer",
        recorded_by=creator.id,
        idempotency_key="test-key-1",
    )
    db_session.add(payment)
    db_session.commit()

    assert isinstance(payment.id, uuid.UUID)


def test_payment_reference_and_notes_are_optional(db_session):
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

    payment = Payment(
        organization_id=org.id,
        invoice_id=invoice.id,
        amount=Decimal("100.00"),
        payment_date=date(2026, 1, 1),
        method="cash",
        recorded_by=creator.id,
        idempotency_key="test-key-1",
    )
    db_session.add(payment)
    db_session.commit()

    assert payment.reference is None
    assert payment.notes is None


def test_payment_stores_exact_decimal_amount(db_session):
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

    payment = Payment(
        organization_id=org.id,
        invoice_id=invoice.id,
        amount=Decimal("1234.56"),
        payment_date=date(2026, 1, 1),
        method="check",
        reference="CHK-001",
        recorded_by=creator.id,
        idempotency_key="test-key-1",
    )
    db_session.add(payment)
    db_session.commit()
    db_session.refresh(payment)

    assert payment.amount == Decimal("1234.56")


def test_payment_method_must_not_be_blank(db_session):
    with pytest.raises(ValueError):
        Payment(
            organization_id=uuid.uuid4(),
            invoice_id=uuid.uuid4(),
            amount=Decimal("1.00"),
            payment_date=date(2026, 1, 1),
            method="   ",
            recorded_by=uuid.uuid4(),
            idempotency_key="test-key-1",
        )


def test_payment_idempotency_key_must_not_be_blank(db_session):
    with pytest.raises(ValueError):
        Payment(
            organization_id=uuid.uuid4(),
            invoice_id=uuid.uuid4(),
            amount=Decimal("1.00"),
            payment_date=date(2026, 1, 1),
            method="cash",
            recorded_by=uuid.uuid4(),
            idempotency_key="   ",
        )


def test_payment_requires_a_real_invoice(db_session):
    org = _make_org()
    db_session.add(org)
    db_session.flush()

    payment = Payment(
        organization_id=org.id,
        invoice_id=uuid.uuid4(),
        amount=Decimal("1.00"),
        payment_date=date(2026, 1, 1),
        method="cash",
        recorded_by=uuid.uuid4(),
        idempotency_key="test-key-1",
    )
    db_session.add(payment)

    with pytest.raises(IntegrityError):
        db_session.commit()


def test_payment_requires_a_real_recorder_membership(db_session):
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

    payment = Payment(
        organization_id=org.id,
        invoice_id=invoice.id,
        amount=Decimal("1.00"),
        payment_date=date(2026, 1, 1),
        method="cash",
        recorded_by=uuid.uuid4(),
        idempotency_key="test-key-1",
    )
    db_session.add(payment)

    with pytest.raises(IntegrityError):
        db_session.commit()


def test_payment_organization_id_must_match_its_invoices_organization(db_session):
    user = _make_user()
    org_a = _make_org(name="Org A", slug="org-a-payment-mismatch")
    org_b = _make_org(name="Org B", slug="org-b-payment-mismatch")
    db_session.add_all([user, org_a, org_b])
    db_session.flush()
    creator = _make_membership(org_a, user)
    customer = _make_customer(org_a)
    db_session.add_all([creator, customer])
    db_session.flush()
    invoice_in_org_a = _make_invoice(org_a, customer, creator)
    db_session.add(invoice_in_org_a)
    db_session.commit()

    payment = Payment(
        organization_id=org_b.id,
        invoice_id=invoice_in_org_a.id,
        amount=Decimal("1.00"),
        payment_date=date(2026, 1, 1),
        method="cash",
        recorded_by=creator.id,
        idempotency_key="test-key-1",
    )
    db_session.add(payment)

    with pytest.raises(IntegrityError):
        db_session.commit()


def test_payment_recorder_organization_id_must_match_its_memberships_organization(db_session):
    user = _make_user()
    org_a = _make_org(name="Org A", slug="org-a-payment-recorder")
    org_b = _make_org(name="Org B", slug="org-b-payment-recorder")
    db_session.add_all([user, org_a, org_b])
    db_session.flush()
    creator_in_org_a = _make_membership(org_a, user)
    customer_in_org_a = _make_customer(org_a)
    db_session.add_all([creator_in_org_a, customer_in_org_a])
    db_session.flush()
    invoice_in_org_a = _make_invoice(org_a, customer_in_org_a, creator_in_org_a)
    db_session.add(invoice_in_org_a)
    db_session.commit()

    recorder_in_org_b = _make_membership(org_b, user)
    db_session.add(recorder_in_org_b)
    db_session.flush()

    payment = Payment(
        organization_id=org_a.id,
        invoice_id=invoice_in_org_a.id,
        amount=Decimal("1.00"),
        payment_date=date(2026, 1, 1),
        method="cash",
        recorded_by=recorder_in_org_b.id,
        idempotency_key="test-key-1",
    )
    db_session.add(payment)

    with pytest.raises(IntegrityError):
        db_session.commit()


def test_deleting_the_recorders_membership_is_blocked_while_it_still_has_payments(db_session):
    """RESTRICT, mirroring Invoice.created_by's own test - who recorded
    a payment is audit-relevant financial history."""
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
        Payment(
            organization_id=org.id,
            invoice_id=invoice.id,
            amount=Decimal("1.00"),
            payment_date=date(2026, 1, 1),
            method="cash",
            recorded_by=creator.id,
            idempotency_key="test-key-1",
        )
    )
    db_session.commit()

    db_session.delete(creator)
    with pytest.raises(IntegrityError):
        db_session.commit()


def test_deleting_an_invoice_cascades_to_its_payments(db_session):
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
        Payment(
            organization_id=org.id,
            invoice_id=invoice.id,
            amount=Decimal("1.00"),
            payment_date=date(2026, 1, 1),
            method="cash",
            recorded_by=creator.id,
            idempotency_key="test-key-1",
        )
    )
    db_session.commit()

    db_session.delete(invoice)
    db_session.commit()

    assert db_session.query(Payment).count() == 0


def test_invoice_relationship_exposes_its_payments(db_session):
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
        Payment(
            organization_id=org.id,
            invoice_id=invoice.id,
            amount=Decimal("1.00"),
            payment_date=date(2026, 1, 1),
            method="cash",
            recorded_by=creator.id,
            idempotency_key="test-key-1",
        )
    )
    db_session.commit()
    db_session.refresh(invoice)

    assert len(invoice.payments) == 1
    assert invoice.payments[0].method == "cash"


def test_payment_idempotency_key_is_unique_per_organization(db_session):
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
        Payment(
            organization_id=org.id,
            invoice_id=invoice.id,
            amount=Decimal("1.00"),
            payment_date=date(2026, 1, 1),
            method="cash",
            recorded_by=creator.id,
            idempotency_key="duplicate-key",
        )
    )
    db_session.commit()

    db_session.add(
        Payment(
            organization_id=org.id,
            invoice_id=invoice.id,
            amount=Decimal("2.00"),
            payment_date=date(2026, 1, 2),
            method="cash",
            recorded_by=creator.id,
            idempotency_key="duplicate-key",
        )
    )
    with pytest.raises(IntegrityError):
        db_session.commit()


def test_payment_idempotency_key_can_repeat_across_different_organizations(db_session):
    user_a = _make_user(email="usera@example.com")
    user_b = _make_user(email="userb@example.com")
    org_a = _make_org(name="Org A", slug="org-a-payment-key")
    org_b = _make_org(name="Org B", slug="org-b-payment-key")
    db_session.add_all([user_a, user_b, org_a, org_b])
    db_session.flush()
    creator_a = _make_membership(org_a, user_a)
    creator_b = _make_membership(org_b, user_b)
    customer_a = _make_customer(org_a)
    customer_b = _make_customer(org_b)
    db_session.add_all([creator_a, creator_b, customer_a, customer_b])
    db_session.flush()
    invoice_a = _make_invoice(org_a, customer_a, creator_a)
    invoice_b = _make_invoice(org_b, customer_b, creator_b)
    db_session.add_all([invoice_a, invoice_b])
    db_session.commit()

    db_session.add(
        Payment(
            organization_id=org_a.id,
            invoice_id=invoice_a.id,
            amount=Decimal("1.00"),
            payment_date=date(2026, 1, 1),
            method="cash",
            recorded_by=creator_a.id,
            idempotency_key="shared-key",
        )
    )
    db_session.add(
        Payment(
            organization_id=org_b.id,
            invoice_id=invoice_b.id,
            amount=Decimal("1.00"),
            payment_date=date(2026, 1, 1),
            method="cash",
            recorded_by=creator_b.id,
            idempotency_key="shared-key",
        )
    )

    db_session.commit()  # no IntegrityError - same key, different orgs


def test_payment_to_public_dict_shape(db_session):
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
    payment = Payment(
        organization_id=org.id,
        invoice_id=invoice.id,
        amount=Decimal("100.00"),
        payment_date=date(2026, 1, 1),
        method="bank_transfer",
        reference="TXN-1",
        notes="Paid in full",
        recorded_by=creator.id,
        idempotency_key="test-key-1",
    )
    db_session.add(payment)
    db_session.commit()

    body = payment.to_public_dict()

    assert body == {
        "id": str(payment.id),
        "invoice_id": str(invoice.id),
        "amount": "100.00",
        "payment_date": "2026-01-01",
        "method": "bank_transfer",
        "reference": "TXN-1",
        "notes": "Paid in full",
        "idempotency_key": "test-key-1",
        "recorded_by": str(creator.id),
        "created_at": payment.created_at.isoformat(),
    }
