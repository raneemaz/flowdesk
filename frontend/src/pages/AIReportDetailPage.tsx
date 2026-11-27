import { useQuery } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";

import { ApiError } from "@/api/client";
import { getAIReport } from "@/api/aiReports";
import { Button } from "@/components/ui/button";
import { useOrganization } from "@/contexts/OrganizationContext";
import type { AIReportPublic } from "@/types/aiReport";

// Plain text, not PDF - every figure in this report already comes
// from `report.summary`'s own real-data narrative (FR-042), so this
// just renders the same facts/recommendations split the page itself
// shows, as a file the viewer can save or forward. No new backend
// endpoint or dependency needed for it.
function buildReportText(report: AIReportPublic): string {
  const lines = [
    `FlowDesk AI Report: ${report.period_start} to ${report.period_end}`,
    `Generated ${report.generated_at} (${report.model})`,
    "",
    "BUSINESS OVERVIEW",
    report.summary.business_overview,
    "",
    "EMPLOYEE PRODUCTIVITY",
    report.summary.employee_productivity,
    "",
    "FINANCIAL OVERVIEW",
    report.summary.financial_overview,
    "",
    "OPERATIONAL PROBLEMS",
    report.summary.operational_problems,
    "",
  ];
  if (report.summary.missing_data.length > 0) {
    lines.push("MISSING DATA", ...report.summary.missing_data.map((item) => `- ${item}`), "");
  }
  lines.push(
    "RECOMMENDATIONS (AI-generated suggestions, not verified facts - review before acting on them)",
    ...(report.recommendations.length > 0 ? report.recommendations.map((item) => `- ${item}`) : ["No recommendations for this period."]),
  );
  return lines.join("\n");
}

function downloadReport(report: AIReportPublic) {
  const blob = new Blob([buildReportText(report)], { type: "text/plain;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = `flowdesk-ai-report-${report.period_start}-to-${report.period_end}.txt`;
  link.click();
  URL.revokeObjectURL(url);
}

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
      <div className="px-4 py-6 sm:px-6 sm:py-8 lg:px-10">
        <p className="text-sm text-foreground/70">Loading report…</p>
      </div>
    );
  }

  if (isError || !report) {
    return (
      <div className="px-4 py-6 sm:px-6 sm:py-8 lg:px-10">
        <div className="flex max-w-3xl flex-col gap-4">
          <p role="alert" className="text-sm text-destructive">
            {error instanceof ApiError ? error.message : "AI report not found."}
          </p>
          <Link to="/ai-reports" className="text-sm font-medium text-primary hover:underline">
            Back to AI Reports
          </Link>
        </div>
      </div>
    );
  }

  return (
    <div className="px-4 py-6 sm:px-6 sm:py-8 lg:px-10">
      <div className="flex max-w-3xl flex-col gap-6">
        <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2">
          <div>
            <h1 className="text-2xl font-semibold">
              {report.period_start} to {report.period_end}
            </h1>
            <p className="text-sm text-foreground/70">
              Generated {report.generated_at} · {report.model}
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
            <Button type="button" variant="outline" size="sm" onClick={() => downloadReport(report)}>
              Download
            </Button>
            <Link to="/ai-reports" className="text-sm font-medium text-primary hover:underline">
              All reports
            </Link>
          </div>
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
            <span className="rounded-full bg-primary/10 px-2 py-0.5 text-xs font-medium text-primary">
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
    </div>
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
