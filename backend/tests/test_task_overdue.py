from datetime import date, datetime, timezone

from app.models import Task, TaskPriority, TaskStatus
from app.tasks.service import is_task_overdue, serialize_task


def _task(*, due_date=None, status=TaskStatus.TODO):
    return Task(
        title="Write report",
        due_date=due_date,
        status=status,
        priority=TaskPriority.MEDIUM,
        creator_membership_id=None,
        organization_id=None,
    )


def test_no_due_date_is_never_overdue():
    task = _task(due_date=None)
    assert is_task_overdue(task, "UTC", now=datetime(2026, 11, 15, tzinfo=timezone.utc)) is False


def test_due_date_in_the_future_is_not_overdue():
    task = _task(due_date=date(2026, 12, 1))
    assert is_task_overdue(task, "UTC", now=datetime(2026, 11, 15, tzinfo=timezone.utc)) is False


def test_due_date_today_is_not_yet_overdue():
    """FR-016's "due date passed" - a task due today hasn't passed its
    deadline yet; it becomes overdue starting tomorrow."""
    task = _task(due_date=date(2026, 11, 15))
    assert is_task_overdue(task, "UTC", now=datetime(2026, 11, 15, 23, 59, tzinfo=timezone.utc)) is False


def test_due_date_yesterday_is_overdue():
    task = _task(due_date=date(2026, 11, 14))
    assert is_task_overdue(task, "UTC", now=datetime(2026, 11, 15, 0, 1, tzinfo=timezone.utc)) is True


def test_completed_task_past_due_date_is_not_overdue():
    task = _task(due_date=date(2020, 1, 1), status=TaskStatus.COMPLETED)
    assert is_task_overdue(task, "UTC", now=datetime(2026, 11, 15, tzinfo=timezone.utc)) is False


def test_cancelled_task_past_due_date_is_not_overdue():
    task = _task(due_date=date(2020, 1, 1), status=TaskStatus.CANCELLED)
    assert is_task_overdue(task, "UTC", now=datetime(2026, 11, 15, tzinfo=timezone.utc)) is False


def test_rollover_boundary_in_a_timezone_behind_utc():
    """America/New_York is UTC-5 in November (standard time, no DST
    complication). A due date of Nov 10 must not flip to overdue until
    local midnight in New York - which is 05:00 UTC the next day, not
    UTC midnight. This is the case a naive UTC-date comparison would
    get wrong by marking the task overdue 5 hours too early."""
    task = _task(due_date=date(2026, 11, 10))

    still_nov_10_locally = datetime(2026, 11, 11, 4, 59, tzinfo=timezone.utc)  # 2026-11-10 23:59 EST
    assert is_task_overdue(task, "America/New_York", now=still_nov_10_locally) is False

    now_nov_11_locally = datetime(2026, 11, 11, 5, 1, tzinfo=timezone.utc)  # 2026-11-11 00:01 EST
    assert is_task_overdue(task, "America/New_York", now=now_nov_11_locally) is True


def test_rollover_boundary_in_a_timezone_ahead_of_utc():
    """Asia/Tokyo is UTC+9, no DST. Local midnight arrives *before*
    UTC's own date rolls over - the opposite direction from the
    behind-UTC case above, and the one a naive "compare to UTC today"
    implementation would get wrong by marking the task overdue 9 hours
    too *late*."""
    task = _task(due_date=date(2026, 11, 10))

    still_nov_10_locally = datetime(2026, 11, 10, 14, 59, tzinfo=timezone.utc)  # 2026-11-10 23:59 JST
    assert is_task_overdue(task, "Asia/Tokyo", now=still_nov_10_locally) is False

    now_nov_11_locally = datetime(2026, 11, 10, 15, 1, tzinfo=timezone.utc)  # 2026-11-11 00:01 JST
    assert is_task_overdue(task, "Asia/Tokyo", now=now_nov_11_locally) is True


def test_unrecognized_timezone_falls_back_to_utc_instead_of_raising():
    task = _task(due_date=date(2026, 11, 14))
    assert is_task_overdue(task, "Not/ARealZone", now=datetime(2026, 11, 15, 0, 1, tzinfo=timezone.utc)) is True


def test_non_string_timezone_falls_back_to_utc_instead_of_raising():
    """Organization.timezone is non-nullable today, but this guards the
    same "must never 500" guarantee if that ever changes or a caller
    passes something unexpected."""
    task = _task(due_date=date(2026, 11, 14))
    assert is_task_overdue(task, None, now=datetime(2026, 11, 15, 0, 1, tzinfo=timezone.utc)) is True


def test_default_now_uses_the_real_clock_without_raising():
    task = _task(due_date=date(2020, 1, 1))
    assert is_task_overdue(task, "UTC") is True


def test_serialize_task_adds_is_overdue_alongside_the_models_own_fields():
    task = _task(due_date=date(2026, 11, 14))
    task.created_at = datetime(2026, 11, 1, tzinfo=timezone.utc)
    body = serialize_task(task, "UTC", now=datetime(2026, 11, 15, 0, 1, tzinfo=timezone.utc))

    assert body["is_overdue"] is True
    assert body["due_date"] == "2026-11-14"
    assert body["status"] == "to_do"
