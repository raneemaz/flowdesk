import uuid

import pytest
from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models import Customer, CustomerRequest, Membership, MembershipRole, Organization, RequestHistory, User


@pytest.fixture
def db_session(app):
    with app.app_context():
        yield db.session
        db.session.rollback()
        db.session.query(RequestHistory).delete()
        db.session.query(CustomerRequest).delete()
        db.session.query(Customer).delete()
        db.session.query(Membership).delete()
        db.session.query(Organization).delete()
        db.session.query(User).delete()
        db.session.commit()


def _make_user(email="actor@example.com"):
    user = User(name="An Actor", email=email)
    user.set_password("correct horse battery staple")
    return user


def _make_org(name="Acme Inc", slug="acme-inc"):
    return Organization(name=name, slug=slug)


def _make_membership(org, user, role=MembershipRole.EMPLOYEE):
    return Membership(organization_id=org.id, user_id=user.id, role=role)


def _make_customer(org):
    return Customer(organization_id=org.id, name="Jane Customer")


def _make_request(org, customer, creator):
    return CustomerRequest(
        organization_id=org.id, customer_id=customer.id, title="Can't log in", creator_membership_id=creator.id
    )


def test_request_history_gets_a_uuid_primary_key_on_insert(db_session):
    user = _make_user()
    org = _make_org()
    db_session.add_all([user, org])
    db_session.flush()
    creator = _make_membership(org, user)
    customer = _make_customer(org)
    db_session.add_all([creator, customer])
    db_session.flush()
    request = _make_request(org, customer, creator)
    db_session.add(request)
    db_session.commit()

    entry = RequestHistory(organization_id=org.id, request_id=request.id, event_type="created")
    db_session.add(entry)
    db_session.commit()

    assert isinstance(entry.id, uuid.UUID)


def test_request_history_has_no_updated_at_column(db_session):
    """Deliberate deviation from TimestampMixin (see the model's own
    docstring): an append-only audit trail shouldn't have a column that
    implies its rows can be edited after the fact."""
    assert not hasattr(RequestHistory, "updated_at")


def test_request_history_actor_previous_value_and_new_value_are_optional(db_session):
    user = _make_user()
    org = _make_org()
    db_session.add_all([user, org])
    db_session.flush()
    creator = _make_membership(org, user)
    customer = _make_customer(org)
    db_session.add_all([creator, customer])
    db_session.flush()
    request = _make_request(org, customer, creator)
    db_session.add(request)
    db_session.commit()

    entry = RequestHistory(organization_id=org.id, request_id=request.id, event_type="created")
    db_session.add(entry)
    db_session.commit()

    assert entry.actor_membership_id is None
    assert entry.previous_value is None
    assert entry.new_value is None


def test_request_history_requires_a_real_request(db_session):
    org = _make_org()
    db_session.add(org)
    db_session.flush()

    entry = RequestHistory(organization_id=org.id, request_id=uuid.uuid4(), event_type="created")
    db_session.add(entry)

    with pytest.raises(IntegrityError):
        db_session.commit()


def test_request_history_organization_id_must_match_its_requests_organization(db_session):
    user = _make_user()
    org_a = _make_org(name="Org A", slug="org-a-request-history-mismatch")
    org_b = _make_org(name="Org B", slug="org-b-request-history-mismatch")
    db_session.add_all([user, org_a, org_b])
    db_session.flush()
    creator = _make_membership(org_a, user)
    customer = _make_customer(org_a)
    db_session.add_all([creator, customer])
    db_session.flush()
    request_in_org_a = _make_request(org_a, customer, creator)
    db_session.add(request_in_org_a)
    db_session.commit()

    entry = RequestHistory(organization_id=org_b.id, request_id=request_in_org_a.id, event_type="created")
    db_session.add(entry)

    with pytest.raises(IntegrityError):
        db_session.commit()


