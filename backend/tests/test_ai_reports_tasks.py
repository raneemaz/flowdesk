import json
from datetime import date, datetime, timezone

import pytest

from app.ai.providers import AICompletionResponse, AIProvider
from app.ai.schemas import WeeklyReportOutput
from app.ai.service import AIReportGenerationError
from app.ai_reports.service import generate_and_store_report, save_ai_report
from app.ai_reports.tasks import _is_due_now, _preceding_week, run_due_weekly_reports
from app.extensions import db
from app.models import AIReport, Membership, MembershipRole, MembershipStatus, Organization, User


@pytest.fixture(autouse=True)
def _clean(app):
    yield
    with app.app_context():
        db.session.query(AIReport).delete()
        db.session.query(Membership).delete()
        db.session.query(Organization).delete()
        db.session.query(User).delete()
        db.session.commit()


def _make_org_with_owner(slug, timezone_name="UTC"):
    org = Organization(name="Acme Inc", slug=slug, timezone=timezone_name)
    db.session.add(org)
    db.session.commit()
    user = User(name="Owner", email=f"{slug}@example.com")
    user.set_password("correct horse battery")
    db.session.add(user)
    db.session.commit()
    db.session.add(
        Membership(organization_id=org.id, user_id=user.id, role=MembershipRole.OWNER, status=MembershipStatus.ACTIVE)
    )
    db.session.commit()
    return org


VALID_RESPONSE = json.dumps(
    {
        "business_overview": "x",
        "employee_productivity": "x",
        "financial_overview": "x",
        "operational_problems": "x",
        "recommendations": [],
        "missing_data": [],
    }
)


class _FakeProvider(AIProvider):
    def complete(self, request, *, timeout_seconds):
        return AICompletionResponse(text=VALID_RESPONSE, model="claude-haiku-5-5", input_tokens=1, output_tokens=1)


# --- _is_due_now / _preceding_week (unit-level, no DB) ----------------------


def test_is_due_now_true_at_monday_six_am_utc():
    org = Organization(name="x", slug="x", timezone="UTC")
    now = datetime(2026, 1, 5, 6, 30, tzinfo=timezone.utc)  # 2026-01-05 is a Monday
    assert _is_due_now(org, now) is True


@pytest.mark.parametrize(
    "hour,weekday_date",
    [
        (5, 5),  # Monday 05:xx - too early
        (7, 5),  # Monday 07:xx - too late
    ],
)
def test_is_due_now_false_outside_the_target_hour(hour, weekday_date):
    org = Organization(name="x", slug="x", timezone="UTC")
    now = datetime(2026, 1, weekday_date, hour, 0, tzinfo=timezone.utc)
    assert _is_due_now(org, now) is False


def test_is_due_now_false_on_a_different_weekday():
    org = Organization(name="x", slug="x", timezone="UTC")
    now = datetime(2026, 1, 6, 6, 0, tzinfo=timezone.utc)  # Tuesday
    assert _is_due_now(org, now) is False


def test_is_due_now_respects_the_organizations_own_timezone_not_utc():
    """06:00 UTC is 01:00 in New York (UTC-5 in January) - not due
    there, even though it's exactly the target hour in UTC."""
    org = Organization(name="x", slug="x", timezone="America/New_York")
    now = datetime(2026, 1, 5, 6, 0, tzinfo=timezone.utc)
    assert _is_due_now(org, now) is False


def test_is_due_now_falls_back_to_utc_for_an_invalid_timezone():
    org = Organization(name="x", slug="x", timezone="not-a-real-timezone")
    now = datetime(2026, 1, 5, 6, 0, tzinfo=timezone.utc)
    assert _is_due_now(org, now) is True


def test_preceding_week_is_the_monday_through_sunday_just_before():
    period_start, period_end = _preceding_week(date(2026, 1, 5))  # a Monday
    assert period_start == date(2025, 12, 29)  # the Monday 7 days back
    assert period_end == date(2026, 1, 4)  # the Sunday just before


# --- run_due_weekly_reports (DB-backed, fake provider) ----------------------


def test_run_due_weekly_reports_generates_for_an_organization_whose_local_time_is_due(app, monkeypatch):
    monkeypatch.setattr("app.ai.service.build_default_provider", lambda: _FakeProvider())
    with app.app_context():
        org = _make_org_with_owner("org-due", timezone_name="UTC")
        now = datetime(2026, 1, 5, 6, 15, tzinfo=timezone.utc)  # Monday 06:15 UTC

        results = run_due_weekly_reports(now=now)

        assert len(results) == 1
        assert results[0]["organization_id"] == org.id
        assert results[0]["status"] == "generated"
        report = db.session.query(AIReport).filter_by(organization_id=org.id).one()
        assert report.period_start == date(2025, 12, 29)
        assert report.period_end == date(2026, 1, 4)


