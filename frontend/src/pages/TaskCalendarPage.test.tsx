import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, describe, expect, it, vi } from "vitest";
import { createMemoryRouter, RouterProvider } from "react-router-dom";

import * as authApi from "@/api/auth";
import * as departmentsApi from "@/api/departments";
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
    // Local date components, not `.toISOString()` (which converts to
    // UTC first) - matching exactly how the page itself now computes
    // a grid cell's own iso date, so this assertion is meaningful
    // regardless of the machine's own timezone running the suite.
    const isoDueDate = `${dueDate.getFullYear()}-${String(dueDate.getMonth() + 1).padStart(2, "0")}-${String(dueDate.getDate()).padStart(2, "0")}`;
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

  it("creates a task for the clicked day via the dialog", async () => {
    mockAuthenticated("owner");
    sessionStorage.setItem("flowdesk:csrf_token", "csrf-abc");
    vi.spyOn(tasksApi, "listTasks").mockResolvedValue({
      tasks: [],
      meta: { page: 1, per_page: 100, total: 0, total_pages: 0 },
    });
    vi.spyOn(departmentsApi, "listDepartments").mockResolvedValue([]);
    const createSpy = vi.spyOn(tasksApi, "createTask").mockResolvedValue(task({}));
    const user = userEvent.setup();

    renderPage();
    const fifteenth = new Date();
    fifteenth.setDate(15);
    const iso = fifteenth.toISOString().slice(0, 10);

    const addButton = await screen.findByRole("button", { name: `Add a task for ${iso}` });
    await user.click(addButton);

    expect(await screen.findByRole("heading", { name: `New task for ${iso}` })).toBeInTheDocument();
    await user.type(screen.getByLabelText("Title"), "Call the customer back");
    await user.click(screen.getByRole("button", { name: "Create task" }));

    await waitFor(() =>
      expect(createSpy).toHaveBeenCalledWith(
        "org-1",
        expect.objectContaining({ title: "Call the customer back", due_date: iso }),
        "csrf-abc",
      ),
    );
  });

  it("edits a task in place when its chip is clicked", async () => {
    mockAuthenticated("owner");
    sessionStorage.setItem("flowdesk:csrf_token", "csrf-abc");
    const due = new Date();
    due.setDate(10);
    const iso = `${due.getFullYear()}-${String(due.getMonth() + 1).padStart(2, "0")}-10`;
    vi.spyOn(tasksApi, "listTasks").mockResolvedValue({
      tasks: [task({ id: "t9", title: "Quarterly report", due_date: iso })],
      meta: { page: 1, per_page: 100, total: 1, total_pages: 1 },
    });
    vi.spyOn(departmentsApi, "listDepartments").mockResolvedValue([]);
    const updateSpy = vi.spyOn(tasksApi, "updateTask").mockResolvedValue(task({}));
    const user = userEvent.setup();

    renderPage();
    await user.click(await screen.findByRole("button", { name: "Quarterly report" }));

    expect(await screen.findByRole("heading", { name: "Edit task" })).toBeInTheDocument();
    const title = screen.getByLabelText("Title");
    await user.clear(title);
    await user.type(title, "Quarterly report v2");
    await user.click(screen.getByRole("button", { name: "Save changes" }));

    await waitFor(() =>
      expect(updateSpy).toHaveBeenCalledWith(
        "org-1",
        "t9",
        expect.objectContaining({ title: "Quarterly report v2", due_date: iso }),
        "csrf-abc",
      ),
    );
  });

  it("cancels a task from the calendar dialog", async () => {
    mockAuthenticated("owner");
    sessionStorage.setItem("flowdesk:csrf_token", "csrf-abc");
    const due = new Date();
    due.setDate(12);
    const iso = `${due.getFullYear()}-${String(due.getMonth() + 1).padStart(2, "0")}-12`;
    vi.spyOn(tasksApi, "listTasks").mockResolvedValue({
      tasks: [task({ id: "t7", title: "Old errand", due_date: iso })],
      meta: { page: 1, per_page: 100, total: 1, total_pages: 1 },
    });
    vi.spyOn(departmentsApi, "listDepartments").mockResolvedValue([]);
    const statusSpy = vi.spyOn(tasksApi, "updateTaskStatus").mockResolvedValue(task({ status: "cancelled" }));
    const user = userEvent.setup();

    renderPage();
    await user.click(await screen.findByRole("button", { name: "Old errand" }));
    await user.click(await screen.findByRole("button", { name: "Cancel task" }));

    await waitFor(() => expect(statusSpy).toHaveBeenCalledWith("org-1", "t7", "cancelled", "csrf-abc"));
  });

  it("permanently deletes a task from the calendar dialog after confirming", async () => {
    mockAuthenticated("owner");
    sessionStorage.setItem("flowdesk:csrf_token", "csrf-abc");
    const due = new Date();
    due.setDate(9);
    const iso = `${due.getFullYear()}-${String(due.getMonth() + 1).padStart(2, "0")}-09`;
    vi.spyOn(tasksApi, "listTasks").mockResolvedValue({
      tasks: [task({ id: "t5", title: "Wrong entry", due_date: iso })],
      meta: { page: 1, per_page: 100, total: 1, total_pages: 1 },
    });
    vi.spyOn(departmentsApi, "listDepartments").mockResolvedValue([]);
    const deleteSpy = vi.spyOn(tasksApi, "deleteTask").mockResolvedValue(null);
    const user = userEvent.setup();

    renderPage();
    await user.click(await screen.findByRole("button", { name: "Wrong entry" }));
    await user.click(await screen.findByRole("button", { name: "Delete" }));
    expect(deleteSpy).not.toHaveBeenCalled();
    await user.click(await screen.findByRole("button", { name: "Delete task" }));

    await waitFor(() => expect(deleteSpy).toHaveBeenCalledWith("org-1", "t5", "csrf-abc"));
  });

  it("shows an agenda list instead of in-cell names on a phone", async () => {
    mockAuthenticated("owner");
    vi.stubGlobal("matchMedia", (query: string) => ({
      matches: query === "(max-width: 639px)",
      media: query,
      addEventListener: () => {},
      removeEventListener: () => {},
    }));
    const due = new Date();
    due.setDate(11);
    const iso = `${due.getFullYear()}-${String(due.getMonth() + 1).padStart(2, "0")}-11`;
    vi.spyOn(tasksApi, "listTasks").mockResolvedValue({
      tasks: [task({ id: "t11", title: "Phone agenda task", due_date: iso })],
      meta: { page: 1, per_page: 100, total: 1, total_pages: 1 },
    });
    vi.spyOn(departmentsApi, "listDepartments").mockResolvedValue([]);
    const user = userEvent.setup();

    renderPage();

    const agenda = await screen.findByRole("region", { name: /Tasks in/ });
    expect(within(agenda).getByRole("button", { name: /Phone agenda task/ })).toBeInTheDocument();
    // Exactly one control per task: the grid shows dots, not a second button.
    expect(screen.getAllByRole("button", { name: /Phone agenda task/ })).toHaveLength(1);
    await user.click(within(agenda).getByRole("button", { name: /Phone agenda task/ }));
    expect(await screen.findByRole("heading", { name: "Edit task" })).toBeInTheDocument();
    vi.unstubAllGlobals();
  });

  it("lets an employee move their task forward but not edit or add", async () => {
    mockAuthenticated("employee");
    sessionStorage.setItem("flowdesk:csrf_token", "csrf-abc");
    const due = new Date();
    due.setDate(8);
    const iso = `${due.getFullYear()}-${String(due.getMonth() + 1).padStart(2, "0")}-08`;
    vi.spyOn(tasksApi, "listTasks").mockResolvedValue({
      tasks: [task({ id: "t3", title: "My errand", due_date: iso })],
      meta: { page: 1, per_page: 100, total: 1, total_pages: 1 },
    });
    const statusSpy = vi.spyOn(tasksApi, "updateTaskStatus").mockResolvedValue(task({ status: "in_progress" }));
    const user = userEvent.setup();

    renderPage();
    await user.click(await screen.findByRole("button", { name: "My errand" }));

    expect(screen.queryByRole("button", { name: /Add a task for/ })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Save changes" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Cancel task" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Delete" })).not.toBeInTheDocument();
    await user.click(await screen.findByRole("button", { name: "In Progress" }));

    await waitFor(() => expect(statusSpy).toHaveBeenCalledWith("org-1", "t3", "in_progress", "csrf-abc"));
  });
});
