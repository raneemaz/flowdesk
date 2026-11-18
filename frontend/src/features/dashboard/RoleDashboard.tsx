import { AccountantDashboard } from "@/features/dashboard/AccountantDashboard";
import { CustomerSupportDashboard } from "@/features/dashboard/CustomerSupportDashboard";
import { EmployeeDashboard } from "@/features/dashboard/EmployeeDashboard";
import { ManagerDashboard } from "@/features/dashboard/ManagerDashboard";
import { OwnerDashboard } from "@/features/dashboard/OwnerDashboard";
import type { MembershipRole } from "@/types/organization";

// Dispatches to the one dashboard matching spec Section 12.3's own
// per-role content list - a thin switch, all the real widget logic
// lives in each role's own component.
export function RoleDashboard({ role, organizationId }: { role: MembershipRole; organizationId: string }) {
  switch (role) {
    case "owner":
      return <OwnerDashboard organizationId={organizationId} />;
    case "manager":
      return <ManagerDashboard organizationId={organizationId} />;
    case "employee":
      return <EmployeeDashboard organizationId={organizationId} />;
    case "accountant":
      return <AccountantDashboard organizationId={organizationId} />;
    case "customer_support":
      return <CustomerSupportDashboard organizationId={organizationId} />;
  }
}
