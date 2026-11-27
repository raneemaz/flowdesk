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
import { RequestDetailPage } from "@/pages/RequestDetailPage";
import type { CustomerPublic } from "@/types/customer";
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
  description: "Customer locked out",
  category: "technical",
  status: "new",
  priority: "medium",
  creator_membership_id: "m1",
  assignee_membership_id: null,
  due_date: null,
  resolution_notes: null,
  created_at: "now",
};

const SAMPLE_CUSTOMER: CustomerPublic = {
  id: "c1",
  organization_id: "org-1",
  name: "Jane Customer",
  email: null,
  phone: null,
  company: null,
  address: null,
  notes: null,
  status: "active",
  created_at: "now",
};

function membership(role: MembershipPublic["role"]): MembershipPublic {
  return { membership_id: "m1", organization: ORG, role, status: "active", joined_at: "now" };
}

function renderPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const router = createMemoryRouter(
    [
      { path: "/requests/:requestId", element: <RequestDetailPage /> },
      { path: "/requests", element: <div>Queue page</div> },
      { path: "/customers/:customerId", element: <div>Customer detail page</div> },
    ],
    { initialEntries: ["/requests/r1"] },
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

function mockCommonQueries() {
  vi.spyOn(employeesApi, "listEmployees").mockResolvedValue({
    employees: [{ membership_id: "m2", name: "Bea", role: "employee", status: "active" }],
    meta: { page: 1, per_page: 100, total: 1, total_pages: 1 },
  });
  vi.spyOn(customerRequestsApi, "listRequestComments").mockResolvedValue({
    comments: [],
    meta: { page: 1, per_page: 100, total: 0, total_pages: 0 },
  });
  vi.spyOn(customerRequestsApi, "listRequestHistory").mockResolvedValue({
    entries: [],
    meta: { page: 1, per_page: 100, total: 0, total_pages: 0 },
  });
}

describe("RequestDetailPage", () => {
  afterEach(() => {
    vi.restoreAllMocks();
    sessionStorage.clear();
    localStorage.clear();
  });

  it("shows the request's details and resolves the customer for a full-scope viewer", async () => {
    mockAuthenticated("owner");
    vi.spyOn(customerRequestsApi, "getRequest").mockResolvedValue(SAMPLE_REQUEST);
    vi.spyOn(customersApi, "getCustomer").mockResolvedValue(SAMPLE_CUSTOMER);
    mockCommonQueries();

    renderPage();

    expect(await screen.findByRole("heading", { name: "Can't log in" })).toBeInTheDocument();
    expect(await screen.findByText("Jane Customer")).toBeInTheDocument();
    expect(screen.getByText("technical")).toBeInTheDocument();
  });

  it("does not fetch the customer for an employee (no CUSTOMER_MANAGE reach)", async () => {
    mockAuthenticated("employee");
    vi.spyOn(customerRequestsApi, "getRequest").mockResolvedValue({
      ...SAMPLE_REQUEST,
      assignee_membership_id: "m2",
    });
    const getCustomerSpy = vi.spyOn(customersApi, "getCustomer");
    mockCommonQueries();

    renderPage();

    await screen.findByRole("heading", { name: "Can't log in" });
    expect(getCustomerSpy).not.toHaveBeenCalled();
    expect(screen.queryByText("Customer")).not.toBeInTheDocument();
  });

  it("assigns the request via the select control", async () => {
    mockAuthenticated("owner");
    vi.spyOn(customerRequestsApi, "getRequest").mockResolvedValue(SAMPLE_REQUEST);
    vi.spyOn(customersApi, "getCustomer").mockResolvedValue(SAMPLE_CUSTOMER);
    mockCommonQueries();
    const assignSpy = vi.spyOn(customerRequestsApi, "assignRequest").mockResolvedValue({
      ...SAMPLE_REQUEST,
      assignee_membership_id: "m2",
      status: "assigned",
    });
    const user = userEvent.setup();

    renderPage();
    await user.selectOptions(await screen.findByLabelText("Assignee"), "m2");

    await waitFor(() => expect(assignSpy).toHaveBeenCalledWith("org-1", "r1", "m2", "csrf-abc"));
  });

  it("moves the request to the next legal status", async () => {
    mockAuthenticated("owner");
    vi.spyOn(customerRequestsApi, "getRequest").mockResolvedValue({
      ...SAMPLE_REQUEST,
      status: "assigned",
      assignee_membership_id: "m2",
    });
    vi.spyOn(customersApi, "getCustomer").mockResolvedValue(SAMPLE_CUSTOMER);
    mockCommonQueries();
    const statusSpy = vi.spyOn(customerRequestsApi, "updateRequestStatus").mockResolvedValue({
      ...SAMPLE_REQUEST,
      status: "in_progress",
    });
    const user = userEvent.setup();

    renderPage();
    await user.click(await screen.findByRole("button", { name: "In Progress" }));

    await waitFor(() => expect(statusSpy).toHaveBeenCalledWith("org-1", "r1", "in_progress", "csrf-abc"));
  });

  it("an employee cannot see a Resolved button on their own assigned, waiting-for-customer request", async () => {
    mockAuthenticated("employee");
    vi.spyOn(customerRequestsApi, "getRequest").mockResolvedValue({
      ...SAMPLE_REQUEST,
      status: "waiting_for_customer",
      assignee_membership_id: "m2",
    });
    mockCommonQueries();

    renderPage();

    await screen.findByRole("heading", { name: "Can't log in" });
    expect(screen.queryByRole("button", { name: "Resolved" })).not.toBeInTheDocument();
  });

  it("posts a comment", async () => {
    mockAuthenticated("owner");
    vi.spyOn(customerRequestsApi, "getRequest").mockResolvedValue(SAMPLE_REQUEST);
    vi.spyOn(customersApi, "getCustomer").mockResolvedValue(SAMPLE_CUSTOMER);
    mockCommonQueries();
    const commentSpy = vi.spyOn(customerRequestsApi, "createRequestComment").mockResolvedValue({
      id: "cm1",
      request_id: "r1",
      author_membership_id: "m1",
      body: "Looked into it.",
      created_at: "now",
    });
    const user = userEvent.setup();

    renderPage();
    await user.type(await screen.findByLabelText("Add a comment"), "Looked into it.");
    await user.click(screen.getByRole("button", { name: "Post comment" }));

    await waitFor(() => expect(commentSpy).toHaveBeenCalledWith("org-1", "r1", "Looked into it.", "csrf-abc"));
  });

  it("shows an error message when the request fails to load", async () => {
    mockAuthenticated("owner");
    vi.spyOn(customerRequestsApi, "getRequest").mockRejectedValue(new ApiError(404, "NOT_FOUND", "Not found.", {}));

    renderPage();

    expect(await screen.findByRole("alert")).toHaveTextContent("Not found.");
  });
  it("deletes the request after confirmation (owner/manager only)", async () => {
    mockAuthenticated("owner");
    vi.spyOn(customerRequestsApi, "getRequest").mockResolvedValue(SAMPLE_REQUEST);
    mockCommonQueries();
    const deleteSpy = vi.spyOn(customerRequestsApi, "deleteRequest").mockResolvedValue(null);
    const user = userEvent.setup();

    renderPage();
    await user.click(await screen.findByRole("button", { name: "Delete request" }));
    expect(deleteSpy).not.toHaveBeenCalled();
    await user.click(within(await screen.findByRole("dialog")).getByRole("button", { name: "Delete request" }));

    await waitFor(() => expect(deleteSpy).toHaveBeenCalledWith("org-1", SAMPLE_REQUEST.id, "csrf-abc"));
    expect(await screen.findByText("Queue page")).toBeInTheDocument();
  });

  it("does not offer Delete request to customer support", async () => {
    mockAuthenticated("customer_support");
    vi.spyOn(customerRequestsApi, "getRequest").mockResolvedValue(SAMPLE_REQUEST);
    mockCommonQueries();

    renderPage();

    expect(await screen.findByRole("heading", { name: SAMPLE_REQUEST.title })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Delete request" })).not.toBeInTheDocument();
  });

  it("lets the author edit and delete their own request comment", async () => {
    mockAuthenticated("customer_support");
    vi.spyOn(customerRequestsApi, "getRequest").mockResolvedValue(SAMPLE_REQUEST);
    mockCommonQueries();
    vi.spyOn(customerRequestsApi, "listRequestComments").mockResolvedValue({
      comments: [{ id: "rc1", request_id: SAMPLE_REQUEST.id, author_membership_id: "m1", body: "Called them", created_at: "now" }],
      meta: { page: 1, per_page: 100, total: 1, total_pages: 1 },
    });
    const updateSpy = vi.spyOn(customerRequestsApi, "updateRequestComment").mockResolvedValue({
      id: "rc1", request_id: SAMPLE_REQUEST.id, author_membership_id: "m1", body: "Called them twice", created_at: "now",
    });
    const deleteSpy = vi.spyOn(customerRequestsApi, "deleteRequestComment").mockResolvedValue(null);
    const user = userEvent.setup();

    renderPage();
    const edit = await screen.findByRole("button", { name: /^Edit comment by/ });
    await user.click(edit);
    const box = screen.getByLabelText("Edit comment");
    await user.clear(box);
    await user.type(box, "Called them twice");
    await user.click(screen.getByRole("button", { name: "Save comment" }));
    await waitFor(() =>
      expect(updateSpy).toHaveBeenCalledWith("org-1", SAMPLE_REQUEST.id, "rc1", "Called them twice", "csrf-abc"),
    );

    await user.click(await screen.findByRole("button", { name: /^Delete comment by/ }));
    await user.click(await screen.findByRole("button", { name: "Delete comment" }));
    await waitFor(() => expect(deleteSpy).toHaveBeenCalledWith("org-1", SAMPLE_REQUEST.id, "rc1", "csrf-abc"));
  });
});
