// Mirrors backend/openapi.yaml's InvoicePublic/InvoiceLineItemPublic/
// FinancialSummaryPublic schemas exactly (Invoice.to_public_dict,
// InvoiceLineItem.to_public_dict, app.invoices.service.get_financial_summary).
// Money fields are decimal strings, never numbers - never parse them
// to a JS number for anything that gets submitted back to the API;
// only a non-authoritative display estimate may do that (see
// features/invoices/calculations.ts).
import type { PaymentPublic } from "@/types/payment";

export type InvoiceStatus = "draft" | "sent" | "partially_paid" | "paid" | "overdue" | "cancelled";
export type DiscountType = "flat" | "percentage";

export interface InvoiceLineItemPublic {
  id: string;
  invoice_id: string;
  description: string;
  quantity: string;
  unit_price: string;
  tax_rate: string | null;
  line_total: string;
  created_at: string;
}

export interface InvoicePublic {
  id: string;
  organization_id: string;
  customer_id: string;
  invoice_number: string;
  status: InvoiceStatus;
  issue_date: string | null;
  due_date: string | null;
  currency: string;
  subtotal: string;
  tax_total: string;
  discount_type: DiscountType;
  discount_value: string;
  discount_total: string;
  total: string;
  notes: string | null;
  payment_terms: string | null;
  created_by: string;
  created_at: string;
}

export interface FinancialSummaryPublic {
  total_invoiced: string;
  total_collected: string;
  outstanding_balance: string;
  overdue_invoice_count: number;
  period_start: string;
  period_end: string;
  monthly_revenue_collected: string;
  recent_payments: PaymentPublic[];
}
