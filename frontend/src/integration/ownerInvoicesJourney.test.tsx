// FD-063: cross-module critical journey - see testHelpers.tsx's own
// header comment for why these tests mount the whole <App/> rather
// than a single page, and why each journey lives in its own file.
import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import * as invoicesApi from "@/api/invoices";
import { mockAuthenticatedSession, renderApp } from "@/integration/testHelpers";
import type { InvoicePublic } from "@/types/invoice";

afterEach(() => {
  vi.restoreAllMocks();
  sessionStorage.clear();
  localStorage.clear();
});

describe("owner invoices journey", () => {
  it("an Owner navigates from the dashboard to Invoices and sees the real invoice list render", async () => {
    mockAuthenticatedSession("owner");
    const invoice: InvoicePublic = {
      id: "inv-1",
      organization_id: "org-1",
      customer_id: "c1",
      invoice_number: "INV-0001",
      status: "sent",
      currency: "USD",
      issue_date: "2026-01-01",
      due_date: "2026-01-31",
      subtotal: "500.00",
      tax_total: "0.00",
      discount_type: "flat",
      discount_value: "0.00",
      discount_total: "0.00",
      total: "500.00",
      notes: null,
      payment_terms: null,
      created_by: "m1",
      created_at: "2026-01-01T00:00:00Z",
    };
    vi.spyOn(invoicesApi, "listInvoices").mockResolvedValue({
      invoices: [invoice],
      meta: { page: 1, per_page: 20, total: 1, total_pages: 1 },
    });

    const user = userEvent.setup();
    renderApp();

    const nav = await screen.findByRole("navigation", { name: "Primary" });
    await user.click(within(nav).getByRole("link", { name: "Invoices" }));

    expect(await screen.findByText("INV-0001")).toBeInTheDocument();
  });
});
