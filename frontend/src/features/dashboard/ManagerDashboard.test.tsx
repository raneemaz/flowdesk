import { render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router-dom";

import * as analyticsApi from "@/api/analytics";
import * as requestsApi from "@/api/customerRequests";
import * as tasksApi from "@/api/tasks";
import { ManagerDashboard } from "@/features/dashboard/ManagerDashboard";
import type { CustomerRequestPublic } from "@/types/customerRequest";
import type { TaskPublic } from "@/types/task";

const TASK: TaskPublic = {
  id: "t1",
  organization_id: "org-1",
  title: "Review the onboarding doc",
  description: null,
  status: "under_review",
  priority: "medium",
  creator_membership_id: "m1",
  assignee_membership_id: "m2",
  department_id: null,
  start_date: null,
  due_date: null,
  estimated_hours: null,
  actual_hours: null,
  created_at: "now",
};

const REQUEST: CustomerRequestPublic = {
  id: "r1",
  organization_id: "org-1",
  customer_id: "c1",
  title: "Can't log in",
  description: null,
  category: null,
  status: "new",
  priority: "medium",
  creator_membership_id: "m1",
  assignee_membership_id: null,
  due_date: null,
  resolution_notes: null,
  created_at: "now",
};

function renderDashboard() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <ManagerDashboard organizationId="org-1" />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("ManagerDashboard", () => {
  afterEach(() => vi.restoreAllMocks());

  it("shows team workload, pending reviews, the request queue, and department activity", async () => {
    vi.spyOn(analyticsApi, "getOverviewAnalytics").mockResolvedValue({
      period_start: "2026-01-01",
      period_end: "2026-01-31",
      employee_count: 5,
      active_tasks: 12,
      completed_tasks: 8,
      overdue_tasks: 2,
      open_requests: 3,
      monthly_invoiced: "0",
      monthly_collected: "0",
    });
    vi.spyOn(analyticsApi, "getDepartmentAnalytics").mockResolvedValue([
      { department_id: "d1", department_name: "Support", active_tasks: 4, completed_tasks: 2, overdue_tasks: 0, request_volume: 3 },
    ]);
    vi.spyOn(tasksApi, "listTasks").mockResolvedValue({ tasks: [TASK], meta: { page: 1, per_page: 5, total: 1, total_pages: 1 } });
    vi.spyOn(requestsApi, "listRequests").mockImplementation(async (_organizationId, filters = {}) => {
      if (filters.perPage === 1) {
        // The useOpenRequestCount hook's own per-status count queries.
        return { requests: [], meta: { page: 1, per_page: 1, total: filters.status === "new" ? 1 : 0, total_pages: 1 } };
      }
      return { requests: [REQUEST], meta: { page: 1, per_page: 10, total: 1, total_pages: 1 } };
    });

    renderDashboard();

    await waitFor(() => expect(screen.getByText("12")).toBeInTheDocument());
    expect(screen.getByText("2")).toBeInTheDocument();
    expect(await screen.findByRole("link", { name: "Review the onboarding doc" })).toHaveAttribute("href", "/tasks/t1");
    expect(await screen.findByRole("link", { name: "Can't log in" })).toHaveAttribute("href", "/requests/r1");
    // Appears twice once the chart actually renders in jsdom (its own
    // axis tick text plus a hidden Recharts measurement span) - at
    // least one real match is what matters here, not an exact count.
    await waitFor(() => expect(screen.getAllByText("Support").length).toBeGreaterThan(0));
    await waitFor(() => expect(screen.getByText("1")).toBeInTheDocument());
  });
});
