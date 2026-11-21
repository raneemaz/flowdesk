import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";

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

  return (
    <header className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2 border-b border-border bg-card px-4 py-3 md:flex-nowrap md:px-6">
      <div className="flex items-center gap-3">
        {onMenuClick && (
          <button
            type="button"
            aria-label="Open navigation menu"
            className="rounded-md border border-border px-2 py-1.5 text-sm md:hidden"
            onClick={onMenuClick}
          >
            ☰
          </button>
        )}
        {activeMembership && <OrganizationSwitcher />}
      </div>
      <div className="flex flex-wrap items-center justify-end gap-x-4 gap-y-2">
        {activeMembership && (
          <Link to="/notifications" className="text-sm font-medium text-primary hover:underline">
            Notifications{unreadCount > 0 ? ` (${unreadCount})` : ""}
          </Link>
        )}
        {user && (
          <p className="text-sm text-foreground/70" data-testid="topbar-user">
            {user.name}
            {activeMembership && ` · ${ROLE_LABELS[activeMembership.role] ?? activeMembership.role}`}
          </p>
        )}
        <Button type="button" size="sm" variant="outline" onClick={() => void logout()}>
          Log out
        </Button>
      </div>
    </header>
  );
}
