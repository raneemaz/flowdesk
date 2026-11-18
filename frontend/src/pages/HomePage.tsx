import { Link } from "react-router-dom";

import { Button } from "@/components/ui/button";
import { useAuth } from "@/contexts/AuthContext";
import { useOrganization } from "@/contexts/OrganizationContext";
import { RoleDashboard } from "@/features/dashboard/RoleDashboard";

const ROLE_LABELS: Record<string, string> = {
  owner: "Owner",
  manager: "Manager",
  employee: "Employee",
  accountant: "Accountant",
  customer_support: "Customer Support",
};

// FD-053: the real Overview dashboard (spec Section 12.3), replacing
// this page's own former minimal nav - that nav, and the org
// switcher/notifications it carried, now live in the persistent
// shell (components/Sidebar.tsx/components/TopBar.tsx), which wraps
// every protected page including this one. Only the "no organization
// yet" prompt (FD-018's own scope) and the per-role widget set
// (RoleDashboard) are this page's job now.
export function HomePage() {
  const { user } = useAuth();
  const { isLoading, activeMembership } = useOrganization();
  const organizationId = activeMembership?.organization.id ?? "";

  return (
    <div className="mx-auto flex max-w-5xl flex-col gap-6 px-4 py-8 text-foreground">
      {isLoading && <p className="text-sm text-foreground/70">Loading your organizations…</p>}

      {!isLoading && !activeMembership && (
        <div className="flex flex-col items-center gap-3 rounded-md border border-border bg-card p-6 text-center">
          {user && <p className="text-sm text-foreground/70">Logged in as {user.name} ({user.email})</p>}
          <p className="text-sm text-foreground/70">You don&apos;t belong to an organization yet.</p>
          <Button asChild>
            <Link to="/organizations/new">Create your first organization</Link>
          </Button>
        </div>
      )}

      {!isLoading && activeMembership && (
        <>
          <div>
            <h1 className="text-2xl font-semibold">Overview</h1>
            <p className="text-sm text-foreground/70" data-testid="active-organization">
              Viewing <span className="font-medium text-foreground">{activeMembership.organization.name}</span> as{" "}
              {ROLE_LABELS[activeMembership.role] ?? activeMembership.role}
            </p>
          </div>
          <RoleDashboard role={activeMembership.role} organizationId={organizationId} />
        </>
      )}
    </div>
  );
}
