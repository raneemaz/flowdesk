import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models import Customer, CustomerStatus, Organization


@pytest.fixture
def db_session(app):
    with app.app_context():
        yield db.session
        db.session.rollback()
        db.session.query(Customer).delete()
        db.session.query(Organization).delete()
        db.session.commit()


def _make_org(name="Acme Inc", slug="acme-inc"):
    return Organization(name=name, slug=slug)


def test_customer_gets_a_uuid_primary_key_on_insert(db_session):
    org = _make_org()
    db_session.add(org)
    db_session.flush()

    customer = Customer(organization_id=org.id, name="Jane Customer")
    db_session.add(customer)
    db_session.commit()

    assert isinstance(customer.id, uuid.UUID)


def test_customer_status_defaults_to_active(db_session):
    org = _make_org()
    db_session.add(org)
    db_session.flush()

    customer = Customer(organization_id=org.id, name="Jane Customer")
    db_session.add(customer)
    db_session.commit()

    assert customer.status == CustomerStatus.ACTIVE


def test_customer_status_is_stored_as_a_lowercase_value(db_session):
    org = _make_org()
    db_session.add(org)
    db_session.flush()

    customer = Customer(organization_id=org.id, name="Jane Customer")
    db_session.add(customer)
    db_session.commit()

    (status_raw,) = db_session.execute(text("SELECT status::text FROM customers WHERE id = :id"), {"id": customer.id}).one()
    assert status_raw == "active"


def test_customer_name_must_not_be_blank(db_session):
    org = _make_org()
    db_session.add(org)
    db_session.flush()

    with pytest.raises(ValueError):
        Customer(organization_id=org.id, name="   ")


def test_customer_optional_fields_default_to_none(db_session):
    org = _make_org()
    db_session.add(org)
    db_session.flush()

    customer = Customer(organization_id=org.id, name="Jane Customer")
    db_session.add(customer)
    db_session.commit()

    assert customer.email is None
    assert customer.phone is None
    assert customer.company is None
    assert customer.address is None
    assert customer.notes is None


def test_customer_requires_a_real_organization(db_session):
    customer = Customer(organization_id=uuid.uuid4(), name="Jane Customer")
    db_session.add(customer)

    with pytest.raises(IntegrityError):
        db_session.commit()


def test_deleting_an_organization_cascades_to_its_customers(db_session):
    org = _make_org()
    db_session.add(org)
    db_session.flush()
    db_session.add(Customer(organization_id=org.id, name="Jane Customer"))
    db_session.commit()

    db_session.delete(org)
    db_session.commit()

    assert db_session.query(Customer).count() == 0


def test_deleting_one_organizations_customers_does_not_touch_another_organizations(db_session):
    org_a = _make_org(name="Org A", slug="org-a-customer-isolation")
    org_b = _make_org(name="Org B", slug="org-b-customer-isolation")
    db_session.add_all([org_a, org_b])
    db_session.flush()
    db_session.add(Customer(organization_id=org_a.id, name="Org A customer"))
    customer_b = Customer(organization_id=org_b.id, name="Org B customer")
    db_session.add(customer_b)
    db_session.commit()
    customer_b_id = customer_b.id

    db_session.delete(org_a)
    db_session.commit()

    survivor = db_session.get(Customer, customer_b_id)
    assert survivor is not None
    assert survivor.organization_id == org_b.id
    assert db_session.query(Customer).filter_by(organization_id=org_a.id).count() == 0


def test_customer_id_organization_id_pair_must_be_unique():
    """Documents the composite UniqueConstraint this model adds
    specifically so FD-036's CustomerRequest can later compose a
    same-organization-enforcing FK against it, the same way
    TaskComment/TaskHistory do against Task (FD-025) - a plain
    metadata-level check, no DB round-trip needed."""
    constraint_columns = {
        tuple(col.name for col in constraint.columns)
        for constraint in Customer.__table__.constraints
        if constraint.name == "uq_customers_id_organization_id"
    }
    assert constraint_columns == {("id", "organization_id")}


def test_customer_to_public_dict_shape(db_session):
    org = _make_org()
    db_session.add(org)
    db_session.flush()
    customer = Customer(
        organization_id=org.id,
        name="Jane Customer",
        email="jane@example.com",
        phone="555-1234",
        company="Jane's Bakery",
        address="1 Main St",
        notes="Prefers email contact",
    )
    db_session.add(customer)
    db_session.commit()

    body = customer.to_public_dict()

    assert body == {
        "id": str(customer.id),
        "organization_id": str(org.id),
        "name": "Jane Customer",
        "email": "jane@example.com",
        "phone": "555-1234",
        "company": "Jane's Bakery",
        "address": "1 Main St",
        "notes": "Prefers email contact",
        "status": "active",
        "created_at": customer.created_at.isoformat(),
    }


def test_customer_relationship_exposes_its_organization(db_session):
    org = _make_org()
    db_session.add(org)
    db_session.flush()
    customer = Customer(organization_id=org.id, name="Jane Customer")
    db_session.add(customer)
    db_session.commit()

    assert customer.organization.id == org.id
    assert customer in org.customers
