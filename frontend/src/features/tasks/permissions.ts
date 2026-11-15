import type { MembershipRole } from "@/types/organization";
import type { TaskStatus } from "@/types/task";

// UI-ONLY hints mirroring backend/app/tasks/service.py's permission
// design (TASK_CREATE_ASSIGN for creation/assignment/editing,
// TASK_VIEW_UPDATE's full/assigned scopes for viewing and status
// progression) - NEVER the real authorization boundary (same
// principle as features/employees/permissions.ts). The backend
// independently re-derives and re-enforces every one of these rules
// on every request.
//
// One simplification this module relies on: there is no client-side
// "am I the assignee" check anywhere here. For a non-manager viewer,
// successfully loading a task's detail at all already proves they're
// its assignee (TASK_VIEW_UPDATE's assigned scope - the only way
// their GET could have succeeded), so the detail page doesn't need to
// independently know the viewer's own membership_id to decide whether
// to show assignee-level controls.
export function canManageTasks(viewerRole: MembershipRole): boolean {
  return viewerRole === "owner" || viewerRole === "manager";
}

// Mirrors app/tasks/service.py's _STATUS_TRANSITIONS exactly.
const STATUS_TRANSITIONS: Record<TaskStatus, TaskStatus[]> = {
  to_do: ["in_progress", "cancelled"],
  in_progress: ["under_review", "cancelled"],
  under_review: ["completed", "in_progress", "cancelled"],
  completed: [],
  cancelled: [],
};

// Mirrors app/tasks/service.py's _ASSIGNEE_ALLOWED_TRANSITIONS exactly
// - the two "forward progress" moves an assignee may drive themselves;
// approving, returning for revision, and cancelling are Owner/Manager-only.
const ASSIGNEE_ALLOWED_TRANSITIONS = new Set<string>(["to_do->in_progress", "in_progress->under_review"]);

export function legalNextStatuses(current: TaskStatus): TaskStatus[] {
  return STATUS_TRANSITIONS[current];
}

// `isManager` - the viewer's own canManageTasks() result. For a
// non-manager, the caller passing `true` here would never actually
// happen in practice (see the module-level note above), but the
// parameter still exists so this function doesn't need to assume
// *which* non-manager case it's being called from.
export function statusOptionsFor(current: TaskStatus, isManager: boolean): TaskStatus[] {
  const legal = legalNextStatuses(current);
  if (isManager) return legal;
  return legal.filter((next) => ASSIGNEE_ALLOWED_TRANSITIONS.has(`${current}->${next}`));
}
