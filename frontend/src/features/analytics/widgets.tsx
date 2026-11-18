import type { ReactNode } from "react";

import { ApiError } from "@/api/client";

// Shared presentational pieces for AnalyticsPage and every role
// dashboard in features/dashboard - kept here rather than duplicated
// across six files.

export function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="flex flex-col gap-3">
      <h2 className="text-lg font-semibold">{title}</h2>
      {children}
    </section>
  );
}

export function StatCard({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex flex-col gap-0.5 rounded-md border border-border bg-card p-4">
      <span className="text-xs font-medium uppercase tracking-wide text-foreground/50">{label}</span>
      <span className="text-lg font-semibold">{value}</span>
    </div>
  );
}

export function Loading() {
  return <p className="text-sm text-foreground/70">Loading…</p>;
}

export function QueryError({ error }: { error: unknown }) {
  return (
    <p role="alert" className="text-sm text-destructive">
      {error instanceof ApiError ? error.message : "Something went wrong loading this section."}
    </p>
  );
}
