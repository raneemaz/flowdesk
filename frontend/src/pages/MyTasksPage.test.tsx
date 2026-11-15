import { render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, describe, expect, it, vi } from "vitest";
import { createMemoryRouter, RouterProvider } from "react-router-dom";

import * as authApi from "@/api/auth";
import * as departmentsApi from "@/api/departments";
import * as employeesApi from "@/api/employees";
import * as organizationsApi from "@/api/organizations";
import * as tasksApi from "@/api/tasks";
import { AuthProvider } from "@/contexts/AuthContext";
import { OrganizationProvider } from "@/contexts/OrganizationContext";
import { MyTasksPage } from "@/pages/MyTasksPage";
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
  const router = createMemoryRouter([{ path: "/tasks/mine", element: <MyTasksPage /> }], {
    initialEntries: ["/tasks/mine"],
  });

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

describe("MyTasksPage", () => {
  afterEach(() => {
    vi.restoreAllMocks();
    sessionStorage.clear();
    localStorage.clear();
  });

  it("resolves the owner's own membership_id and locks the assignee filter to it", async () => {
    mockAuthenticated("owner");
    vi.spyOn(employeesApi, "listEmployees").mockResolvedValue({
      employees: [
        { membership_id: "m-other", name: "Bea", role: "employee", status: "active" },
        { membership_id: "m1", name: "Ada", role: "owner", status: "active", email: "ada@example.com" },
      ],
      meta: { page: 1, per_page: 100, total: 2, total_pages: 1 },
    });
    vi.spyOn(departmentsApi, "listDepartments").mockResolvedValue([]);
    const listTasksSpy = vi.spyOn(tasksApi, "listTasks").mockResolvedValue({
      tasks: [],
      meta: { page: 1, per_page: 20, total: 0, total_pages: 0 },
    });

    renderPage();

    await waitFor(() =>
      expect(listTasksSpy).toHaveBeenCalledWith("org-1", expect.objectContaining({ assigneeMembershipId: "m1" })),
    );
  });

  it("does not need a lookup for a non-manager - the backend already restricts their list", async () => {
    mockAuthenticated("employee");
    const listTasksSpy = vi.spyOn(tasksApi, "listTasks").mockResolvedValue({
      tasks: [],
      meta: { page: 1, per_page: 20, total: 0, total_pages: 0 },
    });
    const listEmployeesSpy = vi.spyOn(employeesApi, "listEmployees");

    renderPage();

    await waitFor(() => expect(listTasksSpy).toHaveBeenCalled());
    expect(listEmployeesSpy).not.toHaveBeenCalled();
    expect(listTasksSpy).toHaveBeenCalledWith("org-1", expect.objectContaining({ assigneeMembershipId: undefined }));
  });

  it("shows the My Tasks heading", async () => {
    mockAuthenticated("owner");
    vi.spyOn(employeesApi, "listEmployees").mockResolvedValue({
      employees: [],
      meta: { page: 1, per_page: 100, total: 0, total_pages: 0 },
    });
    vi.spyOn(departmentsApi, "listDepartments").mockResolvedValue([]);
    vi.spyOn(tasksApi, "listTasks").mockResolvedValue({
      tasks: [],
      meta: { page: 1, per_page: 20, total: 0, total_pages: 0 },
    });

    renderPage();

    expect(await screen.findByRole("heading", { name: "My Tasks" })).toBeInTheDocument();
  });
});
