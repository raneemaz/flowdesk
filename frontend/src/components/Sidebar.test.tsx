import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router-dom";

import * as authApi from "@/api/auth";
import * as organizationsApi from "@/api/organizations";
import { Sidebar } from "@/components/Sidebar";
import { AuthProvider } from "@/contexts/AuthContext";
import { OrganizationProvider } from "@/contexts/OrganizationContext";
import type { MembershipPublic, OrganizationPublic } from "@/types/organization";
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

function membership(role: MembershipPublic["role"]): MembershipPublic {
  return { organization: ORG, role, status: "active", joined_at: "now" };
}

function renderSidebar(role: MembershipPublic["role"]) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  vi.spyOn(authApi, "getCurrentUser").mockResolvedValue(USER);
  vi.spyOn(organizationsApi, "listOrganizations").mockResolvedValue([membership(role)]);

  render(
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <OrganizationProvider>
          <MemoryRouter>
            <Sidebar />
          </MemoryRouter>
        </OrganizationProvider>
      </AuthProvider>
    </QueryClientProvider>,
  );
}

describe("Sidebar", () => {
  afterEach(() => {
    vi.restoreAllMocks();
    sessionStorage.clear();
    localStorage.clear();
  });

  it("shows every link to an Owner", async () => {
    renderSidebar("owner");

    expect(await screen.findByRole("link", { name: "Overview" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Employees" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Departments" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Tasks" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Customers" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Requests" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Invoices" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Analytics" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "AI Reports" })).toBeInTheDocument();
  });

  it("hides Departments, Customers, Invoices, AI Reports from an Employee but still shows Analytics", async () => {
    renderSidebar("employee");

    expect(await screen.findByRole("link", { name: "Overview" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Employees" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Tasks" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Analytics" })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Departments" })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Customers" })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Invoices" })).not.toBeInTheDocument();
    // AI Reports (FD-060) is full-scope only (Owner/Manager) - same
    // features/aiReports/permissions.ts gate the backend itself
    // enforces.
    expect(screen.queryByRole("link", { name: "AI Reports" })).not.toBeInTheDocument();
    // Employee's CUSTOMER_REQUEST_MANAGE is `assigned`, not `none` - so
    // Requests is still reachable (features/requests/permissions.ts's
    // canAccessRequests), unlike Customers/Invoices/Departments.
    expect(screen.getByRole("link", { name: "Requests" })).toBeInTheDocument();
  });

  it("hides Requests and Invoices from an Accountant", async () => {
    renderSidebar("accountant");

    expect(await screen.findByRole("link", { name: "Invoices" })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Requests" })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Departments" })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "AI Reports" })).not.toBeInTheDocument();
  });

  it("renders nothing without an active organization", () => {
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    vi.spyOn(authApi, "getCurrentUser").mockResolvedValue(USER);
    vi.spyOn(organizationsApi, "listOrganizations").mockResolvedValue([]);

    const { container } = render(
      <QueryClientProvider client={queryClient}>
        <AuthProvider>
          <OrganizationProvider>
            <MemoryRouter>
              <Sidebar />
            </MemoryRouter>
          </OrganizationProvider>
        </AuthProvider>
      </QueryClientProvider>,
    );

    expect(container).toBeEmptyDOMElement();
  });
});
