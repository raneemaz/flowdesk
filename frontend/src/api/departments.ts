import { apiFetch } from "@/api/client";
import type { DepartmentPublic, DepartmentStatus } from "@/types/department";

export interface CreateDepartmentInput {
  name: string;
  description?: string;
  manager_membership_id?: string;
}

export function createDepartment(
  organizationId: string,
  input: CreateDepartmentInput,
  csrfToken: string,
): Promise<DepartmentPublic> {
  return apiFetch<DepartmentPublic>(`/organizations/${organizationId}/departments`, {
    method: "POST",
    body: input,
    csrfToken,
  });
}

// Deactivation never hides history (docs/API.md) - this always
// returns every department, any status, same convention as the
// backend's own list_departments.
export function listDepartments(organizationId: string): Promise<DepartmentPublic[]> {
  return apiFetch<DepartmentPublic[]>(`/organizations/${organizationId}/departments`);
}

// Partial update - a key left undefined is omitted from the request
// body (not sent as null); description/manager_membership_id accept
// an explicit null to clear them, name/status don't (docs/API.md).
export interface UpdateDepartmentInput {
  name?: string;
  description?: string | null;
  manager_membership_id?: string | null;
  status?: DepartmentStatus;
}

export function updateDepartment(
  organizationId: string,
  departmentId: string,
  input: UpdateDepartmentInput,
  csrfToken: string,
): Promise<DepartmentPublic> {
  return apiFetch<DepartmentPublic>(`/organizations/${organizationId}/departments/${departmentId}`, {
    method: "PATCH",
    body: input,
    csrfToken,
  });
}

// Soft deactivate (status -> inactive), idempotent - never a real row
// delete (docs/API.md's Departments section).
export function deactivateDepartment(
  organizationId: string,
  departmentId: string,
  csrfToken: string,
): Promise<DepartmentPublic> {
  return apiFetch<DepartmentPublic>(`/organizations/${organizationId}/departments/${departmentId}`, {
    method: "DELETE",
    csrfToken,
  });
}
