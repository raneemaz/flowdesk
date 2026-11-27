import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";

import { getFinancialAnalytics } from "@/api/analytics";
import { listNotifications } from "@/api/notifications";
import { listTasks } from "@/api/tasks";
import { Loading, QueryError } from "@/features/analytics/widgets";
import { entityDetailPath } from "@/features/notifications/constants";
import { STATUS_LABELS } from "@/features/tasks/constants";
import type { TaskPublic, TaskStatus } from "@/types/task";

const CURRENT_MONTH = { period: "current_month" } as const;

// Dashboard-summary widgets (sketched with 21st.dev's Kanban/Activity
// reference components as design inspiration, then adapted to this
// app's own plain-Tailwind style and real FD-052/FD-050/FD-038 data -
// no shadcn Card/Badge/Avatar primitives exist here yet, so these
// reuse Section/StatCard's border+bg-card convention instead).

// Board summary only shows the three non-terminal/first-terminal
// columns that fit a compact card; "cancelled" is a terminal state
// nobody needs to see from a glance-level summary (full detail is one
// click away on the real board).
const SUMMARY_BOARD_COLUMNS: TaskStatus[] = ["to_do", "in_progress", "under_review", "completed"];
const SUMMARY_BOARD_PAGE_SIZE = 100;

export function TaskBoardSummary({ organizationId }: { organizationId: string }) {
  const { data, isPending, isError, error } = useQuery({
    queryKey: ["dashboard-summary-tasks", organizationId],
    queryFn: () => listTasks(organizationId, { perPage: SUMMARY_BOARD_PAGE_SIZE }),
    enabled: Boolean(organizationId),
  });

  const tasksByStatus = new Map<TaskStatus, TaskPublic[]>(SUMMARY_BOARD_COLUMNS.map((status) => [status, []]));
  for (const task of data?.tasks ?? []) {
    tasksByStatus.get(task.status)?.push(task);
  }

  return (
    <div className="@container flex min-w-0 flex-col gap-3 rounded-md border border-border bg-card p-4">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold">Task board</h3>
        <Link to="/tasks/board" className="text-xs font-medium text-primary hover:underline">
          Open board →
        </Link>
      </div>

      {isPending && <Loading />}
      {isError && <QueryError error={error} />}

      {data && (
        // @sm here reacts to this card's own width (a container query),
        // not the viewport - plain `sm:` would fire from a wide window
        // even when this card is squeezed into a third of it by the
        // dashboard's own grid, forcing 4 columns into a card only wide
        // enough for 2 and overflowing its border.
        <div className="grid grid-cols-2 gap-2 @sm:grid-cols-4">
          {SUMMARY_BOARD_COLUMNS.map((status) => {
            const columnTasks = tasksByStatus.get(status) ?? [];
            return (
              <div key={status} className="flex min-w-0 flex-col gap-1.5 rounded-md border border-border bg-background p-2">
                <p className="text-xs font-medium text-foreground/70">
                  {STATUS_LABELS[status]} <span className="text-foreground/50">({columnTasks.length})</span>
                </p>
                <ul className="flex flex-col gap-1">
                  {columnTasks.length === 0 && <li className="text-xs text-foreground/40">Nothing here</li>}
                  {columnTasks.slice(0, 3).map((task) => (
                    <li key={task.id}>
                      <Link to={`/tasks/${task.id}`} className="block truncate text-xs text-primary hover:underline">
                        {task.title}
                      </Link>
                    </li>
                  ))}
                </ul>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

export function InvoicesPaymentsSummary({ organizationId }: { organizationId: string }) {
  const { data, isPending, isError, error } = useQuery({
    queryKey: ["dashboard-summary-finance", organizationId],
    queryFn: () => getFinancialAnalytics(organizationId, CURRENT_MONTH),
    enabled: Boolean(organizationId),
  });

  return (
    <div className="flex min-w-0 flex-col gap-3 rounded-md border border-border bg-card p-4">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold">Invoices &amp; payments</h3>
        <Link to="/invoices" className="text-xs font-medium text-primary hover:underline">
          View invoices →
        </Link>
      </div>

      {isPending && <Loading />}
      {isError && <QueryError error={error} />}

      {data && (
        <>
          <div className="grid grid-cols-2 gap-2">
            <SummaryStat label="Invoiced" value={data.total_invoiced} />
            <SummaryStat label="Collected" value={data.total_collected} />
            <SummaryStat label="Outstanding" value={data.outstanding_balance} />
            <SummaryStat label="Overdue invoices" value={String(data.overdue_invoice_count)} />
          </div>

          <div className="flex flex-col gap-1">
            <p className="text-xs font-medium text-foreground/70">Recent payments</p>
            {data.recent_payments.length === 0 && <p className="text-xs text-foreground/40">No payments recorded yet.</p>}
            <ul className="flex flex-col gap-1">
              {data.recent_payments.slice(0, 3).map((payment) => (
                <li key={payment.id} className="flex items-center justify-between gap-2 text-xs">
                  <span className="truncate text-foreground/70">{payment.payment_date}</span>
                  <span className="shrink-0 font-medium">{payment.amount}</span>
                </li>
              ))}
            </ul>
          </div>
        </>
      )}
    </div>
  );
}

function SummaryStat({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex min-w-0 flex-col gap-0.5 rounded-md border border-border bg-background p-2">
      <span className="truncate text-[10px] font-medium uppercase tracking-wide text-foreground/50" title={label}>
        {label}
      </span>
      <span className="truncate text-sm font-semibold" title={value}>
        {value}
      </span>
    </div>
  );
}

const ACTIVITY_FEED_SIZE = 5;

export function ActivityFeedSummary({ organizationId }: { organizationId: string }) {
  const { data, isPending, isError, error } = useQuery({
    queryKey: ["dashboard-summary-activity", organizationId],
    queryFn: () => listNotifications(organizationId, { page: 1, perPage: ACTIVITY_FEED_SIZE }),
    enabled: Boolean(organizationId),
  });

  const notifications = data?.notifications ?? [];

  return (
    <div className="flex flex-col gap-3 rounded-md border border-border bg-card p-4">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold">Activity</h3>
        <Link to="/notifications" className="text-xs font-medium text-primary hover:underline">
          View all →
        </Link>
      </div>

      {isPending && <Loading />}
      {isError && <QueryError error={error} />}

      {data && notifications.length === 0 && <p className="text-xs text-foreground/40">No recent activity.</p>}

      {data && notifications.length > 0 && (
        <ul className="flex flex-col divide-y divide-border">
          {notifications.map((notification) => {
            const detailPath = entityDetailPath(notification.entity_type, notification.entity_id);
            return (
              <li key={notification.id} className="flex items-center justify-between gap-2 py-2 first:pt-0 last:pb-0">
                <span className="min-w-0 truncate text-xs text-foreground/70">
                  {detailPath ? (
                    <Link to={detailPath} className="font-medium text-primary hover:underline">
                      {notification.title}
                    </Link>
                  ) : (
                    <span className="font-medium text-foreground">{notification.title}</span>
                  )}
                </span>
                <span className="shrink-0 text-[10px] text-foreground/50">{notification.created_at}</span>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
