import { lazy, Suspense } from "react";

import { WidgetsSkeleton } from "@/components/PageSkeleton";
import { CustomerSupportDashboard } from "@/features/dashboard/CustomerSupportDashboard";
import { EmployeeDashboard } from "@/features/dashboard/EmployeeDashboard";
import { OwnerDashboard } from "@/features/dashboard/OwnerDashboard";
import type { MembershipRole } from "@/types/organization";

// Only the two dashboards that draw charts are split out, so the chart
// library stays off the overview for owners, employees and support
// staff. The others stay in this chunk on purpose: a second lazy step
// here (page chunk, then dashboard chunk) measured ~0.8s slower on
// every overview load, because the dashboard can't start downloading
// until the page has rendered, and React 19 spaces out successive
// Suspense reveals.
const ManagerDashboard = lazy(() =>
  import("@/features/dashboard/ManagerDashboard").then((m) => ({ default: m.ManagerDashboard })),
);
const AccountantDashboard = lazy(() =>
  import("@/features/dashboard/AccountantDashboard").then((m) => ({ default: m.AccountantDashboard })),
);

// Dispatches to the one dashboard matching spec Section 12.3's own
// per-role content list - a thin switch, all the real widget logic
// lives in each role's own component.
export function RoleDashboard({ role, organizationId }: { role: MembershipRole; organizationId: string }) {
  switch (role) {
    case "owner":
      return <OwnerDashboard organizationId={organizationId} />;
    case "manager":
      return (
        <Suspense fallback={<WidgetsSkeleton />}>
          <ManagerDashboard organizationId={organizationId} />
        </Suspense>
      );
    case "employee":
      return <EmployeeDashboard organizationId={organizationId} />;
    case "accountant":
      return (
        <Suspense fallback={<WidgetsSkeleton />}>
          <AccountantDashboard organizationId={organizationId} />
        </Suspense>
      );
    case "customer_support":
      return <CustomerSupportDashboard organizationId={organizationId} />;
  }
}
