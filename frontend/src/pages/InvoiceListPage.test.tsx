import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, describe, expect, it, vi } from "vitest";
import { createMemoryRouter, RouterProvider } from "react-router-dom";

import * as authApi from "@/api/auth";
import { ApiError } from "@/api/client";
import * as customersApi from "@/api/customers";
import * as invoicesApi from "@/api/invoices";
import * as organizationsApi from "@/api/organizations";
import { AuthProvider } from "@/contexts/AuthContext";
import { OrganizationProvider } from "@/contexts/OrganizationContext";
import { InvoiceListPage } from "@/pages/InvoiceListPage";
import type { CustomerPublic } from "@/types/customer";
import type { InvoicePublic } from "@/types/invoice";
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

const SAMPLE_CUSTOMER: CustomerPublic = {
  id: "c1",
  organization_id: "org-1",
  name: "Jane Customer",
  email: null,
  phone: null,
  company: null,
  address: null,
  notes: null,
  status: "active",
  created_at: "now",
};

const SAMPLE_INVOICE: InvoicePublic = {
  id: "inv-1",
  organization_id: "org-1",
  customer_id: "c1",
  invoice_number: "INV-0001",
  status: "draft",
  issue_date: null,
  due_date: null,
  currency: "USD",
  subtotal: "0.00",
  tax_total: "0.00",
  discount_type: "flat",
  discount_value: "0.00",
  discount_total: "0.00",
  total: "0.00",
  notes: null,
  payment_terms: null,
  created_by: "m1",
  created_at: "now",
};

function membership(role: MembershipPublic["role"]): MembershipPublic {
  return { organization: ORG, role, status: "active", joined_at: "now" };
}

function renderPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const router = createMemoryRouter(
    [
      { path: "/invoices", element: <InvoiceListPage /> },
      { path: "/invoices/:invoiceId", element: <div>Invoice detail page</div> },
      { path: "/invoices/new", element: <div>New invoice page</div> },
      { path: "/", element: <div>Home page</div> },
    ],
    { initialEntries: ["/invoices"] },
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

describe("InvoiceListPage", () => {
  afterEach(() => {
    vi.restoreAllMocks();
    sessionStorage.clear();
    localStorage.clear();
  });

  it("lists invoices for an owner, resolving the customer name", async () => {
    mockAuthenticated("owner");
    vi.spyOn(customersApi, "listCustomers").mockResolvedValue({
      customers: [SAMPLE_CUSTOMER],
      meta: { page: 1, per_page: 100, total: 1, total_pages: 1 },
    });
    vi.spyOn(invoicesApi, "listInvoices").mockResolvedValue({
      invoices: [SAMPLE_INVOICE],
      meta: { page: 1, per_page: 20, total: 1, total_pages: 1 },
    });
    vi.spyOn(invoicesApi, "getFinancialSummary").mockResolvedValue({
      total_invoiced: "100.00",
      total_collected: "40.00",
      outstanding_balance: "60.00",
      overdue_invoice_count: 0,
      period_start: "2026-01-01",
      period_end: "2026-01-31",
      monthly_revenue_collected: "40.00",
      recent_payments: [],
    });

    renderPage();

    expect(await screen.findByText("INV-0001")).toBeInTheDocument();
    expect(within(screen.getByRole("table")).getByText("Jane Customer")).toBeInTheDocument();
    expect(await screen.findByText("100.00")).toBeInTheDocument();
    expect(screen.getByText("60.00")).toBeInTheDocument();
  });

  it("does not request the financial summary for a role without FINANCIAL_REPORTS_VIEW", async () => {
    // A Manager lacks both INVOICE_PAYMENT_MANAGE and FINANCIAL_REPORTS_VIEW
    // server-side; reaching this page directly by URL (the link itself
    // is hidden) should still never even call getFinancialSummary -
    // canViewFinancialReports is a UI-only hint, but this proves the
    // component actually consults it rather than fetching unconditionally.
    mockAuthenticated("manager");
    vi.spyOn(customersApi, "listCustomers").mockResolvedValue({
      customers: [],
      meta: { page: 1, per_page: 100, total: 0, total_pages: 0 },
    });
    const summarySpy = vi.spyOn(invoicesApi, "getFinancialSummary");
    vi.spyOn(invoicesApi, "listInvoices").mockResolvedValue({
      invoices: [],
      meta: { page: 1, per_page: 20, total: 0, total_pages: 0 },
    });

    renderPage();
    await waitFor(() => expect(screen.getByRole("heading", { name: "Invoices" })).toBeInTheDocument());

    expect(summarySpy).not.toHaveBeenCalled();
  });

  it("shows a New invoice link for an owner", async () => {
    mockAuthenticated("owner");
    vi.spyOn(customersApi, "listCustomers").mockResolvedValue({
      customers: [],
      meta: { page: 1, per_page: 100, total: 0, total_pages: 0 },
    });
    vi.spyOn(invoicesApi, "listInvoices").mockResolvedValue({
      invoices: [],
      meta: { page: 1, per_page: 20, total: 0, total_pages: 0 },
    });

    renderPage();

    expect(await screen.findByRole("link", { name: "+ New invoice" })).toBeInTheDocument();
  });

  it("applies filters only after submitting", async () => {
    mockAuthenticated("owner");
    vi.spyOn(customersApi, "listCustomers").mockResolvedValue({
      customers: [SAMPLE_CUSTOMER],
      meta: { page: 1, per_page: 100, total: 1, total_pages: 1 },
    });
    const listSpy = vi.spyOn(invoicesApi, "listInvoices").mockResolvedValue({
      invoices: [],
      meta: { page: 1, per_page: 20, total: 0, total_pages: 0 },
    });
    const user = userEvent.setup();

    renderPage();
    await waitFor(() => expect(screen.getByRole("heading", { name: "Invoices" })).toBeInTheDocument());

    await user.selectOptions(screen.getByLabelText("Status"), "Overdue");
    await user.click(screen.getByRole("button", { name: "Search" }));

    await waitFor(() => expect(listSpy).toHaveBeenCalledWith("org-1", expect.objectContaining({ status: "overdue" })));
  });

  it("shows an error message when the list fails to load", async () => {
    mockAuthenticated("owner");
    vi.spyOn(customersApi, "listCustomers").mockResolvedValue({
      customers: [],
      meta: { page: 1, per_page: 100, total: 0, total_pages: 0 },
    });
    vi.spyOn(invoicesApi, "listInvoices").mockRejectedValue(new ApiError(403, "FORBIDDEN", "Forbidden.", {}));

    renderPage();

    expect(await screen.findByRole("alert")).toHaveTextContent("Forbidden.");
  });
});
