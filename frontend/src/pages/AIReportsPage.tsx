import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";

import { ApiError } from "@/api/client";
import { listAIReports } from "@/api/aiReports";
import { Button } from "@/components/ui/button";
import { useOrganization } from "@/contexts/OrganizationContext";

const PER_PAGE = 20;

// FD-060. Reached via the dashboard shell's "AI Reports" sidebar link
// (Sidebar.tsx), shown only to canViewAIReports (Owner/Manager) - a
// role this hides the link for would just get a 403 from the request
// below if it reached the route directly, same precedent
// InvoiceListPage's own canManageInvoices-gated entry already
// established. No "generate now" action here - FD-059's own scheduled
// job is the only producer of a report; this page is read-only
// (list, detail), per this task's own title.
export function AIReportsPage() {
  const { activeMembership } = useOrganization();
  const organizationId = activeMembership?.organization.id ?? "";
  const [page, setPage] = useState(1);

  const { data, isPending, isError, error } = useQuery({
    queryKey: ["ai-reports", organizationId, page],
    queryFn: () => listAIReports(organizationId, { page, perPage: PER_PAGE }),
    enabled: Boolean(organizationId),
  });

  const reports = data?.reports ?? [];
  const meta = data?.meta;

  return (
    <main className="min-h-screen bg-background px-4 py-8 text-foreground">
      <div className="mx-auto flex max-w-3xl flex-col gap-6">
        <div className="flex items-center justify-between">
          <h1 className="text-2xl font-semibold">AI Reports</h1>
          <Link to="/" className="text-sm font-medium text-primary hover:underline">
            Back to home
          </Link>
        </div>

        <p className="text-sm text-foreground/70">
          A new weekly summary is generated automatically every Monday. Every figure below comes from this
          organization's own real data; recommendations are the AI's own suggestions, shown separately from the
          facts they're based on.
        </p>

        {isPending && <p className="text-sm text-foreground/70">Loading reports…</p>}

        {isError && (
          <p role="alert" className="text-sm text-destructive">
            {error instanceof ApiError ? error.message : "Something went wrong loading AI reports."}
          </p>
        )}

        {!isPending && !isError && reports.length === 0 && (
          <p className="text-sm text-foreground/70">
            No AI reports yet. The first weekly report is generated automatically the next time it's due.
          </p>
        )}

        {!isPending && !isError && reports.length > 0 && (
          <ul className="flex flex-col gap-3">
            {reports.map((report) => (
              <li key={report.id} className="rounded-md border border-border bg-card p-4">
                <Link to={`/ai-reports/${report.id}`} className="font-medium text-primary hover:underline">
                  {report.period_start} to {report.period_end}
                </Link>
                <p className="text-sm text-foreground/70">
                  Generated {report.generated_at} · {report.model}
                </p>
              </li>
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
