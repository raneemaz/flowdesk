import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { Bell, LogOut, Menu } from "lucide-react";

import { listNotifications } from "@/api/notifications";
import { Button } from "@/components/ui/button";
import { OrganizationSwitcher } from "@/components/OrganizationSwitcher";
import { useAuth } from "@/contexts/AuthContext";
import { useOrganization } from "@/contexts/OrganizationContext";

const ROLE_LABELS: Record<string, string> = {
  owner: "Owner",
  manager: "Manager",
  employee: "Employee",
  accountant: "Accountant",
  customer_support: "Customer Support",
};

// Spec Section 12.2's top bar is "search, notifications, current
// organization switcher, user profile, theme selector". Search and
// the theme selector are deliberately not built here: there is no
// backend endpoint for a cross-entity search (each list page already
// has its own `search` filter - docs/API.md), and this frontend's own
// index.css documents dark theme as explicitly optional and not yet
// implemented (spec Section 12.1) - a toggle with nothing to toggle
// would be exactly the placeholder UI this project's rules forbid.
// Both are documented gaps, not oversights.
interface TopBarProps {
  // FD-063 (NFR-011): present only on the dashboard shell, which is
  // the one place a mobile nav toggle makes sense - omitted (and so
  // never rendered, via the `md:hidden` button below) by any caller
  // that doesn't need it, same convention `activeMembership &&` above
  // already uses for conditionally-relevant TopBar content.
  onMenuClick?: () => void;
}

export function TopBar({ onMenuClick }: TopBarProps = {}) {
  const { user, logout } = useAuth();
  const { activeMembership } = useOrganization();
  const organizationId = activeMembership?.organization.id ?? "";

  // Same minimal per_page:1-plus-meta.total convention HomePage's own
  // badge used before this task moved it here.
  const { data: unreadCountData } = useQuery({
    queryKey: ["notifications-unread-count", organizationId],
    queryFn: () => listNotifications(organizationId, { unreadOnly: true, page: 1, perPage: 1 }),
    enabled: Boolean(organizationId),
  });
  const unreadCount = unreadCountData?.meta.total ?? 0;

  // One row at every width: on phones the org picker takes the free space
  // and Notifications / Log out become icons (their accessible names stay
  // the same); the user's name shows from md up.
  return (
    <header className="flex items-center gap-2 border-b border-border bg-background px-3 py-2.5 sm:gap-3 md:gap-4 md:px-6 md:py-3">
      {onMenuClick && (
        <button
          type="button"
          aria-label="Open navigation menu"
          className="inline-flex h-9 w-9 shrink-0 cursor-pointer items-center justify-center rounded-md border border-border md:hidden"
          onClick={onMenuClick}
        >
          <Menu className="h-4 w-4" aria-hidden="true" />
        </button>
      )}
      <div className="min-w-0 flex-1">{activeMembership && <OrganizationSwitcher />}</div>
      <div className="flex shrink-0 items-center gap-1.5 sm:gap-3 md:gap-4">
        {activeMembership && (
          <Link
            to="/notifications"
            className="relative inline-flex h-9 min-w-9 items-center justify-center gap-1.5 rounded-md text-sm font-medium text-primary hover:underline max-sm:border max-sm:border-border"
          >
            <Bell className="h-4 w-4 sm:hidden" aria-hidden="true" />
            <span className="sr-only sm:not-sr-only">Notifications{unreadCount > 0 ? ` (${unreadCount})` : ""}</span>
            {unreadCount > 0 && (
              <span
                aria-hidden="true"
                className="absolute -right-1.5 -top-1.5 flex h-5 min-w-5 items-center justify-center rounded-full bg-primary px-1 text-[11px] font-semibold text-primary-foreground sm:hidden"
              >
                {unreadCount}
              </span>
            )}
          </Link>
        )}
        {user && (
          <p className="hidden text-sm text-foreground/70 md:block" data-testid="topbar-user">
            {user.name}
            {activeMembership && ` · ${ROLE_LABELS[activeMembership.role] ?? activeMembership.role}`}
          </p>
        )}
        <Button type="button" size="sm" variant="outline" className="max-sm:w-9 max-sm:px-0" onClick={() => void logout()}>
          <LogOut className="h-4 w-4 sm:hidden" aria-hidden="true" />
          <span className="sr-only sm:not-sr-only">Log out</span>
        </Button>
      </div>
    </header>
  );
}
