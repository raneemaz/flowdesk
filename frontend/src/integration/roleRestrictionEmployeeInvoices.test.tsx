// FD-063: "hiding a button is never the real security boundary" (spec
// Section 7.3/32, repeated in nearly every features/*/permissions.ts
// file in this codebase) is already asserted as a comment everywhere
// it applies - this is the one test that actually PROVES it, for the
// one case Sidebar.test.tsx's own thorough per-role nav-visibility
// coverage can't: a role with no sidebar link for a page still reaches
// it by direct URL (a bookmark, a shared link, typing the address bar)
// and the page must surface the backend's real 403, not crash or
// silently show someone else's data.
//
// Uses a local createMemoryRouter (same convention every other test
// file in this codebase already uses, e.g. Sidebar.test.tsx/
// LoginPage.test.tsx) rather than the real singleton router/<App/> -
// that singleton (src/routes/router.tsx) wraps the real browser
// History API, which has no supported way to set an arbitrary
// *initial* location from outside it; createMemoryRouter's own
// `initialEntries` is built for exactly this. The route SHAPE below
// (ProtectedRoute -> DashboardLayout -> the page) mirrors router.tsx's
// real nesting exactly, so this still exercises the real multi-module
// wiring (auth -> org context -> layout/sidebar -> page), just not
// through the literal singleton object.
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, describe, expect, it, vi } from "vitest";
import { createMemoryRouter, RouterProvider } from "react-router-dom";

import * as authApi from "@/api/auth";
import { ApiError } from "@/api/client";
import * as customersApi from "@/api/customers";
import * as invoicesApi from "@/api/invoices";
import * as notificationsApi from "@/api/notifications";
import * as organizationsApi from "@/api/organizations";
import { DashboardLayout } from "@/components/DashboardLayout";
import { AuthProvider } from "@/contexts/AuthContext";
import { OrganizationProvider } from "@/contexts/OrganizationContext";
import { InvoiceListPage } from "@/pages/InvoiceListPage";
import { ProtectedRoute } from "@/routes/ProtectedRoute";
import type { OrganizationPublic } from "@/types/organization";
import type { UserPublic } from "@/types/user";

const USER: UserPublic = {
  id: "u1",
  name: "Evan Employee",
  email: "evan@flowdesk-e2e.example.com",
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
  it("an Employee hitting /invoices directly (no sidebar link) sees the backend's 403, not a crash", async () => {
    vi.spyOn(authApi, "getCurrentUser").mockResolvedValue(USER);
    vi.spyOn(organizationsApi, "listOrganizations").mockResolvedValue([
      { organization: ORG, role: "employee", status: "active", joined_at: "2026-01-01T00:00:00Z" },
    ]);
    vi.spyOn(notificationsApi, "listNotifications").mockResolvedValue({ notifications: [], meta: EMPTY_PAGE_META });
    vi.spyOn(customersApi, "listCustomers").mockResolvedValue({ customers: [], meta: EMPTY_PAGE_META });
    vi.spyOn(invoicesApi, "listInvoices").mockRejectedValue(FORBIDDEN);
    vi.spyOn(invoicesApi, "getFinancialSummary").mockRejectedValue(FORBIDDEN);

    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const router = createMemoryRouter(
      [
        {
          element: <ProtectedRoute />,
          children: [{ element: <DashboardLayout />, children: [{ path: "/invoices", element: <InvoiceListPage /> }] }],
        },
      ],
      { initialEntries: ["/invoices"] },
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

    expect(await screen.findByRole("alert")).toHaveTextContent("You do not have permission to do this.");
    // Never silently shows an empty/successful-looking list instead.
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
  });
});