def test_request_history_actor_must_be_a_real_membership_if_given(db_session):
    user = _make_user()
    org = _make_org()
    db_session.add_all([user, org])
    db_session.flush()
    creator = _make_membership(org, user)
    customer = _make_customer(org)
    db_session.add_all([creator, customer])
    db_session.flush()
    request = _make_request(org, customer, creator)
    db_session.add(request)
    db_session.commit()

    entry = RequestHistory(
        organization_id=org.id, request_id=request.id, event_type="created", actor_membership_id=uuid.uuid4()
    )
    db_session.add(entry)

    with pytest.raises(IntegrityError):
        db_session.commit()


def test_deleting_the_actors_membership_clears_the_historys_actor_instead_of_deleting_the_entry(db_session):
    creator_user = _make_user(email="creator@example.com")
    actor_user = _make_user(email="actor2@example.com")
    org = _make_org()
    db_session.add_all([creator_user, actor_user, org])
    db_session.flush()
    creator = _make_membership(org, creator_user)
    actor = _make_membership(org, actor_user)
    customer = _make_customer(org)
    db_session.add_all([creator, actor, customer])
    db_session.flush()
    request = _make_request(org, customer, creator)
    db_session.add(request)
    db_session.commit()
    entry = RequestHistory(
        organization_id=org.id, request_id=request.id, event_type="status_changed", actor_membership_id=actor.id
    )
    db_session.add(entry)
    db_session.commit()
    entry_id = entry.id

    db_session.delete(actor)
    db_session.commit()

    survivor = db_session.get(RequestHistory, entry_id)
    assert survivor is not None
    assert survivor.actor_membership_id is None


def test_deleting_a_request_cascades_to_its_history(db_session):
    user = _make_user()
    org = _make_org()
    db_session.add_all([user, org])
    db_session.flush()
    creator = _make_membership(org, user)
    customer = _make_customer(org)
    db_session.add_all([creator, customer])
    db_session.flush()
    request = _make_request(org, customer, creator)
    db_session.add(request)
    db_session.commit()
    db_session.add(RequestHistory(organization_id=org.id, request_id=request.id, event_type="created"))
    db_session.commit()

    db_session.delete(request)
    db_session.commit()

    assert db_session.query(RequestHistory).count() == 0


def test_request_relationship_exposes_its_history_in_chronological_order(db_session):
    user = _make_user()
    org = _make_org()
    db_session.add_all([user, org])
    db_session.flush()
    creator = _make_membership(org, user)
    customer = _make_customer(org)
    db_session.add_all([creator, customer])
    db_session.flush()
    request = _make_request(org, customer, creator)
    db_session.add(request)
    db_session.commit()
    # Inserted out of chronological order - the relationship's own
    # order_by="RequestHistory.created_at" must still return them sorted.
    second = RequestHistory(organization_id=org.id, request_id=request.id, event_type="status_changed")
    db_session.add(second)
    db_session.commit()
    first = RequestHistory(organization_id=org.id, request_id=request.id, event_type="created")
    first.created_at = second.created_at.replace(year=second.created_at.year - 1)
    db_session.add(first)
    db_session.commit()
    db_session.refresh(request)

    assert [entry.event_type for entry in request.history] == ["created", "status_changed"]


def test_request_history_to_public_dict_shape(db_session):
    user = _make_user()
    org = _make_org()
    db_session.add_all([user, org])
    db_session.flush()
    creator = _make_membership(org, user)
    customer = _make_customer(org)
    db_session.add_all([creator, customer])
    db_session.flush()
    request = _make_request(org, customer, creator)
    db_session.add(request)
    db_session.commit()
    entry = RequestHistory(
        organization_id=org.id,
        request_id=request.id,
        event_type="status_changed",
        previous_value="new",
        new_value="assigned",
    )
    db_session.add(entry)
    db_session.commit()

    body = entry.to_public_dict()

    assert body == {
        "id": str(entry.id),
        "request_id": str(request.id),
        "actor_membership_id": None,
        "event_type": "status_changed",
        "previous_value": "new",
        "new_value": "assigned",
        "created_at": entry.created_at.isoformat(),
    }
