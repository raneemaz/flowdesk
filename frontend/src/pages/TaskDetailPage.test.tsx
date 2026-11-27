import { render, screen, waitFor, within } from "@testing-library/react";
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
import { TaskDetailPage } from "@/pages/TaskDetailPage";
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

const TASK: TaskPublic = {
  id: "t1",
  organization_id: "org-1",
  title: "Write report",
  description: "Quarterly numbers",
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
  return { membership_id: "m1", organization: ORG, role, status: "active", joined_at: "now" };
}

function renderPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const router = createMemoryRouter(
    [
      { path: "/tasks/:taskId", element: <TaskDetailPage /> },
      { path: "/tasks", element: <div>Task list page</div> },
    ],
    { initialEntries: ["/tasks/t1"] },
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
    employees: [{ membership_id: "m1", name: "Ada", role: "owner", status: "active" }],
    meta: { page: 1, per_page: 100, total: 1, total_pages: 1 },
  });
  vi.spyOn(tasksApi, "listTaskComments").mockResolvedValue({
    comments: [],
    meta: { page: 1, per_page: 100, total: 0, total_pages: 0 },
  });
  vi.spyOn(tasksApi, "listTaskHistory").mockResolvedValue({
    entries: [],
    meta: { page: 1, per_page: 100, total: 0, total_pages: 0 },
  });
}

