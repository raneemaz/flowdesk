import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, describe, expect, it, vi } from "vitest";
import { createMemoryRouter, RouterProvider } from "react-router-dom";

import * as authApi from "@/api/auth";
import * as customersApi from "@/api/customers";
import * as invoicesApi from "@/api/invoices";
import * as organizationsApi from "@/api/organizations";
import { AuthProvider } from "@/contexts/AuthContext";
import { OrganizationProvider } from "@/contexts/OrganizationContext";
import { InvoiceFormPage } from "@/pages/InvoiceFormPage";
import type { CustomerPublic } from "@/types/customer";
import type { InvoiceLineItemPublic, InvoicePublic } from "@/types/invoice";
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

const DRAFT_INVOICE: InvoicePublic = {
  id: "inv-1",
  organization_id: "org-1",
  customer_id: "c1",
  invoice_number: "INV-0001",
  status: "draft",
  issue_date: null,
  due_date: null,
  currency: "USD",
  subtotal: "100.00",
  tax_total: "0.00",
  discount_type: "flat",
  discount_value: "0.00",
  discount_total: "0.00",
  total: "100.00",
  notes: null,
  payment_terms: null,
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

function renderPage(initialPath: string) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const router = createMemoryRouter(
    [
      { path: "/invoices/new", element: <InvoiceFormPage /> },
      { path: "/invoices/:invoiceId/edit", element: <InvoiceFormPage /> },
      { path: "/invoices/:invoiceId", element: <div>Invoice detail page</div> },
      { path: "/invoices", element: <div>Invoice list page</div> },
    ],
    { initialEntries: [initialPath] },
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

describe("InvoiceFormPage - create", () => {
  afterEach(() => {
    vi.restoreAllMocks();
    sessionStorage.clear();
    localStorage.clear();
  });

  it("creates an invoice with a customer and a line item", async () => {
    mockAuthenticated("owner");
    vi.spyOn(customersApi, "listCustomers").mockResolvedValue({
      customers: [SAMPLE_CUSTOMER],
      meta: { page: 1, per_page: 100, total: 1, total_pages: 1 },
    });
    const createSpy = vi.spyOn(invoicesApi, "createInvoice").mockResolvedValue(DRAFT_INVOICE);
    const user = userEvent.setup();

    renderPage("/invoices/new");
    await screen.findByRole("option", { name: "Jane Customer" });
    await user.selectOptions(screen.getByLabelText("Customer"), "c1");
    await user.click(screen.getByRole("button", { name: "+ Add line" }));
    await user.type(screen.getByLabelText("Description"), "Widget");
    await user.clear(screen.getByLabelText("Unit price"));
    await user.type(screen.getByLabelText("Unit price"), "100.00");
    await user.click(screen.getByRole("button", { name: "Create invoice" }));

    await waitFor(() =>
      expect(createSpy).toHaveBeenCalledWith(
        "org-1",
        expect.objectContaining({
          customer_id: "c1",
          currency: "USD",
          line_items: [expect.objectContaining({ description: "Widget", unit_price: "100.00" })],
        }),
        "csrf-abc",
      ),
    );
  });

  it("requires a customer", async () => {
    mockAuthenticated("owner");
    vi.spyOn(customersApi, "listCustomers").mockResolvedValue({
      customers: [SAMPLE_CUSTOMER],
      meta: { page: 1, per_page: 100, total: 1, total_pages: 1 },
    });
    const createSpy = vi.spyOn(invoicesApi, "createInvoice");
    const user = userEvent.setup();

    renderPage("/invoices/new");
    await screen.findByLabelText("Customer");
    await user.click(screen.getByRole("button", { name: "Create invoice" }));

    expect(await screen.findByText("Customer is required.")).toBeInTheDocument();
    expect(createSpy).not.toHaveBeenCalled();
  });

  it("removes a line item", async () => {
    mockAuthenticated("owner");
    vi.spyOn(customersApi, "listCustomers").mockResolvedValue({
      customers: [SAMPLE_CUSTOMER],
      meta: { page: 1, per_page: 100, total: 1, total_pages: 1 },
    });
    const user = userEvent.setup();

    renderPage("/invoices/new");
    await user.click(await screen.findByRole("button", { name: "+ Add line" }));
    expect(screen.getByLabelText("Description")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Remove" }));
    expect(screen.queryByLabelText("Description")).not.toBeInTheDocument();
  });
});

describe("InvoiceFormPage - edit", () => {
  afterEach(() => {
    vi.restoreAllMocks();
    sessionStorage.clear();
    localStorage.clear();
  });

  it("populates the form with the existing draft invoice and its line items", async () => {
    mockAuthenticated("owner");
    vi.spyOn(customersApi, "listCustomers").mockResolvedValue({
      customers: [SAMPLE_CUSTOMER],
      meta: { page: 1, per_page: 100, total: 1, total_pages: 1 },
    });
    vi.spyOn(invoicesApi, "getInvoice").mockResolvedValue(DRAFT_INVOICE);
    vi.spyOn(invoicesApi, "listInvoiceLineItems").mockResolvedValue(SAMPLE_LINE_ITEMS);

    renderPage("/invoices/inv-1/edit");

    expect(await screen.findByDisplayValue("Widget")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Edit invoice" })).toBeInTheDocument();
  });

  it("submits an update via PATCH", async () => {
    mockAuthenticated("owner");
    vi.spyOn(customersApi, "listCustomers").mockResolvedValue({
      customers: [SAMPLE_CUSTOMER],
      meta: { page: 1, per_page: 100, total: 1, total_pages: 1 },
    });
    vi.spyOn(invoicesApi, "getInvoice").mockResolvedValue(DRAFT_INVOICE);
    vi.spyOn(invoicesApi, "listInvoiceLineItems").mockResolvedValue(SAMPLE_LINE_ITEMS);
    const updateSpy = vi.spyOn(invoicesApi, "updateInvoice").mockResolvedValue(DRAFT_INVOICE);
    const user = userEvent.setup();

    renderPage("/invoices/inv-1/edit");
    await screen.findByDisplayValue("Widget");
    await user.click(screen.getByRole("button", { name: "Save changes" }));

    await waitFor(() => expect(updateSpy).toHaveBeenCalledWith("org-1", "inv-1", expect.any(Object), "csrf-abc"));
  });

  it("shows a locked message for a non-draft invoice instead of the form", async () => {
    mockAuthenticated("owner");
    vi.spyOn(customersApi, "listCustomers").mockResolvedValue({
      customers: [SAMPLE_CUSTOMER],
      meta: { page: 1, per_page: 100, total: 1, total_pages: 1 },
    });
    vi.spyOn(invoicesApi, "getInvoice").mockResolvedValue({ ...DRAFT_INVOICE, status: "sent" });
    vi.spyOn(invoicesApi, "listInvoiceLineItems").mockResolvedValue(SAMPLE_LINE_ITEMS);

    renderPage("/invoices/inv-1/edit");

    expect(await screen.findByRole("alert")).toHaveTextContent("Only a draft invoice can be edited");
    expect(screen.queryByLabelText("Customer")).not.toBeInTheDocument();
  });
});
