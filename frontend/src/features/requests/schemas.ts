import { z } from "zod";

// Deliberately minimal (spec Section 32: never duplicate backend
// business logic) - the backend (app/customer_requests/schemas.py)
// remains the source of truth (e.g. customer_id must be an active
// customer in this org).
export const createRequestSchema = z.object({
  customer_id: z.string().min(1, "Customer is required."),
  title: z.string().min(1, "Title is required.").max(255),
  description: z.string().optional().or(z.literal("")),
  category: z.string().max(255).optional().or(z.literal("")),
  priority: z.enum(["low", "medium", "high", "urgent"]),
  due_date: z.string().optional().or(z.literal("")),
});

export type CreateRequestFormValues = z.infer<typeof createRequestSchema>;

export const createRequestCommentSchema = z.object({
  body: z.string().min(1, "Comment cannot be empty."),
});

export type CreateRequestCommentFormValues = z.infer<typeof createRequestCommentSchema>;

export const resolutionNotesSchema = z.object({
  resolution_notes: z.string().optional().or(z.literal("")),
});

export type ResolutionNotesFormValues = z.infer<typeof resolutionNotesSchema>;
