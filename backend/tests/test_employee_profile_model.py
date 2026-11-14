import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models import Department, EmployeeProfile, EmployeeStatus, Membership, MembershipRole, Organization, User


@pytest.fixture
def db_session(app):
    with app.app_context():
        yield db.session
        db.session.rollback()
        db.session.query(EmployeeProfile).delete()
        db.session.query(Department).delete()
        db.session.query(Membership).delete()
        db.session.query(Organization).delete()
        db.session.query(User).delete()
        db.session.commit()


def _make_user(email="employee@example.com"):
    user = User(name="An Employee", email=email)
    user.set_password("correct horse battery staple")
    return user


def _make_org(name="Acme Inc", slug="acme-inc"):
    return Organization(name=name, slug=slug)


def _make_membership(org, user, role=MembershipRole.EMPLOYEE):
    return Membership(organization_id=org.id, user_id=user.id, role=role)


def test_employee_profile_gets_a_uuid_primary_key_on_insert(db_session):
    user = _make_user()
    org = _make_org()
    db_session.add_all([user, org])
    db_session.flush()
    membership = _make_membership(org, user)
    db_session.add(membership)
    db_session.flush()

    profile = EmployeeProfile(organization_id=org.id, membership_id=membership.id)
    db_session.add(profile)
    db_session.commit()

    assert isinstance(profile.id, uuid.UUID)


def test_employee_profile_status_defaults_to_active(db_session):
    user = _make_user()
    org = _make_org()
    db_session.add_all([user, org])
    db_session.flush()
    membership = _make_membership(org, user)
    db_session.add(membership)
    db_session.flush()

    profile = EmployeeProfile(organization_id=org.id, membership_id=membership.id)
    db_session.add(profile)
    db_session.commit()

    assert profile.status == EmployeeStatus.ACTIVE


def test_employee_profile_status_is_stored_as_a_lowercase_value(db_session):
    user = _make_user()
    org = _make_org()
    db_session.add_all([user, org])
    db_session.flush()
    membership = _make_membership(org, user)
    db_session.add(membership)
    db_session.flush()

    profile = EmployeeProfile(organization_id=org.id, membership_id=membership.id)
    db_session.add(profile)
    db_session.commit()

    (status_raw,) = db_session.execute(
        text("SELECT status::text FROM employee_profiles WHERE id = :id"), {"id": profile.id}
    ).one()
    assert status_raw == "active"


def test_employee_profile_job_title_department_and_manager_are_optional(db_session):
    user = _make_user()
    org = _make_org()
    db_session.add_all([user, org])
    db_session.flush()
    membership = _make_membership(org, user)
    db_session.add(membership)
    db_session.flush()

    profile = EmployeeProfile(organization_id=org.id, membership_id=membership.id)
    db_session.add(profile)
    db_session.commit()

    assert profile.job_title is None
    assert profile.department_id is None
    assert profile.manager_membership_id is None


def test_employee_profile_requires_a_real_organization(db_session):
    user = _make_user()
    org = _make_org()
    db_session.add_all([user, org])
    db_session.flush()
    membership = _make_membership(org, user)
    db_session.add(membership)
    db_session.flush()

    profile = EmployeeProfile(organization_id=uuid.uuid4(), membership_id=membership.id)
    db_session.add(profile)

    with pytest.raises(IntegrityError):
        db_session.commit()


def test_employee_profile_requires_a_real_membership(db_session):
    org = _make_org()
    db_session.add(org)
    db_session.flush()

    profile = EmployeeProfile(organization_id=org.id, membership_id=uuid.uuid4())
    db_session.add(profile)

    with pytest.raises(IntegrityError):
        db_session.commit()


def test_employee_profile_organization_id_must_match_its_memberships_organization(db_session):
    """The composite FK's real payoff: unlike Department.manager_membership_id
    (FD-019), this cross-tenant mismatch IS rejected at the DB level,
    not just deferred to a future service layer - organization_id and
    membership_id must jointly resolve to a real (membership.id,
    membership.organization_id) pair."""
    user = _make_user()
    org_a = _make_org(name="Org A", slug="org-a-mismatch")
    org_b = _make_org(name="Org B", slug="org-b-mismatch")
    db_session.add_all([user, org_a, org_b])
    db_session.flush()
    membership_in_org_a = _make_membership(org_a, user)
    db_session.add(membership_in_org_a)
    db_session.flush()

    # organization_id (org_b) does not match membership_in_org_a's real
    # organization (org_a) - no row in memberships has this (id, org_id)
    # pair, so the composite FK must reject it.
    profile = EmployeeProfile(organization_id=org_b.id, membership_id=membership_in_org_a.id)
    db_session.add(profile)

    with pytest.raises(IntegrityError):
        db_session.commit()


