import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models import Department, DepartmentStatus, Membership, MembershipRole, Organization, User


@pytest.fixture
def db_session(app):
    with app.app_context():
        yield db.session
        db.session.rollback()
        db.session.query(Department).delete()
        db.session.query(Membership).delete()
        db.session.query(Organization).delete()
        db.session.query(User).delete()
        db.session.commit()


def _make_user(email="owner@example.com"):
    user = User(name="Org Owner", email=email)
    user.set_password("correct horse battery staple")
    return user


def _make_org(name="Acme Inc", slug="acme-inc"):
    return Organization(name=name, slug=slug)


def test_department_gets_a_uuid_primary_key_on_insert(db_session):
    org = _make_org()
    db_session.add(org)
    db_session.flush()

    department = Department(organization_id=org.id, name="Sales")
    db_session.add(department)
    db_session.commit()

    assert isinstance(department.id, uuid.UUID)


def test_department_status_defaults_to_active(db_session):
    org = _make_org()
    db_session.add(org)
    db_session.flush()

    department = Department(organization_id=org.id, name="Sales")
    db_session.add(department)
    db_session.commit()

    assert department.status == DepartmentStatus.ACTIVE


def test_department_status_is_stored_as_a_lowercase_value(db_session):
    org = _make_org()
    db_session.add(org)
    db_session.flush()

    department = Department(organization_id=org.id, name="Sales")
    db_session.add(department)
    db_session.commit()

    (status_raw,) = db_session.execute(
        text("SELECT status::text FROM departments WHERE id = :id"), {"id": department.id}
    ).one()
    assert status_raw == "active"


def test_department_description_and_manager_are_optional(db_session):
    org = _make_org()
    db_session.add(org)
    db_session.flush()

    department = Department(organization_id=org.id, name="Sales")
    db_session.add(department)
    db_session.commit()

    assert department.description is None
    assert department.manager_membership_id is None


def test_department_requires_a_name_at_the_database_level(db_session):
    org = _make_org()
    db_session.add(org)
    db_session.flush()

    department = Department(organization_id=org.id)
    db_session.add(department)

    with pytest.raises(IntegrityError):
        db_session.commit()


def test_department_name_is_trimmed(db_session):
    org = _make_org()
    db_session.add(org)
    db_session.flush()

    department = Department(organization_id=org.id, name="  Sales  ")
    db_session.add(department)
    db_session.commit()

    assert department.name == "Sales"


def test_department_rejects_a_blank_name(db_session):
    with pytest.raises(ValueError):
        Department(organization_id=uuid.uuid4(), name="   ")


def test_department_requires_a_real_organization(db_session):
    department = Department(organization_id=uuid.uuid4(), name="Sales")
    db_session.add(department)

    with pytest.raises(IntegrityError):
        db_session.commit()


def test_department_manager_must_be_a_real_membership(db_session):
    org = _make_org()
    db_session.add(org)
    db_session.flush()

    department = Department(organization_id=org.id, name="Sales", manager_membership_id=uuid.uuid4())
    db_session.add(department)

    with pytest.raises(IntegrityError):
        db_session.commit()


def test_department_can_have_a_manager_membership_assigned(db_session):
    user = _make_user()
    org = _make_org()
    db_session.add_all([user, org])
    db_session.flush()
    manager_membership = Membership(organization_id=org.id, user_id=user.id, role=MembershipRole.MANAGER)
    db_session.add(manager_membership)
    db_session.flush()

    department = Department(organization_id=org.id, name="Sales", manager_membership_id=manager_membership.id)
    db_session.add(department)
    db_session.commit()

    assert department.manager_membership_id == manager_membership.id


def test_deleting_a_managers_membership_clears_the_department_manager_instead_of_deleting_the_department(
    db_session,
):
    """SET NULL, not CASCADE (see Department's docstring): a department
    is organization history and must survive its manager's membership
    row being removed."""
    user = _make_user()
    org = _make_org()
    db_session.add_all([user, org])
    db_session.flush()
    manager_membership = Membership(organization_id=org.id, user_id=user.id, role=MembershipRole.MANAGER)
    db_session.add(manager_membership)
    db_session.flush()
    department = Department(organization_id=org.id, name="Sales", manager_membership_id=manager_membership.id)
    db_session.add(department)
    db_session.commit()
    department_id = department.id

    db_session.delete(manager_membership)
    db_session.commit()

    survivor = db_session.get(Department, department_id)
    assert survivor is not None
    assert survivor.manager_membership_id is None


def test_department_model_does_not_itself_block_a_manager_from_a_different_organization(db_session):
    """Documents a known, intentional gap (see Department's docstring):
    the model layer alone can't express "manager's membership must
    belong to this department's organization" without letting that FK's
    ON DELETE action null out the required organization_id too. FD-021's
    service layer is responsible for rejecting this case before it ever
    reaches here - this test exists so that responsibility is never
    silently assumed to already be covered at the model level."""
    user = _make_user()
    org_a = _make_org(name="Org A", slug="org-a-manager")
    org_b = _make_org(name="Org B", slug="org-b-manager")
    db_session.add_all([user, org_a, org_b])
    db_session.flush()
    membership_in_org_b = Membership(organization_id=org_b.id, user_id=user.id, role=MembershipRole.MANAGER)
    db_session.add(membership_in_org_b)
    db_session.flush()

    department = Department(organization_id=org_a.id, name="Sales", manager_membership_id=membership_in_org_b.id)
    db_session.add(department)
    db_session.commit()

    assert department.organization_id == org_a.id
    assert department.manager_membership_id == membership_in_org_b.id


def test_deleting_an_organization_cascades_to_its_departments(db_session):
    org = _make_org()
    db_session.add(org)
    db_session.flush()
    db_session.add(Department(organization_id=org.id, name="Sales"))
    db_session.commit()

    db_session.delete(org)
    db_session.commit()

    assert db_session.query(Department).count() == 0


def test_deleting_one_organizations_departments_does_not_touch_another_organizations(db_session):
    org_a = _make_org(name="Org A", slug="org-a-dept-isolation")
    org_b = _make_org(name="Org B", slug="org-b-dept-isolation")
    db_session.add_all([org_a, org_b])
    db_session.flush()
    db_session.add(Department(organization_id=org_a.id, name="Sales"))
    department_b = Department(organization_id=org_b.id, name="Support")
    db_session.add(department_b)
    db_session.commit()
    department_b_id = department_b.id

    db_session.delete(org_a)
    db_session.commit()

    survivor = db_session.get(Department, department_b_id)
    assert survivor is not None
    assert survivor.organization_id == org_b.id
    assert db_session.query(Department).filter_by(organization_id=org_a.id).count() == 0


def test_organization_relationship_exposes_its_departments(db_session):
    org = _make_org()
    db_session.add(org)
    db_session.flush()
    db_session.add(Department(organization_id=org.id, name="Sales"))
    db_session.commit()
    db_session.refresh(org)

    assert len(org.departments) == 1
    assert org.departments[0].name == "Sales"


def test_department_to_public_dict_shape(db_session):
    org = _make_org()
    db_session.add(org)
    db_session.flush()
    department = Department(organization_id=org.id, name="Sales", description="Revenue team")
    db_session.add(department)
    db_session.commit()

    body = department.to_public_dict()

    assert body == {
        "id": str(department.id),
        "organization_id": str(org.id),
        "name": "Sales",
        "description": "Revenue team",
        "manager_membership_id": None,
        "status": "active",
        "created_at": department.created_at.isoformat(),
    }
