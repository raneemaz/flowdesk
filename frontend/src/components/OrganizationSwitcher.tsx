import { Link } from "react-router-dom";
import { Plus } from "lucide-react";

import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { useOrganization } from "@/contexts/OrganizationContext";

const ROLE_LABELS: Record<string, string> = {
  owner: "Owner",
  manager: "Manager",
  employee: "Employee",
  accountant: "Accountant",
  customer_support: "Customer Support",
};

// The org picker takes whatever width the top bar has left (it truncates
// rather than wrapping); "New organization" is a + icon on phones and a
// text link from md up, with the same accessible name either way.
export function OrganizationSwitcher() {
  const { memberships, activeMembership, switchOrganization } = useOrganization();
  const activeMemberships = memberships.filter((m) => m.status === "active");

  if (!activeMembership) return null;

  return (
    <div className="flex min-w-0 items-center gap-2 md:gap-3">
      <div className="min-w-0 flex-1 md:w-72 md:flex-none">
        <Label htmlFor="organization-switcher" className="sr-only">
          Current organization
        </Label>
        <Select
          id="organization-switcher"
          value={activeMembership.organization.id}
          onChange={(event) => switchOrganization(event.target.value)}
          className="h-9 truncate"
        >
          {activeMemberships.map((membership) => (
            <option key={membership.organization.id} value={membership.organization.id}>
              {membership.organization.name} ({ROLE_LABELS[membership.role] ?? membership.role})
            </option>
          ))}
        </Select>
      </div>
      <Link
        to="/organizations/new"
        title="New organization"
        className="inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-md border border-border text-primary hover:bg-card md:h-auto md:w-auto md:border-0 md:text-sm md:font-medium md:hover:bg-transparent md:hover:underline"
      >
        <Plus className="h-4 w-4 md:hidden" aria-hidden="true" />
        <span className="sr-only md:not-sr-only">+ New organization</span>
      </Link>
    </div>
  );
}
