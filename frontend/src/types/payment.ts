// Mirrors backend/openapi.yaml's PaymentPublic/PaymentRecordedData
// schemas exactly (Payment.to_public_dict, the POST .../payments
// response shape).
import type { InvoicePublic } from "@/types/invoice";

export interface PaymentPublic {
  id: string;
  invoice_id: string;
  amount: string;
  payment_date: string;
  method: string;
  reference: string | null;
  notes: string | null;
  idempotency_key: string;
  recorded_by: string;
  created_at: string;
}

export interface PaymentRecordedData {
  payment: PaymentPublic;
  invoice: InvoicePublic;
  amount_paid: string;
  balance_due: string;
}
