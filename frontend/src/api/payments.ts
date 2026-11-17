import { apiFetch, apiFetchWithMeta } from "@/api/client";
import type { PaginationMeta } from "@/types/employee";
import type { PaymentPublic, PaymentRecordedData } from "@/types/payment";

export interface PaymentListResult {
  payments: PaymentPublic[];
  meta: PaginationMeta;
}

export async function listPayments(
  organizationId: string,
  invoiceId: string,
  page = 1,
  perPage = 50,
): Promise<PaymentListResult> {
  const params = new URLSearchParams({ page: String(page), per_page: String(perPage) });
  const { data, meta } = await apiFetchWithMeta<PaymentPublic[], PaginationMeta>(
    `/organizations/${organizationId}/invoices/${invoiceId}/payments?${params.toString()}`,
  );
  return { payments: data, meta };
}

export interface RecordPaymentInput {
  amount: string;
  payment_date: string;
  method: string;
  reference?: string;
  notes?: string;
  idempotency_key: string;
}

// Returns both the payment and the invoice's own freshly-updated
// status/totals in one response (docs/API.md's Payments section) -
// callers should use `data.invoice` directly rather than re-fetching,
// though invalidating the invoice query afterward is still correct
// and keeps every other view of it in sync too.
export function recordPayment(
  organizationId: string,
  invoiceId: string,
  input: RecordPaymentInput,
  csrfToken: string,
): Promise<PaymentRecordedData> {
  return apiFetch<PaymentRecordedData>(`/organizations/${organizationId}/invoices/${invoiceId}/payments`, {
    method: "POST",
    body: input,
    csrfToken,
  });
}
