import { apiFetch } from "@/api/client";
import type { MembershipPublic, OrganizationPublic } from "@/types/organization";

export interface CreateOrganizationInput {
  name: string;
  email?: string;
  currency?: string;
  timezone?: string;
}

// POST /organizations is CSRF-protected (backend/app/organizations/routes.py)
// - the caller passes the token the same way AuthContext/auth.ts's logout
// does, rather than this module reaching into AuthContext itself.
export function createOrganization(input: CreateOrganizationInput, csrfToken: string): Promise<OrganizationPublic> {
  return apiFetch<OrganizationPublic>("/organizations", { method: "POST", body: input, csrfToken });
}

export function listOrganizations(): Promise<MembershipPublic[]> {
  return apiFetch<MembershipPublic[]>("/organizations");
}
