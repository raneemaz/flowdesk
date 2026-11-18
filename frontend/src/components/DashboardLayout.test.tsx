import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider, useQuery } from "@tanstack/react-query";
import { afterEach, describe, expect, it, vi } from "vitest";
import { createMemoryRouter, RouterProvider } from "react-router-dom";

import * as authApi from "@/api/auth";
import { listEmployees } from "@/api/employees";
import * as organizationsApi from "@/api/organizations";
import { DashboardLayout } from "@/components/DashboardLayout";
import { useOrganization } from "@/contexts/OrganizationContext";
import { AuthProvider } from "@/contexts/AuthContext";
import { OrganizationProvider } from "@/contexts/OrganizationContext";
import type { MembershipPublic, OrganizationPublic } from "@/types/organization";
import type { UserPublic } from "@/types/user";

vi.mock("@/api/employees", () => ({ listEmployees: vi.fn() }));

const USER: UserPublic = { id: "u1", name: "Ada", email: "ada@example.com", status: "active", created_at: "now" };

function org(id: string, name: string): OrganizationPublic {
  return {
    id,
    name,
    slug: id,
    logo: null,
    email: null,
    phone: null,
    address: null,
    currency: "USD",
    timezone: "UTC",
    date_format: null,
    created_at: "now",
  };
}

const ORG_A = org("org-a", "Org A");
const ORG_B = org("org-b", "Org B");
const MEMBERSHIPS: MembershipPublic[] = [
  { organization: ORG_A, role: "owner", status: "active", joined_at: "now" },
  { organization: ORG_B, role: "owner", status: "active", joined_at: "now" },
];

// A minimal stand-in for a real org-scoped page (every real one of
// which already keys its own queries by organizationId - this just
// proves the shell lets a switch propagate down to one).
function FakeOrgScopedPage() {
  const { activeMembership } = useOrganization();
  const organizationId = activeMembership?.organization.id ?? "";
  const { data } = useQuery({
    queryKey: ["fake-page", organizationId],
    queryFn: () => listEmployees(organizationId),
    enabled: Boolean(organizationId),
  });
  return <p data-testid="fake-page-data">{data?.employees.map((e) => e.name).join(", ") ?? "loading"}</p>;
}

function renderShell() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const router = createMemoryRouter(
    [{ element: <DashboardLayout />, children: [{ path: "/", element: <FakeOrgScopedPage /> }] }],
    { initialEntries: ["/"] },
  );

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

describe("DashboardLayout", () => {
  afterEach(() => {
    vi.restoreAllMocks();
    sessionStorage.clear();
    localStorage.clear();
  });

  it("switching organizations clears the previous organization's data from a wrapped page", async () => {
    vi.spyOn(authApi, "getCurrentUser").mockResolvedValue(USER);
    vi.spyOn(organizationsApi, "listOrganizations").mockResolvedValue(MEMBERSHIPS);
    vi.mocked(listEmployees).mockImplementation(async (organizationId: string) => {
      const name = organizationId === "org-a" ? "Alice (Org A)" : "Bob (Org B)";
      return { employees: [{ membership_id: "m1", name, role: "owner", status: "active" }], meta: { page: 1, per_page: 20, total: 1, total_pages: 1 } };
    });

    renderShell();
    const user = userEvent.setup();

    await waitFor(() => expect(screen.getByTestId("fake-page-data")).toHaveTextContent("Alice (Org A)"));
    expect(screen.getByTestId("fake-page-data")).not.toHaveTextContent("Bob (Org B)");

    await user.selectOptions(screen.getByLabelText("Current organization"), "org-b");

    await waitFor(() => expect(screen.getByTestId("fake-page-data")).toHaveTextContent("Bob (Org B)"));
    expect(screen.getByTestId("fake-page-data")).not.toHaveTextContent("Alice (Org A)");
  });
});
