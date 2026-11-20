import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, describe, expect, it, vi } from "vitest";
import { createMemoryRouter, RouterProvider } from "react-router-dom";

import * as aiReportsApi from "@/api/aiReports";
import * as authApi from "@/api/auth";
import { ApiError } from "@/api/client";
import * as organizationsApi from "@/api/organizations";
import { AuthProvider } from "@/contexts/AuthContext";
import { OrganizationProvider } from "@/contexts/OrganizationContext";
import { AIReportDetailPage } from "@/pages/AIReportDetailPage";
import type { AIReportPublic } from "@/types/aiReport";
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

const REPORT: AIReportPublic = {
  id: "r1",
  organization_id: "org-1",
  report_type: "weekly",
  period_start: "2026-01-05",
  period_end: "2026-01-11",
  metrics_snapshot: {},
  summary: {
    business_overview: "5 active tasks.",
    employee_productivity: "Ada completed 2 tasks.",
    financial_overview: "Invoiced $1000.",
    operational_problems: "1 task overdue.",
    missing_data: ["No invoices were issued this period."],
  },
  recommendations: ["Follow up on the overdue task."],
  model: "claude-haiku-5-5",
  provider: "anthropic",
  generated_at: "2026-01-12T06:00:00Z",
  created_at: "2026-01-12T06:00:00Z",
};

function membership(role: MembershipPublic["role"] = "owner"): MembershipPublic {
  return { organization: ORG, role, status: "active", joined_at: "now" };
}

function renderPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const router = createMemoryRouter(
    [
      { path: "/ai-reports/:reportId", element: <AIReportDetailPage /> },
      { path: "/ai-reports", element: <div>Reports list page</div> },
    ],
    { initialEntries: ["/ai-reports/r1"] },
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

function mockAuthenticated() {
  vi.spyOn(authApi, "getCurrentUser").mockResolvedValue(USER);
  vi.spyOn(organizationsApi, "listOrganizations").mockResolvedValue([membership()]);
  sessionStorage.setItem("flowdesk:csrf_token", "csrf-abc");
}

describe("AIReportDetailPage", () => {
  afterEach(() => {
    vi.restoreAllMocks();
    sessionStorage.clear();
    localStorage.clear();
  });

  it("shows the period, the four factual sections, missing data, and recommendations separately", async () => {
    mockAuthenticated();
    vi.spyOn(aiReportsApi, "getAIReport").mockResolvedValue(REPORT);

    renderPage();

    expect(await screen.findByText("2026-01-05 to 2026-01-11")).toBeInTheDocument();
    expect(screen.getByText("5 active tasks.")).toBeInTheDocument();
    expect(screen.getByText("Ada completed 2 tasks.")).toBeInTheDocument();
    expect(screen.getByText("Invoiced $1000.")).toBeInTheDocument();
    expect(screen.getByText("1 task overdue.")).toBeInTheDocument();
    expect(screen.getByText("No invoices were issued this period.")).toBeInTheDocument();

    // Recommendations render in their own, explicitly labeled section -
    // never mixed into the factual ones above.
    expect(screen.getByText("Advisory")).toBeInTheDocument();
    expect(screen.getByText("Follow up on the overdue task.")).toBeInTheDocument();
  });

  it("omits the missing-data section entirely when there is nothing missing", async () => {
    mockAuthenticated();
    vi.spyOn(aiReportsApi, "getAIReport").mockResolvedValue({
      ...REPORT,
      summary: { ...REPORT.summary, missing_data: [] },
    });

    renderPage();

    await screen.findByText("2026-01-05 to 2026-01-11");
    expect(screen.queryByText("Missing data")).not.toBeInTheDocument();
  });

  it("shows a not-found message and a link back to the list for a 404", async () => {
    mockAuthenticated();
    vi.spyOn(aiReportsApi, "getAIReport").mockRejectedValue(new ApiError(404, "NOT_FOUND", "Not found.", {}));

    renderPage();

    expect(await screen.findByText("Not found.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Back to AI Reports" })).toHaveAttribute("href", "/ai-reports");
  });
});
