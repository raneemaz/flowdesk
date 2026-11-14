import { z } from "zod";

// Deliberately minimal (spec Section 32) - the backend
// (app/departments/schemas.py) remains the source of truth. Empty-
// string sentinels for description/manager_membership_id are mapped
// to `null` by the page before the request body is built - see
// DepartmentsPage.tsx.
export const createDepartmentSchema = z.object({
  name: z.string().min(1, "Department name is required.").max(255),
  description: z.string().optional().or(z.literal("")),
  manager_membership_id: z.string().optional().or(z.literal("")),
});

export type CreateDepartmentFormValues = z.infer<typeof createDepartmentSchema>;

export const updateDepartmentSchema = z.object({
  name: z.string().min(1, "Department name is required.").max(255),
  description: z.string().optional().or(z.literal("")),
  manager_membership_id: z.string().optional().or(z.literal("")),
  status: z.enum(["active", "inactive"]),
});

export type UpdateDepartmentFormValues = z.infer<typeof updateDepartmentSchema>;
