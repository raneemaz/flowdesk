import json
from datetime import date

import pytest

from app.ai.providers import AICompletionResponse, AIProvider, AIProviderTimeoutError
from app.ai.schemas import WeeklyReportInput, WeeklyReportOutput
from app.ai.service import AIReportGenerationError, generate_report_for_organization, generate_weekly_report
from app.extensions import db
from app.models import Membership, MembershipRole, MembershipStatus, Organization, User


class _FakeProvider(AIProvider):
    """Records the request it received and returns a canned response -
    no network, no Flask app context needed, proving `app.ai.service`
    is reachable as a pure function."""

    def __init__(self, response_text: str):
        self._response_text = response_text
        self.last_request = None

    def complete(self, request, *, timeout_seconds):
        self.last_request = request
        return AICompletionResponse(text=self._response_text, model="claude-haiku-5-5", input_tokens=1, output_tokens=1)


class _AlwaysFailsProvider(AIProvider):
    def complete(self, request, *, timeout_seconds):
        raise AIProviderTimeoutError("provider is down")


VALID_RESPONSE = json.dumps(
    {
        "business_overview": "5 active tasks, 2 completed this period.",
        "employee_productivity": "Ada completed 2 tasks; Bob has none assigned.",
        "financial_overview": "Invoiced $1000, collected $250.50.",
        "operational_problems": "1 task is overdue.",
        "recommendations": ["Follow up on the overdue task."],
        "missing_data": [],
    }
)


def _make_input(**overrides):
    defaults = dict(
        organization_name="Acme Inc",
        period_start=date(2026, 1, 1),
        period_end=date(2026, 1, 31),
        metrics_snapshot={"active_tasks": 5, "completed_tasks": 2, "monthly_invoiced": "1000.00"},
    )
    defaults.update(overrides)
    return WeeklyReportInput(**defaults)


def test_generate_weekly_report_returns_a_valid_output_on_the_happy_path():
    provider = _FakeProvider(VALID_RESPONSE)
    report_input = _make_input()

    output = generate_weekly_report(provider, report_input)

    assert isinstance(output, WeeklyReportOutput)
    assert output.period_start == date(2026, 1, 1)
    assert output.period_end == date(2026, 1, 31)
    assert output.model == "claude-haiku-5-5"
    assert output.recommendations == ["Follow up on the overdue task."]
    assert output.missing_data == []


def test_generate_weekly_report_sends_the_metrics_snapshot_and_period_in_the_prompt():
    provider = _FakeProvider(VALID_RESPONSE)
    report_input = _make_input()

    generate_weekly_report(provider, report_input)

    assert provider.last_request is not None
    assert "Acme Inc" in provider.last_request.user_prompt
    assert "2026-01-01" in provider.last_request.user_prompt
    assert "2026-01-31" in provider.last_request.user_prompt
    assert '"active_tasks": 5' in provider.last_request.user_prompt


def test_generate_weekly_report_period_and_model_come_from_trusted_sources_not_the_ai_text():
    """Even if the AI's own JSON tried to claim a different period or
    model, generate_weekly_report must never use it - these three
    fields come only from report_input/response.model/the real clock."""
    response_with_bogus_fields = json.dumps(
        {
            "business_overview": "x",
            "employee_productivity": "x",
            "financial_overview": "x",
            "operational_problems": "x",
            "recommendations": [],
            "missing_data": [],
            "period_start": "1999-01-01",
            "model": "a-model-the-ai-made-up",
        }
    )
    provider = _FakeProvider(response_with_bogus_fields)
    report_input = _make_input()

    output = generate_weekly_report(provider, report_input)

    assert output.period_start == date(2026, 1, 1)
    assert output.model == "claude-haiku-5-5"


def test_generate_weekly_report_raises_when_the_provider_fails():
    provider = _AlwaysFailsProvider()

    with pytest.raises(AIReportGenerationError):
        generate_weekly_report(provider, _make_input(), max_retries=0)


def test_generate_weekly_report_raises_on_non_json_response():
    provider = _FakeProvider("this is not json")

    with pytest.raises(AIReportGenerationError):
        generate_weekly_report(provider, _make_input())


def test_generate_weekly_report_raises_when_the_json_is_not_an_object():
    provider = _FakeProvider(json.dumps(["just", "a", "list"]))

    with pytest.raises(AIReportGenerationError):
        generate_weekly_report(provider, _make_input())


def test_generate_weekly_report_raises_when_a_required_field_is_missing():
    incomplete = json.dumps(
        {
            "business_overview": "x",
            "employee_productivity": "x",
            "financial_overview": "x",
            # operational_problems missing
            "recommendations": [],
            "missing_data": [],
        }
    )
    provider = _FakeProvider(incomplete)

    with pytest.raises(AIReportGenerationError):
        generate_weekly_report(provider, _make_input())


