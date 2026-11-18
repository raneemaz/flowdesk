"""FD-052: query-string schemas for the analytics endpoints. `period`
resolves the FR-034 named date-filter taxonomy; `custom` is the only
value that accepts explicit `period_start`/`period_end` - any other
value supplying either is a 422, so a caller never silently has an
explicit range ignored in favor of a named one."""

import uuid
from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, model_validator

PeriodName = Literal["last_7_days", "last_30_days", "last_90_days", "current_month", "previous_month", "custom"]


class _PeriodQuery(BaseModel):
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


class OverviewAnalyticsQuery(_PeriodQuery):
    """Query-string params for GET .../analytics/overview."""


class EmployeeAnalyticsQuery(_PeriodQuery):
    """Query-string params for GET .../analytics/employees."""

    target_membership_id: uuid.UUID | None = None


class DepartmentAnalyticsQuery(_PeriodQuery):
    """Query-string params for GET .../analytics/departments."""

    department_id: uuid.UUID | None = None


class FinancialAnalyticsQuery(_PeriodQuery):
    """Query-string params for GET .../analytics/finance."""
