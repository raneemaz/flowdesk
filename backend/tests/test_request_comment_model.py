import uuid

import pytest
from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models import Customer, CustomerRequest, Membership, MembershipRole, Organization, RequestComment, User


@pytest.fixture
def db_session(app):
    with app.app_context():
        yield db.session
        db.session.rollback()
        db.session.query(RequestComment).delete()
        db.session.query(CustomerRequest).delete()
        db.session.query(Customer).delete()
        db.session.query(Membership).delete()
        db.session.query(Organization).delete()
        db.session.query(User).delete()
        db.session.commit()


def _make_user(email="author@example.com"):
    user = User(name="An Author", email=email)
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


def test_request_comment_gets_a_uuid_primary_key_on_insert(db_session):
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

    comment = RequestComment(organization_id=org.id, request_id=request.id, body="Looked into it.")
    db_session.add(comment)
    db_session.commit()

    assert isinstance(comment.id, uuid.UUID)


def test_request_comment_author_is_optional(db_session):
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

    comment = RequestComment(organization_id=org.id, request_id=request.id, body="Looked into it.")
    db_session.add(comment)
    db_session.commit()

    assert comment.author_membership_id is None


def test_request_comment_rejects_a_blank_body(db_session):
    with pytest.raises(ValueError):
        RequestComment(organization_id=uuid.uuid4(), request_id=uuid.uuid4(), body="   ")


def test_request_comment_requires_a_real_request(db_session):
    org = _make_org()
    db_session.add(org)
    db_session.flush()

    comment = RequestComment(organization_id=org.id, request_id=uuid.uuid4(), body="Looked into it.")
    db_session.add(comment)

    with pytest.raises(IntegrityError):
        db_session.commit()


def test_request_comment_organization_id_must_match_its_requests_organization(db_session):
    user = _make_user()
    org_a = _make_org(name="Org A", slug="org-a-request-comment-mismatch")
    org_b = _make_org(name="Org B", slug="org-b-request-comment-mismatch")
    db_session.add_all([user, org_a, org_b])
    db_session.flush()
    creator = _make_membership(org_a, user)
    customer = _make_customer(org_a)
    db_session.add_all([creator, customer])
    db_session.flush()
    request_in_org_a = _make_request(org_a, customer, creator)
    db_session.add(request_in_org_a)
    db_session.commit()

    comment = RequestComment(organization_id=org_b.id, request_id=request_in_org_a.id, body="Looked into it.")
    db_session.add(comment)

    with pytest.raises(IntegrityError):
        db_session.commit()


def test_request_comment_author_must_be_a_real_membership_if_given(db_session):
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

    comment = RequestComment(
        organization_id=org.id, request_id=request.id, body="Looked into it.", author_membership_id=uuid.uuid4()
    )
    db_session.add(comment)

    with pytest.raises(IntegrityError):
        db_session.commit()


def test_deleting_the_authors_membership_clears_the_comments_author_instead_of_deleting_the_comment(db_session):
    creator_user = _make_user(email="creator@example.com")
    author_user = _make_user(email="author2@example.com")
    org = _make_org()
    db_session.add_all([creator_user, author_user, org])
    db_session.flush()
    creator = _make_membership(org, creator_user)
    author = _make_membership(org, author_user)
    customer = _make_customer(org)
    db_session.add_all([creator, author, customer])
    db_session.flush()
    request = _make_request(org, customer, creator)
    db_session.add(request)
    db_session.commit()
    comment = RequestComment(
        organization_id=org.id, request_id=request.id, body="Looked into it.", author_membership_id=author.id
    )
    db_session.add(comment)
    db_session.commit()
    comment_id = comment.id

    db_session.delete(author)
    db_session.commit()

    survivor = db_session.get(RequestComment, comment_id)
    assert survivor is not None
    assert survivor.author_membership_id is None


def test_deleting_a_request_cascades_to_its_comments(db_session):
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
    db_session.add(RequestComment(organization_id=org.id, request_id=request.id, body="Looked into it."))
    db_session.commit()

    db_session.delete(request)
    db_session.commit()

    assert db_session.query(RequestComment).count() == 0


def test_deleting_an_organization_cascades_to_its_request_comments(db_session):
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
    db_session.add(RequestComment(organization_id=org.id, request_id=request.id, body="Looked into it."))
    db_session.commit()

    db_session.delete(org)
    db_session.commit()

    assert db_session.query(RequestComment).count() == 0


def test_request_relationship_exposes_its_comments(db_session):
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
    db_session.add(RequestComment(organization_id=org.id, request_id=request.id, body="Looked into it."))
    db_session.commit()
    db_session.refresh(request)

    assert len(request.comments) == 1
    assert request.comments[0].body == "Looked into it."


def test_request_comment_to_public_dict_shape(db_session):
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
    comment = RequestComment(organization_id=org.id, request_id=request.id, body="Looked into it.")
    db_session.add(comment)
    db_session.commit()

    body = comment.to_public_dict()

    assert body == {
        "id": str(comment.id),
        "request_id": str(request.id),
        "author_membership_id": None,
        "body": "Looked into it.",
        "created_at": comment.created_at.isoformat(),
    }
