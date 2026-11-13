import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models import Membership, MembershipRole, MembershipStatus, Organization, User


@pytest.fixture
def db_session(app):
    with app.app_context():
        yield db.session
        db.session.rollback()
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


def test_organization_gets_a_uuid_primary_key_on_insert(db_session):
    org = _make_org()
    db_session.add(org)
    db_session.commit()

    assert isinstance(org.id, uuid.UUID)


def test_organization_currency_and_timezone_default_when_not_specified(db_session):
    org = _make_org()
    db_session.add(org)
    db_session.commit()

    assert org.currency == "USD"
    assert org.timezone == "UTC"


def test_organization_optional_fields_are_nullable(db_session):
    org = _make_org()
    db_session.add(org)
    db_session.commit()

    assert org.logo is None
    assert org.email is None
    assert org.phone is None
    assert org.address is None
    assert org.date_format is None


def test_organization_requires_name_at_the_database_level(db_session):
    org = Organization(slug="no-name-org")
    db_session.add(org)

    with pytest.raises(IntegrityError):
        db_session.commit()


def test_organization_slug_must_be_unique(db_session):
    db_session.add(_make_org(name="First Org", slug="dup-slug"))
    db_session.commit()

    db_session.add(_make_org(name="Second Org", slug="dup-slug"))
    with pytest.raises(IntegrityError):
        db_session.commit()


def test_organization_slug_is_normalized_to_lowercase(db_session):
    org = Organization(name="Weird Case", slug="Weird-Case-Slug")
    db_session.add(org)
    db_session.commit()

    assert org.slug == "weird-case-slug"


def test_organization_slug_rejects_invalid_characters(db_session):
    with pytest.raises(ValueError):
        Organization(name="Bad Slug", slug="not a valid slug!")


def test_organization_currency_must_be_three_letters(db_session):
    with pytest.raises(ValueError):
        Organization(name="Bad Currency", slug="bad-currency", currency="US")


def test_membership_links_a_user_to_an_organization_with_a_role(db_session):
    user = _make_user()
    org = _make_org()
    db_session.add_all([user, org])
    db_session.flush()

    membership = Membership(organization_id=org.id, user_id=user.id, role=MembershipRole.OWNER)
    db_session.add(membership)
    db_session.commit()

    assert membership.role == MembershipRole.OWNER
    assert membership.status == MembershipStatus.ACTIVE
    assert membership.joined_at is not None


def test_membership_role_and_status_are_stored_as_lowercase_values(db_session):
    user = _make_user()
    org = _make_org()
    db_session.add_all([user, org])
    db_session.flush()

    membership = Membership(organization_id=org.id, user_id=user.id, role=MembershipRole.ACCOUNTANT)
    db_session.add(membership)
    db_session.commit()

    role_raw, status_raw = db_session.execute(
        text("SELECT role::text, status::text FROM memberships WHERE id = :id"), {"id": membership.id}
    ).one()
    assert role_raw == "accountant"
    assert status_raw == "active"


def test_same_user_cannot_have_two_memberships_in_the_same_organization(db_session):
    user = _make_user()
    org = _make_org()
    db_session.add_all([user, org])
    db_session.flush()

    db_session.add(Membership(organization_id=org.id, user_id=user.id, role=MembershipRole.OWNER))
    db_session.commit()

    db_session.add(Membership(organization_id=org.id, user_id=user.id, role=MembershipRole.MANAGER))
    with pytest.raises(IntegrityError):
        db_session.commit()


def test_same_user_can_belong_to_multiple_organizations(db_session):
    user = _make_user()
    org_a = _make_org(name="Org A", slug="org-a")
    org_b = _make_org(name="Org B", slug="org-b")
    db_session.add_all([user, org_a, org_b])
    db_session.flush()

    db_session.add(Membership(organization_id=org_a.id, user_id=user.id, role=MembershipRole.OWNER))
    db_session.add(Membership(organization_id=org_b.id, user_id=user.id, role=MembershipRole.EMPLOYEE))
    db_session.commit()

    assert len(user.memberships) == 2


def test_membership_requires_a_real_organization(db_session):
    user = _make_user()
    db_session.add(user)
    db_session.flush()

    membership = Membership(organization_id=uuid.uuid4(), user_id=user.id, role=MembershipRole.OWNER)
    db_session.add(membership)

    with pytest.raises(IntegrityError):
        db_session.commit()


def test_membership_requires_a_real_user(db_session):
    org = _make_org()
    db_session.add(org)
    db_session.flush()

    membership = Membership(organization_id=org.id, user_id=uuid.uuid4(), role=MembershipRole.OWNER)
    db_session.add(membership)

    with pytest.raises(IntegrityError):
        db_session.commit()


def test_deleting_an_organization_cascades_to_its_memberships(db_session):
    user = _make_user()
    org = _make_org()
    db_session.add_all([user, org])
    db_session.flush()
    db_session.add(Membership(organization_id=org.id, user_id=user.id, role=MembershipRole.OWNER))
    db_session.commit()

    db_session.delete(org)
    db_session.commit()

    remaining = db_session.query(Membership).filter_by(user_id=user.id).count()
    assert remaining == 0


def test_deleting_one_organizations_membership_does_not_touch_another_organizations(db_session):
    """Isolation boundary: the same user belongs to two orgs; deleting
    one org's membership must leave the other org's membership (same
    user) completely untouched - cascade is scoped by organization_id,
    not by user_id."""
    user = _make_user()
    org_a = _make_org(name="Org A", slug="org-a-isolation")
    org_b = _make_org(name="Org B", slug="org-b-isolation")
    db_session.add_all([user, org_a, org_b])
    db_session.flush()
    db_session.add(Membership(organization_id=org_a.id, user_id=user.id, role=MembershipRole.OWNER))
    membership_b = Membership(organization_id=org_b.id, user_id=user.id, role=MembershipRole.EMPLOYEE)
    db_session.add(membership_b)
    db_session.commit()
    membership_b_id = membership_b.id

    db_session.delete(org_a)
    db_session.commit()

    survivor = db_session.get(Membership, membership_b_id)
    assert survivor is not None
    assert survivor.organization_id == org_b.id
    assert db_session.query(Membership).filter_by(organization_id=org_a.id).count() == 0


def test_organization_relationship_exposes_its_memberships(db_session):
    user = _make_user()
    org = _make_org()
    db_session.add_all([user, org])
    db_session.flush()
    db_session.add(Membership(organization_id=org.id, user_id=user.id, role=MembershipRole.OWNER))
    db_session.commit()
    db_session.refresh(org)

    assert len(org.memberships) == 1
    assert org.memberships[0].user_id == user.id
