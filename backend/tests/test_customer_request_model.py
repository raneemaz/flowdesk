import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models import (
    Customer,
    CustomerRequest,
    Membership,
    MembershipRole,
    Organization,
    RequestComment,
    RequestHistory,
    RequestPriority,
    RequestStatus,
    User,
)


@pytest.fixture
def db_session(app):
    with app.app_context():
        yield db.session
        db.session.rollback()
        db.session.query(RequestComment).delete()
        db.session.query(RequestHistory).delete()
        db.session.query(CustomerRequest).delete()
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


def _make_membership(org, user, role=MembershipRole.EMPLOYEE):
    return Membership(organization_id=org.id, user_id=user.id, role=role)


def _make_customer(org, name="Jane Customer"):
    return Customer(organization_id=org.id, name=name)


def test_customer_request_gets_a_uuid_primary_key_on_insert(db_session):
    user = _make_user()
    org = _make_org()
    db_session.add_all([user, org])
    db_session.flush()
    creator = _make_membership(org, user)
    customer = _make_customer(org)
    db_session.add_all([creator, customer])
    db_session.flush()

    request = CustomerRequest(
        organization_id=org.id, customer_id=customer.id, title="Can't log in", creator_membership_id=creator.id
    )
    db_session.add(request)
    db_session.commit()

    assert isinstance(request.id, uuid.UUID)


def test_customer_request_status_defaults_to_new(db_session):
    user = _make_user()
    org = _make_org()
    db_session.add_all([user, org])
    db_session.flush()
    creator = _make_membership(org, user)
    customer = _make_customer(org)
    db_session.add_all([creator, customer])
    db_session.flush()

    request = CustomerRequest(
        organization_id=org.id, customer_id=customer.id, title="Can't log in", creator_membership_id=creator.id
    )
    db_session.add(request)
    db_session.commit()

    assert request.status == RequestStatus.NEW


def test_customer_request_priority_defaults_to_medium(db_session):
    user = _make_user()
    org = _make_org()
    db_session.add_all([user, org])
    db_session.flush()
    creator = _make_membership(org, user)
    customer = _make_customer(org)
    db_session.add_all([creator, customer])
    db_session.flush()

    request = CustomerRequest(
        organization_id=org.id, customer_id=customer.id, title="Can't log in", creator_membership_id=creator.id
    )
    db_session.add(request)
    db_session.commit()

    assert request.priority == RequestPriority.MEDIUM


def test_customer_request_status_and_priority_are_stored_as_lowercase_values(db_session):
    user = _make_user()
    org = _make_org()
    db_session.add_all([user, org])
    db_session.flush()
    creator = _make_membership(org, user)
    customer = _make_customer(org)
    db_session.add_all([creator, customer])
    db_session.flush()

    request = CustomerRequest(
        organization_id=org.id, customer_id=customer.id, title="Can't log in", creator_membership_id=creator.id
    )
    db_session.add(request)
    db_session.commit()

    (status_raw, priority_raw) = db_session.execute(
        text("SELECT status::text, priority::text FROM customer_requests WHERE id = :id"), {"id": request.id}
    ).one()
    assert status_raw == "new"
    assert priority_raw == "medium"


def test_customer_request_title_must_not_be_blank(db_session):
    user = _make_user()
    org = _make_org()
    db_session.add_all([user, org])
    db_session.flush()
    creator = _make_membership(org, user)
    customer = _make_customer(org)
    db_session.add_all([creator, customer])
    db_session.flush()

    with pytest.raises(ValueError):
        CustomerRequest(organization_id=org.id, customer_id=customer.id, title="   ", creator_membership_id=creator.id)


def test_customer_request_optional_fields_default_to_none(db_session):
    user = _make_user()
    org = _make_org()
    db_session.add_all([user, org])
    db_session.flush()
    creator = _make_membership(org, user)
    customer = _make_customer(org)
    db_session.add_all([creator, customer])
    db_session.flush()

    request = CustomerRequest(
        organization_id=org.id, customer_id=customer.id, title="Can't log in", creator_membership_id=creator.id
    )
    db_session.add(request)
    db_session.commit()

    assert request.description is None
    assert request.category is None
    assert request.assignee_membership_id is None
    assert request.due_date is None
    assert request.resolution_notes is None


def test_customer_request_requires_a_real_organization(db_session):
    user = _make_user()
    org = _make_org()
    db_session.add_all([user, org])
    db_session.flush()
    creator = _make_membership(org, user)
    customer = _make_customer(org)
    db_session.add_all([creator, customer])
    db_session.flush()

    request = CustomerRequest(
        organization_id=uuid.uuid4(), customer_id=customer.id, title="Can't log in", creator_membership_id=creator.id
    )
    db_session.add(request)

    with pytest.raises(IntegrityError):
        db_session.commit()


