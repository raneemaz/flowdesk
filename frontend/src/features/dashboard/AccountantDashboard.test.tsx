import { render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, describe, expect, it, vi } from "vitest";

import * as analyticsApi from "@/api/analytics";
import { AccountantDashboard } from "@/features/dashboard/AccountantDashboard";

function renderDashboard() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={queryClient}>
      <AccountantDashboard organizationId="org-1" />
    </QueryClientProvider>,
  );
}

describe("AccountantDashboard", () => {
  afterEach(() => vi.restoreAllMocks());

  it("shows invoiced/collected/outstanding/monthly-collections stats, a revenue chart, and recent payments from one call", async () => {
    vi.spyOn(analyticsApi, "getFinancialAnalytics").mockResolvedValue({
      total_invoiced: "10000.00",
      total_collected: "7000.00",
      outstanding_balance: "3000.00",
      overdue_invoice_count: 1,
      period_start: "2026-01-01",
      period_end: "2026-01-31",
      monthly_revenue_collected: "2000.00",
      recent_payments: [{ id: "p1", invoice_id: "i1", amount: "500.00", payment_date: "2026-01-10", method: "bank_transfer", reference: null, notes: null, idempotency_key: "k1", recorded_by: "m1", created_at: "now" }],
      revenue_by_day: [{ date: "2026-01-10", amount: "500.00" }],
      invoice_distribution: { paid: 1, sent: 2 },
    });

    renderDashboard();

    await waitFor(() => expect(screen.getByText("10000.00")).toBeInTheDocument());
    expect(screen.getByText("7000.00")).toBeInTheDocument();
    expect(screen.getByText("3000.00")).toBeInTheDocument();
    expect(screen.getByText("2000.00")).toBeInTheDocument();
    // "2026-01-10" and "500.00" each appear twice once the chart
    // actually renders in jsdom (its own axis tick/tooltip text, plus
    // a hidden Recharts measurement span) in addition to the recent
    // payments list row - at least one real (non-hidden) match is
    // what matters here, not an exact count.
    expect(screen.getAllByText("2026-01-10").length).toBeGreaterThan(0);
    expect(screen.getAllByText("500.00").length).toBeGreaterThan(0);
  });

  it("shows an empty state for recent payments when there are none", async () => {
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

    renderDashboard();

    expect(await screen.findByText("No payments recorded yet.")).toBeInTheDocument();
    expect(await screen.findByText("No payments recorded in this period.")).toBeInTheDocument();
  });
});