describe("TaskDetailPage", () => {
  afterEach(() => {
    vi.restoreAllMocks();
    sessionStorage.clear();
    localStorage.clear();
  });

  it("shows task fields and an Edit button for an owner", async () => {
    mockAuthenticated("owner");
    vi.spyOn(tasksApi, "getTask").mockResolvedValue(TASK);
    vi.spyOn(departmentsApi, "listDepartments").mockResolvedValue([]);
    mockCommonQueries();

    renderPage();

    expect(await screen.findByRole("heading", { name: "Write report" })).toBeInTheDocument();
    expect(screen.getByText("Quarterly numbers")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Edit task" })).toBeInTheDocument();
  });

  it("does not show an Edit button for a non-manager assignee", async () => {
    mockAuthenticated("employee");
    vi.spyOn(tasksApi, "getTask").mockResolvedValue({ ...TASK, assignee_membership_id: "m1" });
    mockCommonQueries();

    renderPage();

    expect(await screen.findByRole("heading", { name: "Write report" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Edit task" })).not.toBeInTheDocument();
  });

  it("deletes the task after confirmation and returns to the task list", async () => {
    mockAuthenticated("owner");
    vi.spyOn(tasksApi, "getTask").mockResolvedValue(TASK);
    vi.spyOn(departmentsApi, "listDepartments").mockResolvedValue([]);
    mockCommonQueries();
    const deleteSpy = vi.spyOn(tasksApi, "deleteTask").mockResolvedValue(null);
    const user = userEvent.setup();

    renderPage();
    await user.click(await screen.findByRole("button", { name: "Delete task" }));

    // Nothing is deleted until the confirmation is accepted.
    expect(await screen.findByRole("heading", { name: "Delete this task?" })).toBeInTheDocument();
    expect(deleteSpy).not.toHaveBeenCalled();
    const dialog = screen.getByRole("dialog");
    await user.click(within(dialog).getByRole("button", { name: "Delete task" }));

    await waitFor(() => expect(deleteSpy).toHaveBeenCalledWith("org-1", TASK.id, "csrf-abc"));
    expect(await screen.findByText("Task list page")).toBeInTheDocument();
  });

  it("keeps the task when the delete confirmation is dismissed", async () => {
    mockAuthenticated("owner");
    vi.spyOn(tasksApi, "getTask").mockResolvedValue(TASK);
    vi.spyOn(departmentsApi, "listDepartments").mockResolvedValue([]);
    mockCommonQueries();
    const deleteSpy = vi.spyOn(tasksApi, "deleteTask").mockResolvedValue(null);
    const user = userEvent.setup();

    renderPage();
    await user.click(await screen.findByRole("button", { name: "Delete task" }));
    await user.click(await screen.findByRole("button", { name: "Keep it" }));

    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(deleteSpy).not.toHaveBeenCalled();
  });

  it("does not offer Delete to a non-manager", async () => {
    mockAuthenticated("employee");
    vi.spyOn(tasksApi, "getTask").mockResolvedValue({ ...TASK, assignee_membership_id: "m1" });
    mockCommonQueries();

    renderPage();

    expect(await screen.findByRole("heading", { name: "Write report" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Delete task" })).not.toBeInTheDocument();
  });

  it("shows a not-found message when the task doesn't exist", async () => {
    mockAuthenticated("owner");
    vi.spyOn(tasksApi, "getTask").mockRejectedValue(new ApiError(404, "NOT_FOUND", "Not found.", {}));

    renderPage();

    expect(await screen.findByRole("alert")).toHaveTextContent("Not found.");
    expect(screen.getByRole("link", { name: "Back to tasks" })).toBeInTheDocument();
  });

  it("submits the edit form", async () => {
    mockAuthenticated("owner");
    vi.spyOn(tasksApi, "getTask").mockResolvedValue(TASK);
    vi.spyOn(departmentsApi, "listDepartments").mockResolvedValue([]);
    mockCommonQueries();
    const updateSpy = vi.spyOn(tasksApi, "updateTask").mockResolvedValue({ ...TASK, title: "Revised title" });
    const user = userEvent.setup();

    renderPage();
    await user.click(await screen.findByRole("button", { name: "Edit task" }));

    const titleInput = screen.getByLabelText("Title");
    await user.clear(titleInput);
    await user.type(titleInput, "Revised title");
    await user.click(screen.getByRole("button", { name: "Save changes" }));

    await waitFor(() =>
      expect(updateSpy).toHaveBeenCalledWith(
        "org-1",
        "t1",
        expect.objectContaining({ title: "Revised title" }),
        "csrf-abc",
      ),
    );
  });

  it("assigns the task via the assignee select", async () => {
    mockAuthenticated("owner");
    vi.spyOn(tasksApi, "getTask").mockResolvedValue(TASK);
    vi.spyOn(departmentsApi, "listDepartments").mockResolvedValue([]);
    mockCommonQueries();
    const assignSpy = vi.spyOn(tasksApi, "assignTask").mockResolvedValue({ ...TASK, assignee_membership_id: "m1" });
    const user = userEvent.setup();

    renderPage();
    await screen.findByRole("heading", { name: "Write report" });

    await user.selectOptions(screen.getByLabelText("Assignee"), "m1");

    await waitFor(() => expect(assignSpy).toHaveBeenCalledWith("org-1", "t1", "m1", "csrf-abc"));
  });

  it("refetches history after assigning, not just the task itself", async () => {
    mockAuthenticated("owner");
    vi.spyOn(tasksApi, "getTask").mockResolvedValue(TASK);
    vi.spyOn(departmentsApi, "listDepartments").mockResolvedValue([]);
    vi.spyOn(employeesApi, "listEmployees").mockResolvedValue({
      employees: [{ membership_id: "m1", name: "Ada", role: "owner", status: "active" }],
      meta: { page: 1, per_page: 100, total: 1, total_pages: 1 },
    });
    vi.spyOn(tasksApi, "listTaskComments").mockResolvedValue({
      comments: [],
      meta: { page: 1, per_page: 100, total: 0, total_pages: 0 },
    });
    const historySpy = vi
      .spyOn(tasksApi, "listTaskHistory")
      .mockResolvedValue({ entries: [], meta: { page: 1, per_page: 100, total: 0, total_pages: 0 } });
    vi.spyOn(tasksApi, "assignTask").mockResolvedValue({ ...TASK, assignee_membership_id: "m1" });
    const user = userEvent.setup();

    renderPage();
    await screen.findByRole("heading", { name: "Write report" });
    const callsBeforeAssign = historySpy.mock.calls.length;

    await user.selectOptions(screen.getByLabelText("Assignee"), "m1");

    await waitFor(() => expect(historySpy.mock.calls.length).toBeGreaterThan(callsBeforeAssign));
  });

  it("offers a legal status move and calls updateTaskStatus", async () => {
    mockAuthenticated("owner");
    vi.spyOn(tasksApi, "getTask").mockResolvedValue(TASK);
    vi.spyOn(departmentsApi, "listDepartments").mockResolvedValue([]);
    mockCommonQueries();
    const statusSpy = vi.spyOn(tasksApi, "updateTaskStatus").mockResolvedValue({ ...TASK, status: "in_progress" });
    const user = userEvent.setup();

    renderPage();
    await screen.findByRole("heading", { name: "Write report" });

    await user.click(screen.getByRole("button", { name: "In Progress" }));

    await waitFor(() => expect(statusSpy).toHaveBeenCalledWith("org-1", "t1", "in_progress", "csrf-abc"));
  });

  it("posts a comment and shows it in the thread", async () => {
    mockAuthenticated("owner");
    vi.spyOn(tasksApi, "getTask").mockResolvedValue(TASK);
    vi.spyOn(departmentsApi, "listDepartments").mockResolvedValue([]);
    vi.spyOn(employeesApi, "listEmployees").mockResolvedValue({
      employees: [{ membership_id: "m1", name: "Ada", role: "owner", status: "active" }],
      meta: { page: 1, per_page: 100, total: 1, total_pages: 1 },
    });
    vi.spyOn(tasksApi, "listTaskHistory").mockResolvedValue({
      entries: [],
      meta: { page: 1, per_page: 100, total: 0, total_pages: 0 },
    });
    vi.spyOn(tasksApi, "listTaskComments").mockResolvedValue({
      comments: [],
      meta: { page: 1, per_page: 100, total: 0, total_pages: 0 },
    });
    const createCommentSpy = vi.spyOn(tasksApi, "createTaskComment").mockResolvedValue({
      id: "c1",
      task_id: "t1",
      author_membership_id: "m1",
      body: "Looks good.",
      created_at: "now",
    });
    const user = userEvent.setup();

    renderPage();
    await screen.findByRole("heading", { name: "Write report" });

    await user.type(screen.getByPlaceholderText("Add a comment…"), "Looks good.");
    await user.click(screen.getByRole("button", { name: "Post comment" }));

    await waitFor(() => expect(createCommentSpy).toHaveBeenCalledWith("org-1", "t1", "Looks good.", "csrf-abc"));
  });

  it("renders history entries with resolved status labels, not raw enum values", async () => {
    mockAuthenticated("owner");
    vi.spyOn(tasksApi, "getTask").mockResolvedValue(TASK);
    vi.spyOn(departmentsApi, "listDepartments").mockResolvedValue([]);
    vi.spyOn(employeesApi, "listEmployees").mockResolvedValue({
      employees: [{ membership_id: "m1", name: "Ada", role: "owner", status: "active" }],
      meta: { page: 1, per_page: 100, total: 1, total_pages: 1 },
    });
    vi.spyOn(tasksApi, "listTaskComments").mockResolvedValue({
      comments: [],
      meta: { page: 1, per_page: 100, total: 0, total_pages: 0 },
    });
    vi.spyOn(tasksApi, "listTaskHistory").mockResolvedValue({
      entries: [
        {
          id: "h1",
          task_id: "t1",
          actor_membership_id: "m1",
          event_type: "status_changed",
          previous_value: "to_do",
          new_value: "in_progress",
          created_at: "2026-01-01T00:00:00Z",
        },
      ],
      meta: { page: 1, per_page: 100, total: 1, total_pages: 1 },
    });

    renderPage();

    const item = await screen.findByText(/changed status from/);
    expect(item).toHaveTextContent("Ada changed status from To Do to In Progress on");
  });

  it("resolves an assignee_changed history entry's raw membership ids to names", async () => {
    mockAuthenticated("owner");
    vi.spyOn(tasksApi, "getTask").mockResolvedValue({ ...TASK, assignee_membership_id: "m2" });
    vi.spyOn(departmentsApi, "listDepartments").mockResolvedValue([]);
    vi.spyOn(employeesApi, "listEmployees").mockResolvedValue({
      employees: [
        { membership_id: "m1", name: "Ada", role: "owner", status: "active" },
        { membership_id: "m2", name: "Bea", role: "employee", status: "active" },
      ],
      meta: { page: 1, per_page: 100, total: 2, total_pages: 1 },
    });
    vi.spyOn(tasksApi, "listTaskComments").mockResolvedValue({
      comments: [],
      meta: { page: 1, per_page: 100, total: 0, total_pages: 0 },
    });
    vi.spyOn(tasksApi, "listTaskHistory").mockResolvedValue({
      entries: [
        {
          id: "h1",
          task_id: "t1",
          actor_membership_id: "m1",
          event_type: "assignee_changed",
          previous_value: null,
          new_value: "m2",
          created_at: "2026-01-01T00:00:00Z",
        },
      ],
      meta: { page: 1, per_page: 100, total: 1, total_pages: 1 },
    });

    renderPage();

    const item = await screen.findByText(/changed assignee from/);
    expect(item).toHaveTextContent("Ada changed assignee from Unassigned to Bea on");
  });
  it("lets the author edit their own comment and shows it as edited", async () => {
    mockAuthenticated("employee");
    vi.spyOn(tasksApi, "getTask").mockResolvedValue({ ...TASK, assignee_membership_id: "m1" });
    mockCommonQueries();
    vi.spyOn(tasksApi, "listTaskComments").mockResolvedValue({
      comments: [
        { id: "c1", task_id: TASK.id, author_membership_id: "m1", body: "My note", created_at: "2026-11-27T09:00:00Z", edited_at: "2026-11-27T09:05:00Z" },
        { id: "c2", task_id: TASK.id, author_membership_id: "m9", body: "Their note", created_at: "2026-11-27T09:10:00Z" },
      ],
      meta: { page: 1, per_page: 100, total: 2, total_pages: 1 },
    });
    const updateSpy = vi.spyOn(tasksApi, "updateTaskComment").mockResolvedValue({
      id: "c1", task_id: TASK.id, author_membership_id: "m1", body: "My better note", created_at: "now",
    });
    const user = userEvent.setup();

    renderPage();
    expect(await screen.findByText("(edited)")).toBeInTheDocument();
    // An employee can't edit or delete someone else's comment.
    expect(screen.queryByRole("button", { name: "Edit comment by A former member" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Delete comment by A former member" })).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Edit comment by Ada" }));
    const box = screen.getByLabelText("Edit comment");
    await user.clear(box);
    await user.type(box, "My better note");
    await user.click(screen.getByRole("button", { name: "Save comment" }));

    await waitFor(() => expect(updateSpy).toHaveBeenCalledWith("org-1", TASK.id, "c1", "My better note", "csrf-abc"));
  });

  it("lets a manager delete someone else's comment after confirming", async () => {
    mockAuthenticated("owner");
    vi.spyOn(tasksApi, "getTask").mockResolvedValue(TASK);
    vi.spyOn(departmentsApi, "listDepartments").mockResolvedValue([]);
    mockCommonQueries();
    vi.spyOn(tasksApi, "listTaskComments").mockResolvedValue({
      comments: [{ id: "c2", task_id: TASK.id, author_membership_id: "m9", body: "Wrong thread", created_at: "now" }],
      meta: { page: 1, per_page: 100, total: 1, total_pages: 1 },
    });
    const deleteSpy = vi.spyOn(tasksApi, "deleteTaskComment").mockResolvedValue(null);
    const user = userEvent.setup();

    renderPage();
    // Not the author, so no Edit - but moderators may delete.
    expect(await screen.findByRole("button", { name: "Delete comment by A former member" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Edit comment by A former member" })).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Delete comment by A former member" }));
    expect(deleteSpy).not.toHaveBeenCalled();
    await user.click(await screen.findByRole("button", { name: "Delete comment" }));

    await waitFor(() => expect(deleteSpy).toHaveBeenCalledWith("org-1", TASK.id, "c2", "csrf-abc"));
  });
});