def test_customer_request_creator_must_be_a_real_membership(db_session):
    org = _make_org()
    db_session.add(org)
    db_session.flush()
    customer = _make_customer(org)
    db_session.add(customer)
    db_session.flush()

    request = CustomerRequest(
        organization_id=org.id, customer_id=customer.id, title="Can't log in", creator_membership_id=uuid.uuid4()
    )
    db_session.add(request)

    with pytest.raises(IntegrityError):
        db_session.commit()


def test_customer_request_requires_a_real_customer(db_session):
    user = _make_user()
    org = _make_org()
    db_session.add_all([user, org])
    db_session.flush()
    creator = _make_membership(org, user)
    db_session.add(creator)
    db_session.flush()

    request = CustomerRequest(
        organization_id=org.id, customer_id=uuid.uuid4(), title="Can't log in", creator_membership_id=creator.id
    )
    db_session.add(request)

    with pytest.raises(IntegrityError):
        db_session.commit()


def test_customer_request_creator_organization_id_must_match_its_memberships_organization(db_session):
    user = _make_user()
    org_a = _make_org(name="Org A", slug="org-a-request-creator")
    org_b = _make_org(name="Org B", slug="org-b-request-creator")
    db_session.add_all([user, org_a, org_b])
    db_session.flush()
    creator_in_org_a = _make_membership(org_a, user)
    customer_in_org_b = _make_customer(org_b)
    db_session.add_all([creator_in_org_a, customer_in_org_b])
    db_session.flush()

    request = CustomerRequest(
        organization_id=org_b.id,
        customer_id=customer_in_org_b.id,
        title="Can't log in",
        creator_membership_id=creator_in_org_a.id,
    )
    db_session.add(request)

    with pytest.raises(IntegrityError):
        db_session.commit()


def test_customer_request_customer_organization_id_must_match_its_customers_organization(db_session):
    """The composite FK's real payoff, mirroring Task.creator_membership_id's
    own test (FD-025): a customer_id from a different organization than
    the request's own organization_id is rejected at the DB level."""
    user = _make_user()
    org_a = _make_org(name="Org A", slug="org-a-request-customer")
    org_b = _make_org(name="Org B", slug="org-b-request-customer")
    db_session.add_all([user, org_a, org_b])
    db_session.flush()
    creator_in_org_a = _make_membership(org_a, user)
    customer_in_org_b = _make_customer(org_b)
    db_session.add_all([creator_in_org_a, customer_in_org_b])
    db_session.flush()

    request = CustomerRequest(
        organization_id=org_a.id,
        customer_id=customer_in_org_b.id,
        title="Can't log in",
        creator_membership_id=creator_in_org_a.id,
    )
    db_session.add(request)

    with pytest.raises(IntegrityError):
        db_session.commit()


def test_customer_request_assignee_must_be_a_real_membership_if_given(db_session):
    user = _make_user()
    org = _make_org()
    db_session.add_all([user, org])
    db_session.flush()
    creator = _make_membership(org, user)
    customer = _make_customer(org)
    db_session.add_all([creator, customer])
    db_session.flush()

    request = CustomerRequest(
        organization_id=org.id,
        customer_id=customer.id,
        title="Can't log in",
        creator_membership_id=creator.id,
        assignee_membership_id=uuid.uuid4(),
    )
    db_session.add(request)

    with pytest.raises(IntegrityError):
        db_session.commit()


def test_deleting_the_creators_membership_is_blocked_while_it_still_has_requests(db_session):
    user = _make_user()
    org = _make_org()
    db_session.add_all([user, org])
    db_session.flush()
    creator = _make_membership(org, user)
    customer = _make_customer(org)
    db_session.add_all([creator, customer])
    db_session.flush()
    db_session.add(
        CustomerRequest(
            organization_id=org.id, customer_id=customer.id, title="Can't log in", creator_membership_id=creator.id
        )
    )
    db_session.commit()

    db_session.delete(creator)
    with pytest.raises(IntegrityError):
        db_session.commit()


def test_deleting_the_customer_is_blocked_while_it_still_has_requests(db_session):
    """The customer_id composite FK's RESTRICT, mirroring the creator
    test above - Section 26's "archived customers stay linked to
    historical requests" means a customer with request history must
    never silently disappear."""
    user = _make_user()
    org = _make_org()
    db_session.add_all([user, org])
    db_session.flush()
    creator = _make_membership(org, user)
    customer = _make_customer(org)
    db_session.add_all([creator, customer])
    db_session.flush()
    db_session.add(
        CustomerRequest(
            organization_id=org.id, customer_id=customer.id, title="Can't log in", creator_membership_id=creator.id
        )
    )
    db_session.commit()

    db_session.delete(customer)
    with pytest.raises(IntegrityError):
        db_session.commit()


