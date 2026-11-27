import { z } from "zod";

export const inviteEmployeeSchema = z.object({
  email: z.string().min(1, "Email is required").email("Enter a valid email address."),
  role: z.enum(["owner", "manager", "employee", "accountant", "customer_support"], {
    message: "Choose a role.",
  }),
});

export type InviteEmployeeFormValues = z.infer<typeof inviteEmployeeSchema>;
