import type { MembershipRole } from "@/types/organization";
import type { InvoiceStatus } from "@/types/invoice";

// UI-ONLY hint mirroring backend/app/authz/permissions.py's
// INVOICE_PAYMENT_MANAGE scope (full for Owner/Accountant, none for
// Manager/Employee/CustomerSupport) - NEVER the real authorization
// boundary (spec Section 7.3/32). The backend independently
// re-derives and re-enforces this on every request.
export function canManageInvoices(viewerRole: MembershipRole): boolean {
  return viewerRole === "owner" || viewerRole === "accountant";
}

// Mirrors FINANCIAL_REPORTS_VIEW - today an identical Owner/Accountant
// matrix to INVOICE_PAYMENT_MANAGE above, but kept as its own function
// rather than reused, the same way the backend keeps them as two
// separate permissions (docs/API.md's Financial reports section) -
// so a future role change to either doesn't silently affect the other.
export function canViewFinancialReports(viewerRole: MembershipRole): boolean {
  return viewerRole === "owner" || viewerRole === "accountant";
}

// Mirrors app.invoices.service.update_invoice's own gate - editing
// (and therefore reaching the editor at all) is draft-only.
export function canEditInvoice(status: InvoiceStatus): boolean {
  return status === "draft";
}

// Mirrors app.invoices.service.issue_invoice's own gate.
export function canIssueInvoice(status: InvoiceStatus): boolean {
  return status === "draft";
}

// Mirrors app.invoices.service.cancel_invoice's own gate - blocked
// once a payment has been recorded.
const CANCELLABLE_STATUSES: InvoiceStatus[] = ["draft", "sent", "overdue"];
export function canCancelInvoice(status: InvoiceStatus): boolean {
  return CANCELLABLE_STATUSES.includes(status);
}

// Mirrors app.payments.service.record_payment's own _PAYABLE_STATUSES.
const PAYABLE_STATUSES: InvoiceStatus[] = ["sent", "partially_paid", "overdue"];
export function canRecordPayment(status: InvoiceStatus): boolean {
  return PAYABLE_STATUSES.includes(status);
}
