import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";

import { listActivity } from "@/api/activity";
import { ApiError } from "@/api/client";
import { listEmployees } from "@/api/employees";
import { Button } from "@/components/ui/button";
import { useOrganization } from "@/contexts/OrganizationContext";
import { describeActivity } from "@/features/activity/describe";

const PER_PAGE = 20;

// Spec Section 12.2's "Activity": the organization's audit trail, newest
// first. What each viewer sees is decided by the backend
// (ACTIVITY_HISTORY_VIEW: everything for owners/managers, a narrower
// slice for other roles) - this page just shows whatever comes back.
export function ActivityPage() {
  const { activeMembership } = useOrganization();
  const organizationId = activeMembership?.organization.id ?? "";
  const [page, setPage] = useState(1);

  const { data, isPending, isError, error } = useQuery({
    queryKey: ["activity", organizationId, page],
    queryFn: () => listActivity(organizationId, page, PER_PAGE),
    enabled: Boolean(organizationId),
  });

  // Names for the people in each entry. Members who have since left
  // aren't in the directory any more, so they read as "A former member".
  const { data: employees } = useQuery({
    queryKey: ["employees-for-activity-names", organizationId],
    queryFn: () => listEmployees(organizationId, { perPage: 100 }),
    enabled: Boolean(organizationId),
  });
  const names = new Map((employees?.employees ?? []).map((employee) => [employee.membership_id, employee.name]));
  const nameOf = (membershipId: string | null) =>
    membershipId ? (names.get(membershipId) ?? "A former member") : "FlowDesk";

  const entries = data?.entries ?? [];
  const meta = data?.meta;

  return (
    <div className="px-4 py-6 sm:px-6 sm:py-8 lg:px-10">
      <div className="flex max-w-3xl flex-col gap-6">
        <div>
          <h1 className="text-2xl font-semibold">Activity</h1>
          <p className="text-sm text-muted-foreground">A record of what’s been done in this organization, newest first.</p>
        </div>

        {isPending && <p className="text-sm text-muted-foreground">Loading activity…</p>}
        {isError && (
          <p role="alert" className="text-sm text-destructive">
            {error instanceof ApiError ? error.message : "Something went wrong loading activity."}
          </p>
        )}
        {!isPending && !isError && entries.length === 0 && (
          <p className="text-sm text-muted-foreground">Nothing has happened yet. Created tasks, invoices and requests will show up here.</p>
        )}

        {entries.length > 0 && (
          <ol className="flex flex-col divide-y divide-border rounded-md border border-border bg-card">
            {entries.map((entry) => {
              const { text, link } = describeActivity(entry, nameOf);
              return (
                <li key={entry.id} className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1 px-4 py-3 text-sm">
                  {link ? (
                    <Link to={link} className="hover:underline">
                      {text}
                    </Link>
                  ) : (
                    <span>{text}</span>
                  )}
                  <time dateTime={entry.created_at} className="text-xs text-muted-foreground">
                    {new Date(entry.created_at).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" })}
                  </time>
                </li>
              );
            })}
          </ol>
        )}

        {meta && meta.total_pages > 1 && (
          <div className="flex items-center justify-center gap-4">
            <Button type="button" variant="outline" size="sm" disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>
              Newer
            </Button>
            <p className="text-sm text-muted-foreground">
              Page {meta.page} of {meta.total_pages}
            </p>
            <Button
              type="button"
              variant="outline"
              size="sm"
              disabled={page >= meta.total_pages}
              onClick={() => setPage((p) => p + 1)}
            >
              Older
            </Button>
          </div>
        )}
      </div>
    </div>
  );
}
