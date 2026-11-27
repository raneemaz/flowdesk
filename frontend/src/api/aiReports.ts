import { apiFetch, apiFetchWithMeta } from "@/api/client";
import type { PaginationMeta } from "@/types/employee";
import type { AIReportPublic } from "@/types/aiReport";

export interface ListAIReportsFilters {
  page?: number;
  perPage?: number;
}

export interface AIReportListResult {
  reports: AIReportPublic[];
  meta: PaginationMeta;
}

export async function listAIReports(
  organizationId: string,
  filters: ListAIReportsFilters = {},
): Promise<AIReportListResult> {
  const params = new URLSearchParams();
  params.set("page", String(filters.page ?? 1));
  params.set("per_page", String(filters.perPage ?? 20));

  const { data, meta } = await apiFetchWithMeta<AIReportPublic[], PaginationMeta>(
    `/organizations/${organizationId}/ai-reports?${params.toString()}`,
  );
  return { reports: data, meta };
}

export function getAIReport(organizationId: string, reportId: string): Promise<AIReportPublic> {
  return apiFetch<AIReportPublic>(`/organizations/${organizationId}/ai-reports/${reportId}`);
}

export interface GenerateAIReportInput {
  period: "last_7_days" | "last_30_days" | "last_90_days" | "current_month" | "previous_month" | "custom";
  period_start?: string;
  period_end?: string;
}

// Manual, on-demand generation (backend/app/ai_reports/routes.py's
// POST .../generate) - alongside, not instead of, FD-059's own weekly
// scheduled job. A 409 means a report for that exact period already
// exists (the model's own UniqueConstraint); a 502 means the AI
// provider itself failed - both are real ApiError responses the
// caller surfaces, not swallowed here.
export function generateAIReport(
  organizationId: string,
  input: GenerateAIReportInput,
  csrfToken: string,
): Promise<AIReportPublic> {
  return apiFetch<AIReportPublic>(`/organizations/${organizationId}/ai-reports/generate`, {
    method: "POST",
    body: input,
    csrfToken,
    // Waits on the AI provider (with retries) - longer than the default cap.
    timeoutMs: 90_000,
  });
}
