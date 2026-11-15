import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, describe, expect, it, vi } from "vitest";
import { createMemoryRouter, RouterProvider } from "react-router-dom";

import * as authApi from "@/api/auth";
import * as employeesApi from "@/api/employees";
import * as organizationsApi from "@/api/organizations";
import * as tasksApi from "@/api/tasks";
import { AuthProvider } from "@/contexts/AuthContext";
import { OrganizationProvider } from "@/contexts/OrganizationContext";
import { TaskBoardPage } from "@/pages/TaskBoardPage";
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

function membership(role: MembershipPublic["role"]): MembershipPublic {
  return { organization: ORG, role, status: "active", joined_at: "now" };
}

function task(overrides: Partial<TaskPublic>): TaskPublic {
  return {
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
    ...overrides,
  };
}

function renderPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const router = createMemoryRouter([{ path: "/tasks/board", element: <TaskBoardPage /> }], {
    initialEntries: ["/tasks/board"],
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

describe("TaskBoardPage", () => {
  afterEach(() => {
    vi.restoreAllMocks();
    sessionStorage.clear();
    localStorage.clear();
  });

  it("groups tasks into columns by status", async () => {
    mockAuthenticated("owner");
    vi.spyOn(tasksApi, "listTasks").mockResolvedValue({
      tasks: [task({ id: "t1", title: "Todo task", status: "to_do" }), task({ id: "t2", title: "In progress task", status: "in_progress" })],
      meta: { page: 1, per_page: 100, total: 2, total_pages: 1 },
    });
    vi.spyOn(employeesApi, "listEmployees").mockResolvedValue({
      employees: [],
      meta: { page: 1, per_page: 100, total: 0, total_pages: 0 },
    });

    renderPage();

    expect(await screen.findByText("Todo task")).toBeInTheDocument();
    expect(screen.getByText("In progress task")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "To Do (1)" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "In Progress (1)" })).toBeInTheDocument();
  });

  it("offers only the owner's legal next statuses, and moving a card calls updateTaskStatus", async () => {
    mockAuthenticated("owner");
    vi.spyOn(tasksApi, "listTasks").mockResolvedValue({
      tasks: [task({ id: "t1", title: "Todo task", status: "to_do" })],
      meta: { page: 1, per_page: 100, total: 1, total_pages: 1 },
    });
    vi.spyOn(employeesApi, "listEmployees").mockResolvedValue({
      employees: [],
      meta: { page: 1, per_page: 100, total: 0, total_pages: 0 },
    });
    const updateStatusSpy = vi.spyOn(tasksApi, "updateTaskStatus").mockResolvedValue(task({ status: "in_progress" }));
    const user = userEvent.setup();

    renderPage();
    await screen.findByText("Todo task");

    await user.click(screen.getByRole("button", { name: "In Progress" }));

    await waitFor(() => expect(updateStatusSpy).toHaveBeenCalledWith("org-1", "t1", "in_progress", "csrf-abc"));
  });

  it("only offers the two forward-progress moves to a non-manager assignee", async () => {
    mockAuthenticated("employee");
    vi.spyOn(tasksApi, "listTasks").mockResolvedValue({
      tasks: [task({ id: "t1", title: "Review task", status: "under_review", assignee_membership_id: "m1" })],
      meta: { page: 1, per_page: 100, total: 1, total_pages: 1 },
    });

    renderPage();

    await screen.findByText("Review task");
    // under_review's legal moves are completed/in_progress/cancelled,
    // but none of them are in the assignee-allowed set - no buttons.
    expect(screen.queryByRole("button", { name: "Completed" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "In Progress" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Cancelled" })).not.toBeInTheDocument();
  });
});
