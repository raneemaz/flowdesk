// Mirrors backend/openapi.yaml's DepartmentPublic exactly
// (Department.to_public_dict). Note manager_membership_id is a raw id
// here, not a resolved {membership_id, name} object the way
// EmployeePublic.manager is - DepartmentPublic never promised a
// resolved name (docs/API.md's Departments section), so
// DepartmentsPage resolves a display name itself via the employee
// directory it already has access to.
export type DepartmentStatus = "active" | "inactive";

export interface DepartmentPublic {
  id: string;
  organization_id: string;
  name: string;
  description: string | null;
  manager_membership_id: string | null;
  status: DepartmentStatus;
  created_at: string;
}
