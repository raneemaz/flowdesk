import uuid
from datetime import date, datetime, timezone

from sqlalchemy import Date, DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.extensions import db
from app.models.base import UUIDPrimaryKeyMixin


class AIReport(UUIDPrimaryKeyMixin, db.Model):
    """FD-058. Fields per spec Section 10.1's AIReport entity (id,
    organization_id, report_type, period_start, period_end,
    metrics_snapshot, summary, recommendations, model/provider
    metadata).

    **No `TimestampMixin`** - like `ActivityLog`/`TaskHistory`, a
    report is an append-only historical record once generated; there's
    no edit route anywhere in this codebase, so an `updated_at` column
    would imply a capability that doesn't exist. A plain `created_at`
    (row-insertion time) is kept alongside `generated_at` (the AI's own
    generation timestamp, from `WeeklyReportOutput.generated_at`) -
    the two are expected to be very close but aren't the same thing.

    **No `organization` relationship()** - same precedent `ActivityLog`/
    `Notification` (FD-047/FD-048) already established for the most
    recent org-scoped audit-style tables in this codebase: a plain FK
    column, navigated by filtering, never by ORM relationship.
    `Organization` itself is correspondingly left untouched (no
    `ai_reports` back-reference added there either).

    **`summary` vs. `recommendations` as two separate JSONB columns**
    (FR-042: "clearly separate facts from AI-generated
    recommendations") - `summary` holds the four FACTUAL narrative
    sections (`business_overview`/`employee_productivity`/
    `financial_overview`/`operational_problems`) plus `missing_data`;
    `recommendations` (a JSON array of strings) gets its own top-level
    column instead of being folded into `summary`, matching the
    spec's own literal two-field split ("summary, recommendations")
    rather than one opaque blob a frontend (FD-060) would have to
    re-parse to tell facts from opinions.

    **`metrics_snapshot` is stored verbatim** (FD-056's own already-
    JSON-serializable dict, exactly as sent to the AI provider) - this
    is what makes a persisted report independently auditable later
    even if the live analytics numbers have since changed.

    **`UniqueConstraint` on `(organization_id, report_type,
    period_start, period_end)`**: there is exactly one report per
    organization/type/period, ever - the natural key FD-059's own "no
    duplicates" acceptance criterion needs, defined here rather than
    retrofitted later (adding a uniqueness constraint onto a table
    that may already have violating rows is real migration pain this
    avoids by existing from the first migration).
    `app.ai_reports.service.save_ai_report` surfaces a collision as a
    `409`, never a silent second row or a silent overwrite -
    regenerating an existing period is a deliberate action a future
    caller must explicitly choose, not something this task builds.
    """

    __tablename__ = "ai_reports"
    __table_args__ = (
        UniqueConstraint(
            "organization_id", "report_type", "period_start", "period_end", name="uq_ai_reports_org_type_period"
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    report_type: Mapped[str] = mapped_column(String(50), nullable=False, default="weekly", server_default="weekly")
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    metrics_snapshot: Mapped[dict] = mapped_column(JSONB, nullable=False)
    summary: Mapped[dict] = mapped_column(JSONB, nullable=False)
    recommendations: Mapped[list] = mapped_column(JSONB, nullable=False)
    model: Mapped[str] = mapped_column(String(100), nullable=False)
    provider: Mapped[str] = mapped_column(String(50), nullable=False)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )

    def to_public_dict(self) -> dict:
        return {
            "id": str(self.id),
            "organization_id": str(self.organization_id),
            "report_type": self.report_type,
            "period_start": self.period_start.isoformat(),
            "period_end": self.period_end.isoformat(),
            "metrics_snapshot": self.metrics_snapshot,
            "summary": self.summary,
            "recommendations": self.recommendations,
            "model": self.model,
            "provider": self.provider,
            "generated_at": self.generated_at.isoformat(),
            "created_at": self.created_at.isoformat(),
        }

    def __repr__(self) -> str:
        return f"<AIReport org={self.organization_id} type={self.report_type} period={self.period_start}:{self.period_end}>"
