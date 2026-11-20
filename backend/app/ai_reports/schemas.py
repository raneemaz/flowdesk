"""FD-058: HTTP-layer schemas for the ai-reports resource.

`GenerateReportRequest` reuses the exact FR-034 named-period-filter
taxonomy `app.analytics.schemas._PeriodQuery` already established
(`period`/`period_start`/`period_end` + the same "custom requires
both bounds, every other value forbids them" validator) - duplicated,
not imported, same "don't cross-import a private per-module helper"
convention this codebase already follows (e.g. `_today_in_timezone`
across `app.tasks.service`/`app.invoices.service`/
`app.analytics.service`). Read from the POST request's JSON body, not
query params, since this is a state-changing request that creates a
resource - every other POST in this codebase takes its own body the
same way."""

from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

PeriodName = Literal["last_7_days", "last_30_days", "last_90_days", "current_month", "previous_month", "custom"]


class GenerateReportRequest(BaseModel):
    """Body for POST .../ai-reports/generate."""

    model_config = ConfigDict(extra="forbid")

    period: PeriodName
    period_start: date | None = None
    period_end: date | None = None

    @model_validator(mode="after")
    def _custom_requires_bounds_others_forbid_them(self):
        if self.period == "custom":
            if self.period_start is None or self.period_end is None:
                raise ValueError("period_start and period_end are required when period is custom")
            if self.period_start > self.period_end:
                raise ValueError("period_start must not be after period_end")
        elif self.period_start is not None or self.period_end is not None:
            raise ValueError("period_start/period_end must not be given unless period is custom")
        return self


class ListAIReportsQuery(BaseModel):
    """Query-string params for GET .../ai-reports."""

    model_config = ConfigDict(extra="forbid")

    page: int = Field(default=1, ge=1)
    per_page: int = Field(default=20, ge=1, le=100)
