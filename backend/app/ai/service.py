"""FD-055: the "AI reporting service" itself - ties the generic
provider abstraction (`app.ai.providers`) to FR-040's weekly-report
input/output contract (`app.ai.schemas`). `generate_weekly_report` is
a complete, callable implementation of that contract, not a stub -
the mandatory rule "never implement placeholder/stub functionality"
applies to a design task's own illustration of the contract it
defines too.

Epic E08's own acceptance criteria `generate_weekly_report` satisfies
directly:
- "AI never queries the database directly and never receives another
  organization's data" - see `app.ai.schemas`'s own docstring; this
  function takes no db session, no `organization_id`, no ORM object,
  only an already-computed `WeeklyReportInput`.
- "output schema is validated" - the provider's raw text is parsed as
  JSON and validated against `WeeklyReportOutput` by pydantic; any
  failure raises `AIReportGenerationError` rather than guessing.
- "a failed generation never produces a misleading 'successful'
  report" - every failure path below raises; there is no except-and-
  return-a-partial-result branch anywhere in this function.

FD-057 adds `generate_report_for_organization` below - the one
function that actually ties FD-056's snapshot aggregation
(`app.ai.snapshot.build_weekly_metrics_snapshot`) and FD-055's own
provider abstraction (`build_default_provider`) to
`generate_weekly_report` for one real organization and period. What's
deliberately **still not** built here: calling this once per org from
a scheduled job, persisting the result, and making one organization's
failure not block another's - that's FD-058 (persistence)/FD-059
(scheduling)'s job. Nothing calls `generate_report_for_organization`
yet either - still unreachable from any HTTP route."""

import json
from datetime import date, datetime, timezone

from pydantic import ValidationError

from app.ai.providers import AICompletionRequest, AIProvider, AIProviderError, build_default_provider, complete_with_retries
from app.ai.schemas import WeeklyReportInput, WeeklyReportOutput
from app.ai.snapshot import build_weekly_metrics_snapshot
from app.models import Organization

_SYSTEM_PROMPT = """You are FlowDesk's business analyst assistant. You will be given a \
JSON object of already-verified metrics for one organization and one reporting period. \
Using ONLY the numbers in that JSON - never invent, estimate, or recall any business \
fact from outside it - write a weekly business summary.

Respond with a single JSON object and nothing else (no surrounding text, no markdown \
code fences), matching exactly this shape:
{
  "business_overview": string,
  "employee_productivity": string,
  "financial_overview": string,
  "operational_problems": string,
  "recommendations": [string, ...],
  "missing_data": [string, ...]
}

"missing_data" must name any metric you were asked to discuss but that is absent, null, \
or not present in the input - never silently skip mentioning it. "recommendations" are \
your own suggested actions; every other field must be a fact traceable to a specific \
value in the input, never a fabricated statistic."""


class AIReportGenerationError(Exception):
    """The one error type a caller (FD-057+) needs to catch to know
    "no report was produced" - wraps either a provider-level failure
    (`AIProviderError`) or an unparseable/invalid response, without
    the caller needing to know this module's own provider exception
    hierarchy."""


def _build_user_prompt(report_input: WeeklyReportInput) -> str:
    return (
        f"Organization: {report_input.organization_name}\n"
        f"Reporting period: {report_input.period_start.isoformat()} to {report_input.period_end.isoformat()}\n"
        f"Metrics (JSON):\n{json.dumps(report_input.metrics_snapshot, default=str)}"
    )


def generate_weekly_report(
    provider: AIProvider,
    report_input: WeeklyReportInput,
    *,
    max_tokens: int = 1024,
    timeout_seconds: float = 30.0,
    max_retries: int = 2,
) -> WeeklyReportOutput:
    request = AICompletionRequest(
        system_prompt=_SYSTEM_PROMPT, user_prompt=_build_user_prompt(report_input), max_tokens=max_tokens
    )

    try:
        response = complete_with_retries(provider, request, timeout_seconds=timeout_seconds, max_retries=max_retries)
    except AIProviderError as exc:
        raise AIReportGenerationError(f"AI provider call failed: {exc}") from exc

    try:
        parsed = json.loads(response.text)
    except json.JSONDecodeError as exc:
        raise AIReportGenerationError(f"AI response was not valid JSON: {exc}") from exc

    if not isinstance(parsed, dict):
        raise AIReportGenerationError("AI response JSON was not an object.")

    try:
        return WeeklyReportOutput(
            period_start=report_input.period_start,
            period_end=report_input.period_end,
            model=response.model,
            generated_at=datetime.now(timezone.utc),
            business_overview=parsed.get("business_overview"),
            employee_productivity=parsed.get("employee_productivity"),
            financial_overview=parsed.get("financial_overview"),
            operational_problems=parsed.get("operational_problems"),
            recommendations=parsed.get("recommendations"),
            missing_data=parsed.get("missing_data"),
        )
    except ValidationError as exc:
        raise AIReportGenerationError(f"AI response did not match the expected schema: {exc}") from exc


def generate_report_for_organization(
    organization: Organization,
    *,
    period_start: date,
    period_end: date,
    provider: AIProvider | None = None,
    max_tokens: int | None = None,
    timeout_seconds: float | None = None,
    max_retries: int | None = None,
) -> WeeklyReportOutput:
    """FD-057: builds this organization's own metrics snapshot
    (FD-056), wraps it in the FR-040/FR-042 input contract, and
    generates the weekly report - the one call a future caller
    (FD-058/059) needs to go from "an organization and a period" to a
    validated `WeeklyReportOutput`.

    `organization` is an already-loaded ORM instance, not an
    `organization_id` this function would look up itself - a future
    scheduled job (FD-059) iterating every active organization already
    has the object in hand; this function issues no database query of
    its own (the only queries happen inside
    `build_weekly_metrics_snapshot`, unchanged from FD-056).

    `provider`/`max_tokens`/`timeout_seconds`/`max_retries` default to
    `None`, resolved from `current_app.config` only when actually
    needed - so a test can supply a fake provider and explicit numeric
    overrides without ever touching Flask's app context, the same
    testability this whole module already has."""
    if provider is None:
        provider = build_default_provider()

    if max_tokens is None or timeout_seconds is None or max_retries is None:
        from flask import current_app

        config = current_app.config
        if max_tokens is None:
            max_tokens = config["AI_MAX_TOKENS"]
        if timeout_seconds is None:
            timeout_seconds = config["AI_REQUEST_TIMEOUT_SECONDS"]
        if max_retries is None:
            max_retries = config["AI_MAX_RETRIES"]

    metrics_snapshot = build_weekly_metrics_snapshot(
        organization.id, organization.timezone, period_start=period_start, period_end=period_end
    )
    report_input = WeeklyReportInput(
        organization_name=organization.name,
        period_start=period_start,
        period_end=period_end,
        metrics_snapshot=metrics_snapshot,
    )
    return generate_weekly_report(
        provider, report_input, max_tokens=max_tokens, timeout_seconds=timeout_seconds, max_retries=max_retries
    )
