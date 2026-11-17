import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, describe, expect, it, vi } from "vitest";
import { createMemoryRouter, RouterProvider } from "react-router-dom";

import * as authApi from "@/api/auth";
import { ApiError } from "@/api/client";
import * as customersApi from "@/api/customers";
import * as invoicesApi from "@/api/invoices";
import * as organizationsApi from "@/api/organizations";
import * as paymentsApi from "@/api/payments";
import { AuthProvider } from "@/contexts/AuthContext";
import { OrganizationProvider } from "@/contexts/OrganizationContext";
import { InvoiceDetailPage } from "@/pages/InvoiceDetailPage";
import type { CustomerPublic } from "@/types/customer";
import type { InvoiceLineItemPublic, InvoicePublic } from "@/types/invoice";
import type { MembershipPublic, OrganizationPublic } from "@/types/organization";
import type { PaymentPublic } from "@/types/payment";
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

const SENT_INVOICE: InvoicePublic = {
  id: "inv-1",
  organization_id: "org-1",
  customer_id: "c1",
  invoice_number: "INV-0001",
  status: "sent",
  issue_date: "2026-01-01",
  due_date: "2026-02-01",
  currency: "USD",
  subtotal: "100.00",
  tax_total: "0.00",
  discount_type: "flat",
  discount_value: "0.00",
  discount_total: "0.00",
  total: "100.00",
  notes: null,
  payment_terms: "Net 30",
  created_by: "m1",
  created_at: "now",
};

const SAMPLE_LINE_ITEMS: InvoiceLineItemPublic[] = [
  {
    id: "li-1",
    invoice_id: "inv-1",
    description: "Widget",
    quantity: "1.00",
    unit_price: "100.00",
    tax_rate: null,
    line_total: "100.00",
    created_at: "now",
  },
];

function membership(role: MembershipPublic["role"]): MembershipPublic {
  return { organization: ORG, role, status: "active", joined_at: "now" };
}

function renderPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const router = createMemoryRouter(
    [
      { path: "/invoices/:invoiceId", element: <InvoiceDetailPage /> },
      { path: "/invoices", element: <div>Invoice list page</div> },
      { path: "/invoices/:invoiceId/edit", element: <div>Invoice edit page</div> },
    ],
    { initialEntries: ["/invoices/inv-1"] },
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

function mockCommonQueries(options: { payments?: PaymentPublic[] } = {}) {
  vi.spyOn(customersApi, "getCustomer").mockResolvedValue(SAMPLE_CUSTOMER);
  vi.spyOn(invoicesApi, "listInvoiceLineItems").mockResolvedValue(SAMPLE_LINE_ITEMS);
  vi.spyOn(paymentsApi, "listPayments").mockResolvedValue({
    payments: options.payments ?? [],
    meta: { page: 1, per_page: 50, total: (options.payments ?? []).length, total_pages: 1 },
  });
}

describe("InvoiceDetailPage", () => {
  afterEach(() => {
    vi.restoreAllMocks();
    sessionStorage.clear();
    localStorage.clear();
  });

  it("shows the invoice's fields and line items", async () => {
    mockAuthenticated("owner");
    vi.spyOn(invoicesApi, "getInvoice").mockResolvedValue(SENT_INVOICE);
    mockCommonQueries();

    renderPage();

    expect(await screen.findByRole("heading", { name: "Invoice INV-0001" })).toBeInTheDocument();
    expect(await screen.findByText("Jane Customer")).toBeInTheDocument();
    expect(screen.getByText("Widget")).toBeInTheDocument();
    expect(screen.getByText("Net 30")).toBeInTheDocument();
  });

  it("computes amount paid and balance due from the recorded payments", async () => {
    mockAuthenticated("owner");
    vi.spyOn(invoicesApi, "getInvoice").mockResolvedValue(SENT_INVOICE);
    mockCommonQueries({
      payments: [
        {
          id: "p1",
          invoice_id: "inv-1",
          amount: "40.00",
          payment_date: "2026-01-15",
          method: "cash",
          reference: null,
          notes: null,
          idempotency_key: "key-1",
          recorded_by: "m1",
          created_at: "now",
        },
      ],
    });

    renderPage();

    await screen.findByText("Amount paid");
    expect((await screen.findAllByText("USD 40.00")).length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText("USD 60.00")).toBeInTheDocument();
  });

  it("shows Issue/Cancel actions and a PDF link for an owner on a payable invoice", async () => {
    mockAuthenticated("owner");
    vi.spyOn(invoicesApi, "getInvoice").mockResolvedValue(SENT_INVOICE);
    mockCommonQueries();

    renderPage();

    expect(await screen.findByRole("button", { name: "Cancel invoice" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Issue invoice" })).not.toBeInTheDocument();
    const pdfLink = screen.getByRole("link", { name: "View PDF" });
    expect(pdfLink).toHaveAttribute("href", "/api/v1/organizations/org-1/invoices/inv-1/pdf");
  });

  it("shows an Edit link and Issue button for a draft invoice", async () => {
    mockAuthenticated("owner");
    vi.spyOn(invoicesApi, "getInvoice").mockResolvedValue({ ...SENT_INVOICE, status: "draft" });
    mockCommonQueries();

    renderPage();

    expect(await screen.findByRole("link", { name: "Edit" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Issue invoice" })).toBeInTheDocument();
  });

  it("does not show management actions for a Manager (no INVOICE_PAYMENT_MANAGE)", async () => {
    mockAuthenticated("manager");
    vi.spyOn(invoicesApi, "getInvoice").mockResolvedValue(SENT_INVOICE);
    mockCommonQueries();

    renderPage();

    await screen.findByRole("heading", { name: "Invoice INV-0001" });
    expect(screen.queryByRole("button", { name: "Cancel invoice" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Record payment" })).not.toBeInTheDocument();
  });

  it("issues a draft invoice", async () => {
    mockAuthenticated("owner");
    vi.spyOn(invoicesApi, "getInvoice").mockResolvedValue({ ...SENT_INVOICE, status: "draft" });
    mockCommonQueries();
    const issueSpy = vi.spyOn(invoicesApi, "issueInvoice").mockResolvedValue(SENT_INVOICE);
    const user = userEvent.setup();

    renderPage();
    await user.click(await screen.findByRole("button", { name: "Issue invoice" }));

    await waitFor(() => expect(issueSpy).toHaveBeenCalledWith("org-1", "inv-1", "csrf-abc"));
  });

  it("records a payment with a generated idempotency key", async () => {
    mockAuthenticated("owner");
    vi.spyOn(invoicesApi, "getInvoice").mockResolvedValue(SENT_INVOICE);
    mockCommonQueries();
    const recordSpy = vi.spyOn(paymentsApi, "recordPayment").mockResolvedValue({
      payment: {
        id: "p1",
        invoice_id: "inv-1",
        amount: "40.00",
        payment_date: "2026-01-15",
        method: "cash",
        reference: null,
        notes: null,
        idempotency_key: "generated-key",
        recorded_by: "m1",
        created_at: "now",
      },
      invoice: { ...SENT_INVOICE, status: "partially_paid" },
      amount_paid: "40.00",
      balance_due: "60.00",
    });
    const user = userEvent.setup();

    renderPage();
    await user.type(await screen.findByLabelText("Amount"), "40.00");
    await user.type(screen.getByLabelText("Date"), "2026-01-15");
    await user.type(screen.getByLabelText("Method"), "cash");
    await user.click(screen.getByRole("button", { name: "Record payment" }));

    await waitFor(() =>
      expect(recordSpy).toHaveBeenCalledWith(
        "org-1",
        "inv-1",
        expect.objectContaining({
          amount: "40.00",
          payment_date: "2026-01-15",
          method: "cash",
          idempotency_key: expect.any(String),
        }),
        "csrf-abc",
      ),
    );
  });

  it("shows an error message when cancelling fails", async () => {
    mockAuthenticated("owner");
    vi.spyOn(invoicesApi, "getInvoice").mockResolvedValue(SENT_INVOICE);
    mockCommonQueries();
    vi.spyOn(invoicesApi, "cancelInvoice").mockRejectedValue(
      new ApiError(422, "INVALID_STATUS_TRANSITION", "Cannot cancel once a payment has been recorded.", {}),
    );
    const user = userEvent.setup();

    renderPage();
    await user.click(await screen.findByRole("button", { name: "Cancel invoice" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Cannot cancel once a payment has been recorded.");
  });

  it("shows an error message when the invoice fails to load", async () => {
    mockAuthenticated("owner");
    vi.spyOn(invoicesApi, "getInvoice").mockRejectedValue(new ApiError(404, "NOT_FOUND", "Not found.", {}));

    renderPage();

    expect(await screen.findByRole("alert")).toHaveTextContent("Not found.");
  });
});
