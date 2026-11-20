"""FD-058: AI report persistence (store report + snapshot + generation
metadata, FR-040/FR-042). Lives in its own top-level module rather
than inside `app.ai` - `app.ai` stays the stateless generation
pipeline it was built as in FD-055/056/057 (no DB model, no HTTP
routes); this module owns the one genuinely new persisted entity
(`AIReport`) and its HTTP surface, the same separation
`app.analytics` (computes, owns no model) and `app.invoices`/
`app.payments` (own their own models) already draw elsewhere in this
codebase.

`save_ai_report` is pure persistence - no AI call, no snapshot
computation - and `generate_and_store_report` is the one function
that actually ties FD-057's `generate_report_for_organization` to it.
Splitting them this way means a caller already holding a
`GeneratedWeeklyReport` (so a future retry path, FD-059, could in
principle regenerate once and persist separately) is never forced
through a second AI call just to persist, and `save_ai_report` itself
is trivially unit-testable with no provider/network involved at all.

**Collision handling**: `AIReport`'s own `UniqueConstraint` on
`(organization_id, report_type, period_start, period_end)` means a
second `save_ai_report` call for the same organization/type/period
raises `IntegrityError`, caught here and re-raised as `APIError(409)`
- never a silent second row, never a silent overwrite. See
`app.models.ai_report.AIReport`'s own docstring for why this
constraint exists now rather than being retrofitted once FD-059
(Celery Beat, "retry-safe... no duplicates") actually needs it.

**A failed generation never produces a misleading "successful"
report** (Epic E08's own acceptance criterion): `generate_and_store_report`
adds no `except` of its own around the generation call -
`AIReportGenerationError` from `app.ai.service` propagates unchanged,
and nothing is ever written to the database unless generation
actually succeeded first."""

import uuid
from datetime import date

from sqlalchemy.exc import IntegrityError

from app.ai.providers import AIProvider
from app.ai.schemas import WeeklyReportOutput
from app.ai.service import generate_report_for_organization
from app.errors import APIError
from app.extensions import db
from app.models import AIReport, Organization

_PROVIDER_NAME = "anthropic"  # the one real AIProvider this project implements (FD-055, Section 35 decision #12)


def save_ai_report(
    organization_id: uuid.UUID,
    report_type: str,
    metrics_snapshot: dict,
    report: WeeklyReportOutput,
    *,
    provider_name: str = _PROVIDER_NAME,
) -> AIReport:
    ai_report = AIReport(
        organization_id=organization_id,
        report_type=report_type,
        period_start=report.period_start,
        period_end=report.period_end,
        metrics_snapshot=metrics_snapshot,
        summary={
            "business_overview": report.business_overview,
            "employee_productivity": report.employee_productivity,
            "financial_overview": report.financial_overview,
            "operational_problems": report.operational_problems,
            "missing_data": report.missing_data,
        },
        recommendations=report.recommendations,
        model=report.model,
        provider=provider_name,
        generated_at=report.generated_at,
    )
    db.session.add(ai_report)
    try:
        db.session.commit()
    except IntegrityError as exc:
        db.session.rollback()
        raise APIError(
            "A report for this organization, type, and period already exists.",
            status_code=409,
            code="REPORT_ALREADY_EXISTS",
            details={"period": "a report for this period already exists"},
        ) from exc
    return ai_report


def generate_and_store_report(
    organization: Organization,
    *,
    period_start: date,
    period_end: date,
    report_type: str = "weekly",
    provider: AIProvider | None = None,
) -> AIReport:
    generated = generate_report_for_organization(
        organization, period_start=period_start, period_end=period_end, provider=provider
    )
    return save_ai_report(organization.id, report_type, generated.metrics_snapshot, generated.output)


def list_ai_reports(organization_id: uuid.UUID, *, page: int, per_page: int) -> tuple[list[AIReport], int]:
    query = db.session.query(AIReport).filter_by(organization_id=organization_id)
    total = query.count()
    reports = query.order_by(AIReport.period_start.desc()).offset((page - 1) * per_page).limit(per_page).all()
    return reports, total


def get_ai_report_or_404(organization_id: uuid.UUID, report_id: uuid.UUID) -> AIReport:
    report = db.session.query(AIReport).filter_by(id=report_id, organization_id=organization_id).first()
    if report is None:
        raise APIError("Not found.", status_code=404, code="NOT_FOUND")
    return report
