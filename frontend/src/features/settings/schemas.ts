import { z } from "zod";

// Minimal client-side checks for instant feedback; the backend
// (app/organizations/settings.py, app/auth/schemas.py) is the source of
// truth and its field errors are shown as they come back.

export const organizationSettingsSchema = z.object({
  name: z.string().trim().min(1, "Name is required.").max(255),
  email: z.union([z.literal(""), z.email("Enter a valid email address.")]),
  phone: z.string().max(50),
  address: z.string(),
  currency: z
    .string()
    .trim()
    .regex(/^[A-Za-z]{3}$/, "Use a 3-letter currency code, such as USD."),
  timezone: z.string().min(1, "Choose a timezone."),
  date_format: z.string(),
});

export type OrganizationSettingsValues = z.infer<typeof organizationSettingsSchema>;

export const profileSchema = z.object({
  name: z.string().trim().min(1, "Name is required.").max(255),
});

export type ProfileValues = z.infer<typeof profileSchema>;

export const changePasswordSchema = z
  .object({
    current_password: z.string().min(1, "Enter your current password."),
    new_password: z.string().min(8, "Use at least 8 characters.").max(128),
    confirm_password: z.string(),
  })
  .refine((values) => values.new_password === values.confirm_password, {
    path: ["confirm_password"],
    message: "The two new passwords don't match.",
  });

export type ChangePasswordValues = z.infer<typeof changePasswordSchema>;
