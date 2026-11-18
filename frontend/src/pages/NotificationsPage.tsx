import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";

import { ApiError } from "@/api/client";
import { listNotifications, markAllNotificationsRead, markNotificationRead } from "@/api/notifications";
import { Button } from "@/components/ui/button";
import { useAuth } from "@/contexts/AuthContext";
import { useOrganization } from "@/contexts/OrganizationContext";
import { entityDetailPath } from "@/features/notifications/constants";
import type { NotificationPublic } from "@/types/notification";

const PER_PAGE = 20;

// FD-050. Deliberately minimal (no sidebar/top-bar yet - FD-053 builds
// the real dashboard shell), same convention every other list page in
// this frontend already established. No role check here at all -
// unlike every other feature page, notifications has no backend
// Permission to gate on (docs/API.md); every signed-in member sees
// this page, scoped to their own notifications only.
export function NotificationsPage() {
  const { csrfToken } = useAuth();
  const { activeMembership } = useOrganization();
  const organizationId = activeMembership?.organization.id ?? "";
  const queryClient = useQueryClient();

  const [unreadOnly, setUnreadOnly] = useState(false);
  const [page, setPage] = useState(1);
  const [actionError, setActionError] = useState<string | null>(null);

  const queryKey = ["notifications", organizationId, unreadOnly, page];
  const { data, isPending, isError, error } = useQuery({
    queryKey,
    queryFn: () => listNotifications(organizationId, { unreadOnly, page, perPage: PER_PAGE }),
    enabled: Boolean(organizationId),
  });

  // Drives "Mark all read"'s enabled state off the org-wide unread
  // total, not just whatever happens to be on the current page/filter -
  // the same per-page-independent count HomePage's own badge uses
  // (minimal: per_page 1, only meta.total is read).
  const { data: unreadCountData } = useQuery({
    queryKey: ["notifications-unread-count", organizationId],
    queryFn: () => listNotifications(organizationId, { unreadOnly: true, page: 1, perPage: 1 }),
    enabled: Boolean(organizationId),
  });
  const unreadCount = unreadCountData?.meta.total ?? 0;

  const notifications = data?.notifications ?? [];
  const meta = data?.meta;

  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: ["notifications", organizationId] });
    queryClient.invalidateQueries({ queryKey: ["notifications-unread-count", organizationId] });
  };

  const toggleUnreadOnly = () => {
    setUnreadOnly((prev) => !prev);
    setPage(1);
  };

  const onMarkRead = async (notificationId: string) => {
    if (!csrfToken) {
      setActionError("Your session is missing a CSRF token - please log in again.");
      return;
    }
    setActionError(null);
    try {
      await markNotificationRead(organizationId, notificationId, csrfToken);
      invalidate();
    } catch {
      setActionError("Could not mark that notification read. Please try again.");
    }
  };

  const onMarkAllRead = async () => {
    if (!csrfToken) {
      setActionError("Your session is missing a CSRF token - please log in again.");
      return;
    }
    setActionError(null);
    try {
      await markAllNotificationsRead(organizationId, csrfToken);
      invalidate();
    } catch {
      setActionError("Could not mark every notification read. Please try again.");
    }
  };

  return (
    <main className="min-h-screen bg-background px-4 py-8 text-foreground">
      <div className="mx-auto flex max-w-2xl flex-col gap-6">
        <div className="flex items-center justify-between">
          <h1 className="text-2xl font-semibold">Notifications</h1>
          <Link to="/" className="text-sm font-medium text-primary hover:underline">
            Back to home
          </Link>
        </div>

        <div className="flex flex-wrap items-center gap-3">
          <Button type="button" variant="outline" size="sm" onClick={toggleUnreadOnly}>
            {unreadOnly ? "Show all" : "Show unread only"}
          </Button>
          <Button type="button" size="sm" disabled={unreadCount === 0} onClick={() => void onMarkAllRead()}>
            Mark all read{unreadCount > 0 ? ` (${unreadCount})` : ""}
          </Button>
        </div>

        {actionError && (
          <p role="alert" className="text-sm text-destructive">
            {actionError}
          </p>
        )}

        {isPending && <p className="text-sm text-foreground/70">Loading notifications…</p>}

        {isError && (
          <p role="alert" className="text-sm text-destructive">
            {error instanceof ApiError ? error.message : "Something went wrong loading notifications."}
          </p>
        )}

        {!isPending && !isError && notifications.length === 0 && (
          <p className="text-sm text-foreground/70">
            {unreadOnly ? "No unread notifications." : "No notifications yet."}
          </p>
        )}

        {!isPending && !isError && notifications.length > 0 && (
          <ul className="flex flex-col gap-3">
            {notifications.map((notification) => (
              <NotificationRow key={notification.id} notification={notification} onMarkRead={onMarkRead} />
            ))}
          </ul>
        )}

        {meta && meta.total_pages > 1 && (
          <div className="flex items-center justify-center gap-4">
            <Button type="button" variant="outline" size="sm" disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>
              Previous
            </Button>
            <p className="text-sm text-foreground/70">
              Page {meta.page} of {meta.total_pages}
            </p>
            <Button
              type="button"
              variant="outline"
              size="sm"
              disabled={page >= meta.total_pages}
              onClick={() => setPage((p) => p + 1)}
            >
              Next
            </Button>
          </div>
        )}
      </div>
    </main>
  );
}

function NotificationRow({
  notification,
  onMarkRead,
}: {
  notification: NotificationPublic;
  onMarkRead: (notificationId: string) => void | Promise<void>;
}) {
  const isUnread = notification.read_at === null;
  const detailPath = entityDetailPath(notification.entity_type, notification.entity_id);

  return (
    <li
      className={`flex items-start justify-between gap-3 rounded-md border border-border p-4 ${
        isUnread ? "bg-card" : "bg-background"
      }`}
    >
      <div className="flex flex-col gap-0.5">
        <p className="font-medium">
          {detailPath ? (
            <Link to={detailPath} className="text-primary hover:underline">
              {notification.title}
            </Link>
          ) : (
            notification.title
          )}
          {isUnread && <span className="ml-2 text-xs font-normal text-foreground/50">(unread)</span>}
        </p>
        <p className="text-sm text-foreground/70">{notification.body}</p>
      </div>
      {isUnread && (
        <Button type="button" variant="outline" size="sm" onClick={() => void onMarkRead(notification.id)}>
          Mark read
        </Button>
      )}
    </li>
  );
}
