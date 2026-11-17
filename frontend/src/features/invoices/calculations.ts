import type { DiscountType } from "@/types/invoice";
import type { LineItemFormValues } from "@/features/invoices/schemas";

// A live PREVIEW only, shown in the editor while a line item is being
// typed, before the form is ever submitted - never sent to the API
// and never trusted as the real total (spec Section 32: "never
// duplicate backend business logic"; Epic E06's own acceptance
// criterion: "client-submitted totals are never authoritative").
// app/invoices/service.py's recalculate_invoice remains the one real
// source of truth - its own response after a create/update is what
// this page actually displays once a save succeeds. Uses plain JS
// numbers (not Decimal) for that reason - a rounding difference of a
// cent in a preview is an acceptable trade for not needing a decimal
// library in the browser for a value nothing ever acts on.
export interface InvoicePreviewTotals {
  subtotal: number;
  taxTotal: number;
  discountTotal: number;
  total: number;
}

function toNumber(value: string | undefined): number {
  const parsed = Number.parseFloat(value ?? "");
  return Number.isFinite(parsed) ? parsed : 0;
}

export function previewInvoiceTotals(
  lineItems: LineItemFormValues[],
  discountType: DiscountType,
  discountValue: string | undefined,
): InvoicePreviewTotals {
  let subtotal = 0;
  let taxTotal = 0;
  for (const item of lineItems) {
    const lineTotal = toNumber(item.quantity) * toNumber(item.unit_price);
    subtotal += lineTotal;
    if (item.tax_rate) {
      taxTotal += (lineTotal * toNumber(item.tax_rate)) / 100;
    }
  }

  const discountInput = toNumber(discountValue);
  const discountTotal = discountType === "percentage" ? (subtotal * discountInput) / 100 : discountInput;

  const total = Math.max(subtotal + taxTotal - discountTotal, 0);
  return { subtotal, taxTotal, discountTotal, total };
}

export function formatMoney(value: number, currency: string): string {
  return `${currency} ${value.toFixed(2)}`;
}

// Display-only, same reasoning as previewInvoiceTotals above: summing
// already-recorded (server-validated) payment amounts for the page to
// show isn't re-deriving a business rule (which amounts were valid in
// the first place is entirely app.payments.service.record_payment's
// own call) - it's the same category of trust as showing
// `invoice.total` without recomputing tax.
export function sumMoney(amounts: string[]): number {
  return amounts.reduce((total, amount) => total + toNumber(amount), 0);
}