def test_generate_weekly_report_raises_when_recommendations_is_the_wrong_type():
    wrong_type = json.dumps(
        {
            "business_overview": "x",
            "employee_productivity": "x",
            "financial_overview": "x",
            "operational_problems": "x",
            "recommendations": "should be a list, not a string",
            "missing_data": [],
        }
    )
    provider = _FakeProvider(wrong_type)

    with pytest.raises(AIReportGenerationError):
        generate_weekly_report(provider, _make_input())


# --- WeeklyReportInput/Output schema-level checks ---------------------------


def test_weekly_report_input_rejects_an_unexpected_field():
    with pytest.raises(Exception):
        WeeklyReportInput(
            organization_name="Acme",
            period_start=date(2026, 1, 1),
            period_end=date(2026, 1, 31),
            metrics_snapshot={},
            organization_id="should-not-be-accepted",
        )


def test_weekly_report_input_requires_metrics_snapshot():
    with pytest.raises(Exception):
        WeeklyReportInput(organization_name="Acme", period_start=date(2026, 1, 1), period_end=date(2026, 1, 31))


# ---------------------------------------------------------------------------
# generate_report_for_organization (FD-057) - the real snapshot (FD-056)
# aggregation runs for real against the test database; only the AI provider
# itself is faked, so no network call ever happens.
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _clean(app):
    yield
    with app.app_context():
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


def test_generate_report_for_organization_ties_the_real_snapshot_to_ai_generation(app):
    with app.app_context():
        org = _make_org_with_owner("org-057-happy")
        provider = _FakeProvider(VALID_RESPONSE)

        generated = generate_report_for_organization(
            org,
            period_start=date(2026, 1, 1),
            period_end=date(2026, 1, 31),
            provider=provider,
            max_tokens=256,
            timeout_seconds=5,
            max_retries=0,
        )

        assert generated.output.period_start == date(2026, 1, 1)
        assert generated.output.period_end == date(2026, 1, 31)
        assert generated.output.model == "claude-haiku-5-5"
        # The returned metrics_snapshot must be the exact one the AI
        # provider actually saw, not a freshly recomputed one - this is
        # what app.ai_reports.service persists.
        assert generated.metrics_snapshot["overview"]["employee_count"] == 1
        # Proves the prompt was built from the real snapshot (one active
        # owner-membership counted), not a mock or placeholder.
        assert provider.last_request is not None
        assert '"employee_count": 1' in provider.last_request.user_prompt
        assert "Acme Inc" in provider.last_request.user_prompt


def test_generate_report_for_organization_builds_a_default_provider_when_none_given(app, monkeypatch):
    with app.app_context():
        org = _make_org_with_owner("org-057-default-provider")
        fake = _FakeProvider(VALID_RESPONSE)
        monkeypatch.setattr("app.ai.service.build_default_provider", lambda: fake)

        generated = generate_report_for_organization(
            org, period_start=date(2026, 1, 1), period_end=date(2026, 1, 31), max_tokens=256, timeout_seconds=5, max_retries=0
        )

        assert generated.output.model == "claude-haiku-5-5"
        assert fake.last_request is not None


def test_generate_report_for_organization_falls_back_to_config_defaults(app):
    with app.app_context():
        org = _make_org_with_owner("org-057-config-defaults")
        provider = _FakeProvider(VALID_RESPONSE)

        # max_tokens/timeout_seconds/max_retries all omitted - must read
        # AI_MAX_TOKENS/AI_REQUEST_TIMEOUT_SECONDS/AI_MAX_RETRIES from
        # current_app.config rather than raising or using some other
        # hardcoded value.
        generated = generate_report_for_organization(
            org, period_start=date(2026, 1, 1), period_end=date(2026, 1, 31), provider=provider
        )

        assert generated.output.model == "claude-haiku-5-5"


def test_generate_report_for_organization_wraps_a_misconfigured_default_provider(app):
    """No ANTHROPIC_API_KEY configured (the default in tests) must
    surface as AIReportGenerationError, not a raw, unhandled
    AIProviderAuthenticationError escaping before generation even
    starts - this is exactly the failure mode a real route hits when
    nothing supplies a provider explicitly."""
    with app.app_context():
        org = _make_org_with_owner("org-057-no-api-key")

        with pytest.raises(AIReportGenerationError):
            generate_report_for_organization(org, period_start=date(2026, 1, 1), period_end=date(2026, 1, 31))


def test_generate_report_for_organization_propagates_a_provider_failure(app):
    with app.app_context():
        org = _make_org_with_owner("org-057-failure")

        with pytest.raises(AIReportGenerationError):
            generate_report_for_organization(
                org,
                period_start=date(2026, 1, 1),
                period_end=date(2026, 1, 31),
                provider=_AlwaysFailsProvider(),
                max_tokens=256,
                timeout_seconds=5,
                max_retries=0,
            )
