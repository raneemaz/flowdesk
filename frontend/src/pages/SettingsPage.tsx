import { useSearchParams } from "react-router-dom";

import { useOrganization } from "@/contexts/OrganizationContext";
import { canInviteEmployees } from "@/features/employees/permissions";
import { AccountSettings } from "@/features/settings/AccountSettings";
import { MembersSettings } from "@/features/settings/MembersSettings";
import { OrganizationSettings } from "@/features/settings/OrganizationSettings";
import { cn } from "@/lib/utils";

type Section = "organization" | "members" | "account";

// Spec Section 12.2's sidebar "Settings". Sections a viewer can't use
// aren't shown (Members is Owner/Manager only); the backend enforces
// every rule regardless. The open section lives in the URL (?section=)
// so it survives a refresh and can be linked to.
export function SettingsPage() {
  const { activeMembership } = useOrganization();
  const [searchParams, setSearchParams] = useSearchParams();

  const role = activeMembership?.role;
  const sections: { id: Section; label: string }[] = [
    ...(activeMembership ? [{ id: "organization" as const, label: "Organization" }] : []),
    ...(role && canInviteEmployees(role) ? [{ id: "members" as const, label: "Members" }] : []),
    { id: "account", label: "My account" },
  ];
  const requested = searchParams.get("section") as Section | null;
  const current = sections.find((section) => section.id === requested)?.id ?? sections[0].id;

  return (
    <div className="px-4 py-6 sm:px-6 sm:py-8 lg:px-10">
      <div className="flex max-w-3xl flex-col gap-6">
        <h1 className="text-2xl font-semibold">Settings</h1>

        <nav className="flex gap-1 overflow-x-auto whitespace-nowrap border-b border-border [scrollbar-width:none]" aria-label="Settings sections">
          {sections.map((section) => (
            <button
              key={section.id}
              type="button"
              aria-current={current === section.id ? "page" : undefined}
              onClick={() => setSearchParams({ section: section.id }, { replace: true })}
              className={cn(
                "cursor-pointer border-b-2 px-2.5 py-2 text-sm font-medium sm:px-3",
                current === section.id
                  ? "border-primary text-primary"
                  : "border-transparent text-foreground/70 hover:text-foreground",
              )}
            >
              {section.label}
            </button>
          ))}
        </nav>

        {current === "organization" && activeMembership && (
          <OrganizationSettings organization={activeMembership.organization} role={activeMembership.role} />
        )}
        {current === "members" && activeMembership && (
          <MembersSettings organizationId={activeMembership.organization.id} viewerRole={activeMembership.role} />
        )}
        {current === "account" && <AccountSettings />}
      </div>
    </div>
  );
}
