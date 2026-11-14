import uuid
from decimal import Decimal

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models import (
    Department,
    Membership,
    MembershipRole,
    Organization,
    Task,
    TaskComment,
    TaskHistory,
    TaskPriority,
    TaskStatus,
    User,
)


@pytest.fixture
def db_session(app):
    with app.app_context():
        yield db.session
        db.session.rollback()
        db.session.query(TaskComment).delete()
        db.session.query(TaskHistory).delete()
        db.session.query(Task).delete()
        db.session.query(Department).delete()
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


def test_task_gets_a_uuid_primary_key_on_insert(db_session):
    user = _make_user()
    org = _make_org()
    db_session.add_all([user, org])
    db_session.flush()
    creator = _make_membership(org, user)
    db_session.add(creator)
    db_session.flush()

    task = Task(organization_id=org.id, title="Write report", creator_membership_id=creator.id)
    db_session.add(task)
    db_session.commit()

    assert isinstance(task.id, uuid.UUID)


def test_task_status_defaults_to_to_do(db_session):
    user = _make_user()
    org = _make_org()
    db_session.add_all([user, org])
    db_session.flush()
    creator = _make_membership(org, user)
    db_session.add(creator)
    db_session.flush()

    task = Task(organization_id=org.id, title="Write report", creator_membership_id=creator.id)
    db_session.add(task)
    db_session.commit()

    assert task.status == TaskStatus.TODO


def test_task_priority_defaults_to_medium(db_session):
    user = _make_user()
    org = _make_org()
    db_session.add_all([user, org])
    db_session.flush()
    creator = _make_membership(org, user)
    db_session.add(creator)
    db_session.flush()

    task = Task(organization_id=org.id, title="Write report", creator_membership_id=creator.id)
    db_session.add(task)
    db_session.commit()

    assert task.priority == TaskPriority.MEDIUM


def test_task_status_and_priority_are_stored_as_lowercase_values(db_session):
    user = _make_user()
    org = _make_org()
    db_session.add_all([user, org])
    db_session.flush()
    creator = _make_membership(org, user)
    db_session.add(creator)
    db_session.flush()

    task = Task(organization_id=org.id, title="Write report", creator_membership_id=creator.id)
    db_session.add(task)
    db_session.commit()

    (status_raw, priority_raw) = db_session.execute(
        text("SELECT status::text, priority::text FROM tasks WHERE id = :id"), {"id": task.id}
    ).one()
    assert status_raw == "to_do"
    assert priority_raw == "medium"


def test_task_title_must_not_be_blank(db_session):
    user = _make_user()
    org = _make_org()
    db_session.add_all([user, org])
    db_session.flush()
    creator = _make_membership(org, user)
    db_session.add(creator)
    db_session.flush()

    with pytest.raises(ValueError):
        Task(organization_id=org.id, title="   ", creator_membership_id=creator.id)


def test_task_optional_fields_default_to_none(db_session):
    user = _make_user()
    org = _make_org()
    db_session.add_all([user, org])
    db_session.flush()
    creator = _make_membership(org, user)
    db_session.add(creator)
    db_session.flush()

    task = Task(organization_id=org.id, title="Write report", creator_membership_id=creator.id)
    db_session.add(task)
    db_session.commit()

    assert task.description is None
    assert task.assignee_membership_id is None
    assert task.department_id is None
    assert task.start_date is None
    assert task.due_date is None
    assert task.estimated_hours is None
    assert task.actual_hours is None


def test_task_hours_store_exact_decimal_values(db_session):
    user = _make_user()
    org = _make_org()
    db_session.add_all([user, org])
    db_session.flush()
    creator = _make_membership(org, user)
    db_session.add(creator)
    db_session.flush()

    task = Task(
        organization_id=org.id,
        title="Write report",
        creator_membership_id=creator.id,
        estimated_hours=Decimal("2.50"),
        actual_hours=Decimal("3.25"),
    )
    db_session.add(task)
    db_session.commit()
    db_session.refresh(task)

    assert task.estimated_hours == Decimal("2.50")
    assert task.actual_hours == Decimal("3.25")


def test_task_requires_a_real_organization(db_session):
    user = _make_user()
    org = _make_org()
    db_session.add_all([user, org])
    db_session.flush()
    creator = _make_membership(org, user)
    db_session.add(creator)
    db_session.flush()

    task = Task(organization_id=uuid.uuid4(), title="Write report", creator_membership_id=creator.id)
    db_session.add(task)

    with pytest.raises(IntegrityError):
        db_session.commit()


