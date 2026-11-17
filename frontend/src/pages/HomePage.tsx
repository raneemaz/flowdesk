import { Link } from "react-router-dom";

import { Button } from "@/components/ui/button";
import { OrganizationSwitcher } from "@/components/OrganizationSwitcher";
import { useAuth } from "@/contexts/AuthContext";
import { useOrganization } from "@/contexts/OrganizationContext";
import { canManageCustomers } from "@/features/customers/permissions";
import { canManageDepartments } from "@/features/employees/permissions";
import { canManageInvoices } from "@/features/invoices/permissions";
import { canAccessRequests } from "@/features/requests/permissions";

const ROLE_LABELS: Record<string, string> = {
  owner: "Owner",
  manager: "Manager",
  employee: "Employee",
  accountant: "Accountant",
  customer_support: "Customer Support",
};

// Deliberately minimal - FD-018's scope is organization onboarding (the
// creation flow and the switcher), not the real dashboard (spec Section
// 12 - sidebar, role-specific stat cards, etc.), which lands incrementally
// as the domain modules behind it get built.
export function HomePage() {
  const { user, logout } = useAuth();
  const { isLoading, activeMembership } = useOrganization();

  return (
    <main className="flex min-h-screen flex-col items-center justify-center gap-4 bg-background text-foreground">
      <h1 className="text-2xl font-semibold">FlowDesk</h1>
      {user && <p className="text-sm text-foreground/70">Logged in as {user.name} ({user.email})</p>}

      {isLoading && <p className="text-sm text-foreground/70">Loading your organizations…</p>}

      {!isLoading && !activeMembership && (
        <div className="flex flex-col items-center gap-3 rounded-md border border-border bg-card p-6 text-center">
          <p className="text-sm text-foreground/70">You don&apos;t belong to an organization yet.</p>
          <Button asChild>
            <Link to="/organizations/new">Create your first organization</Link>
          </Button>
        </div>
      )}

      {!isLoading && activeMembership && (
        <div className="flex flex-col items-center gap-3">
          <OrganizationSwitcher />
          <p className="text-sm text-foreground/70" data-testid="active-organization">
            Viewing <span className="font-medium text-foreground">{activeMembership.organization.name}</span> as{" "}
            {ROLE_LABELS[activeMembership.role] ?? activeMembership.role}
          </p>
          <nav className="flex gap-4 text-sm font-medium text-primary">
            <Link to="/employees" className="hover:underline">
              Employees
            </Link>
            {canManageDepartments(activeMembership.role) && (
              <Link to="/departments" className="hover:underline">
                Departments
              </Link>
            )}
            <Link to="/tasks" className="hover:underline">
              Tasks
            </Link>
            {canManageCustomers(activeMembership.role) && (
              <Link to="/customers" className="hover:underline">
                Customers
              </Link>
            )}
            {canAccessRequests(activeMembership.role) && (
              <Link to="/requests" className="hover:underline">
                Requests
              </Link>
            )}
            {canManageInvoices(activeMembership.role) && (
              <Link to="/invoices" className="hover:underline">
                Invoices
              </Link>
            )}
          </nav>
        </div>
      )}

      <Button onClick={() => void logout()}>Log out</Button>
    </main>
  );
}
