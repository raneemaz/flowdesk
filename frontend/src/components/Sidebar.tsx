import { NavLink } from "react-router-dom";

import { useOrganization } from "@/contexts/OrganizationContext";
import { canViewAIReports } from "@/features/aiReports/permissions";
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
// Reports, Activity, Settings - Activity and Settings are still
// deliberately omitted. No FD task in the 65-task backlog ever builds
// an Activity or Settings *page* (FD-047/FD-048 only ever built their
// read APIs) - linking to either would be exactly the "placeholder
// functionality" this project's own rules forbid. AI Reports (FD-060)
// is no longer one of the omissions. Revisit the remaining two once/if
// those pages exist.
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
  if (canViewAIReports(role)) items.push({ to: "/ai-reports", label: "AI Reports" });
  return items;
}

interface SidebarProps {
  // Below the `md` breakpoint this is an off-canvas panel (FD-063,
  // NFR-011) rather than an always-visible column - `open`/`onClose`
  // are DashboardLayout's own toggle state, irrelevant at `md` and
  // above where the panel is always shown via `md:translate-x-0`
  // regardless of either prop.
  open?: boolean;
  onClose?: () => void;
}

// Navigation is permission-aware, never the security boundary (spec
// Section 12.2/32) - every link below just reuses this codebase's
// existing UI-only `can*` hint functions, the same ones HomePage's own
// nav used before this task replaced it with this persistent sidebar.
export function Sidebar({ open = false, onClose }: SidebarProps = {}) {
  const { activeMembership } = useOrganization();
  if (!activeMembership) return null;

  return (
    <>
      {/* The backdrop only ever renders (and is only ever reachable by
          a screen reader or focus) while the panel is open on a narrow
          viewport - `md:hidden` keeps it inert at `md` and above, where
          the panel is static, not an overlay. */}
      {open && (
        <div
          className="fixed inset-0 z-40 bg-black/50 md:hidden"
          onClick={onClose}
          aria-hidden="true"
        />
      )}
      <nav
        aria-label="Primary"
        className={`fixed inset-y-0 left-0 z-50 flex w-56 flex-shrink-0 flex-col gap-1 overflow-y-auto bg-sidebar px-3 py-6 text-sidebar-foreground transition-transform duration-200 md:static md:z-auto md:translate-x-0 ${
          open ? "translate-x-0" : "-translate-x-full"
        }`}
      >
        {navItems(activeMembership.role).map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            end={item.to === "/"}
            onClick={onClose}
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
    </>
  );
}
