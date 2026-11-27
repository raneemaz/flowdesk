import { apiFetch, apiFetchWithMeta } from "@/api/client";
import type { PaginationMeta } from "@/types/employee";
import type { TaskCommentPublic, TaskHistoryPublic, TaskPriority, TaskPublic, TaskStatus } from "@/types/task";

export interface ListTasksFilters {
  assigneeMembershipId?: string;
  departmentId?: string;
  priority?: TaskPriority;
  status?: TaskStatus;
  dueDateFrom?: string;
  dueDateTo?: string;
  createdFrom?: string;
  createdTo?: string;
  page?: number;
  perPage?: number;
}

export interface TaskListResult {
  tasks: TaskPublic[];
  meta: PaginationMeta;
}

// Builds the query string by hand, same convention as api/employees.ts's
// listEmployees - this is the other endpoint in this codebase with more
// than a handful of optional filters.
export async function listTasks(organizationId: string, filters: ListTasksFilters = {}): Promise<TaskListResult> {
  const params = new URLSearchParams();
  if (filters.assigneeMembershipId) params.set("assignee_membership_id", filters.assigneeMembershipId);
  if (filters.departmentId) params.set("department_id", filters.departmentId);
  if (filters.priority) params.set("priority", filters.priority);
  if (filters.status) params.set("status", filters.status);
  if (filters.dueDateFrom) params.set("due_date_from", filters.dueDateFrom);
  if (filters.dueDateTo) params.set("due_date_to", filters.dueDateTo);
  if (filters.createdFrom) params.set("created_from", filters.createdFrom);
  if (filters.createdTo) params.set("created_to", filters.createdTo);
  params.set("page", String(filters.page ?? 1));
  params.set("per_page", String(filters.perPage ?? 20));

  const { data, meta } = await apiFetchWithMeta<TaskPublic[], PaginationMeta>(
    `/organizations/${organizationId}/tasks?${params.toString()}`,
  );
  return { tasks: data, meta };
}

export function getTask(organizationId: string, taskId: string): Promise<TaskPublic> {
  return apiFetch<TaskPublic>(`/organizations/${organizationId}/tasks/${taskId}`);
}

export interface CreateTaskInput {
  title: string;
  description?: string | null;
  priority?: TaskPriority;
  department_id?: string | null;
  start_date?: string | null;
  due_date?: string | null;
  estimated_hours?: string | null;
}

// Never accepts assignee_membership_id or status - a new task always
// starts unassigned/to_do (backend/docs/API.md's Tasks section).
export function createTask(organizationId: string, input: CreateTaskInput, csrfToken: string): Promise<TaskPublic> {
  return apiFetch<TaskPublic>(`/organizations/${organizationId}/tasks`, { method: "POST", body: input, csrfToken });
}

export interface UpdateTaskInput {
  title?: string;
  description?: string | null;
  priority?: TaskPriority;
  department_id?: string | null;
  start_date?: string | null;
  due_date?: string | null;
  estimated_hours?: string | null;
  actual_hours?: string | null;
}

export function updateTask(
  organizationId: string,
  taskId: string,
  input: UpdateTaskInput,
  csrfToken: string,
): Promise<TaskPublic> {
  return apiFetch<TaskPublic>(`/organizations/${organizationId}/tasks/${taskId}`, {
    method: "PATCH",
    body: input,
    csrfToken,
  });
}

// Permanent: the task, its comments and history are removed (the
// activity log keeps a "task deleted" entry). Owner/Manager only.
export function deleteTask(organizationId: string, taskId: string, csrfToken: string): Promise<null> {
  return apiFetch<null>(`/organizations/${organizationId}/tasks/${taskId}`, { method: "DELETE", csrfToken });
}

export function assignTask(
  organizationId: string,
  taskId: string,
  assigneeMembershipId: string | null,
  csrfToken: string,
): Promise<TaskPublic> {
  return apiFetch<TaskPublic>(`/organizations/${organizationId}/tasks/${taskId}/assign`, {
    method: "PATCH",
    body: { assignee_membership_id: assigneeMembershipId },
    csrfToken,
  });
}

export function updateTaskStatus(
  organizationId: string,
  taskId: string,
  status: TaskStatus,
  csrfToken: string,
): Promise<TaskPublic> {
  return apiFetch<TaskPublic>(`/organizations/${organizationId}/tasks/${taskId}/status`, {
    method: "PATCH",
    body: { status },
    csrfToken,
  });
}

export interface TaskCommentListResult {
  comments: TaskCommentPublic[];
  meta: PaginationMeta;
}

export async function listTaskComments(
  organizationId: string,
  taskId: string,
  page = 1,
  perPage = 50,
): Promise<TaskCommentListResult> {
  const params = new URLSearchParams({ page: String(page), per_page: String(perPage) });
  const { data, meta } = await apiFetchWithMeta<TaskCommentPublic[], PaginationMeta>(
    `/organizations/${organizationId}/tasks/${taskId}/comments?${params.toString()}`,
  );
  return { comments: data, meta };
}

export function createTaskComment(
  organizationId: string,
  taskId: string,
  body: string,
  csrfToken: string,
): Promise<TaskCommentPublic> {
  return apiFetch<TaskCommentPublic>(`/organizations/${organizationId}/tasks/${taskId}/comments`, {
    method: "POST",
    body: { body },
    csrfToken,
  });
}

export interface TaskHistoryListResult {
  entries: TaskHistoryPublic[];
  meta: PaginationMeta;
}

export async function listTaskHistory(
  organizationId: string,
  taskId: string,
  page = 1,
  perPage = 50,
): Promise<TaskHistoryListResult> {
  const params = new URLSearchParams({ page: String(page), per_page: String(perPage) });
  const { data, meta } = await apiFetchWithMeta<TaskHistoryPublic[], PaginationMeta>(
    `/organizations/${organizationId}/tasks/${taskId}/history?${params.toString()}`,
  );
  return { entries: data, meta };
}

// Author only.
export function updateTaskComment(
  organizationId: string,
  taskId: string,
  commentId: string,
  body: string,
  csrfToken: string,
): Promise<TaskCommentPublic> {
  return apiFetch<TaskCommentPublic>(`/organizations/${organizationId}/tasks/${taskId}/comments/${commentId}`, {
    method: "PATCH",
    body: { body },
    csrfToken,
  });
}

// Author, or an Owner/Manager.
export function deleteTaskComment(
  organizationId: string,
  taskId: string,
  commentId: string,
  csrfToken: string,
): Promise<null> {
  return apiFetch<null>(`/organizations/${organizationId}/tasks/${taskId}/comments/${commentId}`, {
    method: "DELETE",
    csrfToken,
  });
}
