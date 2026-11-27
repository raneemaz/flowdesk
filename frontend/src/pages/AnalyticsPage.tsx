import { useState } from "react";
import { useQuery } from "@tanstack/react-query";


import { getDepartmentAnalytics, getEmployeeAnalytics, getFinancialAnalytics, getOverviewAnalytics } from "@/api/analytics";
import { DepartmentComparisonChart, InvoiceDistributionChart, RevenueByDayChart } from "@/features/analytics/charts";
import { PeriodSelector, type PeriodValue } from "@/features/analytics/PeriodSelector";
import { canViewDepartmentAnalytics, canViewFinancialAnalytics, canViewOverviewAnalytics } from "@/features/analytics/permissions";
import { Loading, QueryError, Section, StatCard } from "@/features/analytics/widgets";
import { useOrganization } from "@/contexts/OrganizationContext";
import type { PeriodFilter } from "@/api/analytics";

const DEFAULT_PERIOD: PeriodValue = { period: "current_month", periodStart: "", periodEnd: "" };

// FR-034's period is ready to query the moment it's a named window;
// "custom" needs both bounds filled in first - never fires a request
// that would just 422 on a half-entered custom range.
function toFilter(value: PeriodValue): PeriodFilter | null {
  if (value.period === "custom") {
    if (!value.periodStart || !value.periodEnd) return null;
    return { period: "custom", periodStart: value.periodStart, periodEnd: value.periodEnd };
  }
  return { period: value.period };
}

