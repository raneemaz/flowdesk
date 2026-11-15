import { useEffect, useState } from "react";
import { zodResolver } from "@hookform/resolvers/zod";
import { useForm } from "react-hook-form";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";

import { ApiError } from "@/api/client";
import { listDepartments } from "@/api/departments";
import { listEmployees } from "@/api/employees";
import {
  assignTask,
  createTaskComment,
  getTask,
  listTaskComments,
  listTaskHistory,
  updateTask,
  updateTaskStatus,
} from "@/api/tasks";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { useAuth } from "@/contexts/AuthContext";
import { useOrganization } from "@/contexts/OrganizationContext";
import { PRIORITY_OPTIONS, STATUS_LABELS } from "@/features/tasks/constants";
import { canManageTasks, statusOptionsFor } from "@/features/tasks/permissions";
import {
  createTaskCommentSchema,
  updateTaskSchema,
  type CreateTaskCommentFormValues,
  type UpdateTaskFormValues,
} from "@/features/tasks/schemas";
import type { TaskStatus } from "@/types/task";

export function TaskDetailPage() {
  const { taskId } = useParams<{ taskId: string }>();
  const { csrfToken } = useAuth();
  const { activeMembership } = useOrganization();
  const organizationId = activeMembership?.organization.id ?? "";
  const canManage = activeMembership ? canManageTasks(activeMembership.role) : false;
  const queryClient = useQueryClient();

  const [isEditing, setIsEditing] = useState(false);
  const [editError, setEditError] = useState<string | null>(null);
  const [assignError, setAssignError] = useState<string | null>(null);
  const [statusError, setStatusError] = useState<string | null>(null);
  const [commentError, setCommentError] = useState<string | null>(null);

  const taskQueryKey = ["task", organizationId, taskId];
  const { data: task, isPending, isError, error } = useQuery({
    queryKey: taskQueryKey,
    queryFn: () => getTask(organizationId, taskId!),
    enabled: Boolean(organizationId && taskId),
  });

  // Every authenticated member can look up names - EMPLOYEE_DIRECTORY_VIEW
  // never grants `none`, and `name` is present even at `limited` scope
  // (docs/API.md's Employee directory section), so this works
  // regardless of role, unlike the department lookup below.
  const { data: employeesForNames } = useQuery({
    queryKey: ["employees-for-task-names", organizationId],
    queryFn: () => listEmployees(organizationId, { perPage: 100 }),
    enabled: Boolean(organizationId),
  });
  const nameById = new Map((employeesForNames?.employees ?? []).map((e) => [e.membership_id, e.name]));

  // Only Owner/Manager can list departments (DEPARTMENT_MANAGE has no
  // `limited` view, docs/API.md) - used for the edit form's picker and
  // to resolve a display name; everyone else just doesn't see a
  // department field rather than this 403ing.
  const { data: departments } = useQuery({
    queryKey: ["departments", organizationId],
    queryFn: () => listDepartments(organizationId),
    enabled: canManage && Boolean(organizationId),
  });
  const departmentNameById = new Map((departments ?? []).map((d) => [d.id, d.name]));

  const { data: commentsData } = useQuery({
    queryKey: ["task-comments", organizationId, taskId],
    queryFn: () => listTaskComments(organizationId, taskId!, 1, 100),
    enabled: Boolean(organizationId && taskId && task),
  });

  const { data: historyData } = useQuery({
    queryKey: ["task-history", organizationId, taskId],
    queryFn: () => listTaskHistory(organizationId, taskId!, 1, 100),
    enabled: Boolean(organizationId && taskId && task),
  });

  const editForm = useForm<UpdateTaskFormValues>({ resolver: zodResolver(updateTaskSchema) });

  useEffect(() => {
    if (task && isEditing) {
      editForm.reset({
        title: task.title,
        description: task.description ?? "",
        priority: task.priority,
        department_id: task.department_id ?? "",
        start_date: task.start_date ?? "",
        due_date: task.due_date ?? "",
        estimated_hours: task.estimated_hours ?? "",
        actual_hours: task.actual_hours ?? "",
      });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [task, isEditing]);

  const commentForm = useForm<CreateTaskCommentFormValues>({
    resolver: zodResolver(createTaskCommentSchema),
    defaultValues: { body: "" },
  });

  // Editing, assigning, and changing status can all write a TaskHistory
  // row (FD-027/FD-028/FD-029), so every mutation refreshes both the
  // task itself and its history - not just whichever one a given
  // action happens to touch most visibly.
  const invalidateTask = async () => {
    await queryClient.invalidateQueries({ queryKey: taskQueryKey });
    await queryClient.invalidateQueries({ queryKey: ["task-history", organizationId, taskId] });
  };

  const onEditSubmit = async (values: UpdateTaskFormValues) => {
    if (!csrfToken || !taskId) return;
    setEditError(null);
    try {
      await updateTask(
        organizationId,
        taskId,
        {
          title: values.title,
          description: values.description || null,
          priority: values.priority,
          department_id: values.department_id || null,
          start_date: values.start_date || null,
          due_date: values.due_date || null,
          estimated_hours: values.estimated_hours || null,
          actual_hours: values.actual_hours || null,
        },
        csrfToken,
      );
      await invalidateTask();
      setIsEditing(false);
    } catch (submitError) {
      setEditError(submitError instanceof ApiError ? submitError.message : "Something went wrong. Please try again.");
    }
  };

  const onAssign = async (assigneeMembershipId: string) => {
    if (!csrfToken || !taskId) return;
    setAssignError(null);
    try {
      await assignTask(organizationId, taskId, assigneeMembershipId || null, csrfToken);
      await invalidateTask();
    } catch (submitError) {
      setAssignError(submitError instanceof ApiError ? submitError.message : "Could not update the assignee.");
    }
  };

  const onStatusChange = async (nextStatus: TaskStatus) => {
    if (!csrfToken || !taskId) return;
    setStatusError(null);
    try {
      await updateTaskStatus(organizationId, taskId, nextStatus, csrfToken);
      await invalidateTask();
    } catch (submitError) {
      setStatusError(submitError instanceof ApiError ? submitError.message : "Could not update the status.");
    }
  };

  const onCommentSubmit = async (values: CreateTaskCommentFormValues) => {
    if (!csrfToken || !taskId) return;
    setCommentError(null);
    try {
      await createTaskComment(organizationId, taskId, values.body, csrfToken);
      commentForm.reset({ body: "" });
      await queryClient.invalidateQueries({ queryKey: ["task-comments", organizationId, taskId] });
    } catch (submitError) {
      setCommentError(submitError instanceof ApiError ? submitError.message : "Could not post your comment.");
    }
  };

  if (isPending) {
    return (
      <main className="flex min-h-screen items-center justify-center bg-background text-foreground">
        <p className="text-sm text-foreground/70">Loading task…</p>
      </main>
    );
  }

  if (isError || !task) {
    return (
      <main className="flex min-h-screen flex-col items-center justify-center gap-3 bg-background text-foreground">
        <p role="alert" className="text-sm text-destructive">
          {error instanceof ApiError ? error.message : "Task not found."}
        </p>
        <Link to="/tasks" className="text-sm font-medium text-primary hover:underline">
          Back to tasks
        </Link>
      </main>
    );
  }

  const nextStatuses = statusOptionsFor(task.status, canManage);

  // TaskHistory stores raw values (a membership_id string for
  // "assignee_changed", a status enum value for "status_changed" -
  // docs/API.md's Tasks section) - resolved to something readable
  // here rather than showing a bare UUID or snake_case value.
  const describeHistoryValue = (fieldLabel: string, raw: string | null): string => {
    if (raw === null) return fieldLabel === "assignee" ? "Unassigned" : "—";
    if (fieldLabel === "assignee") return nameById.get(raw) ?? raw;
    if (fieldLabel === "status") return STATUS_LABELS[raw as TaskStatus] ?? raw;
    if (fieldLabel === "priority") return PRIORITY_OPTIONS.find((option) => option.value === raw)?.label ?? raw;
    return raw;
  };

  return (
    <main className="min-h-screen bg-background px-4 py-8 text-foreground">
      <div className="mx-auto flex max-w-2xl flex-col gap-6">
        <div className="flex items-center justify-between">
          <h1 className="text-2xl font-semibold">{task.title}</h1>
          <Link to="/tasks" className="text-sm font-medium text-primary hover:underline">
            Back to tasks
          </Link>
        </div>

        {!isEditing && (
          <div className="flex flex-col gap-3 rounded-md border border-border bg-card p-6">
            <Field label="Status" value={STATUS_LABELS[task.status]} />
            <Field label="Priority" value={PRIORITY_OPTIONS.find((o) => o.value === task.priority)?.label ?? task.priority} />
            <Field label="Description" value={task.description ?? "—"} />
            {canManage && <Field label="Department" value={task.department_id ? (departmentNameById.get(task.department_id) ?? "—") : "—"} />}
            <Field
              label="Assignee"
              value={task.assignee_membership_id ? (nameById.get(task.assignee_membership_id) ?? "—") : "Unassigned"}
            />
            <Field label="Start date" value={task.start_date ?? "—"} />
            <Field label="Due date" value={task.due_date ?? "—"} />
            {canManage && <Field label="Estimated hours" value={task.estimated_hours ?? "—"} />}
            {canManage && <Field label="Actual hours" value={task.actual_hours ?? "—"} />}

            {canManage && (
              <Button className="mt-2 self-start" onClick={() => setIsEditing(true)}>
                Edit task
              </Button>
            )}
          </div>
        )}

        {isEditing && (
          <form
            className="flex flex-col gap-4 rounded-md border border-border bg-card p-6"
            onSubmit={editForm.handleSubmit(onEditSubmit)}
            noValidate
          >
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="edit-title">Title</Label>
              <Input id="edit-title" aria-invalid={editForm.formState.errors.title ? "true" : "false"} {...editForm.register("title")} />
              {editForm.formState.errors.title && (
                <p className="text-sm text-destructive">{editForm.formState.errors.title.message}</p>
              )}
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="edit-description">Description</Label>
              <Textarea id="edit-description" {...editForm.register("description")} />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="edit-priority">Priority</Label>
              <Select id="edit-priority" {...editForm.register("priority")}>
                {PRIORITY_OPTIONS.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </Select>
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="edit-department">Department</Label>
              <Select id="edit-department" {...editForm.register("department_id")}>
                <option value="">No department</option>
                {(departments ?? [])
                  .filter((d) => d.status === "active")
                  .map((d) => (
                    <option key={d.id} value={d.id}>
                      {d.name}
                    </option>
                  ))}
              </Select>
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="edit-start-date">Start date</Label>
              <Input id="edit-start-date" type="date" {...editForm.register("start_date")} />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="edit-due-date">Due date</Label>
              <Input id="edit-due-date" type="date" {...editForm.register("due_date")} />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="edit-estimated-hours">Estimated hours</Label>
              <Input id="edit-estimated-hours" {...editForm.register("estimated_hours")} />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="edit-actual-hours">Actual hours</Label>
              <Input id="edit-actual-hours" {...editForm.register("actual_hours")} />
            </div>

            {editError && (
              <p role="alert" className="text-sm text-destructive">
                {editError}
              </p>
            )}

            <div className="flex gap-3">
              <Button type="submit" disabled={editForm.formState.isSubmitting}>
                {editForm.formState.isSubmitting ? "Saving…" : "Save changes"}
              </Button>
              <Button type="button" variant="outline" onClick={() => setIsEditing(false)}>
                Cancel
              </Button>
            </div>
          </form>
        )}

        {canManage && (
          <div className="flex flex-col gap-1.5 rounded-md border border-border bg-card p-6">
            <Label htmlFor="assign-select">Assignee</Label>
            <Select
              id="assign-select"
              value={task.assignee_membership_id ?? ""}
              onChange={(event) => void onAssign(event.target.value)}
            >
              <option value="">Unassigned</option>
              {(employeesForNames?.employees ?? []).map((candidate) => (
                <option key={candidate.membership_id} value={candidate.membership_id}>
                  {candidate.name}
                </option>
              ))}
            </Select>
            {assignError && (
              <p role="alert" className="text-sm text-destructive">
                {assignError}
              </p>
            )}
          </div>
        )}

        <div className="flex flex-col gap-2 rounded-md border border-border bg-card p-6">
          <p className="text-sm font-medium">Move to:</p>
          <div className="flex flex-wrap gap-2">
            {nextStatuses.length === 0 && <p className="text-sm text-foreground/70">No further status changes available.</p>}
            {nextStatuses.map((nextStatus) => (
              <Button key={nextStatus} type="button" variant="outline" size="sm" onClick={() => void onStatusChange(nextStatus)}>
                {STATUS_LABELS[nextStatus]}
              </Button>
            ))}
          </div>
          {statusError && (
            <p role="alert" className="text-sm text-destructive">
              {statusError}
            </p>
          )}
        </div>

        <div className="flex flex-col gap-3 rounded-md border border-border bg-card p-6">
          <h2 className="text-lg font-medium">Comments</h2>
          <div className="flex flex-col gap-3">
            {(commentsData?.comments ?? []).length === 0 && <p className="text-sm text-foreground/70">No comments yet.</p>}
            {(commentsData?.comments ?? []).map((comment) => (
              <div key={comment.id} className="rounded-md border border-border p-3">
                <p className="text-xs font-medium text-foreground/70">
                  {comment.author_membership_id ? (nameById.get(comment.author_membership_id) ?? "Unknown") : "Unknown"} ·{" "}
                  {new Date(comment.created_at).toLocaleString()}
                </p>
                <p className="text-sm">{comment.body}</p>
              </div>
            ))}
          </div>
          <form className="flex flex-col gap-2" onSubmit={commentForm.handleSubmit(onCommentSubmit)} noValidate>
            <Label htmlFor="comment-body" className="sr-only">
              Add a comment
            </Label>
            <Textarea id="comment-body" placeholder="Add a comment…" {...commentForm.register("body")} />
            {commentForm.formState.errors.body && (
              <p className="text-sm text-destructive">{commentForm.formState.errors.body.message}</p>
            )}
            {commentError && (
              <p role="alert" className="text-sm text-destructive">
                {commentError}
              </p>
            )}
            <Button type="submit" className="self-start" disabled={commentForm.formState.isSubmitting}>
              {commentForm.formState.isSubmitting ? "Posting…" : "Post comment"}
            </Button>
          </form>
        </div>

        <div className="flex flex-col gap-3 rounded-md border border-border bg-card p-6">
          <h2 className="text-lg font-medium">History</h2>
          {(historyData?.entries ?? []).length === 0 && <p className="text-sm text-foreground/70">No history yet.</p>}
          <ul className="flex flex-col gap-2">
            {(historyData?.entries ?? []).map((entry) => {
              const fieldLabel = entry.event_type.replace(/_changed$/, "").replace(/_/g, " ");
              return (
                <li key={entry.id} className="text-sm text-foreground/70">
                  <span className="font-medium text-foreground">
                    {entry.actor_membership_id ? (nameById.get(entry.actor_membership_id) ?? "Someone") : "Someone"}
                  </span>{" "}
                  changed {fieldLabel} from{" "}
                  <span className="font-medium text-foreground">{describeHistoryValue(fieldLabel, entry.previous_value)}</span>{" "}
                  to{" "}
                  <span className="font-medium text-foreground">{describeHistoryValue(fieldLabel, entry.new_value)}</span> on{" "}
                  {new Date(entry.created_at).toLocaleString()}
                </li>
              );
            })}
          </ul>
        </div>
      </div>
    </main>
  );
}

function Field({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex flex-col gap-0.5">
      <span className="text-xs font-medium uppercase tracking-wide text-foreground/50">{label}</span>
      <span className="text-sm">{value}</span>
    </div>
  );
}
