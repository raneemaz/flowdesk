import { apiFetch } from "@/api/client";
import type {
  AnalyticsPeriod,
  DepartmentAnalyticsPublic,
  EmployeePerformancePublic,
  FinancialAnalyticsPublic,
  OverviewAnalyticsPublic,
} from "@/types/analytics";

// FD-052's own query contract: period_start/period_end are accepted
// only, and required, when period is "custom" - every other named
// value takes no bounds at all (the backend 422s otherwise either
// way), so this always sends exactly one of "period" alone or all
// three together.
export interface PeriodFilter {
  period: AnalyticsPeriod;
  periodStart?: string;
  periodEnd?: string;
}

function periodParams(filter: PeriodFilter): URLSearchParams {
  const params = new URLSearchParams({ period: filter.period });
  if (filter.period === "custom") {
    if (filter.periodStart) params.set("period_start", filter.periodStart);
    if (filter.periodEnd) params.set("period_end", filter.periodEnd);
  }
  return params;
}

export function getOverviewAnalytics(organizationId: string, filter: PeriodFilter): Promise<OverviewAnalyticsPublic> {
  return apiFetch<OverviewAnalyticsPublic>(
    `/organizations/${organizationId}/analytics/overview?${periodParams(filter).toString()}`,
  );
}

export interface EmployeeAnalyticsFilter extends PeriodFilter {
  targetMembershipId?: string;
}

export async function getEmployeeAnalytics(
  organizationId: string,
  filter: EmployeeAnalyticsFilter,
): Promise<EmployeePerformancePublic[]> {
  const params = periodParams(filter);
  if (filter.targetMembershipId) params.set("target_membership_id", filter.targetMembershipId);
  return apiFetch<EmployeePerformancePublic[]>(`/organizations/${organizationId}/analytics/employees?${params.toString()}`);
}

export interface DepartmentAnalyticsFilter extends PeriodFilter {
  departmentId?: string;
}

export async function getDepartmentAnalytics(
  organizationId: string,
  filter: DepartmentAnalyticsFilter,
): Promise<DepartmentAnalyticsPublic[]> {
  const params = periodParams(filter);
  if (filter.departmentId) params.set("department_id", filter.departmentId);
  return apiFetch<DepartmentAnalyticsPublic[]>(`/organizations/${organizationId}/analytics/departments?${params.toString()}`);
}

export function getFinancialAnalytics(organizationId: string, filter: PeriodFilter): Promise<FinancialAnalyticsPublic> {
  return apiFetch<FinancialAnalyticsPublic>(
    `/organizations/${organizationId}/analytics/finance?${periodParams(filter).toString()}`,
  );
}
