import type { MembershipRole } from "@/types/organization";

// UI-ONLY hints for which buttons/forms to show, mirroring
// backend/app/authz/permissions.py's EMPLOYEE_MANAGE/DEPARTMENT_MANAGE
// scopes and app/authz/service.py's can_manage_employee_profile -
// NEVER the real authorization boundary (spec Section 7.3/32: "never
// trust frontend role checks as authorization"; ProtectedRoute.tsx
// documents the same principle for whole pages). The backend
// independently re-derives and re-enforces every one of these rules
// on every request; if this ever drifts out of sync with the backend,
// the worst case is a button that 403s when clicked, not a security
// hole.
const MANAGER_ASSIGNABLE_ROLES = new Set<MembershipRole>(["employee", "accountant", "customer_support"]);

export function canManageEmployeeProfile(viewerRole: MembershipRole, targetRole: MembershipRole): boolean {
  if (viewerRole === "owner") return true;
  if (viewerRole === "manager") return MANAGER_ASSIGNABLE_ROLES.has(targetRole);
  return false;
}

export function canManageDepartments(viewerRole: MembershipRole): boolean {
  return viewerRole === "owner" || viewerRole === "manager";
}

const ALL_ROLES: MembershipRole[] = ["owner", "manager", "employee", "accountant", "customer_support"];

// Mirrors app/authz/service.py's can_invite_with_role exactly: Owner
// may invite any role; Manager only the three MANAGER_ASSIGNABLE_ROLES
// above (never a new Owner/Manager); everyone else may not invite at
// all.
export function canInviteEmployees(viewerRole: MembershipRole): boolean {
  return viewerRole === "owner" || viewerRole === "manager";
}

export function invitableRoles(viewerRole: MembershipRole): MembershipRole[] {
  if (viewerRole === "owner") return ALL_ROLES;
  if (viewerRole === "manager") return [...MANAGER_ASSIGNABLE_ROLES];
  return [];
}
