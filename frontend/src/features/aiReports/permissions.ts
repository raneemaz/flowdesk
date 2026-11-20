import type { MembershipRole } from "@/types/organization";

// UI-ONLY hint mirroring backend/app/ai_reports/routes.py's own
// full-scope-only check (FD-058, reusing ANALYTICS_VIEW rather than a
// dedicated permission) - NEVER the real authorization boundary (spec
// Section 7.3/32). The backend independently re-derives and
// re-enforces this on every request; this page's own queries aren't
// additionally gated on it either (same precedent InvoiceListPage's
// own canManageInvoices-gated sidebar entry already established) -
// a role this hides the sidebar link for would just get a 403 from
// every request if it reached the route directly.
export function canViewAIReports(viewerRole: MembershipRole): boolean {
  return viewerRole === "owner" || viewerRole === "manager";
}
