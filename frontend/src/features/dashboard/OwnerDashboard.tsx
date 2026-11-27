import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";

import { getEmployeeAnalytics, getOverviewAnalytics } from "@/api/analytics";
import { Loading, QueryError, Section, StatCard } from "@/features/analytics/widgets";
import { ActivityFeedSummary, InvoicesPaymentsSummary, TaskBoardSummary } from "@/features/dashboard/SummaryWidgets";

const CURRENT_MONTH = { period: "current_month" } as const;

// Spec Section 12.3's Owner dashboard: "business stats, financial
// overview, employee performance, overdue tasks, AI weekly summary."
// Business stats + financial overview + overdue tasks all come from
// the single overview analytics call (FD-052) - overview's own
// monthly_invoiced/monthly_collected *is* the financial overview, so
// this never makes a second call to the finance endpoint just to
// re-show numbers the overview endpoint already carries. AI weekly
// summary is a documented gap: that's FD-055 onward (AI reporting
// epic), not built yet - omitted rather than stubbed.
export function OwnerDashboard({ organizationId }: { organizationId: string }) {
  const overviewQuery = useQuery({
    queryKey: ["dashboard-overview", organizationId],
    queryFn: () => getOverviewAnalytics(organizationId, CURRENT_MONTH),
    enabled: Boolean(organizationId),
  });

  const employeesQuery = useQuery({
    queryKey: ["dashboard-employees", organizationId],
    queryFn: () => getEmployeeAnalytics(organizationId, CURRENT_MONTH),
    enabled: Boolean(organizationId),
  });

  return (
    <div className="flex flex-col gap-6">
      <Section title="Summary">
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
          <TaskBoardSummary organizationId={organizationId} />
          <InvoicesPaymentsSummary organizationId={organizationId} />
          <ActivityFeedSummary organizationId={organizationId} />
        </div>
      </Section>

      <Section title="Business stats">
        {overviewQuery.isPending && <Loading />}
        {overviewQuery.isError && <QueryError error={overviewQuery.error} />}
        {overviewQuery.data && (
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            <StatCard label="Employees" value={String(overviewQuery.data.employee_count)} />
            <StatCard label="Active tasks" value={String(overviewQuery.data.active_tasks)} />
            <StatCard label="Overdue tasks" value={String(overviewQuery.data.overdue_tasks)} />
            <StatCard label="Open requests" value={String(overviewQuery.data.open_requests)} />
          </div>
        )}
      </Section>

      <Section title="Financial overview (this month)">
        {overviewQuery.data && (
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            <StatCard label="Invoiced" value={overviewQuery.data.monthly_invoiced} />
            <StatCard label="Collected" value={overviewQuery.data.monthly_collected} />
          </div>
        )}
      </Section>

      <Section title="Employee performance">
        {employeesQuery.isPending && <Loading />}
        {employeesQuery.isError && <QueryError error={employeesQuery.error} />}
        {employeesQuery.data && employeesQuery.data.length === 0 && (
          <p className="text-sm text-foreground/70">No employee data yet.</p>
        )}
        {employeesQuery.data && employeesQuery.data.length > 0 && (
          <ul className="flex flex-col gap-2">
            {employeesQuery.data.slice(0, 5).map((row) => (
              <li key={row.membership_id} className="flex items-center justify-between rounded-md border border-border bg-card p-3 text-sm">
                <span>{row.name}</span>
                <span className="text-foreground/70">
                  {row.completed_tasks}/{row.assigned_tasks} completed
                  {row.overdue_tasks > 0 ? ` · ${row.overdue_tasks} overdue` : ""}
                </span>
              </li>
            ))}
          </ul>
        )}
        <Link to="/analytics" className="text-sm font-medium text-primary hover:underline">
          View full analytics →
        </Link>
      </Section>
    </div>
  );
}
