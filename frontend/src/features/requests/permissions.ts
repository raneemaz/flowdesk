import type { MembershipRole } from "@/types/organization";
import type { RequestStatus } from "@/types/customerRequest";

// UI-ONLY hints mirroring backend/app/customer_requests/service.py's
// permission design (CUSTOMER_REQUEST_MANAGE: full for Owner/Manager/
// CustomerSupport, assigned for Employee, none for Accountant) -
// NEVER the real authorization boundary (spec Section 7.3/32). The
// backend independently re-derives and re-enforces every one of these
// rules on every request.
//
// `canManageRequests` mirrors the `full`-scope-only checks
// (`_require_full_scope`) the backend applies inline to create/assign
// - CUSTOMER_REQUEST_MANAGE has no separate create-only permission the
// way Task's TASK_CREATE_ASSIGN does, so this is the frontend's own
// equivalent of that same boundary.
export function canManageRequests(viewerRole: MembershipRole): boolean {
  return viewerRole === "owner" || viewerRole === "manager" || viewerRole === "customer_support";
}

// Whether this role can reach the request queue/detail views at all
// (`assigned` or `full` scope - everyone except Accountant, whose
// CUSTOMER_REQUEST_MANAGE is `none`).
export function canAccessRequests(viewerRole: MembershipRole): boolean {
  return viewerRole !== "accountant";
}

// Mirrors app/customer_requests/service.py's _REQUEST_TRANSITIONS
// exactly - strict and linear, no skipping a stage (FR-019 states a
// single chain with no named exception).
const STATUS_TRANSITIONS: Record<RequestStatus, RequestStatus[]> = {
  new: ["assigned"],
  assigned: ["in_progress"],
  in_progress: ["waiting_for_customer"],
  waiting_for_customer: ["resolved"],
  resolved: ["closed"],
  closed: [],
};

// Mirrors app/customer_requests/service.py's _ASSIGNEE_ALLOWED_TRANSITIONS
// exactly - the two "forward progress" moves an assignee may drive
// themselves; resolving and closing are full-scope only (this task's
// own acceptance criterion: "unauthorized users can't close requests").
const ASSIGNEE_ALLOWED_TRANSITIONS = new Set<string>(["assigned->in_progress", "in_progress->waiting_for_customer"]);

export function legalNextStatuses(current: RequestStatus): RequestStatus[] {
  return STATUS_TRANSITIONS[current];
}

// `isFullScope` - the viewer's own canManageRequests() result.
export function statusOptionsFor(current: RequestStatus, isFullScope: boolean): RequestStatus[] {
  const legal = legalNextStatuses(current);
  if (isFullScope) return legal;
  return legal.filter((next) => ASSIGNEE_ALLOWED_TRANSITIONS.has(`${current}->${next}`));
}
