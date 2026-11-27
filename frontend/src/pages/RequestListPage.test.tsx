import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, describe, expect, it, vi } from "vitest";
import { createMemoryRouter, RouterProvider } from "react-router-dom";

import * as authApi from "@/api/auth";
import { ApiError } from "@/api/client";
import * as customersApi from "@/api/customers";
import * as customerRequestsApi from "@/api/customerRequests";
import * as employeesApi from "@/api/employees";
import * as organizationsApi from "@/api/organizations";
import { AuthProvider } from "@/contexts/AuthContext";
import { OrganizationProvider } from "@/contexts/OrganizationContext";
import { RequestListPage } from "@/pages/RequestListPage";
import type { CustomerRequestPublic } from "@/types/customerRequest";
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

const SAMPLE_REQUEST: CustomerRequestPublic = {
  id: "r1",
  organization_id: "org-1",
  customer_id: "c1",
  title: "Can't log in",
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

function membership(role: MembershipPublic["role"]): MembershipPublic {
  return { organization: ORG, role, status: "active", joined_at: "now" };
}

function renderPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const router = createMemoryRouter(
    [
      { path: "/requests", element: <RequestListPage /> },
      { path: "/requests/:requestId", element: <div>Request detail page</div> },
      { path: "/", element: <div>Home page</div> },
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
}

function mockAuthenticated(role: MembershipPublic["role"] = "owner") {
  vi.spyOn(authApi, "getCurrentUser").mockResolvedValue(USER);
  vi.spyOn(organizationsApi, "listOrganizations").mockResolvedValue([membership(role)]);
  sessionStorage.setItem("flowdesk:csrf_token", "csrf-abc");
}

describe("RequestListPage", () => {
  afterEach(() => {
    vi.restoreAllMocks();
    sessionStorage.clear();
    localStorage.clear();
  });

  it("lists requests for an owner", async () => {
    mockAuthenticated("owner");
    vi.spyOn(customerRequestsApi, "listRequests").mockResolvedValue({
      requests: [SAMPLE_REQUEST],
      meta: { page: 1, per_page: 20, total: 1, total_pages: 1 },
    });
    vi.spyOn(customersApi, "listCustomers").mockResolvedValue({
      customers: [],
      meta: { page: 1, per_page: 100, total: 0, total_pages: 0 },
    });
    vi.spyOn(employeesApi, "listEmployees").mockResolvedValue({
      employees: [],
      meta: { page: 1, per_page: 100, total: 0, total_pages: 0 },
    });

    renderPage();

    expect(await screen.findByText("Can't log in")).toBeInTheDocument();
  });

  it("shows a New request button only for a full-scope role, not an employee", async () => {
    mockAuthenticated("employee");
    vi.spyOn(customerRequestsApi, "listRequests").mockResolvedValue({
      requests: [],
      meta: { page: 1, per_page: 20, total: 0, total_pages: 0 },
    });

    renderPage();

    await waitFor(() => expect(screen.getByRole("heading", { name: "Requests" })).toBeInTheDocument());
    expect(screen.queryByRole("button", { name: "+ New request" })).not.toBeInTheDocument();
  });

  it("creates a request from the New request dialog", async () => {
    mockAuthenticated("owner");
    vi.spyOn(customerRequestsApi, "listRequests").mockResolvedValue({
      requests: [],
      meta: { page: 1, per_page: 20, total: 0, total_pages: 0 },
    });
    vi.spyOn(customersApi, "listCustomers").mockResolvedValue({
      customers: [{ id: "c1", organization_id: "org-1", name: "Jane Customer", email: null, phone: null, company: null, address: null, notes: null, status: "active", created_at: "now" }],
      meta: { page: 1, per_page: 100, total: 1, total_pages: 1 },
    });
    vi.spyOn(employeesApi, "listEmployees").mockResolvedValue({
      employees: [],
      meta: { page: 1, per_page: 100, total: 0, total_pages: 0 },
    });
    const createSpy = vi.spyOn(customerRequestsApi, "createRequest").mockResolvedValue({ ...SAMPLE_REQUEST, title: "New request" });
    const user = userEvent.setup();

    renderPage();
    await user.click(await screen.findByRole("button", { name: "+ New request" }));
    // The form opens in a dialog, on top of the filter bar (which has its
    // own "Customer" select) - so look inside the dialog.
    const dialog = await screen.findByRole("dialog");
    await user.selectOptions(within(dialog).getByLabelText("Customer"), "c1");
    await user.type(within(dialog).getByLabelText("Title"), "New request");
    await user.click(within(dialog).getByRole("button", { name: "Create request" }));

    await waitFor(() =>
      expect(createSpy).toHaveBeenCalledWith(
        "org-1",
        expect.objectContaining({ customer_id: "c1", title: "New request", priority: "medium" }),
        "csrf-abc",
      ),
    );
  });

  it("applies filters only after submitting", async () => {
    mockAuthenticated("owner");
    const listSpy = vi.spyOn(customerRequestsApi, "listRequests").mockResolvedValue({
      requests: [],
      meta: { page: 1, per_page: 20, total: 0, total_pages: 0 },
    });
    vi.spyOn(customersApi, "listCustomers").mockResolvedValue({
      customers: [],
      meta: { page: 1, per_page: 100, total: 0, total_pages: 0 },
    });
    vi.spyOn(employeesApi, "listEmployees").mockResolvedValue({
      employees: [],
      meta: { page: 1, per_page: 100, total: 0, total_pages: 0 },
    });
    const user = userEvent.setup();

    renderPage();
    await waitFor(() => expect(screen.getByRole("heading", { name: "Requests" })).toBeInTheDocument());

    await user.selectOptions(screen.getByLabelText("Status"), "In Progress");
    await user.click(screen.getByRole("button", { name: "Search" }));

    await waitFor(() => expect(listSpy).toHaveBeenCalledWith("org-1", expect.objectContaining({ status: "in_progress" })));
  });

  it("shows an error message when the list fails to load", async () => {
    mockAuthenticated("owner");
    vi.spyOn(customerRequestsApi, "listRequests").mockRejectedValue(new ApiError(404, "NOT_FOUND", "Not found.", {}));
    vi.spyOn(customersApi, "listCustomers").mockResolvedValue({
      customers: [],
      meta: { page: 1, per_page: 100, total: 0, total_pages: 0 },
    });
    vi.spyOn(employeesApi, "listEmployees").mockResolvedValue({
      employees: [],
      meta: { page: 1, per_page: 100, total: 0, total_pages: 0 },
    });

    renderPage();

    expect(await screen.findByRole("alert")).toHaveTextContent("Not found.");
  });
});
