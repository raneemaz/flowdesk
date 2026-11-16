// Mirrors backend/openapi.yaml's CustomerPublic exactly (Customer.to_public_dict).
export type CustomerStatus = "active" | "archived";

export interface CustomerPublic {
  id: string;
  organization_id: string;
  name: string;
  email: string | null;
  phone: string | null;
  company: string | null;
  address: string | null;
  notes: string | null;
  status: CustomerStatus;
  created_at: string;
}
