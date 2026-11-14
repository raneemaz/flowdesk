import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, describe, expect, it, vi } from "vitest";
import { createMemoryRouter, RouterProvider } from "react-router-dom";

import * as authApi from "@/api/auth";
import { ApiError } from "@/api/client";
import * as departmentsApi from "@/api/departments";
import * as employeesApi from "@/api/employees";
import * as organizationsApi from "@/api/organizations";
import { AuthProvider } from "@/contexts/AuthContext";
import { OrganizationProvider } from "@/contexts/OrganizationContext";
import { EmployeeProfilePage } from "@/pages/EmployeeProfilePage";
import type { EmployeePublic } from "@/types/employee";
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

const EMPLOYEE_FULL: EmployeePublic = {
  membership_id: "m2",
  name: "Bea",
  role: "employee",
  status: "active",
  email: "bea@example.com",
  job_title: "Support Rep",
  department: { id: "d1", name: "Support" },
  manager: null,
  joined_at: "now",
};

function membership(role: MembershipPublic["role"]): MembershipPublic {
  return { organization: ORG, role, status: "active", joined_at: "now" };
}

function renderPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const router = createMemoryRouter(
    [
      { path: "/employees/:membershipId", element: <EmployeeProfilePage /> },
      { path: "/employees", element: <div>Directory page</div> },
    ],
    { initialEntries: ["/employees/m2"] },
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

describe("EmployeeProfilePage", () => {
  afterEach(() => {
    vi.restoreAllMocks();
    sessionStorage.clear();
    localStorage.clear();
  });

  it("shows an Edit button for an Owner viewing an Employee's profile", async () => {
    mockAuthenticated("owner");
    vi.spyOn(employeesApi, "getEmployee").mockResolvedValue(EMPLOYEE_FULL);

    renderPage();

    expect(await screen.findByRole("heading", { name: "Bea" })).toBeInTheDocument();
    expect(screen.getByText("Support Rep")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Edit profile" })).toBeInTheDocument();
  });

  it("does not show an Edit button for a Manager viewing another Manager's profile", async () => {
    mockAuthenticated("manager");
    vi.spyOn(employeesApi, "getEmployee").mockResolvedValue({ ...EMPLOYEE_FULL, role: "manager" });

    renderPage();

    expect(await screen.findByRole("heading", { name: "Bea" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Edit profile" })).not.toBeInTheDocument();
  });

  it("submits the edit form with cleared fields mapped to null", async () => {
    mockAuthenticated("owner");
    vi.spyOn(employeesApi, "getEmployee").mockResolvedValue(EMPLOYEE_FULL);
    vi.spyOn(departmentsApi, "listDepartments").mockResolvedValue([]);
    vi.spyOn(employeesApi, "listEmployees").mockResolvedValue({
      employees: [EMPLOYEE_FULL],
      meta: { page: 1, per_page: 100, total: 1, total_pages: 1 },
    });
    const updateSpy = vi.spyOn(employeesApi, "updateEmployeeProfile").mockResolvedValue({
      id: "p1",
      organization_id: "org-1",
      membership_id: "m2",
      department_id: null,
      manager_membership_id: null,
      job_title: null,
      status: "suspended",
      created_at: "now",
    });
    const user = userEvent.setup();

    renderPage();
    await user.click(await screen.findByRole("button", { name: "Edit profile" }));

    await user.clear(screen.getByLabelText("Job title"));
    await user.selectOptions(screen.getByLabelText("Department"), "No department");
    await user.selectOptions(screen.getByLabelText("Employment status"), "Suspended");
    await user.click(screen.getByRole("button", { name: "Save changes" }));

    await waitFor(() =>
      expect(updateSpy).toHaveBeenCalledWith(
        "org-1",
        "m2",
        { job_title: null, department_id: null, manager_membership_id: null, status: "suspended" },
        "csrf-abc",
      ),
    );
    expect(await screen.findByText("Profile updated.")).toBeInTheDocument();
  });

  it("surfaces a backend validation error from the PATCH", async () => {
    mockAuthenticated("owner");
    vi.spyOn(employeesApi, "getEmployee").mockResolvedValue(EMPLOYEE_FULL);
    vi.spyOn(departmentsApi, "listDepartments").mockResolvedValue([]);
    vi.spyOn(employeesApi, "listEmployees").mockResolvedValue({
      employees: [EMPLOYEE_FULL],
      meta: { page: 1, per_page: 100, total: 1, total_pages: 1 },
    });
    vi.spyOn(employeesApi, "updateEmployeeProfile").mockRejectedValue(
      new ApiError(422, "INVALID_DEPARTMENT", "department_id must reference an active department in this organization.", {}),
    );
    const user = userEvent.setup();

    renderPage();
    await user.click(await screen.findByRole("button", { name: "Edit profile" }));
    await user.click(screen.getByRole("button", { name: "Save changes" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("department_id must reference an active department");
  });

  it("shows a not-found message when the employee doesn't exist", async () => {
    mockAuthenticated("owner");
    vi.spyOn(employeesApi, "getEmployee").mockRejectedValue(new ApiError(404, "NOT_FOUND", "Not found.", {}));

    renderPage();

    expect(await screen.findByRole("alert")).toHaveTextContent("Not found.");
    expect(screen.getByRole("link", { name: "Back to directory" })).toBeInTheDocument();
  });
});
