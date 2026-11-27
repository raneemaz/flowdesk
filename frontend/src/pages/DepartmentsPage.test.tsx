import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, describe, expect, it, vi } from "vitest";
import { createMemoryRouter, RouterProvider } from "react-router-dom";

import * as authApi from "@/api/auth";
import * as departmentsApi from "@/api/departments";
import * as employeesApi from "@/api/employees";
import * as organizationsApi from "@/api/organizations";
import { AuthProvider } from "@/contexts/AuthContext";
import { OrganizationProvider } from "@/contexts/OrganizationContext";
import { DepartmentsPage } from "@/pages/DepartmentsPage";
import type { DepartmentPublic } from "@/types/department";
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

const SALES_DEPARTMENT: DepartmentPublic = {
  id: "d1",
  organization_id: "org-1",
  name: "Sales",
  description: "Revenue team",
  manager_membership_id: "m2",
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
      { path: "/departments", element: <DepartmentsPage /> },
      { path: "/", element: <div>Home page</div> },
    ],
    { initialEntries: ["/departments"] },
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

describe("DepartmentsPage", () => {
  afterEach(() => {
    vi.restoreAllMocks();
    sessionStorage.clear();
    localStorage.clear();
  });

  it("denies access for an Employee without calling the departments API", async () => {
    mockAuthenticated("employee");
    const listSpy = vi.spyOn(departmentsApi, "listDepartments");

    renderPage();

    expect(await screen.findByText("You don't have access to department management.")).toBeInTheDocument();
    expect(listSpy).not.toHaveBeenCalled();
  });

  it("lists departments and resolves the manager's name from the directory", async () => {
    mockAuthenticated("owner");
    vi.spyOn(departmentsApi, "listDepartments").mockResolvedValue([SALES_DEPARTMENT]);
    vi.spyOn(employeesApi, "listEmployees").mockResolvedValue({
      employees: [{ membership_id: "m2", name: "Bea", role: "manager", status: "active" }],
      meta: { page: 1, per_page: 100, total: 1, total_pages: 1 },
    });

    renderPage();

    expect(await screen.findByText("Sales")).toBeInTheDocument();
    expect(screen.getByText("Manager: Bea")).toBeInTheDocument();
  });

  it("creates a new department", async () => {
    mockAuthenticated("owner");
    vi.spyOn(departmentsApi, "listDepartments").mockResolvedValue([]);
    vi.spyOn(employeesApi, "listEmployees").mockResolvedValue({
      employees: [],
      meta: { page: 1, per_page: 100, total: 0, total_pages: 0 },
    });
    const createSpy = vi.spyOn(departmentsApi, "createDepartment").mockResolvedValue({
      ...SALES_DEPARTMENT,
      manager_membership_id: null,
    });
    const user = userEvent.setup();

    renderPage();
    await user.click(await screen.findByRole("button", { name: "+ New department" }));
    await user.type(screen.getByLabelText("Name"), "Sales");
    await user.click(screen.getByRole("button", { name: "Create department" }));

    await waitFor(() =>
      expect(createSpy).toHaveBeenCalledWith(
        "org-1",
        { name: "Sales", description: undefined, manager_membership_id: undefined },
        "csrf-abc",
      ),
    );
  });

  it("deactivates a department after confirmation", async () => {
    mockAuthenticated("owner");
    vi.spyOn(departmentsApi, "listDepartments").mockResolvedValue([SALES_DEPARTMENT]);
    vi.spyOn(employeesApi, "listEmployees").mockResolvedValue({
      employees: [{ membership_id: "m2", name: "Bea", role: "manager", status: "active" }],
      meta: { page: 1, per_page: 100, total: 1, total_pages: 1 },
    });
    const deactivateSpy = vi.spyOn(departmentsApi, "deactivateDepartment").mockResolvedValue({
      ...SALES_DEPARTMENT,
      status: "inactive",
    });
    const user = userEvent.setup();

    renderPage();
    await user.click(await screen.findByRole("button", { name: "Deactivate" }));
    await user.click(within(await screen.findByRole("dialog")).getByRole("button", { name: "Deactivate" }));

    await waitFor(() => expect(deactivateSpy).toHaveBeenCalledWith("org-1", "d1", "csrf-abc"));
  });

  it("does not deactivate when the confirmation is declined", async () => {
    mockAuthenticated("owner");
    vi.spyOn(departmentsApi, "listDepartments").mockResolvedValue([SALES_DEPARTMENT]);
    vi.spyOn(employeesApi, "listEmployees").mockResolvedValue({
      employees: [{ membership_id: "m2", name: "Bea", role: "manager", status: "active" }],
      meta: { page: 1, per_page: 100, total: 1, total_pages: 1 },
    });
    const deactivateSpy = vi.spyOn(departmentsApi, "deactivateDepartment");
    const user = userEvent.setup();

    renderPage();
    await user.click(await screen.findByRole("button", { name: "Deactivate" }));
    await user.click(await screen.findByRole("button", { name: "Keep it" }));

    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(deactivateSpy).not.toHaveBeenCalled();
  });
});
