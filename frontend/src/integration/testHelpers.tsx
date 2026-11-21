// FD-063: shared scaffolding for this directory's cross-module
// integration tests - every test here renders the REAL <App/> (real
// AuthContext/OrganizationContext/router/Sidebar/TopBar, exactly as a
// browser would load it), with only the api/* module functions
// mocked (the one seam every other test file in this codebase already
// mocks at - see src/api/client.ts). That's the deliberate difference
// from this codebase's existing per-page/per-component tests: those
// each mount a single page/component in isolation; these mount the
// whole app and drive it via real clicks and real route changes, the
// one place a wiring bug between modules (auth -> org context ->
// sidebar -> a page) would actually show up.
import { render, screen, waitFor } from "@testing-library/react";
import { expect, vi } from "vitest";

import * as activityApi from "@/api/activity";
import * as aiReportsApi from "@/api/aiReports";
import * as analyticsApi from "@/api/analytics";
import * as authApi from "@/api/auth";
import * as customerRequestsApi from "@/api/customerRequests";
import * as customersApi from "@/api/customers";
import * as departmentsApi from "@/api/departments";
import * as employeesApi from "@/api/employees";
import * as invoicesApi from "@/api/invoices";
import * as notificationsApi from "@/api/notifications";
import * as organizationsApi from "@/api/organizations";
import * as tasksApi from "@/api/tasks";
import { App } from "@/App";
import type { MembershipPublic, MembershipRole, OrganizationPublic } from "@/types/organization";
import type { UserPublic } from "@/types/user";

export const USER: UserPublic = {
  id: "u1",
  name: "Ada Owner",
  email: "ada@flowdesk-e2e.example.com",
  status: "active",
  created_at: "2026-01-01T00:00:00Z",
};

export const ORG: OrganizationPublic = {
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
  created_at: "2026-01-01T00:00:00Z",
};

export function membershipOf(role: MembershipRole, organization: OrganizationPublic = ORG): MembershipPublic {
  return { organization, role, status: "active", joined_at: "2026-01-01T00:00:00Z" };
}

const EMPTY_PAGE_META = { page: 1, per_page: 20, total: 0, total_pages: 0 };

// Every list/aggregate endpoint any dashboard widget, the Sidebar, or
// TopBar might call during a journey - stubbed to harmless empty
// defaults so a test only needs to override the handful it actually
// cares about. Without this, an unmocked api/* call falls through to
// the real `fetch` (no server in a Vitest/jsdom run), rejecting every
// query and burying the assertions that matter under unrelated error
// noise.
export function mockEveryDashboardDependency() {
  vi.spyOn(tasksApi, "listTasks").mockResolvedValue({ tasks: [], meta: EMPTY_PAGE_META });
  vi.spyOn(customerRequestsApi, "listRequests").mockResolvedValue({ requests: [], meta: EMPTY_PAGE_META });
  vi.spyOn(employeesApi, "listEmployees").mockResolvedValue({ employees: [], meta: EMPTY_PAGE_META });
  vi.spyOn(customersApi, "listCustomers").mockResolvedValue({ customers: [], meta: EMPTY_PAGE_META });
  vi.spyOn(departmentsApi, "listDepartments").mockResolvedValue([]);
  vi.spyOn(invoicesApi, "listInvoices").mockResolvedValue({ invoices: [], meta: EMPTY_PAGE_META });
  vi.spyOn(invoicesApi, "getFinancialSummary").mockResolvedValue({
    total_invoiced: "0.00",
    total_collected: "0.00",
    outstanding_balance: "0.00",
    overdue_invoice_count: 0,
    period_start: "2026-01-01",
    period_end: "2026-01-31",
    monthly_revenue_collected: "0.00",
    recent_payments: [],
  });
  vi.spyOn(aiReportsApi, "listAIReports").mockResolvedValue({ reports: [], meta: EMPTY_PAGE_META });
  vi.spyOn(activityApi, "listActivity").mockResolvedValue({ entries: [], meta: EMPTY_PAGE_META });
  vi.spyOn(notificationsApi, "listNotifications").mockResolvedValue({ notifications: [], meta: EMPTY_PAGE_META });
  vi.spyOn(analyticsApi, "getOverviewAnalytics").mockResolvedValue({
    period_start: "2026-01-01",
    period_end: "2026-01-31",
    employee_count: 1,
    active_tasks: 0,
    completed_tasks: 0,
    overdue_tasks: 0,
    open_requests: 0,
    monthly_invoiced: "0.00",
    monthly_collected: "0.00",
  });
  vi.spyOn(analyticsApi, "getEmployeeAnalytics").mockResolvedValue([]);
  vi.spyOn(analyticsApi, "getDepartmentAnalytics").mockResolvedValue([]);
  vi.spyOn(analyticsApi, "getFinancialAnalytics").mockResolvedValue({
    total_invoiced: "0.00",
    total_collected: "0.00",
    outstanding_balance: "0.00",
    overdue_invoice_count: 0,
    period_start: "2026-01-01",
    period_end: "2026-01-31",
    monthly_revenue_collected: "0.00",
    recent_payments: [],
    revenue_by_day: [],
    invoice_distribution: {},
  });
}

// Logs the app in as a single-organization member of the given role,
// via the same getCurrentUser/listOrganizations calls AuthContext and
// OrganizationContext really make on mount - never a hand-fed context
// value, so a wiring bug between the two contexts would still surface.
export function mockAuthenticatedSession(role: MembershipRole) {
  vi.spyOn(authApi, "getCurrentUser").mockResolvedValue(USER);
  vi.spyOn(organizationsApi, "listOrganizations").mockResolvedValue([membershipOf(role)]);
  mockEveryDashboardDependency();
}

// Mounts the real <App/>, starting at whatever the browser's current
// location is - "/" for the first render in a fresh module graph.
// `src/routes/router.tsx`'s `router` is a module-level
// createBrowserRouter singleton: every render() in the SAME test file
// shares it and therefore its current location, so a test cannot
// reliably "jump" to an arbitrary starting path by force (a raw
// `window.history.pushState` is invisible to it - it only reacts to
// its own navigate() calls or a real popstate event - and calling its
// own `router.navigate()` from test code races unpredictably against
// the app's own in-flight redirects, e.g. ProtectedRoute's auth
// check). Each test in this directory instead starts at "/" like a
// real page load and reaches every other page by clicking real
// links/NavLinks, the same mechanism a user would use - which is also
// why each journey lives in its OWN test file: a fresh module graph
// per file (vitest's default test isolation) is what actually
// guarantees "/" on every run, rather than wherever a previous test
// in a shared file last clicked to.
export function renderApp() {
  render(<App />);
}

export async function waitForHeading(name: string | RegExp) {
  await waitFor(() => expect(screen.getByRole("heading", { name })).toBeInTheDocument());
}
