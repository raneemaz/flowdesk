import { apiFetch, apiFetchWithMeta } from "@/api/client";
import type { PaginationMeta } from "@/types/employee";
import type {
  DiscountType,
  FinancialSummaryPublic,
  InvoiceLineItemPublic,
  InvoicePublic,
  InvoiceStatus,
} from "@/types/invoice";

export interface ListInvoicesFilters {
  customerId?: string;
  status?: InvoiceStatus;
  dueDateFrom?: string;
  dueDateTo?: string;
  page?: number;
  perPage?: number;
}

export interface InvoiceListResult {
  invoices: InvoicePublic[];
  meta: PaginationMeta;
}

export async function listInvoices(
  organizationId: string,
  filters: ListInvoicesFilters = {},
): Promise<InvoiceListResult> {
  const params = new URLSearchParams();
  if (filters.customerId) params.set("customer_id", filters.customerId);
  if (filters.status) params.set("status", filters.status);
  if (filters.dueDateFrom) params.set("due_date_from", filters.dueDateFrom);
  if (filters.dueDateTo) params.set("due_date_to", filters.dueDateTo);
  params.set("page", String(filters.page ?? 1));
  params.set("per_page", String(filters.perPage ?? 20));

  const { data, meta } = await apiFetchWithMeta<InvoicePublic[], PaginationMeta>(
    `/organizations/${organizationId}/invoices?${params.toString()}`,
  );
  return { invoices: data, meta };
}

export function getInvoice(organizationId: string, invoiceId: string): Promise<InvoicePublic> {
  return apiFetch<InvoicePublic>(`/organizations/${organizationId}/invoices/${invoiceId}`);
}

// Not paginated (docs/API.md's Invoices section) - an invoice's own
// line items are never large enough to need it.
export function listInvoiceLineItems(organizationId: string, invoiceId: string): Promise<InvoiceLineItemPublic[]> {
  return apiFetch<InvoiceLineItemPublic[]>(`/organizations/${organizationId}/invoices/${invoiceId}/line-items`);
}

export interface LineItemInput {
  description: string;
  quantity: string;
  unit_price: string;
  tax_rate?: string;
}

export interface InvoiceFormInput {
  customer_id: string;
  currency: string;
  issue_date?: string;
  due_date?: string;
  notes?: string;
  payment_terms?: string;
  discount_type: DiscountType;
  discount_value: string;
  line_items: LineItemInput[];
}

// Never accepts status or invoice_number - a new invoice always
// starts draft, with a server-generated number (docs/API.md's
// Invoices section).
export function createInvoice(
  organizationId: string,
  input: InvoiceFormInput,
  csrfToken: string,
): Promise<InvoicePublic> {
  return apiFetch<InvoicePublic>(`/organizations/${organizationId}/invoices`, {
    method: "POST",
    body: input,
    csrfToken,
  });
}

// Draft-only server-side (422 INVOICE_LOCKED otherwise) - this form
// is only ever reachable for a draft invoice (see InvoiceFormPage),
// but the real lock is the backend's, not this page's own routing.
// `line_items`, if sent, replaces the entire set.
export function updateInvoice(
  organizationId: string,
  invoiceId: string,
  input: Partial<InvoiceFormInput>,
  csrfToken: string,
): Promise<InvoicePublic> {
  return apiFetch<InvoicePublic>(`/organizations/${organizationId}/invoices/${invoiceId}`, {
    method: "PATCH",
    body: input,
    csrfToken,
  });
}

// draft -> sent, not idempotent (re-issuing an already-sent invoice
// is a 422, docs/API.md's Invoices section).
export function issueInvoice(organizationId: string, invoiceId: string, csrfToken: string): Promise<InvoicePublic> {
  return apiFetch<InvoicePublic>(`/organizations/${organizationId}/invoices/${invoiceId}/issue`, {
    method: "PATCH",
    csrfToken,
  });
}

// -> cancelled, idempotent; blocked once a payment has been recorded
// (422, docs/API.md's Invoices section).
export function cancelInvoice(organizationId: string, invoiceId: string, csrfToken: string): Promise<InvoicePublic> {
  return apiFetch<InvoicePublic>(`/organizations/${organizationId}/invoices/${invoiceId}/cancel`, {
    method: "PATCH",
    csrfToken,
  });
}

export interface FinancialSummaryFilters {
  periodStart?: string;
  periodEnd?: string;
}

// Requires FINANCIAL_REPORTS_VIEW, not INVOICE_PAYMENT_MANAGE -
// deliberately a different permission than every other function here
// (docs/API.md's Financial reports section); only call this from a
// place already gated by canViewFinancialReports.
export function getFinancialSummary(
  organizationId: string,
  filters: FinancialSummaryFilters = {},
): Promise<FinancialSummaryPublic> {
  const params = new URLSearchParams();
  if (filters.periodStart) params.set("period_start", filters.periodStart);
  if (filters.periodEnd) params.set("period_end", filters.periodEnd);
  const query = params.toString();
  return apiFetch<FinancialSummaryPublic>(
    `/organizations/${organizationId}/invoices/financial-summary${query ? `?${query}` : ""}`,
  );
}

// Not a JSON endpoint - the caller renders this as a plain link/anchor
// (credentials ride along automatically for a same-origin navigation,
// same as every other request the browser already sends cookies on;
// no need to fetch-and-blob it in JS). See docs/API.md's Invoice PDF
// section.
export function invoicePdfUrl(organizationId: string, invoiceId: string): string {
  const base = (import.meta.env.VITE_API_BASE_URL as string | undefined) ?? "/api/v1";
  return `${base}/organizations/${organizationId}/invoices/${invoiceId}/pdf`;
}