def test_task_creator_must_be_a_real_membership(db_session):
    org = _make_org()
    db_session.add(org)
    db_session.flush()

    task = Task(organization_id=org.id, title="Write report", creator_membership_id=uuid.uuid4())
    db_session.add(task)

    with pytest.raises(IntegrityError):
        db_session.commit()


def test_task_creator_organization_id_must_match_its_memberships_organization(db_session):
    """The composite FK's real payoff, mirroring EmployeeProfile's own
    test (FD-020): a creator_membership_id from a different organization
    than the task's own organization_id is rejected at the DB level."""
    user = _make_user()
    org_a = _make_org(name="Org A", slug="org-a-task-creator")
    org_b = _make_org(name="Org B", slug="org-b-task-creator")
    db_session.add_all([user, org_a, org_b])
    db_session.flush()
    creator_in_org_a = _make_membership(org_a, user)
    db_session.add(creator_in_org_a)
    db_session.flush()

    task = Task(organization_id=org_b.id, title="Write report", creator_membership_id=creator_in_org_a.id)
    db_session.add(task)

    with pytest.raises(IntegrityError):
        db_session.commit()


def test_task_assignee_must_be_a_real_membership_if_given(db_session):
    user = _make_user()
    org = _make_org()
    db_session.add_all([user, org])
    db_session.flush()
    creator = _make_membership(org, user)
    db_session.add(creator)
    db_session.flush()

    task = Task(
        organization_id=org.id,
        title="Write report",
        creator_membership_id=creator.id,
        assignee_membership_id=uuid.uuid4(),
    )
    db_session.add(task)

    with pytest.raises(IntegrityError):
        db_session.commit()


def test_task_department_must_be_a_real_department_if_given(db_session):
    user = _make_user()
    org = _make_org()
    db_session.add_all([user, org])
    db_session.flush()
    creator = _make_membership(org, user)
    db_session.add(creator)
    db_session.flush()

    task = Task(
        organization_id=org.id, title="Write report", creator_membership_id=creator.id, department_id=uuid.uuid4()
    )
    db_session.add(task)

    with pytest.raises(IntegrityError):
        db_session.commit()


def test_task_model_does_not_itself_block_an_assignee_from_a_different_organization(db_session):
    """Documents the same intentional gap as Department.manager_membership_id
    (FD-019) and EmployeeProfile.manager_membership_id (FD-020):
    assignee_membership_id is a simple (non-composite) FK, so the model
    layer alone doesn't enforce the assignee belongs to the task's
    organization - a future service layer (FD-026/FD-027) is
    responsible for that check."""
    creator_user = _make_user(email="creator2@example.com")
    assignee_user = _make_user(email="assignee@example.com")
    org_a = _make_org(name="Org A", slug="org-a-task-assignee")
    org_b = _make_org(name="Org B", slug="org-b-task-assignee")
    db_session.add_all([creator_user, assignee_user, org_a, org_b])
    db_session.flush()
    creator = _make_membership(org_a, creator_user)
    assignee_in_org_b = _make_membership(org_b, assignee_user)
    db_session.add_all([creator, assignee_in_org_b])
    db_session.flush()

    task = Task(
        organization_id=org_a.id,
        title="Write report",
        creator_membership_id=creator.id,
        assignee_membership_id=assignee_in_org_b.id,
    )
    db_session.add(task)
    db_session.commit()

    assert task.assignee_membership_id == assignee_in_org_b.id


def test_task_model_does_not_itself_block_a_department_from_a_different_organization(db_session):
    """Same documented gap as above, for department_id."""
    user = _make_user()
    org_a = _make_org(name="Org A", slug="org-a-task-department")
    org_b = _make_org(name="Org B", slug="org-b-task-department")
    db_session.add_all([user, org_a, org_b])
    db_session.flush()
    creator = _make_membership(org_a, user)
    department_in_org_b = Department(organization_id=org_b.id, name="Sales")
    db_session.add_all([creator, department_in_org_b])
    db_session.flush()

    task = Task(
        organization_id=org_a.id,
        title="Write report",
        creator_membership_id=creator.id,
        department_id=department_in_org_b.id,
    )
    db_session.add(task)
    db_session.commit()

    assert task.department_id == department_in_org_b.id


