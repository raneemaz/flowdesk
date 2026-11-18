import { useQueries } from "@tanstack/react-query";

import { listRequests, type ListRequestsFilters } from "@/api/customerRequests";
import type { RequestStatus } from "@/types/customerRequest";

// FR-019's workflow has no single "open" status - resolved, closed
// are terminal; the rest (new, assigned, in_progress,
// waiting_for_customer) are all "still open". api/customerRequests.ts
// only accepts one status value per request, so there is no
// server-side "not in" filter to ask for directly: an exact "how many
// are open" figure is the sum of one minimal (perPage 1, reading only
// meta.total) request per open status - four small real totals, never
// an estimate or a client-side guess from a single partial page.
const OPEN_STATUSES: RequestStatus[] = ["new", "assigned", "in_progress", "waiting_for_customer"];

export function useOpenRequestCount(
  organizationId: string,
  extraFilters: Omit<ListRequestsFilters, "status" | "page" | "perPage"> = {},
  enabled = true,
) {
  const results = useQueries({
    queries: OPEN_STATUSES.map((status) => ({
      queryKey: ["open-requests-count", organizationId, status, extraFilters],
      queryFn: () => listRequests(organizationId, { ...extraFilters, status, perPage: 1 }),
      enabled: enabled && Boolean(organizationId),
    })),
  });

  return {
    total: results.reduce((sum, result) => sum + (result.data?.meta.total ?? 0), 0),
    isPending: results.some((result) => result.isPending),
    isError: results.some((result) => result.isError),
  };
}