def test_employee_profile_membership_id_must_be_unique(db_session):
    user = _make_user()
    org = _make_org()
    db_session.add_all([user, org])
    db_session.flush()
    membership = _make_membership(org, user)
    db_session.add(membership)
    db_session.flush()
    db_session.add(EmployeeProfile(organization_id=org.id, membership_id=membership.id))
    db_session.commit()

    db_session.add(EmployeeProfile(organization_id=org.id, membership_id=membership.id))
    with pytest.raises(IntegrityError):
        db_session.commit()


def test_employee_profile_department_must_be_a_real_department(db_session):
    user = _make_user()
    org = _make_org()
    db_session.add_all([user, org])
    db_session.flush()
    membership = _make_membership(org, user)
    db_session.add(membership)
    db_session.flush()

    profile = EmployeeProfile(organization_id=org.id, membership_id=membership.id, department_id=uuid.uuid4())
    db_session.add(profile)

    with pytest.raises(IntegrityError):
        db_session.commit()


def test_employee_profile_manager_must_be_a_real_membership(db_session):
    user = _make_user()
    org = _make_org()
    db_session.add_all([user, org])
    db_session.flush()
    membership = _make_membership(org, user)
    db_session.add(membership)
    db_session.flush()

    profile = EmployeeProfile(
        organization_id=org.id, membership_id=membership.id, manager_membership_id=uuid.uuid4()
    )
    db_session.add(profile)

    with pytest.raises(IntegrityError):
        db_session.commit()


def test_employee_profile_model_does_not_itself_block_a_manager_from_a_different_organization(db_session):
    """Documents the same intentional gap as Department.manager_membership_id
    (FD-019): manager_membership_id is a simple (non-composite) FK, so
    the model layer alone doesn't enforce the manager belongs to this
    employee's organization - a future service layer (FD-022/FD-023) is
    responsible for that check."""
    manager_user = _make_user(email="manager@example.com")
    employee_user = _make_user(email="other-org-employee@example.com")
    org_a = _make_org(name="Org A", slug="org-a-emp-manager")
    org_b = _make_org(name="Org B", slug="org-b-emp-manager")
    db_session.add_all([manager_user, employee_user, org_a, org_b])
    db_session.flush()
    manager_membership_in_org_b = _make_membership(org_b, manager_user, role=MembershipRole.MANAGER)
    employee_membership_in_org_a = _make_membership(org_a, employee_user)
    db_session.add_all([manager_membership_in_org_b, employee_membership_in_org_a])
    db_session.flush()

    profile = EmployeeProfile(
        organization_id=org_a.id,
        membership_id=employee_membership_in_org_a.id,
        manager_membership_id=manager_membership_in_org_b.id,
    )
    db_session.add(profile)
    db_session.commit()

    assert profile.manager_membership_id == manager_membership_in_org_b.id


def test_deleting_a_membership_cascades_to_its_employee_profile(db_session):
    """CASCADE, not SET NULL: an EmployeeProfile has no identity
    independent of its Membership."""
    user = _make_user()
    org = _make_org()
    db_session.add_all([user, org])
    db_session.flush()
    membership = _make_membership(org, user)
    db_session.add(membership)
    db_session.flush()
    profile = EmployeeProfile(organization_id=org.id, membership_id=membership.id)
    db_session.add(profile)
    db_session.commit()

    db_session.delete(membership)
    db_session.commit()

    assert db_session.query(EmployeeProfile).count() == 0


def test_deleting_a_department_clears_the_employee_profiles_department_instead_of_deleting_the_profile(
    db_session,
):
    user = _make_user()
    org = _make_org()
    db_session.add_all([user, org])
    db_session.flush()
    membership = _make_membership(org, user)
    department = Department(organization_id=org.id, name="Sales")
    db_session.add_all([membership, department])
    db_session.flush()
    profile = EmployeeProfile(organization_id=org.id, membership_id=membership.id, department_id=department.id)
    db_session.add(profile)
    db_session.commit()
    profile_id = profile.id

    db_session.delete(department)
    db_session.commit()

    survivor = db_session.get(EmployeeProfile, profile_id)
    assert survivor is not None
    assert survivor.department_id is None


