"""FD-055: the weekly-report-specific input/output contract (FR-040/
FR-042), layered on top of `app.ai.providers`'s generic completion
abstraction by `app.ai.service.generate_weekly_report`.

`WeeklyReportInput.metrics_snapshot` is the **only** organization-
scoped data that ever reaches an `AIProvider` - a plain dict, already
computed by the deterministic Analytics Service (FD-051), never a DB
session, ORM object, or raw row. This is how Epic E08's own
acceptance criterion ("AI never queries the database directly and
never receives another organization's data") is satisfied by
construction: nothing in `app.ai` ever imports `app.extensions.db` or
takes an `organization_id`.

`WeeklyReportOutput` mirrors FR-040's five items, split so a renderer
can tell facts from opinions without re-deriving which is which
(FR-042: "Clearly separate facts from AI-generated recommendations"):
`business_overview`/`employee_productivity`/`financial_overview`/
`operational_problems` are the four **factual** sections, each
expected to be traceable to a value in `metrics_snapshot`;
`recommendations` is the one **AI-generated** section (FR-040 item 5,
"suggested actions"). `missing_data` is FR-042's "identify missing
data" - a plain list of named gaps, never silently dropped."""

from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class WeeklyReportInput(BaseModel):
    """Everything `generate_weekly_report` needs - and the only thing
    it's allowed to use - to produce a `WeeklyReportOutput`."""

    model_config = ConfigDict(extra="forbid")

    organization_name: str
    period_start: date
    period_end: date
    metrics_snapshot: dict[str, Any]


class WeeklyReportOutput(BaseModel):
    """`period_start`/`period_end`/`model`/`generated_at` are set by
    `generate_weekly_report` itself from already-trusted values (the
    input's own period, the provider's own reported model name, the
    current time) - never taken from the AI's own response text, so a
    misbehaving provider can't claim a period or model it didn't
    actually use."""

    model_config = ConfigDict(extra="forbid")

    period_start: date
    period_end: date
    business_overview: str
    employee_productivity: str
    financial_overview: str
    operational_problems: str
    recommendations: list[str]
    missing_data: list[str]
    model: str
    generated_at: datetime
