import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, describe, expect, it, vi } from "vitest";
import { createMemoryRouter, RouterProvider } from "react-router-dom";

import * as authApi from "@/api/auth";
import * as departmentsApi from "@/api/departments";
import * as employeesApi from "@/api/employees";
import * as organizationsApi from "@/api/organizations";
import { ApiError } from "@/api/client";
import { AuthProvider } from "@/contexts/AuthContext";
import { OrganizationProvider } from "@/contexts/OrganizationContext";
import { EmployeeDirectoryPage } from "@/pages/EmployeeDirectoryPage";
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

function renderPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const router = createMemoryRouter(
    [
      { path: "/employees", element: <EmployeeDirectoryPage /> },
      { path: "/employees/:membershipId", element: <div>Profile page</div> },
    ],
    { initialEntries: ["/employees"] },
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
}

describe("EmployeeDirectoryPage", () => {
  afterEach(() => {
    vi.restoreAllMocks();
    sessionStorage.clear();
    localStorage.clear();
  });

  it("shows full columns (job title, department) for an owner", async () => {
    mockAuthenticated("owner");
    vi.spyOn(employeesApi, "listEmployees").mockResolvedValue({
      employees: [
        {
          membership_id: "m1",
          name: "Bea",
          role: "employee",
          status: "active",
          email: "bea@example.com",
          job_title: "Support Rep",
          department: { id: "d1", name: "Support" },
          manager: null,
          joined_at: "now",
        },
      ],
      meta: { page: 1, per_page: 20, total: 1, total_pages: 1 },
    });
    vi.spyOn(departmentsApi, "listDepartments").mockResolvedValue([]);

    renderPage();

    expect(await screen.findByText("Bea")).toBeInTheDocument();
    expect(screen.getByText("Support Rep")).toBeInTheDocument();
    expect(screen.getByText("Support")).toBeInTheDocument();
  });

  it("hides job title/department columns for a limited-scope employee viewer", async () => {
    mockAuthenticated("employee");
    vi.spyOn(employeesApi, "listEmployees").mockResolvedValue({
      employees: [{ membership_id: "m1", name: "Bea", role: "employee", status: "active" }],
      meta: { page: 1, per_page: 20, total: 1, total_pages: 1 },
    });
    const departmentsSpy = vi.spyOn(departmentsApi, "listDepartments");

    renderPage();

    expect(await screen.findByText("Bea")).toBeInTheDocument();
    expect(screen.queryByText("Job title")).not.toBeInTheDocument();
    expect(screen.queryByText("Department")).not.toBeInTheDocument();
    // An Employee viewer never has DEPARTMENT_MANAGE, so the directory
    // must not even call listDepartments for the filter dropdown.
    expect(departmentsSpy).not.toHaveBeenCalled();
  });

  it("applies the search filter only after submitting", async () => {
    mockAuthenticated("owner");
    const listSpy = vi.spyOn(employeesApi, "listEmployees").mockResolvedValue({
      employees: [],
      meta: { page: 1, per_page: 20, total: 0, total_pages: 0 },
    });
    vi.spyOn(departmentsApi, "listDepartments").mockResolvedValue([]);
    const user = userEvent.setup();

    renderPage();
    await waitFor(() => expect(screen.getByRole("heading", { name: "Employee directory" })).toBeInTheDocument());

    await user.type(screen.getByLabelText("Search by name"), "Bea");
    expect(listSpy).not.toHaveBeenCalledWith(expect.anything(), expect.objectContaining({ search: "Bea" }));

    await user.click(screen.getByRole("button", { name: "Search" }));

    await waitFor(() =>
      expect(listSpy).toHaveBeenCalledWith("org-1", expect.objectContaining({ search: "Bea", page: 1, perPage: 20 })),
    );
  });

  it("paginates with Previous/Next using the response meta", async () => {
    mockAuthenticated("owner");
    const listSpy = vi.spyOn(employeesApi, "listEmployees").mockResolvedValue({
      employees: [{ membership_id: "m1", name: "Bea", role: "employee", status: "active" }],
      meta: { page: 1, per_page: 20, total: 40, total_pages: 2 },
    });
    vi.spyOn(departmentsApi, "listDepartments").mockResolvedValue([]);
    const user = userEvent.setup();

    renderPage();
    expect(await screen.findByText("Page 1 of 2")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Previous" })).toBeDisabled();

    await user.click(screen.getByRole("button", { name: "Next" }));

    await waitFor(() => expect(listSpy).toHaveBeenCalledWith("org-1", expect.objectContaining({ page: 2 })));
  });

  it("shows an error message when the directory fails to load", async () => {
    mockAuthenticated("owner");
    vi.spyOn(employeesApi, "listEmployees").mockRejectedValue(new ApiError(404, "NOT_FOUND", "Not found.", {}));
    vi.spyOn(departmentsApi, "listDepartments").mockResolvedValue([]);

    renderPage();

    expect(await screen.findByRole("alert")).toHaveTextContent("Not found.");
  });
});
