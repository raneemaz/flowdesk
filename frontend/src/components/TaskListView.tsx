import { useState, type FormEvent } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";

import { ApiError } from "@/api/client";
import { listDepartments } from "@/api/departments";
import { listEmployees } from "@/api/employees";
import { listTasks } from "@/api/tasks";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { TasksNav } from "@/components/TasksNav";
import { useOrganization } from "@/contexts/OrganizationContext";
import { PRIORITY_OPTIONS, STATUS_OPTIONS } from "@/features/tasks/constants";
import { canManageTasks } from "@/features/tasks/permissions";
import { CreateTaskDialog } from "@/features/tasks/CreateTaskDialog";
import type { TaskPriority, TaskStatus } from "@/types/task";

const PER_PAGE = 20;

interface Filters {
  status: TaskStatus | "";
  priority: TaskPriority | "";
  departmentId: string;
  assigneeMembershipId: string;
  dueDateFrom: string;
  dueDateTo: string;
}

const EMPTY_FILTERS: Filters = {
  status: "",
  priority: "",
  departmentId: "",
  assigneeMembershipId: "",
  dueDateFrom: "",
  dueDateTo: "",
};

export function TaskListView({
  title,
  lockedAssigneeId,
  lockedAssigneeLoading,
}: {
  title: string;
  /** When set, every request is forced to this assignee and the filter
   * control is hidden - used by MyTasksPage for an Owner/Manager
   * viewer. Non-manager viewers never need this: GET /tasks already
   * auto-restricts to their own assigned tasks server-side. */
  lockedAssigneeId?: string;
  /** True while the locked assignee id is still being resolved -
   * avoids a flash of "all tasks" before the lock applies. */
  lockedAssigneeLoading?: boolean;
}) {
  const { activeMembership } = useOrganization();
  const organizationId = activeMembership?.organization.id ?? "";
  const canManage = activeMembership ? canManageTasks(activeMembership.role) : false;

  const [draftFilters, setDraftFilters] = useState<Filters>(EMPTY_FILTERS);
  const [appliedFilters, setAppliedFilters] = useState<Filters>(EMPTY_FILTERS);
  const [page, setPage] = useState(1);
  const [isCreateOpen, setIsCreateOpen] = useState(false);

  const { data: departments } = useQuery({
    queryKey: ["departments", organizationId],
    queryFn: () => listDepartments(organizationId),
    enabled: canManage && Boolean(organizationId),
  });
  const { data: employeesForNames } = useQuery({
    queryKey: ["employees-for-task-names", organizationId],
    queryFn: () => listEmployees(organizationId, { perPage: 100 }),
    enabled: canManage && Boolean(organizationId),
  });
  const employeeNameById = new Map((employeesForNames?.employees ?? []).map((e) => [e.membership_id, e.name]));
  const departmentNameById = new Map((departments ?? []).map((d) => [d.id, d.name]));

  const tasksQueryKey = ["tasks", organizationId, appliedFilters, lockedAssigneeId, page];
  const { data, isPending, isError, error } = useQuery({
    queryKey: tasksQueryKey,
    queryFn: () =>
      listTasks(organizationId, {
        status: appliedFilters.status || undefined,
        priority: appliedFilters.priority || undefined,
        departmentId: appliedFilters.departmentId || undefined,
        assigneeMembershipId: lockedAssigneeId ?? (appliedFilters.assigneeMembershipId || undefined),
        dueDateFrom: appliedFilters.dueDateFrom || undefined,
        dueDateTo: appliedFilters.dueDateTo || undefined,
        page,
        perPage: PER_PAGE,
      }),
    enabled: Boolean(organizationId) && !lockedAssigneeLoading,
  });

  const tasks = data?.tasks ?? [];
  const meta = data?.meta;

  const applyFilters = (event: FormEvent) => {
    event.preventDefault();
    setAppliedFilters(draftFilters);
    setPage(1);
  };

  const clearFilters = () => {
    setDraftFilters(EMPTY_FILTERS);
    setAppliedFilters(EMPTY_FILTERS);
    setPage(1);
  };

  return (
    <div className="px-4 py-6 sm:px-6 sm:py-8 lg:px-10">
      <div className="flex max-w-7xl flex-col gap-6">
        <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2">
          <h1 className="text-2xl font-semibold">{title}</h1>
          {canManage && (
            <Button type="button" onClick={() => setIsCreateOpen(true)}>
              + New task
            </Button>
          )}
        </div>

        <TasksNav />

        {canManage && <CreateTaskDialog open={isCreateOpen} onOpenChange={setIsCreateOpen} />}

        <form className="grid grid-cols-1 gap-3 rounded-md border border-border bg-card p-4 sm:flex sm:flex-wrap sm:items-end" onSubmit={applyFilters}>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="status-filter">Status</Label>
            <Select
              id="status-filter"
              value={draftFilters.status}
              onChange={(event) => setDraftFilters((prev) => ({ ...prev, status: event.target.value as TaskStatus | "" }))}
            >
              <option value="">All statuses</option>
              {STATUS_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </Select>
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="priority-filter">Priority</Label>
            <Select
              id="priority-filter"
              value={draftFilters.priority}
              onChange={(event) => setDraftFilters((prev) => ({ ...prev, priority: event.target.value as TaskPriority | "" }))}
            >
              <option value="">All priorities</option>
              {PRIORITY_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </Select>
          </div>
          {canManage && departments && departments.length > 0 && (
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="department-filter">Department</Label>
              <Select
                id="department-filter"
                value={draftFilters.departmentId}
                onChange={(event) => setDraftFilters((prev) => ({ ...prev, departmentId: event.target.value }))}
              >
                <option value="">All departments</option>
                {departments.map((d) => (
                  <option key={d.id} value={d.id}>
                    {d.name}
                  </option>
                ))}
              </Select>
            </div>
          )}
          {canManage && !lockedAssigneeId && employeesForNames && (
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="assignee-filter">Assignee</Label>
              <Select
                id="assignee-filter"
                value={draftFilters.assigneeMembershipId}
                onChange={(event) => setDraftFilters((prev) => ({ ...prev, assigneeMembershipId: event.target.value }))}
              >
                <option value="">Anyone</option>
                {employeesForNames.employees.map((e) => (
                  <option key={e.membership_id} value={e.membership_id}>
                    {e.name}
                  </option>
                ))}
              </Select>
            </div>
          )}
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="due-from-filter">Due from</Label>
            <Input
              id="due-from-filter"
              type="date"
              value={draftFilters.dueDateFrom}
              onChange={(event) => setDraftFilters((prev) => ({ ...prev, dueDateFrom: event.target.value }))}
            />
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="due-to-filter">Due to</Label>
            <Input
              id="due-to-filter"
              type="date"
              value={draftFilters.dueDateTo}
              onChange={(event) => setDraftFilters((prev) => ({ ...prev, dueDateTo: event.target.value }))}
            />
          </div>
          <Button type="submit">Search</Button>
          <Button type="button" variant="outline" onClick={clearFilters}>
            Clear
          </Button>
        </form>

        {(isPending || lockedAssigneeLoading) && <p className="text-sm text-foreground/70">Loading tasks…</p>}

        {isError && (
          <p role="alert" className="text-sm text-destructive">
            {error instanceof ApiError ? error.message : "Something went wrong loading tasks."}
          </p>
        )}

        {!isPending && !lockedAssigneeLoading && !isError && tasks.length === 0 && (
          <p className="text-sm text-foreground/70">No tasks match these filters.</p>
        )}

        {!isPending && !lockedAssigneeLoading && !isError && tasks.length > 0 && (
          <div className="relative overflow-x-auto rounded-md border border-border">
            <table className="w-full text-left text-sm [&_td]:whitespace-nowrap [&_th]:whitespace-nowrap">
              <thead className="bg-card">
                <tr>
                  <th className="px-4 py-2 font-medium">Title</th>
                  <th className="px-4 py-2 font-medium">Status</th>
                  <th className="px-4 py-2 font-medium">Priority</th>
                  <th className="px-4 py-2 font-medium">Assignee</th>
                  {canManage && <th className="px-4 py-2 font-medium">Department</th>}
                  <th className="px-4 py-2 font-medium">Due date</th>
                </tr>
              </thead>
              <tbody>
                {tasks.map((task) => (
                  <tr key={task.id} className="border-t border-border">
                    <td className="px-4 py-2">
                      <Link to={`/tasks/${task.id}`} className="font-medium text-primary hover:underline">
                        {task.title}
                      </Link>
                    </td>
                    <td className="px-4 py-2">{STATUS_OPTIONS.find((o) => o.value === task.status)?.label}</td>
                    <td className="px-4 py-2">{PRIORITY_OPTIONS.find((o) => o.value === task.priority)?.label}</td>
                    <td className="px-4 py-2">
                      {task.assignee_membership_id
                        ? canManage
                          ? (employeeNameById.get(task.assignee_membership_id) ?? "—")
                          : "You"
                        : "—"}
                    </td>
                    {canManage && (
                      <td className="px-4 py-2">
                        {task.department_id ? (departmentNameById.get(task.department_id) ?? "—") : "—"}
                      </td>
                    )}
                    <td className="px-4 py-2">{task.due_date ?? "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {meta && meta.total_pages > 1 && (
          <div className="flex items-center justify-center gap-4">
            <Button type="button" variant="outline" size="sm" disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>
              Previous
            </Button>
            <p className="text-sm text-foreground/70">
              Page {meta.page} of {meta.total_pages}
            </p>
            <Button
              type="button"
              variant="outline"
              size="sm"
              disabled={page >= meta.total_pages}
              onClick={() => setPage((p) => p + 1)}
            >
              Next
            </Button>
          </div>
        )}
      </div>
    </div>
  );
}
