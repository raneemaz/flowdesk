import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";

import { listRequests } from "@/api/customerRequests";
import { listTasks } from "@/api/tasks";
import { getDepartmentAnalytics, getOverviewAnalytics } from "@/api/analytics";
import { DepartmentComparisonChart } from "@/features/analytics/charts";
import { Loading, QueryError, Section, StatCard } from "@/features/analytics/widgets";
import { useOpenRequestCount } from "@/features/dashboard/useOpenRequestCount";

const CURRENT_MONTH = { period: "current_month" } as const;
const OPEN_REQUEST_STATUSES = new Set(["new", "assigned", "in_progress", "waiting_for_customer"]);

// Spec Section 12.3's Manager dashboard: "team workload, task
// progress, pending reviews, request queue, department-level
// activity." Team workload/task progress come from the overview
// analytics call (full scope, same as Owner's); department-level
// activity reuses the exact department comparison chart
// AnalyticsPage's own Departments section uses. Pending reviews and
// the request queue preview are plain list-endpoint reads (CUSTOMER_REQUEST_MANAGE/
// TASK_VIEW_UPDATE are both full scope for Manager, org-wide already) -
// these are row lists, not aggregates, so they come from the list
// endpoints rather than the analytics API, which has no "list of
// individual records" shape at all.
export function ManagerDashboard({ organizationId }: { organizationId: string }) {
  const overviewQuery = useQuery({
    queryKey: ["dashboard-overview", organizationId],
    queryFn: () => getOverviewAnalytics(organizationId, CURRENT_MONTH),
    enabled: Boolean(organizationId),
  });

  const departmentsQuery = useQuery({
    queryKey: ["dashboard-departments", organizationId],
    queryFn: () => getDepartmentAnalytics(organizationId, CURRENT_MONTH),
    enabled: Boolean(organizationId),
  });

  const pendingReviewsQuery = useQuery({
    queryKey: ["dashboard-pending-reviews", organizationId],
    queryFn: () => listTasks(organizationId, { status: "under_review", perPage: 5 }),
    enabled: Boolean(organizationId),
  });

  const queueQuery = useQuery({
    queryKey: ["dashboard-request-queue", organizationId],
    queryFn: () => listRequests(organizationId, { perPage: 10 }),
    enabled: Boolean(organizationId),
  });
  const openQueuePreview = (queueQuery.data?.requests ?? []).filter((request) => OPEN_REQUEST_STATUSES.has(request.status));
  const openQueueCount = useOpenRequestCount(organizationId);

  return (
    <div className="flex flex-col gap-6">
      <Section title="Team workload">
        {overviewQuery.isPending && <Loading />}
        {overviewQuery.isError && <QueryError error={overviewQuery.error} />}
        {overviewQuery.data && (
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            <StatCard label="Active tasks" value={String(overviewQuery.data.active_tasks)} />
            <StatCard label="Completed tasks" value={String(overviewQuery.data.completed_tasks)} />
            <StatCard label="Overdue tasks" value={String(overviewQuery.data.overdue_tasks)} />
            <StatCard label="Open requests" value={openQueueCount.isPending ? "…" : String(openQueueCount.total)} />
          </div>
        )}
      </Section>

      <Section title="Pending reviews">
        {pendingReviewsQuery.isPending && <Loading />}
        {pendingReviewsQuery.isError && <QueryError error={pendingReviewsQuery.error} />}
        {pendingReviewsQuery.data && pendingReviewsQuery.data.tasks.length === 0 && (
          <p className="text-sm text-foreground/70">Nothing waiting for review.</p>
        )}
        {pendingReviewsQuery.data && pendingReviewsQuery.data.tasks.length > 0 && (
          <ul className="flex flex-col gap-2">
            {pendingReviewsQuery.data.tasks.map((task) => (
              <li key={task.id}>
                <Link to={`/tasks/${task.id}`} className="block rounded-md border border-border bg-card p-3 text-sm text-primary hover:underline">
                  {task.title}
                </Link>
              </li>
            ))}
          </ul>
        )}
      </Section>

      <Section title="Request queue">
        {queueQuery.isPending && <Loading />}
        {queueQuery.isError && <QueryError error={queueQuery.error} />}
        {queueQuery.data && openQueuePreview.length === 0 && <p className="text-sm text-foreground/70">No open requests.</p>}
        {queueQuery.data && openQueuePreview.length > 0 && (
          <ul className="flex flex-col gap-2">
            {openQueuePreview.slice(0, 5).map((request) => (
              <li key={request.id}>
                <Link to={`/requests/${request.id}`} className="block rounded-md border border-border bg-card p-3 text-sm text-primary hover:underline">
                  {request.title}
                </Link>
              </li>
            ))}
          </ul>
        )}
        <Link to="/requests" className="text-sm font-medium text-primary hover:underline">
          View all requests →
        </Link>
      </Section>

      <Section title="Department-level activity">
        {departmentsQuery.isPending && <Loading />}
        {departmentsQuery.isError && <QueryError error={departmentsQuery.error} />}
        {departmentsQuery.data && <DepartmentComparisonChart departments={departmentsQuery.data} />}
      </Section>
    </div>
  );
}
