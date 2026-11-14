import { z } from "zod";

// Deliberately minimal (spec Section 32: never duplicate backend business
// logic) - only name is actually required (backend/app/organizations/schemas.py);
// these just catch obviously-empty/malformed input before a request is sent.
// The creation form itself only surfaces name/email/currency/timezone - logo,
// phone, address, and date_format are real fields the backend already
// accepts, but there's no organization-settings page yet to edit them later
// (backend/openapi.yaml notes no GET/PATCH /organizations/{id} exists), so
// asking for them during onboarding would collect data nobody could ever
// change. They're left for whichever future task adds that settings page.
export const createOrganizationSchema = z.object({
  name: z.string().min(1, "Organization name is required.").max(255),
  email: z.union([z.string().email("Enter a valid email address."), z.literal("")]).optional(),
  currency: z.union([z.string().length(3, "Use a 3-letter code, e.g. USD."), z.literal("")]).optional(),
  timezone: z.string().optional(),
});

export type CreateOrganizationFormValues = z.infer<typeof createOrganizationSchema>;
