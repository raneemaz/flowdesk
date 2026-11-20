import json
import uuid
from datetime import date, datetime, timezone

import pytest

from app.ai.providers import AICompletionResponse, AIProvider
from app.ai.schemas import WeeklyReportOutput
from app.ai_reports.service import generate_and_store_report, get_ai_report_or_404, list_ai_reports, save_ai_report
from app.errors import APIError
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


def _make_org_with_owner(slug):
    org = Organization(name="Acme Inc", slug=slug, timezone="UTC")
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


def _make_report_output(**overrides):
    defaults = dict(
        period_start=date(2026, 1, 1),
        period_end=date(2026, 1, 31),
        business_overview="5 active tasks.",
        employee_productivity="Ada completed 2 tasks.",
        financial_overview="Invoiced $1000.",
        operational_problems="1 task overdue.",
        recommendations=["Follow up on the overdue task."],
        missing_data=[],
        model="claude-haiku-5-5",
        generated_at=datetime(2026, 2, 1, 12, 0, tzinfo=timezone.utc),
    )
    defaults.update(overrides)
    return WeeklyReportOutput(**defaults)


VALID_RESPONSE = json.dumps(
    {
        "business_overview": "5 active tasks.",
        "employee_productivity": "Ada completed 2 tasks.",
        "financial_overview": "Invoiced $1000.",
        "operational_problems": "1 task overdue.",
        "recommendations": ["Follow up."],
        "missing_data": [],
    }
)


class _FakeProvider(AIProvider):
    def complete(self, request, *, timeout_seconds):
        return AICompletionResponse(text=VALID_RESPONSE, model="claude-haiku-5-5", input_tokens=1, output_tokens=1)


# --- save_ai_report ----------------------------------------------------


def test_save_ai_report_persists_the_separated_summary_and_recommendations(app):
    with app.app_context():
        org = _make_org_with_owner("org-save-happy")
        output = _make_report_output()

        report = save_ai_report(org.id, "weekly", {"overview": {"employee_count": 1}}, output)

        assert report.id is not None
        assert report.report_type == "weekly"
        assert report.period_start == date(2026, 1, 1)
        assert report.period_end == date(2026, 1, 31)
        assert report.metrics_snapshot == {"overview": {"employee_count": 1}}
        assert report.summary == {
            "business_overview": "5 active tasks.",
            "employee_productivity": "Ada completed 2 tasks.",
            "financial_overview": "Invoiced $1000.",
            "operational_problems": "1 task overdue.",
            "missing_data": [],
        }
        assert report.recommendations == ["Follow up on the overdue task."]
        assert report.model == "claude-haiku-5-5"
        assert report.provider == "anthropic"
        assert report.generated_at == datetime(2026, 2, 1, 12, 0, tzinfo=timezone.utc)


def test_save_ai_report_raises_409_on_a_duplicate_organization_type_period(app):
    with app.app_context():
        org = _make_org_with_owner("org-save-dup")
        save_ai_report(org.id, "weekly", {}, _make_report_output())

        with pytest.raises(APIError) as exc_info:
            save_ai_report(org.id, "weekly", {}, _make_report_output())

        assert exc_info.value.status_code == 409


def test_save_ai_report_allows_a_different_period_for_the_same_organization(app):
    with app.app_context():
        org = _make_org_with_owner("org-save-diffperiod")
        save_ai_report(org.id, "weekly", {}, _make_report_output())

        second = save_ai_report(
            org.id, "weekly", {}, _make_report_output(period_start=date(2026, 2, 1), period_end=date(2026, 2, 28))
        )

        assert second.id is not None


def test_save_ai_report_allows_the_same_period_for_a_different_organization(app):
    with app.app_context():
        org_a = _make_org_with_owner("org-save-a")
        org_b = _make_org_with_owner("org-save-b")
        save_ai_report(org_a.id, "weekly", {}, _make_report_output())

        second = save_ai_report(org_b.id, "weekly", {}, _make_report_output())

        assert second.id is not None


# --- generate_and_store_report ------------------------------------------


def test_generate_and_store_report_persists_the_exact_snapshot_the_ai_saw(app):
    with app.app_context():
        org = _make_org_with_owner("org-generate-store")

        report = generate_and_store_report(
            org, period_start=date(2026, 1, 1), period_end=date(2026, 1, 31), provider=_FakeProvider()
        )

        assert report.id is not None
        # The real snapshot (built from this org's own data - one active
        # owner-membership) was persisted, not a placeholder.
        assert report.metrics_snapshot["overview"]["employee_count"] == 1


# --- list_ai_reports / get_ai_report_or_404 ------------------------------


def test_list_ai_reports_orders_by_period_start_descending(app):
    with app.app_context():
        org = _make_org_with_owner("org-list")
        save_ai_report(org.id, "weekly", {}, _make_report_output(period_start=date(2026, 1, 1), period_end=date(2026, 1, 31)))
        save_ai_report(org.id, "weekly", {}, _make_report_output(period_start=date(2026, 3, 1), period_end=date(2026, 3, 31)))
        save_ai_report(org.id, "weekly", {}, _make_report_output(period_start=date(2026, 2, 1), period_end=date(2026, 2, 28)))

        reports, total = list_ai_reports(org.id, page=1, per_page=20)

        assert total == 3
        assert [r.period_start for r in reports] == [date(2026, 3, 1), date(2026, 2, 1), date(2026, 1, 1)]


def test_list_ai_reports_is_scoped_to_the_given_organization(app):
    with app.app_context():
        org_a = _make_org_with_owner("org-list-a")
        org_b = _make_org_with_owner("org-list-b")
        save_ai_report(org_a.id, "weekly", {}, _make_report_output())

        reports, total = list_ai_reports(org_b.id, page=1, per_page=20)

        assert total == 0
        assert reports == []


def test_get_ai_report_or_404_returns_404_for_a_cross_organization_report(app):
    with app.app_context():
        org_a = _make_org_with_owner("org-get-a")
        org_b = _make_org_with_owner("org-get-b")
        report = save_ai_report(org_a.id, "weekly", {}, _make_report_output())

        with pytest.raises(APIError) as exc_info:
            get_ai_report_or_404(org_b.id, report.id)

        assert exc_info.value.status_code == 404


def test_get_ai_report_or_404_returns_404_for_an_unknown_id(app):
    with app.app_context():
        org = _make_org_with_owner("org-get-unknown")

        with pytest.raises(APIError) as exc_info:
            get_ai_report_or_404(org.id, uuid.uuid4())

        assert exc_info.value.status_code == 404