def test_deleting_the_creators_membership_is_blocked_while_it_still_has_tasks(db_session):
    """RESTRICT (the composite FK's default, no ON DELETE clause given)
    - unlike assignee/department below, who created a task is audit
    history that must never silently disappear (spec Section 10.3 rule
    #5); the DB refuses the delete outright rather than nulling it or
    cascading the task away."""
    user = _make_user()
    org = _make_org()
    db_session.add_all([user, org])
    db_session.flush()
    creator = _make_membership(org, user)
    db_session.add(creator)
    db_session.flush()
    db_session.add(Task(organization_id=org.id, title="Write report", creator_membership_id=creator.id))
    db_session.commit()

    db_session.delete(creator)
    with pytest.raises(IntegrityError):
        db_session.commit()


def test_deleting_the_assignees_membership_clears_the_tasks_assignee_instead_of_deleting_the_task(db_session):
    creator_user = _make_user(email="creator3@example.com")
    assignee_user = _make_user(email="assignee2@example.com")
    org = _make_org()
    db_session.add_all([creator_user, assignee_user, org])
    db_session.flush()
    creator = _make_membership(org, creator_user)
    assignee = _make_membership(org, assignee_user)
    db_session.add_all([creator, assignee])
    db_session.flush()
    task = Task(
        organization_id=org.id,
        title="Write report",
        creator_membership_id=creator.id,
        assignee_membership_id=assignee.id,
    )
    db_session.add(task)
    db_session.commit()
    task_id = task.id

    db_session.delete(assignee)
    db_session.commit()

    survivor = db_session.get(Task, task_id)
    assert survivor is not None
    assert survivor.assignee_membership_id is None


def test_deleting_the_tasks_department_clears_the_tasks_department_instead_of_deleting_the_task(db_session):
    user = _make_user()
    org = _make_org()
    db_session.add_all([user, org])
    db_session.flush()
    creator = _make_membership(org, user)
    department = Department(organization_id=org.id, name="Sales")
    db_session.add_all([creator, department])
    db_session.flush()
    task = Task(
        organization_id=org.id, title="Write report", creator_membership_id=creator.id, department_id=department.id
    )
    db_session.add(task)
    db_session.commit()
    task_id = task.id

    db_session.delete(department)
    db_session.commit()

    survivor = db_session.get(Task, task_id)
    assert survivor is not None
    assert survivor.department_id is None


def test_deleting_an_organization_cascades_to_its_tasks(db_session):
    user = _make_user()
    org = _make_org()
    db_session.add_all([user, org])
    db_session.flush()
    creator = _make_membership(org, user)
    db_session.add(creator)
    db_session.flush()
    db_session.add(Task(organization_id=org.id, title="Write report", creator_membership_id=creator.id))
    db_session.commit()

    db_session.delete(org)
    db_session.commit()

    assert db_session.query(Task).count() == 0


def test_deleting_one_organizations_tasks_does_not_touch_another_organizations(db_session):
    user_a = _make_user(email="user-a@example.com")
    user_b = _make_user(email="user-b@example.com")
    org_a = _make_org(name="Org A", slug="org-a-task-isolation")
    org_b = _make_org(name="Org B", slug="org-b-task-isolation")
    db_session.add_all([user_a, user_b, org_a, org_b])
    db_session.flush()
    creator_a = _make_membership(org_a, user_a)
    creator_b = _make_membership(org_b, user_b)
    db_session.add_all([creator_a, creator_b])
    db_session.flush()
    db_session.add(Task(organization_id=org_a.id, title="Org A task", creator_membership_id=creator_a.id))
    task_b = Task(organization_id=org_b.id, title="Org B task", creator_membership_id=creator_b.id)
    db_session.add(task_b)
    db_session.commit()
    task_b_id = task_b.id

    db_session.delete(org_a)
    db_session.commit()

    survivor = db_session.get(Task, task_b_id)
    assert survivor is not None
    assert survivor.organization_id == org_b.id
    assert db_session.query(Task).filter_by(organization_id=org_a.id).count() == 0


def test_task_to_public_dict_shape(db_session):
    user = _make_user()
    org = _make_org()
    db_session.add_all([user, org])
    db_session.flush()
    creator = _make_membership(org, user)
    db_session.add(creator)
    db_session.flush()
    task = Task(organization_id=org.id, title="Write report", creator_membership_id=creator.id)
    db_session.add(task)
    db_session.commit()

    body = task.to_public_dict()

    assert body == {
        "id": str(task.id),
        "organization_id": str(org.id),
        "title": "Write report",
        "description": None,
        "status": "to_do",
        "priority": "medium",
        "creator_membership_id": str(creator.id),
        "assignee_membership_id": None,
        "department_id": None,
        "start_date": None,
        "due_date": None,
        "estimated_hours": None,
        "actual_hours": None,
        "created_at": task.created_at.isoformat(),
    }
