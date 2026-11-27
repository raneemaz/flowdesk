import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, describe, expect, it, vi } from "vitest";
import { createMemoryRouter, RouterProvider } from "react-router-dom";

import * as activityApi from "@/api/activity";
import * as authApi from "@/api/auth";
import * as employeesApi from "@/api/employees";
import * as organizationsApi from "@/api/organizations";
import { AuthProvider } from "@/contexts/AuthContext";
import { OrganizationProvider } from "@/contexts/OrganizationContext";
import { ActivityPage } from "@/pages/ActivityPage";
import type { ActivityLogPublic } from "@/types/activity";
import type { OrganizationPublic } from "@/types/organization";
import type { UserPublic } from "@/types/user";

const USER: UserPublic = { id: "u1", name: "Ada", email: "ada@example.com", status: "active", created_at: "now" };
const ORG: OrganizationPublic = {
  id: "org-1",
  name: "Acme Inc",
  slug: "acme-inc",
  logo: null,
  email: null,
  phone: null,
  address: null,
  currency: "USD",
  timezone: "UTC",
  date_format: null,
  created_at: "now",
};

function entry(overrides: Partial<ActivityLogPublic>): ActivityLogPublic {
  return {
    id: crypto.randomUUID(),
    organization_id: "org-1",
    actor_membership_id: "m1",
    action: "task_created",
    entity_type: "task",
    entity_id: "t1",
    metadata: {},
    created_at: "2026-11-27T09:30:00Z",
    ...overrides,
  };
}

function renderPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const router = createMemoryRouter([{ path: "/activity", element: <ActivityPage /> }], { initialEntries: ["/activity"] });
  render(
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <OrganizationProvider>
          <RouterProvider router={router} />
        </OrganizationProvider>
      </AuthProvider>
    </QueryClientProvider>,
  );
}

describe("ActivityPage", () => {
  afterEach(() => vi.restoreAllMocks());

  it("describes entries in plain sentences with links to records that still exist", async () => {
    vi.spyOn(authApi, "getCurrentUser").mockResolvedValue(USER);
    vi.spyOn(organizationsApi, "listOrganizations").mockResolvedValue([
      { organization: ORG, role: "owner", status: "active", joined_at: "now" },
    ]);
    vi.spyOn(employeesApi, "listEmployees").mockResolvedValue({
      employees: [
        { membership_id: "m1", name: "Ada", role: "owner", status: "active" },
        { membership_id: "m2", name: "Bea", role: "employee", status: "active" },
      ],
      meta: { page: 1, per_page: 100, total: 2, total_pages: 1 },
    });
    vi.spyOn(activityApi, "listActivity").mockResolvedValue({
      entries: [
        entry({ action: "task_created", metadata: { title: "Payroll" } }),
        entry({ action: "task_deleted", entity_id: "t2", metadata: { title: "Old errand" } }),
        entry({ action: "member_role_changed", entity_type: "membership", entity_id: "m2", metadata: { from: "employee", to: "manager" } }),
        entry({ action: "organization_updated", entity_type: "organization", metadata: { fields: ["phone", "timezone"] } }),
        entry({ action: "something_new", actor_membership_id: "gone" }),
      ],
      meta: { page: 1, per_page: 20, total: 5, total_pages: 1 },
    });

    renderPage();

    expect(await screen.findByRole("link", { name: "Ada created task “Payroll”" })).toHaveAttribute("href", "/tasks/t1");
    // A deleted task has nothing to link to.
    expect(screen.getByText("Ada deleted task “Old errand”").closest("a")).toBeNull();
    expect(screen.getByText("Ada changed Bea’s role from Employee to Manager")).toBeInTheDocument();
    expect(screen.getByText("Ada updated the organization’s phone, timezone")).toBeInTheDocument();
    expect(screen.getByText("A former member: something new")).toBeInTheDocument();
  });

  it("pages through older entries", async () => {
    vi.spyOn(authApi, "getCurrentUser").mockResolvedValue(USER);
    vi.spyOn(organizationsApi, "listOrganizations").mockResolvedValue([
      { organization: ORG, role: "employee", status: "active", joined_at: "now" },
    ]);
    vi.spyOn(employeesApi, "listEmployees").mockResolvedValue({ employees: [], meta: { page: 1, per_page: 100, total: 0, total_pages: 0 } });
    const listSpy = vi.spyOn(activityApi, "listActivity").mockResolvedValue({
      entries: [entry({ metadata: { title: "Payroll" } })],
      meta: { page: 1, per_page: 20, total: 30, total_pages: 2 },
    });
    const user = userEvent.setup();

    renderPage();
    await user.click(await screen.findByRole("button", { name: "Older" }));

    expect(listSpy).toHaveBeenLastCalledWith("org-1", 2, 20);
  });
});
