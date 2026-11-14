import { z } from "zod";

// Deliberately minimal (spec Section 32: never duplicate backend
// business logic) - the backend (app/employees/schemas.py) remains the
// source of truth for what's actually valid (e.g. department_id must
// be an active department in this org). This only catches obviously
// malformed input before a request is sent. Empty-string sentinels
// ("" for job_title/department_id/manager_membership_id) represent
// "cleared" in the <select>/<input> controls and are mapped to
// `null` by the page before the PATCH body is built - see
// EmployeeProfilePage.tsx.
export const updateEmployeeProfileSchema = z.object({
  job_title: z.string().max(255).optional().or(z.literal("")),
  department_id: z.string().optional().or(z.literal("")),
  manager_membership_id: z.string().optional().or(z.literal("")),
  status: z.enum(["active", "inactive", "suspended"]),
});

export type UpdateEmployeeProfileFormValues = z.infer<typeof updateEmployeeProfileSchema>;
