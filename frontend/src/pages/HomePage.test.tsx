import { render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, describe, expect, it, vi } from "vitest";
import { createMemoryRouter, RouterProvider } from "react-router-dom";

import * as analyticsApi from "@/api/analytics";
import * as authApi from "@/api/auth";
import * as organizationsApi from "@/api/organizations";
import { AuthProvider } from "@/contexts/AuthContext";
import { OrganizationProvider } from "@/contexts/OrganizationContext";
import { HomePage } from "@/pages/HomePage";
import type { UserPublic } from "@/types/user";

const USER: UserPublic = { id: "u1", name: "Ada", email: "ada@example.com", status: "active", created_at: "now" };

function renderHome() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const router = createMemoryRouter(
    [
      { path: "/", element: <HomePage /> },
      { path: "/organizations/new", element: <div>Create organization page</div> },
    ],
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

describe("HomePage", () => {
  afterEach(() => {
    vi.restoreAllMocks();
    sessionStorage.clear();
    localStorage.clear();
  });

  it("prompts a user with no organizations to create their first one", async () => {
    vi.spyOn(authApi, "getCurrentUser").mockResolvedValue(USER);
    vi.spyOn(organizationsApi, "listOrganizations").mockResolvedValue([]);

    renderHome();

    expect(await screen.findByText("You don't belong to an organization yet.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Create your first organization" })).toBeInTheDocument();
  });

  it("shows the active organization's name/role and dispatches to that role's own dashboard", async () => {
    vi.spyOn(authApi, "getCurrentUser").mockResolvedValue(USER);
    vi.spyOn(organizationsApi, "listOrganizations").mockResolvedValue([
      {
        organization: {
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
        },
        role: "owner",
        status: "active",
        joined_at: "now",
      },
    ]);
    vi.spyOn(analyticsApi, "getOverviewAnalytics").mockResolvedValue({
      period_start: "2026-01-01",
      period_end: "2026-01-31",
      employee_count: 1,
      active_tasks: 0,
      completed_tasks: 0,
      overdue_tasks: 0,
      open_requests: 0,
      monthly_invoiced: "0",
      monthly_collected: "0",
    });
    vi.spyOn(analyticsApi, "getEmployeeAnalytics").mockResolvedValue([]);

    renderHome();

    await waitFor(() => expect(screen.getByTestId("active-organization")).toHaveTextContent("Viewing Acme Inc as Owner"));
    // The dispatched OwnerDashboard's own section headings, proving
    // HomePage actually rendered RoleDashboard rather than stopping at
    // the header.
    expect(await screen.findByText("Business stats")).toBeInTheDocument();
    expect(screen.getByText("Financial overview (this month)")).toBeInTheDocument();
  });
});
