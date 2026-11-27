import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";

import { ApiError } from "@/api/client";
import { generateAIReport, listAIReports } from "@/api/aiReports";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { useAuth } from "@/contexts/AuthContext";
import { useOrganization } from "@/contexts/OrganizationContext";
import { PeriodSelector, type PeriodValue } from "@/features/analytics/PeriodSelector";

const PER_PAGE = 20;
const DEFAULT_PERIOD: PeriodValue = { period: "last_7_days", periodStart: "", periodEnd: "" };

// FD-060/FD-065-follow-up. Reached via the dashboard shell's "AI
// Reports" sidebar link (Sidebar.tsx), shown only to canViewAIReports
// (Owner/Manager) - a role this hides the link for would just get a
// 403 from the request below if it reached the route directly, same
// precedent InvoiceListPage's own canManageInvoices-gated entry
// already established. "Generate now" (added after launch) calls the
// same POST .../ai-reports/generate endpoint FD-059's scheduled job
// itself has always used - manual generation alongside, not instead
// of, the weekly automatic one.
export function AIReportsPage() {
  const { csrfToken } = useAuth();
  const { activeMembership } = useOrganization();
  const organizationId = activeMembership?.organization.id ?? "";
  const [page, setPage] = useState(1);
  const [isGenerateOpen, setIsGenerateOpen] = useState(false);
  const [periodValue, setPeriodValue] = useState<PeriodValue>(DEFAULT_PERIOD);
  const queryClient = useQueryClient();

  const { data, isPending, isError, error } = useQuery({
    queryKey: ["ai-reports", organizationId, page],
    queryFn: () => listAIReports(organizationId, { page, perPage: PER_PAGE }),
    enabled: Boolean(organizationId),
  });

  const generateMutation = useMutation({
    mutationFn: () =>
      generateAIReport(
        organizationId,
        {
          period: periodValue.period,
          period_start: periodValue.period === "custom" ? periodValue.periodStart : undefined,
          period_end: periodValue.period === "custom" ? periodValue.periodEnd : undefined,
        },
        csrfToken ?? "",
      ),
    onSuccess: () => {
      setIsGenerateOpen(false);
      setPeriodValue(DEFAULT_PERIOD);
      return queryClient.invalidateQueries({ queryKey: ["ai-reports", organizationId] });
    },
  });

  const reports = data?.reports ?? [];
  const meta = data?.meta;

  return (
    <div className="px-4 py-6 sm:px-6 sm:py-8 lg:px-10">
      <div className="flex max-w-3xl flex-col gap-6">
        <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2">
          <h1 className="text-2xl font-semibold">AI Reports</h1>
          <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
            <Dialog
              open={isGenerateOpen}
              onOpenChange={(nextOpen) => {
                setIsGenerateOpen(nextOpen);
                if (!nextOpen) generateMutation.reset();
              }}
            >
              <DialogTrigger asChild>
                <Button type="button">Generate now</Button>
              </DialogTrigger>
              <DialogContent>
                <DialogHeader>
                  <DialogTitle>Generate an AI report</DialogTitle>
                </DialogHeader>
                <div className="flex flex-col gap-4">
                  <PeriodSelector value={periodValue} onChange={setPeriodValue} />
                  {generateMutation.isError && (
                    <p role="alert" className="text-sm text-destructive">
                      {generateMutation.error instanceof ApiError
                        ? generateMutation.error.message
                        : "Something went wrong. Please try again."}
                    </p>
                  )}
                  <DialogFooter>
                    <Button type="button" disabled={generateMutation.isPending} onClick={() => generateMutation.mutate()}>
                      {generateMutation.isPending ? "Generating…" : "Generate"}
                    </Button>
                  </DialogFooter>
                </div>
              </DialogContent>
            </Dialog>
          </div>
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
    </div>
  );
}
