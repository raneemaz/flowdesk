import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, describe, expect, it, vi } from "vitest";
import { createMemoryRouter, RouterProvider } from "react-router-dom";

import * as authApi from "@/api/auth";
import * as organizationsApi from "@/api/organizations";
import * as tasksApi from "@/api/tasks";
import { AuthProvider } from "@/contexts/AuthContext";
import { OrganizationProvider } from "@/contexts/OrganizationContext";
import { TaskCalendarPage } from "@/pages/TaskCalendarPage";
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
  const router = createMemoryRouter([{ path: "/tasks/calendar", element: <TaskCalendarPage /> }], {
    initialEntries: ["/tasks/calendar"],
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
}

describe("TaskCalendarPage", () => {
  afterEach(() => {
    vi.restoreAllMocks();
    sessionStorage.clear();
    localStorage.clear();
  });

  it("places a task on the day matching its due date", async () => {
    mockAuthenticated("owner");
    const dueDate = new Date();
    dueDate.setDate(15);
    const isoDueDate = dueDate.toISOString().slice(0, 10);
    vi.spyOn(tasksApi, "listTasks").mockResolvedValue({
      tasks: [task({ title: "Quarterly report", due_date: isoDueDate })],
      meta: { page: 1, per_page: 100, total: 1, total_pages: 1 },
    });

    renderPage();

    expect(await screen.findByText("Quarterly report")).toBeInTheDocument();
  });

  it("navigates to the next month and refetches with the new range", async () => {
    mockAuthenticated("owner");
    const listSpy = vi.spyOn(tasksApi, "listTasks").mockResolvedValue({
      tasks: [],
      meta: { page: 1, per_page: 100, total: 0, total_pages: 0 },
    });
    const user = userEvent.setup();

    renderPage();
    await waitFor(() => expect(listSpy).toHaveBeenCalledTimes(1));

    await user.click(screen.getByRole("button", { name: "Next" }));

    await waitFor(() => expect(listSpy).toHaveBeenCalledTimes(2));
    const firstRange = listSpy.mock.calls[0][1];
    const secondRange = listSpy.mock.calls[1][1];
    expect(secondRange?.dueDateFrom).not.toBe(firstRange?.dueDateFrom);
  });
});
