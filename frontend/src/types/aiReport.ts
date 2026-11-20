// Mirrors backend/openapi.yaml's AIReportPublic schema exactly (FD-058).
// `summary` holds the four FACTUAL narrative sections plus
// missing_data; `recommendations` is its own top-level field - the
// same split the backend model keeps as two separate JSONB columns
// (FR-042: "clearly separate facts from AI-generated
// recommendations") so this type alone is enough to render the two
// differently without re-parsing anything.
export interface AIReportSummary {
  business_overview: string;
  employee_productivity: string;
  financial_overview: string;
  operational_problems: string;
  missing_data: string[];
}

export interface AIReportPublic {
  id: string;
  organization_id: string;
  report_type: string;
  period_start: string;
  period_end: string;
  // Not rendered anywhere in FD-060 - the raw FD-056 snapshot, kept
  // for later auditability, not meant for direct display.
  metrics_snapshot: Record<string, unknown>;
  summary: AIReportSummary;
  recommendations: string[];
  model: string;
  provider: string;
  generated_at: string;
  created_at: string;
}