// FD-053. Every sub-section below is gated exactly the way FD-052's
// own endpoints gate it (features/analytics/permissions.ts) - a role
// this page shows nothing extra for (Employee/CustomerSupport beyond
// the employee-performance table) isn't a bug, it's FD-051's own
// documented scope: no FR asks for a historical/aggregate view for
// those roles beyond what's shown here.
export function AnalyticsPage() {
  const { activeMembership } = useOrganization();
  const organizationId = activeMembership?.organization.id ?? "";
  const role = activeMembership?.role;

  const [periodValue, setPeriodValue] = useState<PeriodValue>(DEFAULT_PERIOD);
  const filter = toFilter(periodValue);

  const canSeeOverview = role ? canViewOverviewAnalytics(role) : false;
  const canSeeDepartments = role ? canViewDepartmentAnalytics(role) : false;
  const canSeeFinance = role ? canViewFinancialAnalytics(role) : false;

  const overviewQuery = useQuery({
    queryKey: ["analytics-overview", organizationId, filter],
    queryFn: () => getOverviewAnalytics(organizationId, filter!),
    enabled: Boolean(organizationId) && canSeeOverview && filter !== null,
  });

  const employeesQuery = useQuery({
    queryKey: ["analytics-employees", organizationId, filter],
    queryFn: () => getEmployeeAnalytics(organizationId, filter!),
    enabled: Boolean(organizationId) && filter !== null,
  });

  const departmentsQuery = useQuery({
    queryKey: ["analytics-departments", organizationId, filter],
    queryFn: () => getDepartmentAnalytics(organizationId, filter!),
    enabled: Boolean(organizationId) && canSeeDepartments && filter !== null,
  });

  const financeQuery = useQuery({
    queryKey: ["analytics-finance", organizationId, filter],
    queryFn: () => getFinancialAnalytics(organizationId, filter!),
    enabled: Boolean(organizationId) && canSeeFinance && filter !== null,
  });

  return (
    <div className="flex max-w-7xl flex-col gap-6 px-6 py-8 lg:px-10">
      <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2">
        <h1 className="text-2xl font-semibold">Analytics</h1>
      </div>

      <PeriodSelector value={periodValue} onChange={setPeriodValue} />

      {filter === null && <p className="text-sm text-foreground/70">Choose a start and end date for the custom range.</p>}

      {canSeeOverview && (
        <Section title="Overview">
          {filter !== null && overviewQuery.isPending && <Loading />}
          {overviewQuery.isError && <QueryError error={overviewQuery.error} />}
          {overviewQuery.data && (
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
              <StatCard label="Employees" value={String(overviewQuery.data.employee_count)} />
              <StatCard label="Active tasks" value={String(overviewQuery.data.active_tasks)} />
              <StatCard label="Completed tasks" value={String(overviewQuery.data.completed_tasks)} />
              <StatCard label="Overdue tasks" value={String(overviewQuery.data.overdue_tasks)} />
              <StatCard label="Open requests" value={String(overviewQuery.data.open_requests)} />
              <StatCard label="Invoiced" value={overviewQuery.data.monthly_invoiced} />
              <StatCard label="Collected" value={overviewQuery.data.monthly_collected} />
            </div>
          )}
        </Section>
      )}

      {canSeeDepartments && (
        <Section title="Departments">
          {filter !== null && departmentsQuery.isPending && <Loading />}
          {departmentsQuery.isError && <QueryError error={departmentsQuery.error} />}
          {departmentsQuery.data && <DepartmentComparisonChart departments={departmentsQuery.data} />}
        </Section>
      )}

      <Section title="Employee performance">
        {filter !== null && employeesQuery.isPending && <Loading />}
        {employeesQuery.isError && <QueryError error={employeesQuery.error} />}
        {employeesQuery.data && employeesQuery.data.length === 0 && (
          <p className="text-sm text-foreground/70">No employee data for this period.</p>
        )}
        {employeesQuery.data && employeesQuery.data.length > 0 && (
          <div className="relative overflow-x-auto rounded-md border border-border">
            <table className="w-full text-left text-sm [&_td]:whitespace-nowrap [&_th]:whitespace-nowrap">
              <thead className="bg-card">
                <tr>
                  <th className="px-4 py-2 font-medium">Name</th>
                  <th className="px-4 py-2 font-medium">Assigned</th>
                  <th className="px-4 py-2 font-medium">Completed</th>
                  <th className="px-4 py-2 font-medium">Overdue</th>
                  <th className="px-4 py-2 font-medium">Completion rate</th>
                  <th className="px-4 py-2 font-medium">Avg. completion time</th>
                </tr>
              </thead>
              <tbody>
                {employeesQuery.data.map((row) => (
                  <tr key={row.membership_id} className="border-t border-border">
                    <td className="px-4 py-2">{row.name}</td>
                    <td className="px-4 py-2">{row.assigned_tasks}</td>
                    <td className="px-4 py-2">{row.completed_tasks}</td>
                    <td className="px-4 py-2">{row.overdue_tasks}</td>
                    <td className="px-4 py-2">
                      {row.completion_rate === null ? "—" : `${Math.round(row.completion_rate * 100)}%`}
                    </td>
                    <td className="px-4 py-2">
                      {row.avg_completion_time_hours === null ? "—" : `${row.avg_completion_time_hours.toFixed(1)}h`}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Section>

      {canSeeFinance && (
        <Section title="Finance">
          {filter !== null && financeQuery.isPending && <Loading />}
          {financeQuery.isError && <QueryError error={financeQuery.error} />}
          {financeQuery.data && (
            <div className="flex flex-col gap-4">
              <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
                <StatCard label="Invoiced" value={financeQuery.data.total_invoiced} />
                <StatCard label="Collected" value={financeQuery.data.total_collected} />
                <StatCard label="Outstanding" value={financeQuery.data.outstanding_balance} />
                <StatCard label="Overdue invoices" value={String(financeQuery.data.overdue_invoice_count)} />
              </div>
              <div className="rounded-md border border-border bg-card p-4">
                <h3 className="mb-2 text-sm font-medium text-foreground/70">Revenue over time</h3>
                <RevenueByDayChart data={financeQuery.data.revenue_by_day} />
              </div>
              <div className="rounded-md border border-border bg-card p-4">
                <h3 className="mb-2 text-sm font-medium text-foreground/70">Invoice distribution</h3>
                <InvoiceDistributionChart distribution={financeQuery.data.invoice_distribution} />
              </div>
            </div>
          )}
        </Section>
      )}
    </div>
  );
}
