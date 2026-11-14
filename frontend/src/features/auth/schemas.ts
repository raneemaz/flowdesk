import { z } from "zod";

// Deliberately minimal - the backend is the source of truth (spec
// Section 32's "never duplicate business logic between frontend and
// backend"). These only catch obviously-empty/malformed input before a
// request is even sent; the backend's own validation errors (422) are
// what get surfaced for anything these don't catch, e.g. password
// length or uniqueness.
export const loginSchema = z.object({
  email: z.string().min(1, "Email is required").email("Enter a valid email address."),
  password: z.string().min(1, "Password is required."),
});

export type LoginFormValues = z.infer<typeof loginSchema>;

export const registerSchema = z
  .object({
    name: z.string().min(1, "Name is required."),
    email: z.string().min(1, "Email is required").email("Enter a valid email address."),
    password: z.string().min(8, "Password must be at least 8 characters."),
    confirmPassword: z.string().min(1, "Please confirm your password."),
  })
  // Confirmation is a frontend-only UX check - the backend never sees
  // or validates confirmPassword.
  .refine((values) => values.password === values.confirmPassword, {
    message: "Passwords do not match.",
    path: ["confirmPassword"],
  });

export type RegisterFormValues = z.infer<typeof registerSchema>;
