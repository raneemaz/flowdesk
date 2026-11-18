import { apiFetch, apiFetchWithMeta } from "@/api/client";
import type { PaginationMeta } from "@/types/employee";
import type { NotificationPublic } from "@/types/notification";

export interface ListNotificationsFilters {
  unreadOnly?: boolean;
  page?: number;
  perPage?: number;
}

export interface NotificationListResult {
  notifications: NotificationPublic[];
  meta: PaginationMeta;
}

export async function listNotifications(
  organizationId: string,
  filters: ListNotificationsFilters = {},
): Promise<NotificationListResult> {
  const params = new URLSearchParams();
  if (filters.unreadOnly) params.set("unread_only", "true");
  params.set("page", String(filters.page ?? 1));
  params.set("per_page", String(filters.perPage ?? 20));

  const { data, meta } = await apiFetchWithMeta<NotificationPublic[], PaginationMeta>(
    `/organizations/${organizationId}/notifications?${params.toString()}`,
  );
  return { notifications: data, meta };
}

export function markNotificationRead(
  organizationId: string,
  notificationId: string,
  csrfToken: string,
): Promise<NotificationPublic> {
  return apiFetch<NotificationPublic>(`/organizations/${organizationId}/notifications/${notificationId}/read`, {
    method: "PATCH",
    csrfToken,
  });
}

export interface MarkAllNotificationsReadResult {
  updated_count: number;
}

export function markAllNotificationsRead(
  organizationId: string,
  csrfToken: string,
): Promise<MarkAllNotificationsReadResult> {
  return apiFetch<MarkAllNotificationsReadResult>(`/organizations/${organizationId}/notifications/read-all`, {
    method: "PATCH",
    csrfToken,
  });
}
