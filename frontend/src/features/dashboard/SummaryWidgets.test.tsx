import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router-dom";

import * as analyticsApi from "@/api/analytics";
import * as notificationsApi from "@/api/notifications";
import * as tasksApi from "@/api/tasks";
import { ActivityFeedSummary, InvoicesPaymentsSummary, TaskBoardSummary } from "@/features/dashboard/SummaryWidgets";
import type { TaskPublic } from "@/types/task";

function renderWithProviders(ui: React.ReactElement) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>{ui}</MemoryRouter>
    </QueryClientProvider>,
  );
}

function makeTask(overrides: Partial<TaskPublic>): TaskPublic {
  return {
    id: "t1",
    organization_id: "org-1",
    title: "Untitled task",
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
    created_at: "2026-01-01T00:00:00Z",
    ...overrides,
  };
}

describe("TaskBoardSummary", () => {
  afterEach(() => vi.restoreAllMocks());

  it("groups tasks into columns by status", async () => {
    vi.spyOn(tasksApi, "listTasks").mockResolvedValue({
      tasks: [
        makeTask({ id: "t1", title: "Fix login bug", status: "to_do" }),
        makeTask({ id: "t2", title: "Ship invoices", status: "in_progress" }),
        makeTask({ id: "t3", title: "Review PR", status: "under_review" }),
        makeTask({ id: "t4", title: "Write docs", status: "completed" }),
      ],
      meta: { page: 1, per_page: 100, total: 4, total_pages: 1 },
    });

    renderWithProviders(<TaskBoardSummary organizationId="org-1" />);

    expect(await screen.findByText("Fix login bug")).toBeInTheDocument();
    expect(screen.getByText("Ship invoices")).toBeInTheDocument();
    expect(screen.getByText("Review PR")).toBeInTheDocument();
    expect(screen.getByText("Write docs")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Open board →" })).toHaveAttribute("href", "/tasks/board");
  });

  it("shows an empty placeholder for columns with no tasks", async () => {
    vi.spyOn(tasksApi, "listTasks").mockResolvedValue({
      tasks: [],
      meta: { page: 1, per_page: 100, total: 0, total_pages: 1 },
    });

    renderWithProviders(<TaskBoardSummary organizationId="org-1" />);

    expect((await screen.findAllByText("Nothing here")).length).toBe(4);
  });
});

describe("InvoicesPaymentsSummary", () => {
  afterEach(() => vi.restoreAllMocks());

  it("shows invoiced/collected/outstanding stats and recent payments", async () => {
    vi.spyOn(analyticsApi, "getFinancialAnalytics").mockResolvedValue({
      total_invoiced: "10000.00",
      total_collected: "7000.00",
      outstanding_balance: "3000.00",
      overdue_invoice_count: 2,
      period_start: "2026-01-01",
      period_end: "2026-01-31",
      monthly_revenue_collected: "2000.00",
      recent_payments: [
        { id: "p1", invoice_id: "i1", amount: "500.00", payment_date: "2026-01-10", method: "bank_transfer", reference: null, notes: null, idempotency_key: "k1", recorded_by: "m1", created_at: "now" },
      ],
      revenue_by_day: [],
      invoice_distribution: {},
    });

    renderWithProviders(<InvoicesPaymentsSummary organizationId="org-1" />);

    expect(await screen.findByText("10000.00")).toBeInTheDocument();
    expect(screen.getByText("7000.00")).toBeInTheDocument();
    expect(screen.getByText("3000.00")).toBeInTheDocument();
    expect(screen.getByText("500.00")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "View invoices →" })).toHaveAttribute("href", "/invoices");
  });

  it("shows an empty state when there are no recent payments", async () => {
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

    renderWithProviders(<InvoicesPaymentsSummary organizationId="org-1" />);

    expect(await screen.findByText("No payments recorded yet.")).toBeInTheDocument();
  });
});

describe("ActivityFeedSummary", () => {
  afterEach(() => vi.restoreAllMocks());

  it("links a notification to its entity when a route exists", async () => {
    vi.spyOn(notificationsApi, "listNotifications").mockResolvedValue({
      notifications: [
        {
          id: "n1",
          organization_id: "org-1",
          recipient_membership_id: "m1",
          type: "task_assigned",
          title: "You were assigned a task",
          body: "body",
          entity_type: "task",
          entity_id: "t1",
          read_at: null,
          created_at: "2026-01-10T00:00:00Z",
        },
      ],
      meta: { page: 1, per_page: 5, total: 1, total_pages: 1 },
    });

    renderWithProviders(<ActivityFeedSummary organizationId="org-1" />);

    const link = await screen.findByRole("link", { name: "You were assigned a task" });
    expect(link).toHaveAttribute("href", "/tasks/t1");
    expect(screen.getByRole("link", { name: "View all →" })).toHaveAttribute("href", "/notifications");
  });

  it("shows an empty state when there is no recent activity", async () => {
    vi.spyOn(notificationsApi, "listNotifications").mockResolvedValue({
      notifications: [],
      meta: { page: 1, per_page: 5, total: 0, total_pages: 1 },
    });

    renderWithProviders(<ActivityFeedSummary organizationId="org-1" />);

    expect(await screen.findByText("No recent activity.")).toBeInTheDocument();
  });
});
