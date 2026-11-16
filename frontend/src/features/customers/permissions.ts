import type { MembershipRole } from "@/types/organization";

// UI-ONLY hint mirroring backend/app/authz/permissions.py's
// CUSTOMER_MANAGE scope (full for Owner/Manager/Accountant/
// CustomerSupport, none for Employee) - NEVER the real authorization
// boundary (spec Section 7.3/32). The backend independently
// re-derives and re-enforces this on every request; an Employee
// hitting a hidden customers link would just get a 403.
export function canManageCustomers(viewerRole: MembershipRole): boolean {
  return viewerRole !== "employee";
}
