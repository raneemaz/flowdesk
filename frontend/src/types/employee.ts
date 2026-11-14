import type { MembershipRole } from "@/types/organization";

// Mirrors backend/openapi.yaml's EmployeePublic exactly
// (app/employees/service.py's _serialize). At `limited` scope the
// backend omits email/job_title/department/manager/joined_at from the
// response entirely, not as null - so those fields are optional here,
// never `| null`, and every render in this feature must check for
// their *presence*, not just truthiness.
export interface EmployeeDepartmentRef {
  id: string;
  name: string;
}

export interface EmployeeManagerRef {
  membership_id: string;
  name: string;
}

export type EmployeeProfileStatus = "active" | "inactive" | "suspended";

export interface EmployeePublic {
  membership_id: string;
  name: string;
  role: MembershipRole;
  // null, not absent, even at `limited` scope - it's EmployeeProfile's
  // own status (not Membership's), which is simply unset until a
  // profile row exists (see docs/DATABASE.md).
  status: EmployeeProfileStatus | null;
  email?: string;
  job_title?: string | null;
  department?: EmployeeDepartmentRef | null;
  manager?: EmployeeManagerRef | null;
  joined_at?: string;
}

export interface PaginationMeta {
  page: number;
  per_page: number;
  total: number;
  total_pages: number;
}

export interface EmployeeListResult {
  employees: EmployeePublic[];
  meta: PaginationMeta;
}

// The PATCH /employees/{membership_id} response shape - the raw
// EmployeeProfile row (backend/openapi.yaml's EmployeeProfilePublic),
// distinct from EmployeePublic above. See api/employees.ts.
export interface EmployeeProfilePublic {
  id: string;
  organization_id: string;
  membership_id: string;
  department_id: string | null;
  manager_membership_id: string | null;
  job_title: string | null;
  status: EmployeeProfileStatus;
  created_at: string;
}
