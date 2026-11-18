import { NavLink } from "react-router-dom";

import { useOrganization } from "@/contexts/OrganizationContext";
import { canManageCustomers } from "@/features/customers/permissions";
import { canManageDepartments } from "@/features/employees/permissions";
import { canManageInvoices } from "@/features/invoices/permissions";
import { canAccessRequests } from "@/features/requests/permissions";
import type { MembershipRole } from "@/types/organization";

interface NavItem {
  to: string;
  label: string;
}

// Spec Section 12.2's own sidebar list is Overview, Employees,
// Departments, Tasks, Customers, Requests, Invoices, Analytics, AI
// Reports, Activity, Settings - the last three are deliberately
// omitted here. No FD task in the 65-task backlog ever builds an
// Activity or Settings *page* (FD-047/FD-048 only ever built their
// read APIs), and AI Reports' own frontend is FD-060, not this task -
// linking to any of the three would be exactly the "placeholder
// functionality" this project's own rules forbid. Revisit this list
// once/if those pages exist.
function navItems(role: MembershipRole): NavItem[] {
  const items: NavItem[] = [
    { to: "/", label: "Overview" },
    { to: "/employees", label: "Employees" },
  ];
  if (canManageDepartments(role)) items.push({ to: "/departments", label: "Departments" });
  items.push({ to: "/tasks", label: "Tasks" });
  if (canManageCustomers(role)) items.push({ to: "/customers", label: "Customers" });
  if (canAccessRequests(role)) items.push({ to: "/requests", label: "Requests" });
  if (canManageInvoices(role)) items.push({ to: "/invoices", label: "Invoices" });
  // Every active role reaches at least the employees sub-view of
  // Analytics (features/analytics/permissions.ts) - never conditional.
  items.push({ to: "/analytics", label: "Analytics" });
  return items;
}

// Navigation is permission-aware, never the security boundary (spec
// Section 12.2/32) - every link below just reuses this codebase's
// existing UI-only `can*` hint functions, the same ones HomePage's own
// nav used before this task replaced it with this persistent sidebar.
export function Sidebar() {
  const { activeMembership } = useOrganization();
  if (!activeMembership) return null;

  return (
    <nav
      aria-label="Primary"
      className="flex w-56 flex-shrink-0 flex-col gap-1 bg-sidebar px-3 py-6 text-sidebar-foreground"
    >
      {navItems(activeMembership.role).map((item) => (
        <NavLink
          key={item.to}
          to={item.to}
          end={item.to === "/"}
          className={({ isActive }) =>
            `rounded-md px-3 py-2 text-sm font-medium transition-colors ${
              isActive ? "bg-primary text-primary-foreground" : "text-sidebar-foreground/80 hover:bg-white/10"
            }`
          }
        >
          {item.label}
        </NavLink>
      ))}
    </nav>
  );
}
