import { Link } from "react-router-dom";

import { Select } from "@/components/ui/select";
import { Label } from "@/components/ui/label";
import { useOrganization } from "@/contexts/OrganizationContext";

const ROLE_LABELS: Record<string, string> = {
  owner: "Owner",
  manager: "Manager",
  employee: "Employee",
  accountant: "Accountant",
  customer_support: "Customer Support",
};

// Only active memberships are offered here (OrganizationContext's
// usableMemberships) - an inactive/suspended one carries no capabilities
// server-side, so switching into it would just produce 403s everywhere.
export function OrganizationSwitcher() {
  const { memberships, activeMembership, switchOrganization } = useOrganization();
  const activeMemberships = memberships.filter((m) => m.status === "active");

  if (!activeMembership) return null;

  return (
    <div className="flex items-center gap-3">
      <div className="flex flex-col gap-1">
        <Label htmlFor="organization-switcher" className="sr-only">
          Current organization
        </Label>
        <Select
          id="organization-switcher"
          value={activeMembership.organization.id}
          onChange={(event) => switchOrganization(event.target.value)}
          className="h-9"
        >
          {activeMemberships.map((membership) => (
            <option key={membership.organization.id} value={membership.organization.id}>
              {membership.organization.name} ({ROLE_LABELS[membership.role] ?? membership.role})
            </option>
          ))}
        </Select>
      </div>
      <Link to="/organizations/new" className="text-sm font-medium text-primary hover:underline">
        + New organization
      </Link>
    </div>
  );
}
