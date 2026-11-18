import { render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router-dom";

import * as analyticsApi from "@/api/analytics";
import { OwnerDashboard } from "@/features/dashboard/OwnerDashboard";

function renderDashboard() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <OwnerDashboard organizationId="org-1" />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("OwnerDashboard", () => {
  afterEach(() => vi.restoreAllMocks());

  it("shows business stats, financial overview, and employee performance from real analytics calls", async () => {
    vi.spyOn(analyticsApi, "getOverviewAnalytics").mockResolvedValue({
      period_start: "2026-01-01",
      period_end: "2026-01-31",
      employee_count: 5,
      active_tasks: 12,
      completed_tasks: 8,
      overdue_tasks: 2,
      open_requests: 3,
      monthly_invoiced: "5000.00",
      monthly_collected: "4200.00",
    });
    vi.spyOn(analyticsApi, "getEmployeeAnalytics").mockResolvedValue([
      {
        membership_id: "m1",
        name: "Alice",
        assigned_tasks: 4,
        completed_tasks: 3,
        overdue_tasks: 1,
        completion_rate: 0.75,
        avg_completion_time_hours: 5.5,
      },
    ]);

    renderDashboard();

    await waitFor(() => expect(screen.getByText("5")).toBeInTheDocument());
    expect(screen.getByText("12")).toBeInTheDocument();
    expect(screen.getByText("5000.00")).toBeInTheDocument();
    expect(screen.getByText("4200.00")).toBeInTheDocument();
    expect(await screen.findByText("Alice")).toBeInTheDocument();
    expect(screen.getByText("3/4 completed · 1 overdue")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "View full analytics →" })).toHaveAttribute("href", "/analytics");
  });

  it("shows an error message when the overview call fails", async () => {
    vi.spyOn(analyticsApi, "getOverviewAnalytics").mockRejectedValue(new Error("boom"));
    vi.spyOn(analyticsApi, "getEmployeeAnalytics").mockResolvedValue([]);

    renderDashboard();

    expect(await screen.findByRole("alert")).toHaveTextContent("Something went wrong loading this section.");
  });
});
