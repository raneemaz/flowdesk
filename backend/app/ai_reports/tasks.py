"""FD-059: the scheduled weekly AI report job's real logic (Section
14: "Weekly business/AI summary | Once per week, per organization, in
the org's own timezone"; Section 35 open decision #11, resolved at
the user's explicit direction: every Monday at 06:00 in each
organization's own local time, covering the preceding Monday-Sunday
week. An organization with no real activity yet still gets a report
- FR-042's own "identify missing data" already covers this (the AI
lists empty sections under `missing_data`); this job doesn't invent a
skip condition the spec never asks for.

**Celery-free by design** - `app.celery_app` wraps `run_due_weekly_reports`
below in the one `@celery_app.task` Beat actually schedules; this
module itself imports nothing Celery-related, so it's directly
unit-testable with no broker/worker involved (same "pure function +
thin framework wrapper" split this codebase already uses throughout,
e.g. `app.ai.providers.complete_with_retries`).

**"One organization's failure never blocks another's"** (Epic E08's
own acceptance criterion): every organization is processed inside its
own try/except; a provider failure or an already-existing report
(`409` - e.g. the same hour's Beat tick firing twice) is logged and
the loop continues, never propagated past that one organization.

**"No duplicates"**: this job never tracks "has this organization
already gotten a report this week" itself - it relies entirely on
`AIReport`'s own `UniqueConstraint` (FD-058) via `save_ai_report`'s
`409`. Re-running this job (a worker restart mid-sweep, a retried
Celery task, Beat double-firing) is always safe: an organization
already generated this week is skipped by the database, not by this
job's own bookkeeping - one less thing that could ever get out of
sync."""

import logging
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.ai.service import AIReportGenerationError
from app.ai_reports.service import generate_and_store_report
from app.errors import APIError
from app.extensions import db
from app.models import Organization

logger = logging.getLogger(__name__)

_TARGET_WEEKDAY = 0  # date.weekday(): Monday == 0
_TARGET_HOUR = 6  # 06:00, in the organization's own local timezone


def _organization_local_time(organization: Organization, now_utc: datetime) -> datetime:
    """Identical in intent to `app.analytics.service._today_in_timezone`'s
    own invalid-timezone fallback - duplicated, not imported, same
    "don't cross-import a private per-module helper" convention this
    codebase already follows."""
    try:
        tz = ZoneInfo(organization.timezone)
    except (ZoneInfoNotFoundError, ValueError, TypeError):
        tz = timezone.utc
    return now_utc.astimezone(tz)


def _is_due_now(organization: Organization, now_utc: datetime) -> bool:
    local_time = _organization_local_time(organization, now_utc)
    return local_time.weekday() == _TARGET_WEEKDAY and local_time.hour == _TARGET_HOUR


def _preceding_week(local_date: date) -> tuple[date, date]:
    """`local_date` is "today" in the organization's own local time
    (a Monday, since this is only ever called when `_is_due_now` just
    confirmed that) - the week this report covers is the one that
    just ended: the Sunday before `local_date`, back through the
    Monday 7 days before `local_date`."""
    period_end = local_date - timedelta(days=1)
    period_start = period_end - timedelta(days=6)
    return period_start, period_end


def run_due_weekly_reports(now: datetime | None = None) -> list[dict]:
    """Checks every organization in the system (there is no org-level
    active/inactive concept anywhere in this codebase - every row is
    live) and generates+persists a weekly report for whichever ones
    are currently at their own Monday-06:00 local time. Returns one
    result dict per organization actually *attempted* (most hourly
    ticks match nobody, so most calls return an empty list) -
    `{"organization_id", "status": "generated"|"skipped"|"failed",
    "detail"}` - useful for tests and for a human reading worker logs
    alongside them; nothing else in this codebase consumes this return
    value."""
    now_utc = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    results: list[dict] = []

    for organization in db.session.query(Organization).all():
        if not _is_due_now(organization, now_utc):
            continue

        local_date = _organization_local_time(organization, now_utc).date()
        period_start, period_end = _preceding_week(local_date)

        try:
            report = generate_and_store_report(organization, period_start=period_start, period_end=period_end)
        except AIReportGenerationError as exc:
            logger.warning("Weekly AI report generation failed for organization %s: %s", organization.id, exc)
            results.append({"organization_id": organization.id, "status": "failed", "detail": str(exc)})
            continue
        except APIError as exc:
            if exc.status_code != 409:
                raise
            logger.info("Weekly AI report already exists for organization %s: %s", organization.id, exc.message)
            results.append({"organization_id": organization.id, "status": "skipped", "detail": exc.message})
            continue

        logger.info("Generated weekly AI report %s for organization %s", report.id, organization.id)
        results.append({"organization_id": organization.id, "status": "generated", "detail": str(report.id)})

    return results
