import { apiFetch, apiFetchWithMeta } from "@/api/client";
import type { PaginationMeta } from "@/types/employee";
import type { CustomerPublic, CustomerStatus } from "@/types/customer";

export interface ListCustomersFilters {
  search?: string;
  status?: CustomerStatus;
  page?: number;
  perPage?: number;
}

export interface CustomerListResult {
  customers: CustomerPublic[];
  meta: PaginationMeta;
}

// Includes both active and archived customers by default - archiving
// never hides history (docs/API.md's Customers section) - `status`
// narrows it down when the caller supplies one.
export async function listCustomers(
  organizationId: string,
  filters: ListCustomersFilters = {},
): Promise<CustomerListResult> {
  const params = new URLSearchParams();
  if (filters.search) params.set("search", filters.search);
  if (filters.status) params.set("status", filters.status);
  params.set("page", String(filters.page ?? 1));
  params.set("per_page", String(filters.perPage ?? 20));

  const { data, meta } = await apiFetchWithMeta<CustomerPublic[], PaginationMeta>(
    `/organizations/${organizationId}/customers?${params.toString()}`,
  );
  return { customers: data, meta };
}

export function getCustomer(organizationId: string, customerId: string): Promise<CustomerPublic> {
  return apiFetch<CustomerPublic>(`/organizations/${organizationId}/customers/${customerId}`);
}

export interface CreateCustomerInput {
  name: string;
  email?: string;
  phone?: string;
  company?: string;
  address?: string;
  notes?: string;
}

// Never accepts status - a new customer always starts active
// (docs/API.md's Customers section).
export function createCustomer(
  organizationId: string,
  input: CreateCustomerInput,
  csrfToken: string,
): Promise<CustomerPublic> {
  return apiFetch<CustomerPublic>(`/organizations/${organizationId}/customers`, {
    method: "POST",
    body: input,
    csrfToken,
  });
}

// Partial update - a key left undefined is omitted from the request
// body (not sent as null); email/phone/company/address/notes accept
// an explicit null to clear them, name/status don't (docs/API.md).
export interface UpdateCustomerInput {
  name?: string;
  email?: string | null;
  phone?: string | null;
  company?: string | null;
  address?: string | null;
  notes?: string | null;
  status?: CustomerStatus;
}

export function updateCustomer(
  organizationId: string,
  customerId: string,
  input: UpdateCustomerInput,
  csrfToken: string,
): Promise<CustomerPublic> {
  return apiFetch<CustomerPublic>(`/organizations/${organizationId}/customers/${customerId}`, {
    method: "PATCH",
    body: input,
    csrfToken,
  });
}

// Soft archive (status -> archived), idempotent - never a real row
// delete (docs/API.md's Customers section). Reactivation is via
// updateCustomer({status: "active"}), same convention as departments.
export function archiveCustomer(
  organizationId: string,
  customerId: string,
  csrfToken: string,
): Promise<CustomerPublic> {
  return apiFetch<CustomerPublic>(`/organizations/${organizationId}/customers/${customerId}`, {
    method: "DELETE",
    csrfToken,
  });
}
