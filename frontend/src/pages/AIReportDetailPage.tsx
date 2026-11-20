import { useQuery } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";

import { ApiError } from "@/api/client";
import { getAIReport } from "@/api/aiReports";
import { useOrganization } from "@/contexts/OrganizationContext";

// FD-060. FR-042's reliability requirements, directly satisfied by
// this page's own layout rather than left to chance: "always show the
// reporting period" (the header below), "identify missing data" (the
// callout, rendered only when the AI actually named a gap - never a
// fabricated "nothing missing"), and "clearly separate facts from
// AI-generated recommendations" - the four factual sections render as
// plain prose; Recommendations gets its own visually distinct,
// explicitly labeled "AI-generated suggestions, not verified facts"
// section, so a reader never has to guess which half of the page is
// an opinion.
export function AIReportDetailPage() {
  const { reportId } = useParams<{ reportId: string }>();
  const { activeMembership } = useOrganization();
  const organizationId = activeMembership?.organization.id ?? "";

  const { data: report, isPending, isError, error } = useQuery({
    queryKey: ["ai-report", organizationId, reportId],
    queryFn: () => getAIReport(organizationId, reportId!),
    enabled: Boolean(organizationId && reportId),
  });

  if (isPending) {
    return (
      <main className="min-h-screen bg-background px-4 py-8 text-foreground">
        <p className="text-sm text-foreground/70">Loading report…</p>
      </main>
    );
  }

  if (isError || !report) {
    return (
      <main className="min-h-screen bg-background px-4 py-8 text-foreground">
        <div className="mx-auto flex max-w-2xl flex-col gap-4">
          <p role="alert" className="text-sm text-destructive">
            {error instanceof ApiError ? error.message : "AI report not found."}
          </p>
          <Link to="/ai-reports" className="text-sm font-medium text-primary hover:underline">
            Back to AI Reports
          </Link>
        </div>
      </main>
    );
  }

  return (
    <main className="min-h-screen bg-background px-4 py-8 text-foreground">
      <div className="mx-auto flex max-w-2xl flex-col gap-6">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-semibold">
              {report.period_start} to {report.period_end}
            </h1>
            <p className="text-sm text-foreground/70">
              Generated {report.generated_at} · {report.model}
            </p>
          </div>
          <Link to="/ai-reports" className="text-sm font-medium text-primary hover:underline">
            All reports
          </Link>
        </div>

        <ReportSection title="Business overview" text={report.summary.business_overview} />
        <ReportSection title="Employee productivity" text={report.summary.employee_productivity} />
        <ReportSection title="Financial overview" text={report.summary.financial_overview} />
        <ReportSection title="Operational problems" text={report.summary.operational_problems} />

        {report.summary.missing_data.length > 0 && (
          <section className="flex flex-col gap-2 rounded-md border border-border bg-card p-4">
            <h2 className="text-sm font-medium text-foreground/70">Missing data</h2>
            <ul className="list-inside list-disc text-sm text-foreground/70">
              {report.summary.missing_data.map((item, index) => (
                <li key={index}>{item}</li>
              ))}
            </ul>
          </section>
        )}

        <section className="flex flex-col gap-2 rounded-md border-2 border-dashed border-primary/50 bg-primary/5 p-4">
          <div className="flex items-center gap-2">
            <h2 className="text-lg font-semibold">Recommendations</h2>
            <span className="rounded-full bg-primary/10 px-2 py-0.5 text-xs font-medium uppercase tracking-wide text-primary">
              Advisory
            </span>
          </div>
          <p className="text-xs text-foreground/60">
            These are the AI's own suggested actions, not verified facts - review before acting on them.
          </p>
          {report.recommendations.length === 0 ? (
            <p className="text-sm text-foreground/70">No recommendations for this period.</p>
          ) : (
            <ul className="list-inside list-disc text-sm">
              {report.recommendations.map((recommendation, index) => (
                <li key={index}>{recommendation}</li>
              ))}
            </ul>
          )}
        </section>
      </div>
    </main>
  );
}

function ReportSection({ title, text }: { title: string; text: string }) {
  return (
    <section className="flex flex-col gap-1 rounded-md border border-border bg-card p-4">
      <h2 className="text-sm font-medium text-foreground/70">{title}</h2>
      <p className="text-sm">{text}</p>
    </section>
  );
}
