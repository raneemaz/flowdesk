"""FD-055: the "AI reporting service" itself - ties the generic
provider abstraction (`app.ai.providers`) to FR-040's weekly-report
input/output contract (`app.ai.schemas`). This is still a *design*
task (FD-057 is titled "Implement AI weekly summary generation"), but
the mandatory rule "never implement placeholder/stub functionality"
applies to a design task's own illustration of the contract it
defines too - `generate_weekly_report` below is a complete, callable
implementation, not a stub. What's deliberately **not** built here is
the real per-organization orchestration: calling this once per org
from a scheduled job, persisting the result, and making one
organization's failure not block another's - that's FD-056
(aggregation)/FD-058 (persistence)/FD-059 (scheduling)'s job.

Epic E08's own acceptance criteria this function satisfies directly:
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
"""

import json
from datetime import datetime, timezone

from pydantic import ValidationError

from app.ai.providers import AICompletionRequest, AIProvider, AIProviderError, complete_with_retries
from app.ai.schemas import WeeklyReportInput, WeeklyReportOutput

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
