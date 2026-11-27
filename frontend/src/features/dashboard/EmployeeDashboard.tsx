import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";

import { listActivity } from "@/api/activity";
import { describeActivity } from "@/features/activity/describe";
import { getEmployeeAnalytics } from "@/api/analytics";
import { listNotifications } from "@/api/notifications";
import { listTasks } from "@/api/tasks";
import { Loading, QueryError, Section, StatCard } from "@/features/analytics/widgets";
import type { TaskPublic } from "@/types/task";

const CURRENT_MONTH = { period: "current_month" } as const;
const TERMINAL_STATUSES = new Set(["completed", "cancelled"]);

// "Upcoming" and "overdue" are spec Section 12.3's own two separate
// dashboard items - a task whose due_date has already passed belongs
// to the overdue stat card above, not here too, even though it's
// still open. Plain ISO (yyyy-mm-dd) string comparison against
// today's own date is enough for a same-day-granularity due_date
// field - no timezone-aware parsing needed for this comparison.
function upcomingDeadlines(tasks: TaskPublic[]): TaskPublic[] {
  const todayIso = new Date().toISOString().slice(0, 10);
  return tasks
    .filter((task) => task.due_date !== null && task.due_date >= todayIso && !TERMINAL_STATUSES.has(task.status))
    .sort((a, b) => (a.due_date! < b.due_date! ? -1 : a.due_date! > b.due_date! ? 1 : 0));
}

// Spec Section 12.3's Employee dashboard: "my tasks, upcoming
// deadlines, overdue tasks, recent activity, notifications." TASK_VIEW_UPDATE's
// `assigned` scope already auto-restricts GET /tasks to this caller's
// own tasks server-side (same precedent pages/MyTasksPage.tsx
// documents) - no own-membership-id lookup needed here, unlike the
// CustomerSupport dashboard. "My tasks" and "upcoming deadlines" are
// two views of the one fetched page, not two separate requests.
// Overdue tasks comes from the employee analytics endpoint's own
// scope-forced-to-self overdue_tasks count (a precise server
// aggregate) rather than a client count over a possibly-partial page.
export function EmployeeDashboard({ organizationId }: { organizationId: string }) {
  const tasksQuery = useQuery({
    queryKey: ["dashboard-my-tasks", organizationId],
    queryFn: () => listTasks(organizationId, { perPage: 20 }),
    enabled: Boolean(organizationId),
  });

  const performanceQuery = useQuery({
    queryKey: ["dashboard-employees", organizationId],
    queryFn: () => getEmployeeAnalytics(organizationId, CURRENT_MONTH),
    enabled: Boolean(organizationId),
  });
  const overdueTasks = performanceQuery.data?.[0]?.overdue_tasks ?? null;

  const activityQuery = useQuery({
    queryKey: ["dashboard-activity", organizationId],
    queryFn: () => listActivity(organizationId, 1, 5),
    enabled: Boolean(organizationId),
  });

  const notificationsQuery = useQuery({
    queryKey: ["dashboard-notifications", organizationId],
    queryFn: () => listNotifications(organizationId, { perPage: 5 }),
    enabled: Boolean(organizationId),
  });

  const tasks = tasksQuery.data?.tasks ?? [];
  const deadlines = upcomingDeadlines(tasks).slice(0, 5);

  return (
    <div className="flex flex-col gap-6">
      <Section title="Overdue tasks">
        {performanceQuery.isPending && <Loading />}
        {performanceQuery.isError && <QueryError error={performanceQuery.error} />}
        {overdueTasks !== null && <StatCard label="Overdue tasks" value={String(overdueTasks)} />}
      </Section>

      <Section title="My tasks">
        {tasksQuery.isPending && <Loading />}
        {tasksQuery.isError && <QueryError error={tasksQuery.error} />}
        {tasksQuery.data && tasks.length === 0 && <p className="text-sm text-foreground/70">No tasks assigned to you.</p>}
        {tasksQuery.data && tasks.length > 0 && (
          <ul className="flex flex-col gap-2">
            {tasks.slice(0, 5).map((task) => (
              <li key={task.id}>
                <Link to={`/tasks/${task.id}`} className="block rounded-md border border-border bg-card p-3 text-sm text-primary hover:underline">
                  {task.title}
                </Link>
              </li>
            ))}
          </ul>
        )}
      </Section>

      <Section title="Upcoming deadlines">
        {tasksQuery.data && deadlines.length === 0 && <p className="text-sm text-foreground/70">Nothing due soon.</p>}
        {deadlines.length > 0 && (
          <ul className="flex flex-col gap-2">
            {deadlines.map((task) => (
              <li key={task.id} className="flex items-center justify-between rounded-md border border-border bg-card p-3 text-sm">
                <Link to={`/tasks/${task.id}`} className="text-primary hover:underline">
                  {task.title}
                </Link>
                <span className="text-foreground/70">{task.due_date}</span>
              </li>
            ))}
          </ul>
        )}
      </Section>

      <Section title="Recent activity">
        {activityQuery.isPending && <Loading />}
        {activityQuery.isError && <QueryError error={activityQuery.error} />}
        {activityQuery.data && activityQuery.data.entries.length === 0 && (
          <p className="text-sm text-foreground/70">No recent activity.</p>
        )}
        {activityQuery.data && activityQuery.data.entries.length > 0 && (
          <ul className="flex flex-col gap-2">
            {activityQuery.data.entries.map((entry) => (
              <li key={entry.id} className="rounded-md border border-border bg-card p-3 text-sm text-foreground/70">
                {describeActivity(entry, () => "You").text}
              </li>
            ))}
          </ul>
        )}
      </Section>

      <Section title="Notifications">
        {notificationsQuery.isPending && <Loading />}
        {notificationsQuery.isError && <QueryError error={notificationsQuery.error} />}
        {notificationsQuery.data && notificationsQuery.data.notifications.length === 0 && (
          <p className="text-sm text-foreground/70">No notifications yet.</p>
        )}
        {notificationsQuery.data && notificationsQuery.data.notifications.length > 0 && (
          <ul className="flex flex-col gap-2">
            {notificationsQuery.data.notifications.map((notification) => (
              <li key={notification.id} className="rounded-md border border-border bg-card p-3 text-sm">
                {notification.title}
              </li>
            ))}
          </ul>
        )}
        <Link to="/notifications" className="text-sm font-medium text-primary hover:underline">
          View all notifications →
        </Link>
      </Section>
    </div>
  );
}
