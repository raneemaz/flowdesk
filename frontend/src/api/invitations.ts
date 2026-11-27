import { apiFetch } from "@/api/client";
import type { InvitationPublic } from "@/types/invitation";
import type { MembershipRole } from "@/types/organization";

export interface CreateInvitationInput {
  email: string;
  role: MembershipRole;
}

// The real Invitation row also carries an `email_delivery` field
// (app/invitations/routes.py) describing whether the real email send
// succeeded or fell back to the dev-only log - not modeled here since
// no caller needs it (the UI just shows "invited", same as every
// other create response in this codebase that ignores side-channel
// fields it doesn't need).
export function createInvitation(
  organizationId: string,
  input: CreateInvitationInput,
  csrfToken: string,
): Promise<InvitationPublic> {
  return apiFetch<InvitationPublic>(`/organizations/${organizationId}/invitations`, {
    method: "POST",
    body: input,
    csrfToken,
  });
}

export function listInvitations(organizationId: string): Promise<InvitationPublic[]> {
  return apiFetch<InvitationPublic[]>(`/organizations/${organizationId}/invitations`);
}

export function cancelInvitation(organizationId: string, invitationId: string, csrfToken: string): Promise<InvitationPublic> {
  return apiFetch<InvitationPublic>(`/organizations/${organizationId}/invitations/${invitationId}`, {
    method: "DELETE",
    csrfToken,
  });
}
