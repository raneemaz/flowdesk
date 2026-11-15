import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";

import { ApiError } from "@/api/client";
import { listEmployees } from "@/api/employees";
import { listTasks, updateTaskStatus } from "@/api/tasks";
import { Button } from "@/components/ui/button";
import { TasksNav } from "@/components/TasksNav";
import { useAuth } from "@/contexts/AuthContext";
import { useOrganization } from "@/contexts/OrganizationContext";
import { PRIORITY_OPTIONS, STATUS_LABELS, STATUS_ORDER } from "@/features/tasks/constants";
import { canManageTasks, statusOptionsFor } from "@/features/tasks/permissions";
import type { TaskPublic, TaskStatus } from "@/types/task";

// Not paginated - a board view needs every task visible across its
// columns at once, not one page of one status. 100 comfortably covers
// a small-business org's active task volume (spec Section 16's seed
// data uses 30); a future task can add true pagination if a real org
// outgrows this.
const BOARD_PAGE_SIZE = 100;

export function TaskBoardPage() {
  const { csrfToken } = useAuth();
  const { activeMembership } = useOrganization();
  const organizationId = activeMembership?.organization.id ?? "";
  const canManage = activeMembership ? canManageTasks(activeMembership.role) : false;
  const queryClient = useQueryClient();
  const [moveError, setMoveError] = useState<string | null>(null);

  const { data: employeesForNames } = useQuery({
    queryKey: ["employees-for-task-names", organizationId],
    queryFn: () => listEmployees(organizationId, { perPage: 100 }),
    enabled: canManage && Boolean(organizationId),
  });
  const employeeNameById = new Map((employeesForNames?.employees ?? []).map((e) => [e.membership_id, e.name]));

  const { data, isPending, isError, error } = useQuery({
    queryKey: ["tasks-board", organizationId],
    queryFn: () => listTasks(organizationId, { perPage: BOARD_PAGE_SIZE }),
    enabled: Boolean(organizationId),
  });

  const tasks = data?.tasks ?? [];
  const tasksByStatus = new Map<TaskStatus, TaskPublic[]>(STATUS_ORDER.map((status) => [status, []]));
  for (const task of tasks) {
    tasksByStatus.get(task.status)?.push(task);
  }

  const moveTask = async (task: TaskPublic, nextStatus: TaskStatus) => {
    if (!csrfToken) {
      setMoveError("Your session is missing a CSRF token - please log in again.");
      return;
    }
    setMoveError(null);
    try {
      await updateTaskStatus(organizationId, task.id, nextStatus, csrfToken);
      await queryClient.invalidateQueries({ queryKey: ["tasks-board", organizationId] });
    } catch (submitError) {
      setMoveError(submitError instanceof ApiError ? submitError.message : "Could not move this task. Please try again.");
    }
  };

  return (
    <main className="min-h-screen bg-background px-4 py-8 text-foreground">
      <div className="mx-auto flex max-w-6xl flex-col gap-6">
        <div className="flex items-center justify-between">
          <h1 className="text-2xl font-semibold">Tasks</h1>
          <Link to="/" className="text-sm font-medium text-primary hover:underline">
            Back to home
          </Link>
        </div>

        <TasksNav />

        {isPending && <p className="text-sm text-foreground/70">Loading board…</p>}
        {isError && (
          <p role="alert" className="text-sm text-destructive">
            {error instanceof ApiError ? error.message : "Something went wrong loading the board."}
          </p>
        )}
        {moveError && (
          <p role="alert" className="text-sm text-destructive">
            {moveError}
          </p>
        )}

        {!isPending && !isError && (
          <div className="flex gap-4 overflow-x-auto pb-2">
            {STATUS_ORDER.map((status) => (
              <div key={status} className="flex w-64 shrink-0 flex-col gap-3 rounded-md border border-border bg-card p-3">
                <h2 className="text-sm font-semibold">
                  {STATUS_LABELS[status]} <span className="text-foreground/50">({tasksByStatus.get(status)?.length ?? 0})</span>
                </h2>
                <div className="flex flex-col gap-2">
                  {(tasksByStatus.get(status) ?? []).map((task) => {
                    const nextStatuses = statusOptionsFor(task.status, canManage);
                    return (
                      <div key={task.id} className="flex flex-col gap-2 rounded-md border border-border bg-background p-3">
                        <Link to={`/tasks/${task.id}`} className="text-sm font-medium text-primary hover:underline">
                          {task.title}
                        </Link>
                        <p className="text-xs text-foreground/70">
                          {PRIORITY_OPTIONS.find((o) => o.value === task.priority)?.label}
                          {task.due_date ? ` · Due ${task.due_date}` : ""}
                        </p>
                        <p className="text-xs text-foreground/50">
                          {task.assignee_membership_id
                            ? canManage
                              ? (employeeNameById.get(task.assignee_membership_id) ?? "—")
                              : "Assigned to you"
                            : "Unassigned"}
                        </p>
                        {nextStatuses.length > 0 && (
                          <div className="flex flex-wrap gap-1">
                            {nextStatuses.map((nextStatus) => (
                              <Button
                                key={nextStatus}
                                type="button"
                                variant="outline"
                                size="sm"
                                onClick={() => void moveTask(task, nextStatus)}
                              >
                                {STATUS_LABELS[nextStatus]}
                              </Button>
                            ))}
                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </main>
  );
}
