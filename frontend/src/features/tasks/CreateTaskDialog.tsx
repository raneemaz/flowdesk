import { useEffect, useState } from "react";
import { zodResolver } from "@hookform/resolvers/zod";
import { useForm } from "react-hook-form";
import { useQuery, useQueryClient } from "@tanstack/react-query";

import { ApiError } from "@/api/client";
import { listDepartments } from "@/api/departments";
import { createTask } from "@/api/tasks";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { useAuth } from "@/contexts/AuthContext";
import { useOrganization } from "@/contexts/OrganizationContext";
import { PRIORITY_OPTIONS } from "@/features/tasks/constants";
import { createTaskSchema, type CreateTaskFormValues } from "@/features/tasks/schemas";

interface CreateTaskDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** Pre-fills the due date - the calendar's own "click a day to add a
   * task" entry point (FD-065 follow-up feedback). ISO yyyy-mm-dd. */
  defaultDueDate?: string;
  onCreated?: () => void;
}

// The one "new task" form, used by the task list's "+ New task" button
// and by the calendar's "click a day" (which pre-fills the due date).
export function CreateTaskDialog({ open, onOpenChange, defaultDueDate, onCreated }: CreateTaskDialogProps) {
  const { csrfToken } = useAuth();
  const { activeMembership } = useOrganization();
  const organizationId = activeMembership?.organization.id ?? "";
  const queryClient = useQueryClient();
  const [submitError, setSubmitError] = useState<string | null>(null);

  const { data: departments } = useQuery({
    queryKey: ["departments", organizationId],
    queryFn: () => listDepartments(organizationId),
    enabled: open && Boolean(organizationId),
  });

  const {
    register,
    handleSubmit,
    reset,
    setValue,
    formState: { errors, isSubmitting },
  } = useForm<CreateTaskFormValues>({
    resolver: zodResolver(createTaskSchema),
    defaultValues: {
      title: "",
      description: "",
      priority: "medium",
      department_id: "",
      start_date: "",
      due_date: defaultDueDate ?? "",
      estimated_hours: "",
    },
  });

  // Keeps the form's due date in sync with whichever day was clicked -
  // the dialog instance is reused across days, not remounted per click.
  useEffect(() => {
    if (open) setValue("due_date", defaultDueDate ?? "");
  }, [open, defaultDueDate, setValue]);

  const onSubmit = async (values: CreateTaskFormValues) => {
    if (!csrfToken) {
      setSubmitError("Your session is missing a CSRF token - please log in again.");
      return;
    }
    setSubmitError(null);
    try {
      await createTask(
        organizationId,
        {
          title: values.title,
          description: values.description || undefined,
          priority: values.priority,
          department_id: values.department_id || undefined,
          start_date: values.start_date || undefined,
          due_date: values.due_date || undefined,
          estimated_hours: values.estimated_hours || undefined,
        },
        csrfToken,
      );
      reset({ title: "", description: "", priority: "medium", department_id: "", start_date: "", due_date: "", estimated_hours: "" });
      onOpenChange(false);
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["tasks-calendar", organizationId] }),
        queryClient.invalidateQueries({ queryKey: ["tasks", organizationId] }),
      ]);
      onCreated?.();
    } catch (error) {
      setSubmitError(error instanceof ApiError ? error.message : "Something went wrong. Please try again.");
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>New task{defaultDueDate ? ` for ${defaultDueDate}` : ""}</DialogTitle>
        </DialogHeader>
        <form className="flex flex-col gap-4" onSubmit={handleSubmit(onSubmit)} noValidate>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="new-task-title">Title</Label>
            <Input id="new-task-title" aria-invalid={errors.title ? "true" : "false"} {...register("title")} />
            {errors.title && <p className="text-sm text-destructive">{errors.title.message}</p>}
          </div>

          <div className="flex flex-col gap-1.5">
            <Label htmlFor="new-task-description">Description (optional)</Label>
            <Textarea id="new-task-description" {...register("description")} />
          </div>

          <div className="flex flex-wrap gap-4">
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="new-task-priority">Priority</Label>
              <Select id="new-task-priority" {...register("priority")}>
                {PRIORITY_OPTIONS.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </Select>
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="new-task-department">Department (optional)</Label>
              <Select id="new-task-department" {...register("department_id")}>
                <option value="">No department</option>
                {(departments ?? [])
                  .filter((department) => department.status === "active")
                  .map((department) => (
                    <option key={department.id} value={department.id}>
                      {department.name}
                    </option>
                  ))}
              </Select>
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="new-task-start-date">Start date (optional)</Label>
              <Input id="new-task-start-date" type="date" {...register("start_date")} />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="new-task-due-date">Due date</Label>
              <Input id="new-task-due-date" type="date" {...register("due_date")} />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="new-task-estimated-hours">Estimated hours (optional)</Label>
              <Input id="new-task-estimated-hours" inputMode="decimal" {...register("estimated_hours")} />
            </div>
          </div>

          {submitError && (
            <p role="alert" className="text-sm text-destructive">
              {submitError}
            </p>
          )}

          <DialogFooter>
            <Button type="submit" disabled={isSubmitting}>
              {isSubmitting ? "Creating…" : "Create task"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
