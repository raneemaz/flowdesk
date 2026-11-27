import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, describe, expect, it, vi } from "vitest";
import { createMemoryRouter, RouterProvider } from "react-router-dom";

import * as authApi from "@/api/auth";
import { ApiError } from "@/api/client";
import * as customersApi from "@/api/customers";
import * as customerRequestsApi from "@/api/customerRequests";
import * as organizationsApi from "@/api/organizations";
import { AuthProvider } from "@/contexts/AuthContext";
import { OrganizationProvider } from "@/contexts/OrganizationContext";
import { CustomerDetailPage } from "@/pages/CustomerDetailPage";
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
  phone: "555-1234",
  company: "Jane's Bakery",
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
      { path: "/customers/:customerId", element: <CustomerDetailPage /> },
      { path: "/customers", element: <div>Directory page</div> },
    ],
    { initialEntries: ["/customers/c1"] },
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

describe("CustomerDetailPage", () => {
  afterEach(() => {
    vi.restoreAllMocks();
    sessionStorage.clear();
    localStorage.clear();
  });

  it("shows the customer's details and linked requests", async () => {
    mockAuthenticated("owner");
    vi.spyOn(customersApi, "getCustomer").mockResolvedValue(SAMPLE_CUSTOMER);
    vi.spyOn(customerRequestsApi, "listRequests").mockResolvedValue({
      requests: [],
      meta: { page: 1, per_page: 50, total: 0, total_pages: 0 },
    });

    renderPage();

    expect(await screen.findByRole("heading", { name: "Jane Customer" })).toBeInTheDocument();
    expect(screen.getByText("jane@example.com")).toBeInTheDocument();
    expect(screen.getByText("Jane's Bakery")).toBeInTheDocument();
  });

  it("edits the customer via the inline form", async () => {
    mockAuthenticated("owner");
    vi.spyOn(customersApi, "getCustomer").mockResolvedValue(SAMPLE_CUSTOMER);
    vi.spyOn(customerRequestsApi, "listRequests").mockResolvedValue({
      requests: [],
      meta: { page: 1, per_page: 50, total: 0, total_pages: 0 },
    });
    const updateSpy = vi.spyOn(customersApi, "updateCustomer").mockResolvedValue({ ...SAMPLE_CUSTOMER, company: "New Co" });
    const user = userEvent.setup();

    renderPage();
    await user.click(await screen.findByRole("button", { name: "Edit customer" }));
    const companyInput = screen.getByLabelText("Company");
    await user.clear(companyInput);
    await user.type(companyInput, "New Co");
    await user.click(screen.getByRole("button", { name: "Save changes" }));

    await waitFor(() =>
      expect(updateSpy).toHaveBeenCalledWith("org-1", "c1", expect.objectContaining({ company: "New Co" }), "csrf-abc"),
    );
  });

  it("archives the customer after confirmation", async () => {
    mockAuthenticated("owner");
    vi.spyOn(customersApi, "getCustomer").mockResolvedValue(SAMPLE_CUSTOMER);
    vi.spyOn(customerRequestsApi, "listRequests").mockResolvedValue({
      requests: [],
      meta: { page: 1, per_page: 50, total: 0, total_pages: 0 },
    });
    const archiveSpy = vi.spyOn(customersApi, "archiveCustomer").mockResolvedValue({ ...SAMPLE_CUSTOMER, status: "archived" });
    const user = userEvent.setup();

    renderPage();
    await user.click(await screen.findByRole("button", { name: "Archive" }));
    expect(archiveSpy).not.toHaveBeenCalled();
    await user.click(await screen.findByRole("button", { name: "Archive customer" }));

    await waitFor(() => expect(archiveSpy).toHaveBeenCalledWith("org-1", "c1", "csrf-abc"));
  });

  it("does not fetch requests for an accountant (no CUSTOMER_REQUEST_MANAGE reach)", async () => {
    mockAuthenticated("accountant");
    vi.spyOn(customersApi, "getCustomer").mockResolvedValue(SAMPLE_CUSTOMER);
    const listRequestsSpy = vi.spyOn(customerRequestsApi, "listRequests");

    renderPage();

    await screen.findByRole("heading", { name: "Jane Customer" });
    expect(listRequestsSpy).not.toHaveBeenCalled();
  });

  it("shows an error message when the customer fails to load", async () => {
    mockAuthenticated("owner");
    vi.spyOn(customersApi, "getCustomer").mockRejectedValue(new ApiError(404, "NOT_FOUND", "Not found.", {}));

    renderPage();

    expect(await screen.findByRole("alert")).toHaveTextContent("Not found.");
  });
});
