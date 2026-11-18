import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";

import { listRequests } from "@/api/customerRequests";
import { Loading, QueryError, Section, StatCard } from "@/features/analytics/widgets";
import { useOpenRequestCount } from "@/features/dashboard/useOpenRequestCount";
import { useOwnMembershipId } from "@/features/dashboard/useOwnMembershipId";

const OPEN_REQUEST_STATUSES = new Set(["new", "assigned", "in_progress", "waiting_for_customer"]);

// Spec Section 12.3's CustomerSupport dashboard: "open/waiting
// requests, assignments, response workload." CUSTOMER_REQUEST_MANAGE
// is `full` for this role (org-wide, not self-scoped), so "my
// assignments"/"response workload" need this caller's own
// membership_id first (same lookup EmployeeDashboard's sibling,
// pages/MyTasksPage.tsx, already established) - unlike Employee's own
// dashboard, where TASK_VIEW_UPDATE's `assigned` scope does that
// restriction server-side automatically. "Response workload" is read
// as this person's *currently open* assignments (a real, defensible
// proxy for how much is on their plate right now) rather than a
// fabricated response-time metric no endpoint computes.
export function CustomerSupportDashboard({ organizationId }: { organizationId: string }) {
  const ownMembershipQuery = useOwnMembershipId(organizationId, true);
  const ownMembershipId = ownMembershipQuery.data ?? undefined;

  const queueQuery = useQuery({
    queryKey: ["dashboard-request-queue", organizationId],
    queryFn: () => listRequests(organizationId, { perPage: 10 }),
    enabled: Boolean(organizationId),
  });
  const openQueuePreview = (queueQuery.data?.requests ?? []).filter((request) => OPEN_REQUEST_STATUSES.has(request.status));
  const openQueueCount = useOpenRequestCount(organizationId);

  const myAssignmentsQuery = useQuery({
    queryKey: ["dashboard-my-assignments", organizationId, ownMembershipId],
    queryFn: () => listRequests(organizationId, { assigneeMembershipId: ownMembershipId, perPage: 5 }),
    enabled: Boolean(organizationId) && Boolean(ownMembershipId),
  });
  const myOpenCount = useOpenRequestCount(organizationId, { assigneeMembershipId: ownMembershipId }, Boolean(ownMembershipId));

  return (
    <div className="flex flex-col gap-6">
      <Section title="Open & waiting requests">
        {openQueueCount.isPending && <Loading />}
        {openQueueCount.isError && (
          <p role="alert" className="text-sm text-destructive">
            Something went wrong loading request counts.
          </p>
        )}
        {!openQueueCount.isPending && !openQueueCount.isError && (
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            <StatCard label="Open org-wide" value={String(openQueueCount.total)} />
            <StatCard label="My open assignments (workload)" value={myOpenCount.isPending ? "…" : String(myOpenCount.total)} />
            <StatCard label="My total assignments" value={myAssignmentsQuery.data ? String(myAssignmentsQuery.data.meta.total) : "…"} />
          </div>
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
      </Section>

      <Section title="My assignments">
        {myAssignmentsQuery.isPending && <Loading />}
        {myAssignmentsQuery.isError && <QueryError error={myAssignmentsQuery.error} />}
        {myAssignmentsQuery.data && myAssignmentsQuery.data.requests.length === 0 && (
          <p className="text-sm text-foreground/70">Nothing assigned to you.</p>
        )}
        {myAssignmentsQuery.data && myAssignmentsQuery.data.requests.length > 0 && (
          <ul className="flex flex-col gap-2">
            {myAssignmentsQuery.data.requests.map((request) => (
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
    </div>
  );
}
