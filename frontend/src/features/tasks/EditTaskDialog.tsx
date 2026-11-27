import { useEffect, useState } from "react";
import { zodResolver } from "@hookform/resolvers/zod";
import { useForm } from "react-hook-form";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";

import { ApiError } from "@/api/client";
import { listDepartments } from "@/api/departments";
import { deleteTask, updateTask, updateTaskStatus } from "@/api/tasks";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { useAuth } from "@/contexts/AuthContext";
import { useOrganization } from "@/contexts/OrganizationContext";
import { PRIORITY_OPTIONS, STATUS_LABELS } from "@/features/tasks/constants";
import { canManageTasks, statusOptionsFor } from "@/features/tasks/permissions";
import { updateTaskSchema, type UpdateTaskFormValues } from "@/features/tasks/schemas";
import type { TaskPublic, TaskStatus } from "@/types/task";

interface EditTaskDialogProps {
  task: TaskPublic | null;
  onOpenChange: (open: boolean) => void;
}

// The calendar's in-place "open a task" view: edit its fields, move it
// along its workflow, or cancel it, without leaving the month grid.
// Same updateTask/updateTaskStatus calls and schema TaskDetailPage uses;
// the backend still enforces who may do what (transitions, scopes).
// Two ways to take a task off the board: Cancel (a workflow status - the
// task stays on record) and Delete (permanent, Owner/Manager only, with
// a confirmation step in the footer rather than a second stacked dialog).
export function EditTaskDialog({ task, onOpenChange }: EditTaskDialogProps) {
  const { csrfToken } = useAuth();
  const { activeMembership } = useOrganization();
  const organizationId = activeMembership?.organization.id ?? "";
  const isManager = activeMembership ? canManageTasks(activeMembership.role) : false;
  const queryClient = useQueryClient();
  const [error, setError] = useState<string | null>(null);
  const [isChangingStatus, setIsChangingStatus] = useState(false);
  const [isConfirmingDelete, setIsConfirmingDelete] = useState(false);

  const isFinished = task?.status === "completed" || task?.status === "cancelled";
  const canEditFields = isManager && !isFinished;

  const { data: departments } = useQuery({
    queryKey: ["departments", organizationId],
    queryFn: () => listDepartments(organizationId),
    enabled: Boolean(task) && canEditFields && Boolean(organizationId),
  });

  const {
    register,
    handleSubmit,
    reset,
    formState: { errors, isSubmitting },
  } = useForm<UpdateTaskFormValues>({ resolver: zodResolver(updateTaskSchema) });

  useEffect(() => {
    if (!task) return;
    setError(null);
    setIsConfirmingDelete(false);
    reset({
      title: task.title,
      description: task.description ?? "",
      priority: task.priority,
      department_id: task.department_id ?? "",
      start_date: task.start_date ?? "",
      due_date: task.due_date ?? "",
      estimated_hours: task.estimated_hours ?? "",
      actual_hours: task.actual_hours ?? "",
    });
  }, [task, reset]);

  const refresh = async () => {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ["tasks-calendar", organizationId] }),
      queryClient.invalidateQueries({ queryKey: ["tasks", organizationId] }),
      queryClient.invalidateQueries({ queryKey: ["task", organizationId, task?.id] }),
    ]);
  };

  const onSave = async (values: UpdateTaskFormValues) => {
    if (!task || !csrfToken) return;
    setError(null);
    try {
      await updateTask(
        organizationId,
        task.id,
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
      await refresh();
      onOpenChange(false);
    } catch (saveError) {
      setError(saveError instanceof ApiError ? saveError.message : "Something went wrong. Please try again.");
    }
  };

  const onStatusChange = async (nextStatus: TaskStatus) => {
    if (!task || !csrfToken) return;
    setError(null);
    setIsChangingStatus(true);
    try {
      await updateTaskStatus(organizationId, task.id, nextStatus, csrfToken);
      await refresh();
      onOpenChange(false);
    } catch (statusError) {
      setError(statusError instanceof ApiError ? statusError.message : "Could not update the status.");
    } finally {
      setIsChangingStatus(false);
    }
  };

  const onDelete = async () => {
    if (!task || !csrfToken) return;
    setError(null);
    setIsChangingStatus(true);
    try {
      await deleteTask(organizationId, task.id, csrfToken);
      queryClient.removeQueries({ queryKey: ["task", organizationId, task.id] });
      await refresh();
      onOpenChange(false);
    } catch (deleteError) {
      setError(deleteError instanceof ApiError ? deleteError.message : "Could not delete the task.");
    } finally {
      setIsChangingStatus(false);
    }
  };

  const nextStatuses = task ? statusOptionsFor(task.status, isManager) : [];
  const forwardStatuses = nextStatuses.filter((status) => status !== "cancelled");
  const canCancel = nextStatuses.includes("cancelled");

  return (
    <Dialog open={task !== null} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{canEditFields ? "Edit task" : (task?.title ?? "Task")}</DialogTitle>
          <DialogDescription>Status: {task ? STATUS_LABELS[task.status] : ""}</DialogDescription>
        </DialogHeader>

        {canEditFields ? (
          <form id="calendar-edit-task" className="flex flex-col gap-4" onSubmit={handleSubmit(onSave)} noValidate>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="calendar-edit-title">Title</Label>
              <Input id="calendar-edit-title" aria-invalid={errors.title ? "true" : "false"} {...register("title")} />
              {errors.title && <p className="text-sm text-destructive">{errors.title.message}</p>}
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="calendar-edit-description">Description (optional)</Label>
              <Textarea id="calendar-edit-description" {...register("description")} />
            </div>
            <div className="flex flex-wrap gap-4">
              <div className="flex flex-col gap-1.5">
                <Label htmlFor="calendar-edit-priority">Priority</Label>
                <Select id="calendar-edit-priority" {...register("priority")}>
                  {PRIORITY_OPTIONS.map((option) => (
                    <option key={option.value} value={option.value}>
                      {option.label}
                    </option>
                  ))}
                </Select>
              </div>
              <div className="flex flex-col gap-1.5">
                <Label htmlFor="calendar-edit-department">Department (optional)</Label>
                <Select id="calendar-edit-department" {...register("department_id")}>
                  <option value="">No department</option>
                  {(departments ?? [])
                    .filter((department) => department.status === "active" || department.id === task?.department_id)
                    .map((department) => (
                      <option key={department.id} value={department.id}>
                        {department.name}
                      </option>
                    ))}
                </Select>
              </div>
              <div className="flex flex-col gap-1.5">
                <Label htmlFor="calendar-edit-due-date">Due date</Label>
                <Input id="calendar-edit-due-date" type="date" {...register("due_date")} />
              </div>
            </div>
          </form>
        ) : (
          task?.description && <p className="text-sm text-foreground/80">{task.description}</p>
        )}

        {forwardStatuses.length > 0 && (
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-sm text-muted-foreground">Move to</span>
            {forwardStatuses.map((status) => (
              <Button
                key={status}
                type="button"
                variant="outline"
                size="sm"
                disabled={isChangingStatus}
                onClick={() => void onStatusChange(status)}
              >
                {STATUS_LABELS[status]}
              </Button>
            ))}
          </div>
        )}

        {error && (
          <p role="alert" className="text-sm text-destructive">
            {error}
          </p>
        )}

        {isConfirmingDelete ? (
          <DialogFooter className="items-center sm:justify-between">
            <p className="text-sm">Delete this task and its comments and history for good? This can’t be undone.</p>
            <div className="flex gap-3">
              <Button type="button" variant="outline" disabled={isChangingStatus} onClick={() => setIsConfirmingDelete(false)}>
                Keep it
              </Button>
              <Button type="button" variant="destructive" disabled={isChangingStatus} onClick={() => void onDelete()}>
                {isChangingStatus ? "Deleting…" : "Delete task"}
              </Button>
            </div>
          </DialogFooter>
        ) : (
          <DialogFooter className="sm:justify-between">
            <div className="flex flex-wrap items-center gap-3">
              {canCancel && (
                <Button
                  type="button"
                  variant="outline"
                  disabled={isChangingStatus}
                  onClick={() => void onStatusChange("cancelled")}
                >
                  Cancel task
                </Button>
              )}
              {isManager && (
                <Button
                  type="button"
                  variant="outline"
                  className="text-destructive"
                  disabled={isChangingStatus}
                  onClick={() => setIsConfirmingDelete(true)}
                >
                  Delete
                </Button>
              )}
              {task && (
                <Link to={`/tasks/${task.id}`} className="text-sm font-medium text-primary hover:underline">
                  Open full details
                </Link>
              )}
            </div>
            {canEditFields && (
              <Button type="submit" form="calendar-edit-task" disabled={isSubmitting}>
                {isSubmitting ? "Saving…" : "Save changes"}
              </Button>
            )}
          </DialogFooter>
        )}
      </DialogContent>
    </Dialog>
  );
}
