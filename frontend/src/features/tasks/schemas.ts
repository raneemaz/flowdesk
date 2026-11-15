import { z } from "zod";

// Deliberately minimal (spec Section 32: never duplicate backend
// business logic) - the backend (app/tasks/schemas.py) remains the
// source of truth for what's actually valid (e.g. department_id must
// be an active department in this org, due_date >= start_date).
// Empty-string sentinels for department_id/start_date/due_date/
// estimated_hours are mapped to `undefined`/`null` by the page before
// the request body is built - see TaskFormFields.tsx.
export const createTaskSchema = z.object({
  title: z.string().min(1, "Title is required.").max(255),
  description: z.string().optional().or(z.literal("")),
  priority: z.enum(["low", "medium", "high", "urgent"]),
  department_id: z.string().optional().or(z.literal("")),
  start_date: z.string().optional().or(z.literal("")),
  due_date: z.string().optional().or(z.literal("")),
  estimated_hours: z.string().optional().or(z.literal("")),
});

export type CreateTaskFormValues = z.infer<typeof createTaskSchema>;

export const updateTaskSchema = createTaskSchema.extend({
  actual_hours: z.string().optional().or(z.literal("")),
});

export type UpdateTaskFormValues = z.infer<typeof updateTaskSchema>;

export const createTaskCommentSchema = z.object({
  body: z.string().min(1, "Comment cannot be empty."),
});

export type CreateTaskCommentFormValues = z.infer<typeof createTaskCommentSchema>;
