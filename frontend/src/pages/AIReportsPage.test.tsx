import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, describe, expect, it, vi } from "vitest";
import { createMemoryRouter, RouterProvider } from "react-router-dom";

import * as aiReportsApi from "@/api/aiReports";
import * as authApi from "@/api/auth";
import { ApiError } from "@/api/client";
import * as organizationsApi from "@/api/organizations";
import { AuthProvider } from "@/contexts/AuthContext";
import { OrganizationProvider } from "@/contexts/OrganizationContext";
import { AIReportsPage } from "@/pages/AIReportsPage";
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
    missing_data: [],
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
      { path: "/ai-reports", element: <AIReportsPage /> },
      { path: "/ai-reports/:reportId", element: <div>Report detail page</div> },
      { path: "/", element: <div>Home page</div> },
    ],
    { initialEntries: ["/ai-reports"] },
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

function mockAuthenticated(role: MembershipPublic["role"] = "owner") {
  vi.spyOn(authApi, "getCurrentUser").mockResolvedValue(USER);
  vi.spyOn(organizationsApi, "listOrganizations").mockResolvedValue([membership(role)]);
  sessionStorage.setItem("flowdesk:csrf_token", "csrf-abc");
}

describe("AIReportsPage", () => {
  afterEach(() => {
    vi.restoreAllMocks();
    sessionStorage.clear();
    localStorage.clear();
  });

  it("lists AI reports with their period and links to the detail page", async () => {
    mockAuthenticated();
    vi.spyOn(aiReportsApi, "listAIReports").mockResolvedValue({
      reports: [REPORT],
      meta: { page: 1, per_page: 20, total: 1, total_pages: 1 },
    });

    renderPage();

    const link = await screen.findByRole("link", { name: "2026-01-05 to 2026-01-11" });
    expect(link).toHaveAttribute("href", "/ai-reports/r1");
    expect(screen.getByText(/claude-haiku-5-5/)).toBeInTheDocument();
  });

  it("shows an empty state when there are no reports yet", async () => {
    mockAuthenticated();
    vi.spyOn(aiReportsApi, "listAIReports").mockResolvedValue({
      reports: [],
      meta: { page: 1, per_page: 20, total: 0, total_pages: 0 },
    });

    renderPage();

    expect(await screen.findByText(/No AI reports yet/)).toBeInTheDocument();
  });

  it("shows pagination controls only when there is more than one page", async () => {
    mockAuthenticated();
    vi.spyOn(aiReportsApi, "listAIReports").mockResolvedValue({
      reports: [REPORT],
      meta: { page: 1, per_page: 20, total: 25, total_pages: 2 },
    });

    renderPage();

    expect(await screen.findByText("Page 1 of 2")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Previous" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Next" })).toBeEnabled();
  });

  it("generates a report on demand via the Generate now dialog", async () => {
    mockAuthenticated();
    vi.spyOn(aiReportsApi, "listAIReports").mockResolvedValue({
      reports: [],
      meta: { page: 1, per_page: 20, total: 0, total_pages: 0 },
    });
    const generateSpy = vi.spyOn(aiReportsApi, "generateAIReport").mockResolvedValue(REPORT);
    const user = userEvent.setup();

    renderPage();
    await screen.findByText(/No AI reports yet/);

    await user.click(screen.getByRole("button", { name: "Generate now" }));
    await user.click(screen.getByRole("button", { name: "Generate" }));

    await waitFor(() =>
      expect(generateSpy).toHaveBeenCalledWith("org-1", { period: "last_7_days", period_start: undefined, period_end: undefined }, "csrf-abc"),
    );
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
  });

  it("shows the backend's error when generation fails", async () => {
    mockAuthenticated();
    vi.spyOn(aiReportsApi, "listAIReports").mockResolvedValue({
      reports: [],
      meta: { page: 1, per_page: 20, total: 0, total_pages: 0 },
    });
    vi.spyOn(aiReportsApi, "generateAIReport").mockRejectedValue(
      new ApiError(502, "AI_GENERATION_FAILED", "The AI report could not be generated.", {}),
    );
    const user = userEvent.setup();

    renderPage();
    await screen.findByText(/No AI reports yet/);

    await user.click(screen.getByRole("button", { name: "Generate now" }));
    await user.click(screen.getByRole("button", { name: "Generate" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("The AI report could not be generated.");
  });
});
