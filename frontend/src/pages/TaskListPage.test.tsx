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
import * as tasksApi from "@/api/tasks";
import { AuthProvider } from "@/contexts/AuthContext";
import { OrganizationProvider } from "@/contexts/OrganizationContext";
import { TaskListPage } from "@/pages/TaskListPage";
import type { MembershipPublic, OrganizationPublic } from "@/types/organization";
import type { TaskPublic } from "@/types/task";
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

const SAMPLE_TASK: TaskPublic = {
  id: "t1",
  organization_id: "org-1",
  title: "Write report",
  description: null,
  status: "to_do",
  priority: "medium",
  creator_membership_id: "m1",
  assignee_membership_id: null,
  department_id: null,
  start_date: null,
  due_date: null,
  estimated_hours: null,
  actual_hours: null,
  created_at: "now",
};

function membership(role: MembershipPublic["role"]): MembershipPublic {
  return { organization: ORG, role, status: "active", joined_at: "now" };
}

function renderPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const router = createMemoryRouter(
    [
      { path: "/tasks", element: <TaskListPage /> },
      { path: "/tasks/:taskId", element: <div>Task detail page</div> },
      { path: "/", element: <div>Home page</div> },
    ],
    { initialEntries: ["/tasks"] },
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

describe("TaskListPage", () => {
  afterEach(() => {
    vi.restoreAllMocks();
    sessionStorage.clear();
    localStorage.clear();
  });

  it("lists tasks for an owner", async () => {
    mockAuthenticated("owner");
    vi.spyOn(tasksApi, "listTasks").mockResolvedValue({
      tasks: [SAMPLE_TASK],
      meta: { page: 1, per_page: 20, total: 1, total_pages: 1 },
    });
    vi.spyOn(departmentsApi, "listDepartments").mockResolvedValue([]);
    vi.spyOn(employeesApi, "listEmployees").mockResolvedValue({
      employees: [],
      meta: { page: 1, per_page: 100, total: 0, total_pages: 0 },
    });

    renderPage();

    expect(await screen.findByText("Write report")).toBeInTheDocument();
  });

  it("shows a New task button only for an owner, not an employee", async () => {
    mockAuthenticated("employee");
    vi.spyOn(tasksApi, "listTasks").mockResolvedValue({
      tasks: [],
      meta: { page: 1, per_page: 20, total: 0, total_pages: 0 },
    });

    renderPage();

    await waitFor(() => expect(screen.getByRole("heading", { name: "Tasks" })).toBeInTheDocument());
    expect(screen.queryByRole("button", { name: "+ New task" })).not.toBeInTheDocument();
  });

  it("creates a task via the inline form", async () => {
    mockAuthenticated("owner");
    vi.spyOn(tasksApi, "listTasks").mockResolvedValue({
      tasks: [],
      meta: { page: 1, per_page: 20, total: 0, total_pages: 0 },
    });
    vi.spyOn(departmentsApi, "listDepartments").mockResolvedValue([]);
    vi.spyOn(employeesApi, "listEmployees").mockResolvedValue({
      employees: [],
      meta: { page: 1, per_page: 100, total: 0, total_pages: 0 },
    });
    const createSpy = vi.spyOn(tasksApi, "createTask").mockResolvedValue({ ...SAMPLE_TASK, title: "New task" });
    const user = userEvent.setup();

    renderPage();
    await user.click(await screen.findByRole("button", { name: "+ New task" }));
    await user.type(screen.getByLabelText("Title"), "New task");
    await user.click(screen.getByRole("button", { name: "Create task" }));

    await waitFor(() =>
      expect(createSpy).toHaveBeenCalledWith(
        "org-1",
        expect.objectContaining({ title: "New task", priority: "medium" }),
        "csrf-abc",
      ),
    );
  });

  it("applies filters only after submitting", async () => {
    mockAuthenticated("owner");
    const listSpy = vi.spyOn(tasksApi, "listTasks").mockResolvedValue({
      tasks: [],
      meta: { page: 1, per_page: 20, total: 0, total_pages: 0 },
    });
    vi.spyOn(departmentsApi, "listDepartments").mockResolvedValue([]);
    vi.spyOn(employeesApi, "listEmployees").mockResolvedValue({
      employees: [],
      meta: { page: 1, per_page: 100, total: 0, total_pages: 0 },
    });
    const user = userEvent.setup();

    renderPage();
    await waitFor(() => expect(screen.getByRole("heading", { name: "Tasks" })).toBeInTheDocument());

    await user.selectOptions(screen.getByLabelText("Status"), "In Progress");
    await user.click(screen.getByRole("button", { name: "Search" }));

    await waitFor(() => expect(listSpy).toHaveBeenCalledWith("org-1", expect.objectContaining({ status: "in_progress" })));
  });

  it("shows an error message when the list fails to load", async () => {
    mockAuthenticated("owner");
    vi.spyOn(tasksApi, "listTasks").mockRejectedValue(new ApiError(404, "NOT_FOUND", "Not found.", {}));
    vi.spyOn(departmentsApi, "listDepartments").mockResolvedValue([]);
    vi.spyOn(employeesApi, "listEmployees").mockResolvedValue({
      employees: [],
      meta: { page: 1, per_page: 100, total: 0, total_pages: 0 },
    });

    renderPage();

    expect(await screen.findByRole("alert")).toHaveTextContent("Not found.");
  });
});
