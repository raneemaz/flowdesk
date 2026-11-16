import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, describe, expect, it, vi } from "vitest";
import { createMemoryRouter, RouterProvider } from "react-router-dom";

import * as authApi from "@/api/auth";
import { ApiError } from "@/api/client";
import * as customersApi from "@/api/customers";
import * as organizationsApi from "@/api/organizations";
import { AuthProvider } from "@/contexts/AuthContext";
import { OrganizationProvider } from "@/contexts/OrganizationContext";
import { CustomerListPage } from "@/pages/CustomerListPage";
import type { CustomerPublic } from "@/types/customer";
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

const SAMPLE_CUSTOMER: CustomerPublic = {
  id: "c1",
  organization_id: "org-1",
  name: "Jane Customer",
  email: "jane@example.com",
  phone: null,
  company: null,
  address: null,
  notes: null,
  status: "active",
  created_at: "now",
};

function membership(role: MembershipPublic["role"]): MembershipPublic {
  return { organization: ORG, role, status: "active", joined_at: "now" };
}

function renderPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const router = createMemoryRouter(
    [
      { path: "/customers", element: <CustomerListPage /> },
      { path: "/customers/:customerId", element: <div>Customer detail page</div> },
      { path: "/", element: <div>Home page</div> },
    ],
    { initialEntries: ["/customers"] },
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

function mockAuthenticated(role: MembershipPublic["role"] = "owner") {
  vi.spyOn(authApi, "getCurrentUser").mockResolvedValue(USER);
  vi.spyOn(organizationsApi, "listOrganizations").mockResolvedValue([membership(role)]);
  sessionStorage.setItem("flowdesk:csrf_token", "csrf-abc");
}

describe("CustomerListPage", () => {
  afterEach(() => {
    vi.restoreAllMocks();
    sessionStorage.clear();
    localStorage.clear();
  });

  it("lists customers for an owner", async () => {
    mockAuthenticated("owner");
    vi.spyOn(customersApi, "listCustomers").mockResolvedValue({
      customers: [SAMPLE_CUSTOMER],
      meta: { page: 1, per_page: 20, total: 1, total_pages: 1 },
    });

    renderPage();

    expect(await screen.findByText("Jane Customer")).toBeInTheDocument();
  });

  it("creates a customer via the inline form", async () => {
    mockAuthenticated("owner");
    vi.spyOn(customersApi, "listCustomers").mockResolvedValue({
      customers: [],
      meta: { page: 1, per_page: 20, total: 0, total_pages: 0 },
    });
    const createSpy = vi.spyOn(customersApi, "createCustomer").mockResolvedValue({ ...SAMPLE_CUSTOMER, name: "New Customer" });
    const user = userEvent.setup();

    renderPage();
    await user.click(await screen.findByRole("button", { name: "+ New customer" }));
    await user.type(screen.getByLabelText("Name"), "New Customer");
    await user.click(screen.getByRole("button", { name: "Create customer" }));

    await waitFor(() =>
      expect(createSpy).toHaveBeenCalledWith("org-1", expect.objectContaining({ name: "New Customer" }), "csrf-abc"),
    );
  });

  it("applies filters only after submitting", async () => {
    mockAuthenticated("owner");
    const listSpy = vi.spyOn(customersApi, "listCustomers").mockResolvedValue({
      customers: [],
      meta: { page: 1, per_page: 20, total: 0, total_pages: 0 },
    });
    const user = userEvent.setup();

    renderPage();
    await waitFor(() => expect(screen.getByRole("heading", { name: "Customers" })).toBeInTheDocument());

    await user.selectOptions(screen.getByLabelText("Status"), "Archived");
    await user.click(screen.getByRole("button", { name: "Search" }));

    await waitFor(() => expect(listSpy).toHaveBeenCalledWith("org-1", expect.objectContaining({ status: "archived" })));
  });

  it("shows an error message when the list fails to load", async () => {
    mockAuthenticated("owner");
    vi.spyOn(customersApi, "listCustomers").mockRejectedValue(new ApiError(404, "NOT_FOUND", "Not found.", {}));

    renderPage();

    expect(await screen.findByRole("alert")).toHaveTextContent("Not found.");
  });
});