def test_deleting_a_managers_membership_clears_the_employee_profiles_manager_instead_of_deleting_the_profile(
    db_session,
):
    manager_user = _make_user(email="manager@example.com")
    employee_user = _make_user(email="employee2@example.com")
    org = _make_org()
    db_session.add_all([manager_user, employee_user, org])
    db_session.flush()
    manager_membership = _make_membership(org, manager_user, role=MembershipRole.MANAGER)
    employee_membership = _make_membership(org, employee_user)
    db_session.add_all([manager_membership, employee_membership])
    db_session.flush()
    profile = EmployeeProfile(
        organization_id=org.id, membership_id=employee_membership.id, manager_membership_id=manager_membership.id
    )
    db_session.add(profile)
    db_session.commit()
    profile_id = profile.id

    db_session.delete(manager_membership)
    db_session.commit()

    survivor = db_session.get(EmployeeProfile, profile_id)
    assert survivor is not None
    assert survivor.manager_membership_id is None


def test_deleting_an_organization_cascades_to_its_employee_profiles(db_session):
    user = _make_user()
    org = _make_org()
    db_session.add_all([user, org])
    db_session.flush()
    membership = _make_membership(org, user)
    db_session.add(membership)
    db_session.flush()
    db_session.add(EmployeeProfile(organization_id=org.id, membership_id=membership.id))
    db_session.commit()

    db_session.delete(org)
    db_session.commit()

    assert db_session.query(EmployeeProfile).count() == 0


def test_deleting_one_organizations_employee_profiles_does_not_touch_another_organizations(db_session):
    user_a = _make_user(email="user-a@example.com")
    user_b = _make_user(email="user-b@example.com")
    org_a = _make_org(name="Org A", slug="org-a-profile-isolation")
    org_b = _make_org(name="Org B", slug="org-b-profile-isolation")
    db_session.add_all([user_a, user_b, org_a, org_b])
    db_session.flush()
    membership_a = _make_membership(org_a, user_a)
    membership_b = _make_membership(org_b, user_b)
    db_session.add_all([membership_a, membership_b])
    db_session.flush()
    db_session.add(EmployeeProfile(organization_id=org_a.id, membership_id=membership_a.id))
    profile_b = EmployeeProfile(organization_id=org_b.id, membership_id=membership_b.id)
    db_session.add(profile_b)
    db_session.commit()
    profile_b_id = profile_b.id

    db_session.delete(org_a)
    db_session.commit()

    survivor = db_session.get(EmployeeProfile, profile_b_id)
    assert survivor is not None
    assert survivor.organization_id == org_b.id
    assert db_session.query(EmployeeProfile).filter_by(organization_id=org_a.id).count() == 0


def test_membership_relationship_exposes_its_employee_profile(db_session):
    user = _make_user()
    org = _make_org()
    db_session.add_all([user, org])
    db_session.flush()
    membership = _make_membership(org, user)
    db_session.add(membership)
    db_session.flush()
    db_session.add(EmployeeProfile(organization_id=org.id, membership_id=membership.id, job_title="Engineer"))
    db_session.commit()
    db_session.refresh(membership)

    assert membership.employee_profile is not None
    assert membership.employee_profile.job_title == "Engineer"


def test_department_relationship_exposes_its_employee_profiles(db_session):
    user = _make_user()
    org = _make_org()
    db_session.add_all([user, org])
    db_session.flush()
    membership = _make_membership(org, user)
    department = Department(organization_id=org.id, name="Sales")
    db_session.add_all([membership, department])
    db_session.flush()
    db_session.add(EmployeeProfile(organization_id=org.id, membership_id=membership.id, department_id=department.id))
    db_session.commit()
    db_session.refresh(department)

    assert len(department.employee_profiles) == 1


def test_employee_profile_to_public_dict_shape(db_session):
    user = _make_user()
    org = _make_org()
    db_session.add_all([user, org])
    db_session.flush()
    membership = _make_membership(org, user)
    db_session.add(membership)
    db_session.flush()
    profile = EmployeeProfile(organization_id=org.id, membership_id=membership.id, job_title="Engineer")
    db_session.add(profile)
    db_session.commit()

    body = profile.to_public_dict()

    assert body == {
        "id": str(profile.id),
        "organization_id": str(org.id),
        "membership_id": str(membership.id),
        "department_id": None,
        "manager_membership_id": None,
        "job_title": "Engineer",
        "status": "active",
        "created_at": profile.created_at.isoformat(),
    }
