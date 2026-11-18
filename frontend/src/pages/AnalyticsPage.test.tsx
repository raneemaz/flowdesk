import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router-dom";

import * as analyticsApi from "@/api/analytics";
import * as authApi from "@/api/auth";
import * as organizationsApi from "@/api/organizations";
import { AuthProvider } from "@/contexts/AuthContext";
import { OrganizationProvider } from "@/contexts/OrganizationContext";
import { AnalyticsPage } from "@/pages/AnalyticsPage";
import type { MembershipPublic, OrganizationPublic } from "@/types/organization";
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

function renderPage(role: MembershipPublic["role"]) {
  vi.spyOn(authApi, "getCurrentUser").mockResolvedValue(USER);
  vi.spyOn(organizationsApi, "listOrganizations").mockResolvedValue([membership(role)]);
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });

  render(
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <OrganizationProvider>
          <MemoryRouter>
            <AnalyticsPage />
          </MemoryRouter>
        </OrganizationProvider>
      </AuthProvider>
    </QueryClientProvider>,
  );
}

const OVERVIEW = {
  period_start: "2026-01-01",
  period_end: "2026-01-31",
  employee_count: 3,
  active_tasks: 5,
  completed_tasks: 2,
  overdue_tasks: 1,
  open_requests: 0,
  monthly_invoiced: "0",
  monthly_collected: "0",
};

describe("AnalyticsPage", () => {
  afterEach(() => vi.restoreAllMocks());

  it("shows Overview, Departments, and Finance sections to an Owner, gated by features/analytics/permissions.ts", async () => {
    vi.spyOn(analyticsApi, "getOverviewAnalytics").mockResolvedValue(OVERVIEW);
    vi.spyOn(analyticsApi, "getEmployeeAnalytics").mockResolvedValue([]);
    vi.spyOn(analyticsApi, "getDepartmentAnalytics").mockResolvedValue([]);
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

    renderPage("owner");

    expect(await screen.findByText("Overview")).toBeInTheDocument();
    expect(screen.getByText("Departments")).toBeInTheDocument();
    expect(screen.getByText("Finance")).toBeInTheDocument();
    expect(screen.getByText("Employee performance")).toBeInTheDocument();
  });

  it("only shows the Employee performance section to an Employee", async () => {
    vi.spyOn(analyticsApi, "getEmployeeAnalytics").mockResolvedValue([
      { membership_id: "m1", name: "Ada", assigned_tasks: 1, completed_tasks: 0, overdue_tasks: 0, completion_rate: 0, avg_completion_time_hours: null },
    ]);

    renderPage("employee");

    expect(await screen.findByText("Employee performance")).toBeInTheDocument();
    expect(screen.queryByText("Overview")).not.toBeInTheDocument();
    expect(screen.queryByText("Departments")).not.toBeInTheDocument();
    expect(screen.queryByText("Finance")).not.toBeInTheDocument();
  });

  it("waits for both custom-range bounds before firing any request", async () => {
    const overviewSpy = vi.spyOn(analyticsApi, "getOverviewAnalytics").mockResolvedValue(OVERVIEW);
    vi.spyOn(analyticsApi, "getEmployeeAnalytics").mockResolvedValue([]);
    vi.spyOn(analyticsApi, "getDepartmentAnalytics").mockResolvedValue([]);
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
    const user = userEvent.setup();

    renderPage("owner");
    await screen.findByText("Overview");
    overviewSpy.mockClear();

    await user.selectOptions(screen.getByLabelText("Period"), "custom");

    expect(screen.getByText("Choose a start and end date for the custom range.")).toBeInTheDocument();
    expect(overviewSpy).not.toHaveBeenCalled();
    // A disabled query (no bounds yet) is still "pending" in
    // TanStack Query v5 terms - every section must suppress its own
    // Loading indicator in this state rather than showing one forever
    // for a request that was never actually sent.
    expect(screen.queryByText("Loading…")).not.toBeInTheDocument();

    await user.type(screen.getByLabelText("From"), "2026-02-01");
    expect(overviewSpy).not.toHaveBeenCalled();

    await user.type(screen.getByLabelText("To"), "2026-02-10");
    await waitFor(() => expect(overviewSpy).toHaveBeenCalledWith("org-1", { period: "custom", periodStart: "2026-02-01", periodEnd: "2026-02-10" }));
  });
});
