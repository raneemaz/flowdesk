import json
from datetime import date

import pytest

from app.ai.providers import AICompletionResponse, AIProvider, AIProviderTimeoutError
from app.ai.schemas import WeeklyReportInput, WeeklyReportOutput
from app.ai.service import AIReportGenerationError, generate_weekly_report


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
