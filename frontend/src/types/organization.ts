// Mirrors backend/openapi.yaml's OrganizationPublic/MembershipPublic
// schemas exactly (Organization.to_public_dict / Membership.to_public_dict).
export interface OrganizationPublic {
  id: string;
  name: string;
  slug: string;
  logo: string | null;
  email: string | null;
  phone: string | null;
  address: string | null;
  currency: string;
  timezone: string;
  date_format: string | null;
  created_at: string;
}

export type MembershipRole = "owner" | "manager" | "employee" | "accountant" | "customer_support";
export type MembershipStatus = "active" | "inactive" | "suspended";

export interface MembershipPublic {
  organization: OrganizationPublic;
  role: MembershipRole;
  status: MembershipStatus;
  joined_at: string;
}
