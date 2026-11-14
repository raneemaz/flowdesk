import type { MembershipRole } from "@/types/organization";
import type { EmployeeProfileStatus } from "@/types/employee";

// Duplicated from HomePage.tsx/OrganizationSwitcher.tsx rather than
// factored into a shared module - those are pre-existing, already
// -tested files outside this task's scope, and this feature needs its
// own ordered ROLE_OPTIONS (for a <select>) anyway, which neither of
// those files has.
export const ROLE_LABELS: Record<MembershipRole, string> = {
  owner: "Owner",
  manager: "Manager",
  employee: "Employee",
  accountant: "Accountant",
  customer_support: "Customer Support",
};

export const ROLE_OPTIONS: { value: MembershipRole; label: string }[] = [
  { value: "owner", label: "Owner" },
  { value: "manager", label: "Manager" },
  { value: "employee", label: "Employee" },
  { value: "accountant", label: "Accountant" },
  { value: "customer_support", label: "Customer Support" },
];

export const EMPLOYEE_STATUS_LABELS: Record<EmployeeProfileStatus, string> = {
  active: "Active",
  inactive: "Inactive",
  suspended: "Suspended",
};

export const EMPLOYEE_STATUS_OPTIONS: { value: EmployeeProfileStatus; label: string }[] = [
  { value: "active", label: "Active" },
  { value: "inactive", label: "Inactive" },
  { value: "suspended", label: "Suspended" },
];
