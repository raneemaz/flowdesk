import { z } from "zod";

// Deliberately minimal (spec Section 32: never duplicate backend
// business logic) - the backend (app/customers/schemas.py) remains
// the source of truth (e.g. email must be a syntactically valid
// address). Only `name` is required, matching FD-034's own judgment
// call that nothing else here carries login/identity semantics the
// way User.email does.
export const createCustomerSchema = z.object({
  name: z.string().min(1, "Name is required.").max(255),
  email: z.string().optional().or(z.literal("")),
  phone: z.string().max(50).optional().or(z.literal("")),
  company: z.string().max(255).optional().or(z.literal("")),
  address: z.string().optional().or(z.literal("")),
  notes: z.string().optional().or(z.literal("")),
});

export type CreateCustomerFormValues = z.infer<typeof createCustomerSchema>;

export const updateCustomerSchema = createCustomerSchema.extend({
  status: z.enum(["active", "archived"]),
});

export type UpdateCustomerFormValues = z.infer<typeof updateCustomerSchema>;
