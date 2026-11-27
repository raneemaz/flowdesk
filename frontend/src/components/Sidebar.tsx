import { useEffect, useState } from "react";
import { Link, NavLink } from "react-router-dom";
import {
  Activity,
  BarChart3,
  Building2,
  CheckSquare,
  Home,
  Inbox,
  PanelLeft,
  PanelLeftClose,
  Receipt,
  Settings,
  Sparkles,
  UserCircle,
  Users,
  type LucideIcon,
} from "lucide-react";

import { LogoMark } from "@/components/Logo";
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
  icon: LucideIcon;
}

// Collapsed state is a desktop-only, per-viewer convenience (like
// Claude's own sidebar toggle) - persisted in localStorage, never read
// back by the server or by Claude; irrelevant to the mobile off-canvas
// drawer, which always shows full labels when open.
const COLLAPSE_STORAGE_KEY = "flowdesk:sidebar_collapsed";

// Spec Section 12.2's own sidebar list is Overview, Employees,
// Departments, Tasks, Customers, Requests, Invoices, Analytics, AI
// Reports, Activity, Settings - all present now.
function navItems(role: MembershipRole): NavItem[] {
  const items: NavItem[] = [
    { to: "/", label: "Overview", icon: Home },
    { to: "/employees", label: "Employees", icon: Users },
  ];
  if (canManageDepartments(role)) items.push({ to: "/departments", label: "Departments", icon: Building2 });
  items.push({ to: "/tasks", label: "Tasks", icon: CheckSquare });
  if (canManageCustomers(role)) items.push({ to: "/customers", label: "Customers", icon: UserCircle });
  if (canAccessRequests(role)) items.push({ to: "/requests", label: "Requests", icon: Inbox });
  if (canManageInvoices(role)) items.push({ to: "/invoices", label: "Invoices", icon: Receipt });
  // Every active role reaches at least the employees sub-view of
  // Analytics (features/analytics/permissions.ts) - never conditional.
  items.push({ to: "/analytics", label: "Analytics", icon: BarChart3 });
  if (canViewAIReports(role)) items.push({ to: "/ai-reports", label: "AI Reports", icon: Sparkles });
  // Every role sees at least their own slice of the activity log, and
  // has at least "My account" in Settings.
  items.push({ to: "/activity", label: "Activity", icon: Activity });
  items.push({ to: "/settings", label: "Settings", icon: Settings });
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
  const [isCollapsed, setIsCollapsed] = useState(() => {
    try {
      return localStorage.getItem(COLLAPSE_STORAGE_KEY) === "true";
    } catch {
      return false;
    }
  });

  useEffect(() => {
    try {
      localStorage.setItem(COLLAPSE_STORAGE_KEY, String(isCollapsed));
    } catch {
      // Per-viewer convenience only - fine to silently no-op if storage
      // is blocked (private browsing, cleared site data, etc.).
    }
  }, [isCollapsed]);

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
        className={`fixed inset-y-0 left-0 z-50 flex w-56 flex-shrink-0 flex-col gap-1 overflow-y-auto bg-sidebar px-3 py-6 text-sidebar-foreground transition-transform duration-200 md:relative md:z-auto md:translate-x-0 ${
          open ? "translate-x-0" : "-translate-x-full"
        } ${isCollapsed ? "md:w-16" : ""}`}
      >
        <Link
          to="/"
          onClick={onClose}
          className={`mb-5 flex items-center gap-2.5 px-2 ${isCollapsed ? "md:justify-center md:px-0" : ""}`}
          aria-label="FlowDesk overview"
        >
          <LogoMark tone="dark" size={30} />
          <span
            className={`text-[1.3rem] font-bold leading-none tracking-[-0.03em] text-sidebar-foreground ${isCollapsed ? "md:sr-only" : ""}`}
          >
            FlowDesk
          </span>
        </Link>

        {navItems(activeMembership.role).map((item) => {
          const Icon = item.icon;
          return (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.to === "/"}
              onClick={onClose}
              title={item.label}
              // The active item is a filing tab pulled out of the blotter:
              // paper-colored and flush to the nav's right edge (-mr-3
              // cancels the nav's own px-3), so the current section reads
              // as opening straight into the page beside it.
              className={({ isActive }) =>
                `flex cursor-pointer items-center gap-3 px-3 py-2 text-sm font-medium transition-colors ${
                  isActive
                    ? "-mr-3 rounded-l-md bg-background text-foreground"
                    : "rounded-md text-sidebar-foreground/80 hover:bg-sidebar-accent hover:text-sidebar-foreground"
                } ${isCollapsed ? "md:justify-center" : ""}`
              }
            >
              <Icon className="h-4 w-4 flex-shrink-0" aria-hidden="true" />
              <span className={isCollapsed ? "md:sr-only" : ""}>{item.label}</span>
            </NavLink>
          );
        })}

        {/* Desktop-only - the mobile off-canvas drawer always shows
            full labels, so there's nothing to collapse there. */}
        <button
          type="button"
          onClick={() => setIsCollapsed((collapsed) => !collapsed)}
          aria-label={isCollapsed ? "Expand sidebar" : "Collapse sidebar"}
          title={isCollapsed ? "Expand sidebar" : "Collapse sidebar"}
          className={`mt-auto hidden cursor-pointer items-center gap-3 rounded-md px-3 py-2 text-sm font-medium text-sidebar-foreground/60 hover:bg-sidebar-accent hover:text-sidebar-foreground md:flex ${
            isCollapsed ? "md:justify-center" : ""
          }`}
        >
          {isCollapsed ? (
            <PanelLeft className="h-4 w-4 flex-shrink-0" aria-hidden="true" />
          ) : (
            <PanelLeftClose className="h-4 w-4 flex-shrink-0" aria-hidden="true" />
          )}
          <span className={isCollapsed ? "md:sr-only" : ""}>Collapse</span>
        </button>
      </nav>
    </>
  );
}
