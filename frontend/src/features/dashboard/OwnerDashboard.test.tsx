import { render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router-dom";

import * as analyticsApi from "@/api/analytics";
import * as notificationsApi from "@/api/notifications";
import * as tasksApi from "@/api/tasks";
import { OwnerDashboard } from "@/features/dashboard/OwnerDashboard";

function mockSummaryWidgetCalls() {
  vi.spyOn(tasksApi, "listTasks").mockResolvedValue({
    tasks: [],
    meta: { page: 1, per_page: 100, total: 0, total_pages: 1 },
  });
  vi.spyOn(analyticsApi, "getFinancialAnalytics").mockResolvedValue({
    total_invoiced: "0",
    total_collected: "0",
    outstanding_balance: "0",
    overdue_invoice_count: 0,
    period_start: "2026-01-01",
    period_end: "2026-01-31",
    monthly_revenue_collected: "0",
    recent_payments: [],
    revenue_by_day: [],
    invoice_distribution: {},
  });
  vi.spyOn(notificationsApi, "listNotifications").mockResolvedValue({
    notifications: [],
    meta: { page: 1, per_page: 5, total: 0, total_pages: 1 },
  });
}

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
    mockSummaryWidgetCalls();
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
    mockSummaryWidgetCalls();
    vi.spyOn(analyticsApi, "getOverviewAnalytics").mockRejectedValue(new Error("boom"));
    vi.spyOn(analyticsApi, "getEmployeeAnalytics").mockResolvedValue([]);

    renderDashboard();

    const alerts = await screen.findAllByRole("alert");
    expect(alerts.some((alert) => alert.textContent === "Something went wrong loading this section.")).toBe(true);
  });
});
