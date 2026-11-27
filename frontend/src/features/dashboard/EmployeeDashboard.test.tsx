import { render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router-dom";

import * as activityApi from "@/api/activity";
import * as analyticsApi from "@/api/analytics";
import * as notificationsApi from "@/api/notifications";
import * as tasksApi from "@/api/tasks";
import { EmployeeDashboard } from "@/features/dashboard/EmployeeDashboard";
import type { TaskPublic } from "@/types/task";

// "Now" is pinned (vi.setSystemTime below) rather than left to the
// real wall clock - upcomingDeadlines (features/dashboard/EmployeeDashboard.tsx)
// excludes any due_date before today, so fixture dates relative to an
// unpinned "now" would silently start failing the moment the real
// date passed them.
const NOW = new Date("2026-06-15T12:00:00Z");

const DUE_SOON: TaskPublic = {
  id: "t1",
  organization_id: "org-1",
  title: "Due soon",
  description: null,
  status: "to_do",
  priority: "medium",
  creator_membership_id: "m1",
  assignee_membership_id: "m2",
  department_id: null,
  start_date: null,
  due_date: "2026-06-20",
  estimated_hours: null,
  actual_hours: null,
  created_at: "now",
};
const DUE_LATER: TaskPublic = { ...DUE_SOON, id: "t2", title: "Due later", due_date: "2026-07-01" };
const NO_DUE_DATE: TaskPublic = { ...DUE_SOON, id: "t3", title: "No due date", due_date: null };
const ALREADY_DONE: TaskPublic = { ...DUE_SOON, id: "t4", title: "Already done", due_date: "2026-06-01", status: "completed" };
const PAST_DUE_BUT_OPEN: TaskPublic = { ...DUE_SOON, id: "t5", title: "Past due but open", due_date: "2026-06-01" };

function renderDashboard() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <EmployeeDashboard organizationId="org-1" />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("EmployeeDashboard", () => {
  beforeEach(() => vi.useFakeTimers({ now: NOW, toFake: ["Date"] }));
  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  it("shows my tasks, upcoming deadlines sorted ascending, overdue count, recent activity, and notifications", async () => {
    vi.spyOn(tasksApi, "listTasks").mockResolvedValue({
      tasks: [DUE_LATER, DUE_SOON, NO_DUE_DATE, ALREADY_DONE, PAST_DUE_BUT_OPEN],
      meta: { page: 1, per_page: 20, total: 5, total_pages: 1 },
    });
    vi.spyOn(analyticsApi, "getEmployeeAnalytics").mockResolvedValue([
      { membership_id: "m2", name: "Bob", assigned_tasks: 4, completed_tasks: 1, overdue_tasks: 2, completion_rate: 0.25, avg_completion_time_hours: 3 },
    ]);
    vi.spyOn(activityApi, "listActivity").mockResolvedValue({
      entries: [{ id: "a1", organization_id: "org-1", actor_membership_id: "m2", action: "task_completed", entity_type: "task", entity_id: "t4", metadata: {}, created_at: "now" }],
      meta: { page: 1, per_page: 5, total: 1, total_pages: 1 },
    });
    vi.spyOn(notificationsApi, "listNotifications").mockResolvedValue({
      notifications: [{ id: "n1", organization_id: "org-1", recipient_membership_id: "m2", type: "task_assigned", title: "You were assigned a task", body: "", entity_type: "task", entity_id: "t1", read_at: null, created_at: "now" }],
      meta: { page: 1, per_page: 5, total: 1, total_pages: 1 },
    });

    renderDashboard();

    // "Due soon"/"Due later" each appear twice - once in "My tasks"
    // (every fetched task), once in "Upcoming deadlines" (the subset
    // with a due date, filtered/sorted) - two distinct widgets over
    // the same one fetched page, not two requests.
    await waitFor(() => expect(screen.getAllByRole("link", { name: "Due soon" })).toHaveLength(2));
    expect(screen.getAllByRole("link", { name: "Due later" })).toHaveLength(2);
    expect(screen.getByRole("link", { name: "No due date" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Already done" })).toBeInTheDocument();
    // Still open and still shown in "My tasks", but excluded from
    // "Upcoming deadlines" below - its due date has already passed, so
    // it's the overdue stat card's concern, not this one's (spec
    // Section 12.3 lists them as two separate dashboard items).
    expect(screen.getByRole("link", { name: "Past due but open" })).toBeInTheDocument();

    // Upcoming deadlines: only non-terminal tasks with a due date that
    // hasn't passed yet, sorted ascending - "Due soon" (2026-06-20)
    // before "Due later" (2026-07-01); "No due date", the
    // already-completed task, and the past-due-but-open task are all
    // excluded from this section specifically.
    const deadlinesSection = screen.getByText("Upcoming deadlines").closest("section")!;
    const deadlineLinks = within(deadlinesSection).getAllByRole("link");
    expect(deadlineLinks.map((link) => link.textContent)).toEqual(["Due soon", "Due later"]);

    await waitFor(() => expect(screen.getByText("2")).toBeInTheDocument()); // overdue_tasks from analytics
    expect(await screen.findByText("You completed a task")).toBeInTheDocument();
    expect(await screen.findByText("You were assigned a task")).toBeInTheDocument();
  });
});