def test_run_due_weekly_reports_skips_an_organization_whose_local_time_is_not_due(app, monkeypatch):
    monkeypatch.setattr("app.ai.service.build_default_provider", lambda: _FakeProvider())
    with app.app_context():
        _make_org_with_owner("org-not-due", timezone_name="UTC")
        now = datetime(2026, 1, 5, 14, 0, tzinfo=timezone.utc)  # Monday 2pm UTC - not 6am

        results = run_due_weekly_reports(now=now)

        assert results == []
        assert db.session.query(AIReport).count() == 0


def test_run_due_weekly_reports_uses_each_organizations_own_timezone(app, monkeypatch):
    """One org in UTC (due at 06:00 UTC) and one in a timezone where
    06:00 UTC is NOT 06:00 local - only the UTC one should generate at
    this instant, proving per-organization timezone handling, not a
    single blanket UTC check."""
    monkeypatch.setattr("app.ai.service.build_default_provider", lambda: _FakeProvider())
    with app.app_context():
        due_org = _make_org_with_owner("org-tz-due", timezone_name="UTC")
        not_due_org = _make_org_with_owner("org-tz-notdue", timezone_name="America/New_York")
        now = datetime(2026, 1, 5, 6, 0, tzinfo=timezone.utc)

        results = run_due_weekly_reports(now=now)

        assert len(results) == 1
        assert results[0]["organization_id"] == due_org.id
        assert db.session.query(AIReport).filter_by(organization_id=not_due_org.id).count() == 0


def test_run_due_weekly_reports_marks_an_existing_report_as_skipped_not_failed(app, monkeypatch):
    monkeypatch.setattr("app.ai.service.build_default_provider", lambda: _FakeProvider())
    with app.app_context():
        org = _make_org_with_owner("org-already-exists", timezone_name="UTC")
        existing_output = WeeklyReportOutput(
            period_start=date(2025, 12, 29),
            period_end=date(2026, 1, 4),
            business_overview="x",
            employee_productivity="x",
            financial_overview="x",
            operational_problems="x",
            recommendations=[],
            missing_data=[],
            model="claude-haiku-5-5",
            generated_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        )
        save_ai_report(org.id, "weekly", {}, existing_output)
        now = datetime(2026, 1, 5, 6, 0, tzinfo=timezone.utc)

        results = run_due_weekly_reports(now=now)

        assert len(results) == 1
        assert results[0]["status"] == "skipped"
        assert db.session.query(AIReport).filter_by(organization_id=org.id).count() == 1  # still just the one


def test_run_due_weekly_reports_marks_a_provider_failure_as_failed_and_does_not_persist(app):
    """No ANTHROPIC_API_KEY is configured in the test environment (the
    real default) - build_default_provider() fails, which
    generate_report_for_organization already wraps as
    AIReportGenerationError; this job must mark that organization
    "failed" and persist nothing for it, not raise and abort the
    whole sweep."""
    with app.app_context():
        org = _make_org_with_owner("org-provider-fails", timezone_name="UTC")
        now = datetime(2026, 1, 5, 6, 0, tzinfo=timezone.utc)

        results = run_due_weekly_reports(now=now)

        assert len(results) == 1
        assert results[0]["organization_id"] == org.id
        assert results[0]["status"] == "failed"
        assert db.session.query(AIReport).count() == 0


def test_run_due_weekly_reports_does_not_let_one_organizations_failure_block_another(app, monkeypatch):
    with app.app_context():
        failing_org = _make_org_with_owner("org-fails", timezone_name="UTC")
        succeeding_org = _make_org_with_owner("org-succeeds", timezone_name="UTC")
        now = datetime(2026, 1, 5, 6, 0, tzinfo=timezone.utc)

        def fake_generate_and_store_report(organization, *, period_start, period_end, **kwargs):
            if organization.id == failing_org.id:
                raise AIReportGenerationError("simulated provider failure")
            return generate_and_store_report(
                organization, period_start=period_start, period_end=period_end, provider=_FakeProvider()
            )

        monkeypatch.setattr("app.ai_reports.tasks.generate_and_store_report", fake_generate_and_store_report)

        results = run_due_weekly_reports(now=now)

        statuses = {r["organization_id"]: r["status"] for r in results}
        assert statuses[failing_org.id] == "failed"
        assert statuses[succeeding_org.id] == "generated"
        assert db.session.query(AIReport).filter_by(organization_id=succeeding_org.id).count() == 1
        assert db.session.query(AIReport).filter_by(organization_id=failing_org.id).count() == 0
