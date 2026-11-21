// FD-063: see roleRestrictionEmployeeInvoices.test.tsx's header
// comment for why this uses a local createMemoryRouter mirroring
// router.tsx's real nesting, rather than the singleton router/<App/>.
import { render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, describe, expect, it, vi } from "vitest";
import { createMemoryRouter, RouterProvider } from "react-router-dom";

import * as authApi from "@/api/auth";
import { ApiError } from "@/api/client";
import * as customerRequestsApi from "@/api/customerRequests";
import * as customersApi from "@/api/customers";
import * as employeesApi from "@/api/employees";
import * as notificationsApi from "@/api/notifications";
import * as organizationsApi from "@/api/organizations";
import { DashboardLayout } from "@/components/DashboardLayout";
import { AuthProvider } from "@/contexts/AuthContext";
import { OrganizationProvider } from "@/contexts/OrganizationContext";
import { RequestListPage } from "@/pages/RequestListPage";
import { ProtectedRoute } from "@/routes/ProtectedRoute";
import type { OrganizationPublic } from "@/types/organization";
import type { UserPublic } from "@/types/user";

const USER: UserPublic = {
  id: "u1",
  name: "Amy Accountant",
  email: "amy@flowdesk-e2e.example.com",
  status: "active",
  created_at: "2026-01-01T00:00:00Z",
};

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
  created_at: "2026-01-01T00:00:00Z",
};

const EMPTY_PAGE_META = { page: 1, per_page: 20, total: 0, total_pages: 0 };
const FORBIDDEN = new ApiError(403, "FORBIDDEN", "You do not have permission to do this.", {});

afterEach(() => {
  vi.restoreAllMocks();
  sessionStorage.clear();
  localStorage.clear();
});

describe("role restrictions", () => {
  it("an Accountant hitting /requests directly (no sidebar link) sees the backend's 403, not a crash", async () => {
    vi.spyOn(authApi, "getCurrentUser").mockResolvedValue(USER);
    vi.spyOn(organizationsApi, "listOrganizations").mockResolvedValue([
      { organization: ORG, role: "accountant", status: "active", joined_at: "2026-01-01T00:00:00Z" },
    ]);
    vi.spyOn(notificationsApi, "listNotifications").mockResolvedValue({ notifications: [], meta: EMPTY_PAGE_META });
    vi.spyOn(customersApi, "listCustomers").mockResolvedValue({ customers: [], meta: EMPTY_PAGE_META });
    vi.spyOn(employeesApi, "listEmployees").mockResolvedValue({ employees: [], meta: EMPTY_PAGE_META });
    vi.spyOn(customerRequestsApi, "listRequests").mockRejectedValue(FORBIDDEN);

    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const router = createMemoryRouter(
      [
        {
          element: <ProtectedRoute />,
          children: [{ element: <DashboardLayout />, children: [{ path: "/requests", element: <RequestListPage /> }] }],
        },
      ],
      { initialEntries: ["/requests"] },
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

    await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent("You do not have permission to do this."));
  });
});
