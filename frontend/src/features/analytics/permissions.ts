import type { MembershipRole } from "@/types/organization";

// UI-ONLY hints mirroring backend/app/analytics/service.py's own
// per-endpoint scope rules (FD-051/FD-052) - NEVER the real
// authorization boundary (spec Section 7.3/32). The backend
// independently re-derives and re-enforces every one of these on
// every request; a widget shown to the wrong role here would just
// 403 when fetched.
//
// Every active role can reach GET .../analytics/employees (Owner/
// Manager get `full`, Employee gets `own` silently forced to
// themselves) - there is no role this ever 403s for, unlike the other
// three endpoints below.
export function canViewOverviewAnalytics(viewerRole: MembershipRole): boolean {
  return viewerRole === "owner" || viewerRole === "manager";
}

export function canViewDepartmentAnalytics(viewerRole: MembershipRole): boolean {
  return viewerRole === "owner" || viewerRole === "manager";
}

export function canViewFinancialAnalytics(viewerRole: MembershipRole): boolean {
  return viewerRole === "owner" || viewerRole === "accountant";
}
