import { render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router-dom";

import * as authApi from "@/api/auth";
import * as requestsApi from "@/api/customerRequests";
import * as employeesApi from "@/api/employees";
import { AuthProvider } from "@/contexts/AuthContext";
import { CustomerSupportDashboard } from "@/features/dashboard/CustomerSupportDashboard";
import type { CustomerRequestPublic } from "@/types/customerRequest";
import type { UserPublic } from "@/types/user";

const USER: UserPublic = { id: "u1", name: "Casey", email: "casey@example.com", status: "active", created_at: "now" };

const OPEN_REQUEST: CustomerRequestPublic = {
  id: "r1",
  organization_id: "org-1",
  customer_id: "c1",
  title: "Can't reset password",
  description: null,
  category: null,
  status: "new",
  priority: "medium",
  creator_membership_id: "m1",
  assignee_membership_id: null,
  due_date: null,
  resolution_notes: null,
  created_at: "now",
};

const MY_REQUEST: CustomerRequestPublic = { ...OPEN_REQUEST, id: "r2", title: "Billing question", assignee_membership_id: "m-casey", status: "assigned" };

function renderDashboard() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <MemoryRouter>
          <CustomerSupportDashboard organizationId="org-1" />
        </MemoryRouter>
      </AuthProvider>
    </QueryClientProvider>,
  );
}

describe("CustomerSupportDashboard", () => {
  afterEach(() => vi.restoreAllMocks());

  it("shows the open org-wide count, the queue preview, and this caller's own assignments", async () => {
    vi.spyOn(authApi, "getCurrentUser").mockResolvedValue(USER);
    vi.spyOn(employeesApi, "listEmployees").mockResolvedValue({
      employees: [{ membership_id: "m-casey", name: "Casey", role: "customer_support", status: "active", email: "casey@example.com" }],
      meta: { page: 1, per_page: 100, total: 1, total_pages: 1 },
    });
    vi.spyOn(requestsApi, "listRequests").mockImplementation(async (_organizationId, filters = {}) => {
      if (filters.perPage === 1) {
        const isMine = filters.assigneeMembershipId === "m-casey";
        const matches = isMine ? filters.status === "assigned" : filters.status === "new";
        return { requests: [], meta: { page: 1, per_page: 1, total: matches ? 1 : 0, total_pages: 1 } };
      }
      if (filters.assigneeMembershipId === "m-casey") {
        return { requests: [MY_REQUEST], meta: { page: 1, per_page: 5, total: 1, total_pages: 1 } };
      }
      return { requests: [OPEN_REQUEST, MY_REQUEST], meta: { page: 1, per_page: 10, total: 2, total_pages: 1 } };
    });

    renderDashboard();

    await waitFor(() => expect(screen.getByText("Open org-wide")).toBeInTheDocument());
    expect(await screen.findByRole("link", { name: "Can't reset password" })).toHaveAttribute("href", "/requests/r1");
    // "Billing question" is assigned to this caller and still open, so
    // it legitimately appears in both the org-wide queue preview and
    // "My assignments" below it, once each section has loaded - two
    // distinct links, same request.
    await waitFor(() => expect(screen.getAllByRole("link", { name: "Billing question" })).toHaveLength(2));
    for (const link of screen.getAllByRole("link", { name: "Billing question" })) {
      expect(link).toHaveAttribute("href", "/requests/r2");
    }
  });
});
