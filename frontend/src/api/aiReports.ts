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
