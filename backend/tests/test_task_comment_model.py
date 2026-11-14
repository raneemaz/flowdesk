import uuid

import pytest
from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models import Membership, MembershipRole, Organization, Task, TaskComment, TaskHistory, User


@pytest.fixture
def db_session(app):
    with app.app_context():
        yield db.session
        db.session.rollback()
        db.session.query(TaskComment).delete()
        db.session.query(TaskHistory).delete()
        db.session.query(Task).delete()
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


def _make_task(org, creator):
    return Task(organization_id=org.id, title="Write report", creator_membership_id=creator.id)


def test_task_comment_gets_a_uuid_primary_key_on_insert(db_session):
    user = _make_user()
    org = _make_org()
    db_session.add_all([user, org])
    db_session.flush()
    creator = _make_membership(org, user)
    db_session.add(creator)
    db_session.flush()
    task = _make_task(org, creator)
    db_session.add(task)
    db_session.commit()

    comment = TaskComment(organization_id=org.id, task_id=task.id, body="Looks good.")
    db_session.add(comment)
    db_session.commit()

    assert isinstance(comment.id, uuid.UUID)


def test_task_comment_author_is_optional(db_session):
    user = _make_user()
    org = _make_org()
    db_session.add_all([user, org])
    db_session.flush()
    creator = _make_membership(org, user)
    db_session.add(creator)
    db_session.flush()
    task = _make_task(org, creator)
    db_session.add(task)
    db_session.commit()

    comment = TaskComment(organization_id=org.id, task_id=task.id, body="Looks good.")
    db_session.add(comment)
    db_session.commit()

    assert comment.author_membership_id is None


def test_task_comment_rejects_a_blank_body(db_session):
    with pytest.raises(ValueError):
        TaskComment(organization_id=uuid.uuid4(), task_id=uuid.uuid4(), body="   ")


def test_task_comment_requires_a_real_task(db_session):
    org = _make_org()
    db_session.add(org)
    db_session.flush()

    comment = TaskComment(organization_id=org.id, task_id=uuid.uuid4(), body="Looks good.")
    db_session.add(comment)

    with pytest.raises(IntegrityError):
        db_session.commit()


def test_task_comment_organization_id_must_match_its_tasks_organization(db_session):
    """The composite FK's real payoff, mirroring EmployeeProfile's own
    test (FD-020): a task_comment whose organization_id doesn't match
    its task's real organization is rejected at the DB level."""
    user = _make_user()
    org_a = _make_org(name="Org A", slug="org-a-comment-mismatch")
    org_b = _make_org(name="Org B", slug="org-b-comment-mismatch")
    db_session.add_all([user, org_a, org_b])
    db_session.flush()
    creator = _make_membership(org_a, user)
    db_session.add(creator)
    db_session.flush()
    task_in_org_a = _make_task(org_a, creator)
    db_session.add(task_in_org_a)
    db_session.commit()

    comment = TaskComment(organization_id=org_b.id, task_id=task_in_org_a.id, body="Looks good.")
    db_session.add(comment)

    with pytest.raises(IntegrityError):
        db_session.commit()


def test_task_comment_author_must_be_a_real_membership_if_given(db_session):
    user = _make_user()
    org = _make_org()
    db_session.add_all([user, org])
    db_session.flush()
    creator = _make_membership(org, user)
    db_session.add(creator)
    db_session.flush()
    task = _make_task(org, creator)
    db_session.add(task)
    db_session.commit()

    comment = TaskComment(
        organization_id=org.id, task_id=task.id, body="Looks good.", author_membership_id=uuid.uuid4()
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
    db_session.add_all([creator, author])
    db_session.flush()
    task = _make_task(org, creator)
    db_session.add(task)
    db_session.commit()
    comment = TaskComment(
        organization_id=org.id, task_id=task.id, body="Looks good.", author_membership_id=author.id
    )
    db_session.add(comment)
    db_session.commit()
    comment_id = comment.id

    db_session.delete(author)
    db_session.commit()

    survivor = db_session.get(TaskComment, comment_id)
    assert survivor is not None
    assert survivor.author_membership_id is None


def test_deleting_a_task_cascades_to_its_comments(db_session):
    user = _make_user()
    org = _make_org()
    db_session.add_all([user, org])
    db_session.flush()
    creator = _make_membership(org, user)
    db_session.add(creator)
    db_session.flush()
    task = _make_task(org, creator)
    db_session.add(task)
    db_session.commit()
    db_session.add(TaskComment(organization_id=org.id, task_id=task.id, body="Looks good."))
    db_session.commit()

    db_session.delete(task)
    db_session.commit()

    assert db_session.query(TaskComment).count() == 0


def test_deleting_an_organization_cascades_to_its_task_comments(db_session):
    user = _make_user()
    org = _make_org()
    db_session.add_all([user, org])
    db_session.flush()
    creator = _make_membership(org, user)
    db_session.add(creator)
    db_session.flush()
    task = _make_task(org, creator)
    db_session.add(task)
    db_session.commit()
    db_session.add(TaskComment(organization_id=org.id, task_id=task.id, body="Looks good."))
    db_session.commit()

    db_session.delete(org)
    db_session.commit()

    assert db_session.query(TaskComment).count() == 0


def test_task_relationship_exposes_its_comments(db_session):
    user = _make_user()
    org = _make_org()
    db_session.add_all([user, org])
    db_session.flush()
    creator = _make_membership(org, user)
    db_session.add(creator)
    db_session.flush()
    task = _make_task(org, creator)
    db_session.add(task)
    db_session.commit()
    db_session.add(TaskComment(organization_id=org.id, task_id=task.id, body="Looks good."))
    db_session.commit()
    db_session.refresh(task)

    assert len(task.comments) == 1
    assert task.comments[0].body == "Looks good."


def test_task_comment_to_public_dict_shape(db_session):
    user = _make_user()
    org = _make_org()
    db_session.add_all([user, org])
    db_session.flush()
    creator = _make_membership(org, user)
    db_session.add(creator)
    db_session.flush()
    task = _make_task(org, creator)
    db_session.add(task)
    db_session.commit()
    comment = TaskComment(organization_id=org.id, task_id=task.id, body="Looks good.")
    db_session.add(comment)
    db_session.commit()

    body = comment.to_public_dict()

    assert body == {
        "id": str(comment.id),
        "task_id": str(task.id),
        "author_membership_id": None,
        "body": "Looks good.",
        "created_at": comment.created_at.isoformat(),
    }
