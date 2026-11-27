import type { MembershipRole } from "@/types/organization";

// Mirrors backend/app/models/invitation.py's Invitation.to_public_dict()
// exactly.
export type InvitationStatus = "pending" | "accepted" | "cancelled" | "expired";

export interface InvitationPublic {
  id: string;
  email: string;
  role: MembershipRole;
  status: InvitationStatus;
  expires_at: string;
  accepted_at: string | null;
  cancelled_at: string | null;
  inviter_id: string | null;
  created_at: string;
}
