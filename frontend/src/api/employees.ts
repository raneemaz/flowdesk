import { apiFetch, apiFetchWithMeta } from "@/api/client";
import type { EmployeeListResult, EmployeePublic, EmployeeProfilePublic, EmployeeProfileStatus, PaginationMeta } from "@/types/employee";
import type { MembershipRole } from "@/types/organization";

export interface ListEmployeesFilters {
  search?: string;
  departmentId?: string;
  role?: MembershipRole;
  status?: EmployeeProfileStatus;
  page?: number;
  perPage?: number;
}

// Builds the query string by hand rather than extending apiFetch's
// options - GET /employees is the only endpoint in this codebase so
// far with more than a handful of optional filters, so a shared
// "params" option isn't worth adding for one caller.
export async function listEmployees(
  organizationId: string,
  filters: ListEmployeesFilters = {},
): Promise<EmployeeListResult> {
  const params = new URLSearchParams();
  if (filters.search) params.set("search", filters.search);
  if (filters.departmentId) params.set("department_id", filters.departmentId);
  if (filters.role) params.set("role", filters.role);
  if (filters.status) params.set("status", filters.status);
  params.set("page", String(filters.page ?? 1));
  params.set("per_page", String(filters.perPage ?? 20));

  const { data, meta } = await apiFetchWithMeta<EmployeePublic[], PaginationMeta>(
    `/organizations/${organizationId}/employees?${params.toString()}`,
  );
  return { employees: data, meta };
}

export function getEmployee(organizationId: string, membershipId: string): Promise<EmployeePublic> {
  return apiFetch<EmployeePublic>(`/organizations/${organizationId}/employees/${membershipId}`);
}

// Partial update - a key left undefined here is simply omitted from
// the request body (not sent as null), matching the backend's
// exclude_unset semantics (docs/API.md). An explicit null clears
// job_title/department_id/manager_membership_id; status never accepts
// null (backend rejects it with 422).
export interface UpdateEmployeeProfileInput {
  job_title?: string | null;
  department_id?: string | null;
  manager_membership_id?: string | null;
  status?: EmployeeProfileStatus;
}

export function updateEmployeeProfile(
  organizationId: string,
  membershipId: string,
  input: UpdateEmployeeProfileInput,
  csrfToken: string,
): Promise<EmployeeProfilePublic> {
  return apiFetch<EmployeeProfilePublic>(`/organizations/${organizationId}/employees/${membershipId}`, {
    method: "PATCH",
    body: input,
    csrfToken,
  });
}
