// FD-063: cross-module critical journey - see testHelpers.tsx's own
// header comment for why these tests mount the whole <App/> rather
// than a single page, and why each journey lives in its own file.
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import * as tasksApi from "@/api/tasks";
import { mockAuthenticatedSession, renderApp } from "@/integration/testHelpers";
import type { TaskPublic } from "@/types/task";

afterEach(() => {
  vi.restoreAllMocks();
  sessionStorage.clear();
  localStorage.clear();
});

describe("employee tasks journey", () => {
  it("an Employee has no Invoices/Customers link, and can reach My Tasks", async () => {
    mockAuthenticatedSession("employee");
    const myTask: TaskPublic = {
      id: "t2",
      organization_id: "org-1",
      title: "Follow up with the customer",
      description: null,
      status: "in_progress",
      priority: "medium",
      creator_membership_id: "m1",
      assignee_membership_id: "m2",
      department_id: null,
      start_date: null,
      due_date: null,
      estimated_hours: null,
      actual_hours: null,
      created_at: "2026-01-01T00:00:00Z",
    };
    vi.spyOn(tasksApi, "listTasks").mockResolvedValue({
      tasks: [myTask],
      meta: { page: 1, per_page: 20, total: 1, total_pages: 1 },
    });

    const user = userEvent.setup();
    renderApp();

    const nav = await screen.findByRole("navigation", { name: "Primary" });
    expect(within(nav).queryByRole("link", { name: "Invoices" })).not.toBeInTheDocument();
    expect(within(nav).queryByRole("link", { name: "Customers" })).not.toBeInTheDocument();

    await user.click(within(nav).getByRole("link", { name: "Tasks" }));
    await waitFor(() => expect(screen.getByRole("heading", { name: "Tasks" })).toBeInTheDocument());

    await user.click(screen.getByRole("link", { name: "My Tasks" }));
    // Pages load on demand, and the Tasks page (showing the same task)
    // stays up until My Tasks is ready - so wait for My Tasks itself.
    expect(await screen.findByRole("heading", { name: "My Tasks" })).toBeInTheDocument();
    expect(await screen.findByText("Follow up with the customer")).toBeInTheDocument();
  });
});
