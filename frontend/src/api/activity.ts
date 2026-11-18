import { apiFetchWithMeta } from "@/api/client";
import type { ActivityLogPublic } from "@/types/activity";
import type { PaginationMeta } from "@/types/employee";

export interface ActivityListResult {
  entries: ActivityLogPublic[];
  meta: PaginationMeta;
}

// FD-053 only ever uses this for a small "recent activity" dashboard
// feed (see features/dashboard) - never pagination controls or
// filters, so page/perPage are the only filters exposed here, unlike
// the fuller api/tasks.ts-style clients. A full Activity list page is
// not in this task's scope (no FD task in the backlog ever builds
// one), only this read.
export async function listActivity(
  organizationId: string,
  page = 1,
  perPage = 5,
): Promise<ActivityListResult> {
  const params = new URLSearchParams({ page: String(page), per_page: String(perPage) });
  const { data, meta } = await apiFetchWithMeta<ActivityLogPublic[], PaginationMeta>(
    `/organizations/${organizationId}/activity?${params.toString()}`,
  );
  return { entries: data, meta };
}