def test_deleting_the_assignees_membership_clears_the_requests_assignee_instead_of_deleting_the_request(db_session):
    creator_user = _make_user(email="creator2@example.com")
    assignee_user = _make_user(email="assignee@example.com")
    org = _make_org()
    db_session.add_all([creator_user, assignee_user, org])
    db_session.flush()
    creator = _make_membership(org, creator_user)
    assignee = _make_membership(org, assignee_user)
    customer = _make_customer(org)
    db_session.add_all([creator, assignee, customer])
    db_session.flush()
    request = CustomerRequest(
        organization_id=org.id,
        customer_id=customer.id,
        title="Can't log in",
        creator_membership_id=creator.id,
        assignee_membership_id=assignee.id,
    )
    db_session.add(request)
    db_session.commit()
    request_id = request.id

    db_session.delete(assignee)
    db_session.commit()

    survivor = db_session.get(CustomerRequest, request_id)
    assert survivor is not None
    assert survivor.assignee_membership_id is None


def test_deleting_an_organization_cascades_to_its_customer_requests(db_session):
    user = _make_user()
    org = _make_org()
    db_session.add_all([user, org])
    db_session.flush()
    creator = _make_membership(org, user)
    customer = _make_customer(org)
    db_session.add_all([creator, customer])
    db_session.flush()
    db_session.add(
        CustomerRequest(
            organization_id=org.id, customer_id=customer.id, title="Can't log in", creator_membership_id=creator.id
        )
    )
    db_session.commit()

    db_session.delete(org)
    db_session.commit()

    assert db_session.query(CustomerRequest).count() == 0


def test_deleting_one_organizations_requests_does_not_touch_another_organizations(db_session):
    user_a = _make_user(email="user-a@example.com")
    user_b = _make_user(email="user-b@example.com")
    org_a = _make_org(name="Org A", slug="org-a-request-isolation")
    org_b = _make_org(name="Org B", slug="org-b-request-isolation")
    db_session.add_all([user_a, user_b, org_a, org_b])
    db_session.flush()
    creator_a = _make_membership(org_a, user_a)
    creator_b = _make_membership(org_b, user_b)
    customer_a = _make_customer(org_a, name="Org A customer")
    customer_b = _make_customer(org_b, name="Org B customer")
    db_session.add_all([creator_a, creator_b, customer_a, customer_b])
    db_session.flush()
    db_session.add(
        CustomerRequest(
            organization_id=org_a.id, customer_id=customer_a.id, title="Org A request", creator_membership_id=creator_a.id
        )
    )
    request_b = CustomerRequest(
        organization_id=org_b.id, customer_id=customer_b.id, title="Org B request", creator_membership_id=creator_b.id
    )
    db_session.add(request_b)
    db_session.commit()
    request_b_id = request_b.id

    db_session.delete(org_a)
    db_session.commit()

    survivor = db_session.get(CustomerRequest, request_b_id)
    assert survivor is not None
    assert survivor.organization_id == org_b.id
    assert db_session.query(CustomerRequest).filter_by(organization_id=org_a.id).count() == 0


def test_customer_request_to_public_dict_shape(db_session):
    user = _make_user()
    org = _make_org()
    db_session.add_all([user, org])
    db_session.flush()
    creator = _make_membership(org, user)
    customer = _make_customer(org)
    db_session.add_all([creator, customer])
    db_session.flush()
    request = CustomerRequest(
        organization_id=org.id, customer_id=customer.id, title="Can't log in", creator_membership_id=creator.id
    )
    db_session.add(request)
    db_session.commit()

    body = request.to_public_dict()

    assert body == {
        "id": str(request.id),
        "organization_id": str(org.id),
        "customer_id": str(customer.id),
        "title": "Can't log in",
        "description": None,
        "category": None,
        "status": "new",
        "priority": "medium",
        "creator_membership_id": str(creator.id),
        "assignee_membership_id": None,
        "due_date": None,
        "resolution_notes": None,
        "created_at": request.created_at.isoformat(),
    }


def test_customer_relationship_exposes_its_requests(db_session):
    user = _make_user()
    org = _make_org()
    db_session.add_all([user, org])
    db_session.flush()
    creator = _make_membership(org, user)
    customer = _make_customer(org)
    db_session.add_all([creator, customer])
    db_session.flush()
    request = CustomerRequest(
        organization_id=org.id, customer_id=customer.id, title="Can't log in", creator_membership_id=creator.id
    )
    db_session.add(request)
    db_session.commit()
    db_session.refresh(customer)

    assert len(customer.requests) == 1
    assert customer.requests[0].id == request.id
