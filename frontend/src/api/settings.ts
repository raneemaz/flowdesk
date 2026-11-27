import { apiFetch } from "@/api/client";
import type { MembershipRole, MembershipStatus, OrganizationPublic } from "@/types/organization";
import type { UserPublic } from "@/types/user";

// Settings page API (backend: app/organizations/settings.py and
// app/auth/routes.py). The backend decides who may change what; the
// page only hides controls a viewer can't use.

export interface UpdateOrganizationInput {
  name?: string;
  email?: string | null;
  phone?: string | null;
  address?: string | null;
  currency?: string;
  timezone?: string;
  date_format?: string | null;
}

export function updateOrganization(
  organizationId: string,
  input: UpdateOrganizationInput,
  csrfToken: string,
): Promise<OrganizationPublic> {
  return apiFetch<OrganizationPublic>(`/organizations/${organizationId}`, { method: "PATCH", body: input, csrfToken });
}

export interface MemberPublic {
  membership_id: string;
  user_id: string;
  name: string;
  email: string;
  role: MembershipRole;
  status: MembershipStatus;
  joined_at: string;
}

export function listMembers(organizationId: string): Promise<MemberPublic[]> {
  return apiFetch<MemberPublic[]>(`/organizations/${organizationId}/members`);
}

export function updateMember(
  organizationId: string,
  membershipId: string,
  input: { role?: MembershipRole; status?: MembershipStatus },
  csrfToken: string,
): Promise<MemberPublic> {
  return apiFetch<MemberPublic>(`/organizations/${organizationId}/members/${membershipId}`, {
    method: "PATCH",
    body: input,
    csrfToken,
  });
}

export function updateProfile(input: { name: string }, csrfToken: string): Promise<UserPublic> {
  return apiFetch<UserPublic>("/auth/me", { method: "PATCH", body: input, csrfToken });
}

export function changePassword(
  input: { current_password: string; new_password: string },
  csrfToken: string,
): Promise<null> {
  return apiFetch<null>("/auth/change-password", { method: "POST", body: input, csrfToken });
}
