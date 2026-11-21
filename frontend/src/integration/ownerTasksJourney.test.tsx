// FD-063: cross-module critical journey - see testHelpers.tsx's own
// header comment for why these tests mount the whole <App/> rather
// than a single page, and why each journey lives in its own file.
import { screen, within } from "@testing-library/react";
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

describe("owner tasks journey", () => {
  it("an Owner navigates from the dashboard to Tasks and sees the real task list render", async () => {
    mockAuthenticatedSession("owner");
    const task: TaskPublic = {
      id: "t1",
      organization_id: "org-1",
      title: "Ship the release notes",
      description: null,
      status: "to_do",
      priority: "high",
      creator_membership_id: "m1",
      assignee_membership_id: null,
      department_id: null,
      start_date: null,
      due_date: null,
      estimated_hours: null,
      actual_hours: null,
      created_at: "2026-01-01T00:00:00Z",
    };
    vi.spyOn(tasksApi, "listTasks").mockResolvedValue({
      tasks: [task],
      meta: { page: 1, per_page: 20, total: 1, total_pages: 1 },
    });

    const user = userEvent.setup();
    renderApp();

    const nav = await screen.findByRole("navigation", { name: "Primary" });
    await user.click(within(nav).getByRole("link", { name: "Tasks" }));

    expect(await screen.findByText("Ship the release notes")).toBeInTheDocument();
  });
});
