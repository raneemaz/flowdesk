import { useState } from "react";
import { zodResolver } from "@hookform/resolvers/zod";
import { useForm } from "react-hook-form";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";

import { ApiError } from "@/api/client";
import { getCustomer } from "@/api/customers";
import { cancelInvoice, getInvoice, invoicePdfUrl, issueInvoice, listInvoiceLineItems } from "@/api/invoices";
import { listPayments, recordPayment } from "@/api/payments";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { useAuth } from "@/contexts/AuthContext";
import { useOrganization } from "@/contexts/OrganizationContext";
import { formatMoney, sumMoney } from "@/features/invoices/calculations";
import { STATUS_LABELS } from "@/features/invoices/constants";
import { canCancelInvoice, canEditInvoice, canIssueInvoice, canManageInvoices, canRecordPayment } from "@/features/invoices/permissions";
import { createPaymentSchema, type CreatePaymentFormValues } from "@/features/invoices/schemas";

function newIdempotencyKey(): string {
  return crypto.randomUUID();
}

export function InvoiceDetailPage() {
  const { invoiceId } = useParams<{ invoiceId: string }>();
  const { csrfToken } = useAuth();
  const { activeMembership } = useOrganization();
  const organizationId = activeMembership?.organization.id ?? "";
  const canManage = activeMembership ? canManageInvoices(activeMembership.role) : false;
  const queryClient = useQueryClient();

  const [actionError, setActionError] = useState<string | null>(null);
  const [paymentError, setPaymentError] = useState<string | null>(null);
  // Generated once per "payment attempt": reused across a retry of the
  // same submission (so a network hiccup doesn't accidentally create a
  // second payment - the whole point of FD-043's idempotency_key), and
  // only ever replaced after a submission actually succeeds.
  const [idempotencyKey, setIdempotencyKey] = useState(newIdempotencyKey);

  const invoiceQueryKey = ["invoice", organizationId, invoiceId];
  const { data: invoice, isPending, isError, error } = useQuery({
    queryKey: invoiceQueryKey,
    queryFn: () => getInvoice(organizationId, invoiceId!),
    enabled: Boolean(organizationId && invoiceId),
  });

  const { data: customer } = useQuery({
    queryKey: ["customer-for-invoice", organizationId, invoice?.customer_id],
    queryFn: () => getCustomer(organizationId, invoice!.customer_id),
    enabled: Boolean(organizationId && invoice),
  });

  const lineItemsQueryKey = ["invoice-line-items", organizationId, invoiceId];
  const { data: lineItems } = useQuery({
    queryKey: lineItemsQueryKey,
    queryFn: () => listInvoiceLineItems(organizationId, invoiceId!),
    enabled: Boolean(organizationId && invoiceId),
  });

  const paymentsQueryKey = ["payments", organizationId, invoiceId];
  const { data: paymentsData } = useQuery({
    queryKey: paymentsQueryKey,
    queryFn: () => listPayments(organizationId, invoiceId!),
    enabled: Boolean(organizationId && invoiceId && invoice),
  });
  const payments = paymentsData?.payments ?? [];
  // Computed from the real, already-recorded payments - see
  // features/invoices/calculations.ts's own docstring for why this is
  // a display-only sum, not a re-derivation of record_payment's own
  // validation.
  const amountPaid = sumMoney(payments.map((payment) => payment.amount));
  const balanceDue = invoice ? Number(invoice.total) - amountPaid : 0;

  const paymentForm = useForm<CreatePaymentFormValues>({
    resolver: zodResolver(createPaymentSchema),
    defaultValues: { amount: "", payment_date: "", method: "", reference: "", notes: "" },
  });

  const invalidateInvoice = async () => {
    await queryClient.invalidateQueries({ queryKey: invoiceQueryKey });
    await queryClient.invalidateQueries({ queryKey: paymentsQueryKey });
  };

  const onIssue = async () => {
    if (!csrfToken || !invoiceId) return;
    setActionError(null);
    try {
      await issueInvoice(organizationId, invoiceId, csrfToken);
      await invalidateInvoice();
    } catch (submitError) {
      setActionError(submitError instanceof ApiError ? submitError.message : "Could not issue the invoice.");
    }
  };

  const onCancel = async () => {
    if (!csrfToken || !invoiceId) return;
    setActionError(null);
    try {
      await cancelInvoice(organizationId, invoiceId, csrfToken);
      await invalidateInvoice();
    } catch (submitError) {
      setActionError(submitError instanceof ApiError ? submitError.message : "Could not cancel the invoice.");
    }
  };

  const onRecordPayment = async (values: CreatePaymentFormValues) => {
    if (!csrfToken || !invoiceId) return;
    setPaymentError(null);
    try {
      await recordPayment(
        organizationId,
        invoiceId,
        {
          amount: values.amount,
          payment_date: values.payment_date,
          method: values.method,
          reference: values.reference || undefined,
          notes: values.notes || undefined,
          idempotency_key: idempotencyKey,
        },
        csrfToken,
      );
      paymentForm.reset({ amount: "", payment_date: "", method: "", reference: "", notes: "" });
      setIdempotencyKey(newIdempotencyKey());
      await invalidateInvoice();
    } catch (submitError) {
      setPaymentError(submitError instanceof ApiError ? submitError.message : "Could not record the payment.");
    }
  };

  if (isPending) {
    return (
      <main className="flex min-h-screen items-center justify-center bg-background text-foreground">
        <p className="text-sm text-foreground/70">Loading invoice…</p>
      </main>
    );
  }

  if (isError || !invoice) {
    return (
      <main className="flex min-h-screen flex-col items-center justify-center gap-3 bg-background text-foreground">
        <p role="alert" className="text-sm text-destructive">
          {error instanceof ApiError ? error.message : "Invoice not found."}
        </p>
        <Link to="/invoices" className="text-sm font-medium text-primary hover:underline">
          Back to invoices
        </Link>
      </main>
    );
  }

  return (
    <main className="min-h-screen bg-background px-4 py-8 text-foreground">
      <div className="mx-auto flex max-w-2xl flex-col gap-6">
        <div className="flex items-center justify-between">
          <h1 className="text-2xl font-semibold">Invoice {invoice.invoice_number}</h1>
          <Link to="/invoices" className="text-sm font-medium text-primary hover:underline">
            Back to invoices
          </Link>
        </div>

        <div className="flex flex-col gap-3 rounded-md border border-border bg-card p-6">
          <Field label="Status" value={STATUS_LABELS[invoice.status]} />
          <Field label="Customer" value={customer ? customer.name : "—"} />
          <Field label="Issue date" value={invoice.issue_date ?? "—"} />
          <Field label="Due date" value={invoice.due_date ?? "—"} />
          <Field label="Payment terms" value={invoice.payment_terms ?? "—"} />
          <Field label="Notes" value={invoice.notes ?? "—"} />
        </div>

        {canManage && (
          <div className="flex flex-wrap gap-3 rounded-md border border-border bg-card p-6">
            {canEditInvoice(invoice.status) && (
              <Button asChild variant="outline" size="sm">
                <Link to={`/invoices/${invoice.id}/edit`}>Edit</Link>
              </Button>
            )}
            {canIssueInvoice(invoice.status) && (
              <Button type="button" size="sm" onClick={() => void onIssue()}>
                Issue invoice
              </Button>
            )}
            {canCancelInvoice(invoice.status) && (
              <Button type="button" variant="destructive" size="sm" onClick={() => void onCancel()}>
                Cancel invoice
              </Button>
            )}
            <Button asChild variant="outline" size="sm">
              <a href={invoicePdfUrl(organizationId, invoice.id)} target="_blank" rel="noreferrer">
                View PDF
              </a>
            </Button>
            {actionError && (
              <p role="alert" className="w-full text-sm text-destructive">
                {actionError}
              </p>
            )}
          </div>
        )}

        <div className="flex flex-col gap-3 rounded-md border border-border bg-card p-6">
          <h2 className="text-lg font-medium">Line items</h2>
          {(lineItems ?? []).length === 0 && <p className="text-sm text-foreground/70">No line items.</p>}
          {(lineItems ?? []).length > 0 && (
            <table className="w-full text-left text-sm">
              <thead>
                <tr className="border-b border-border">
                  <th className="py-1 font-medium">Description</th>
                  <th className="py-1 text-right font-medium">Qty</th>
                  <th className="py-1 text-right font-medium">Unit price</th>
                  <th className="py-1 text-right font-medium">Tax</th>
                  <th className="py-1 text-right font-medium">Line total</th>
                </tr>
              </thead>
              <tbody>
                {(lineItems ?? []).map((item) => (
                  <tr key={item.id} className="border-b border-border/50">
                    <td className="py-1">{item.description}</td>
                    <td className="py-1 text-right">{item.quantity}</td>
                    <td className="py-1 text-right">{item.unit_price}</td>
                    <td className="py-1 text-right">{item.tax_rate ? `${item.tax_rate}%` : "—"}</td>
                    <td className="py-1 text-right">{item.line_total}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
          <div className="ml-auto flex w-64 flex-col gap-1 text-sm">
            <TotalRow label="Subtotal" value={`${invoice.currency} ${invoice.subtotal}`} />
            <TotalRow label="Tax" value={`${invoice.currency} ${invoice.tax_total}`} />
            <TotalRow label="Discount" value={`-${invoice.currency} ${invoice.discount_total}`} />
            <TotalRow label="Total" value={`${invoice.currency} ${invoice.total}`} emphasize />
          </div>
        </div>

        <div className="flex flex-col gap-3 rounded-md border border-border bg-card p-6">
          <h2 className="text-lg font-medium">Payments</h2>
          <div className="ml-auto flex w-64 flex-col gap-1 text-sm">
            <TotalRow label="Amount paid" value={formatMoney(amountPaid, invoice.currency)} />
            <TotalRow label="Balance due" value={formatMoney(balanceDue, invoice.currency)} emphasize />
          </div>
          {payments.length === 0 && <p className="text-sm text-foreground/70">No payments recorded yet.</p>}
          {payments.length > 0 && (
            <ul className="flex flex-col gap-2">
              {payments.map((payment) => (
                <li key={payment.id} className="flex justify-between rounded-md border border-border p-2 text-sm">
                  <span>
                    {payment.payment_date} · {payment.method}
                    {payment.reference ? ` · ${payment.reference}` : ""}
                  </span>
                  <span className="font-medium">
                    {invoice.currency} {payment.amount}
                  </span>
                </li>
              ))}
            </ul>
          )}

          {canManage && canRecordPayment(invoice.status) && (
            <form
              className="flex flex-col gap-3 border-t border-border pt-4"
              onSubmit={paymentForm.handleSubmit(onRecordPayment)}
              noValidate
            >
              <h3 className="text-sm font-medium">Record a payment</h3>
              <div className="flex flex-wrap gap-4">
                <div className="flex w-32 flex-col gap-1.5">
                  <Label htmlFor="payment-amount">Amount</Label>
                  <Input id="payment-amount" inputMode="decimal" {...paymentForm.register("amount")} />
                  {paymentForm.formState.errors.amount && (
                    <p className="text-sm text-destructive">{paymentForm.formState.errors.amount.message}</p>
                  )}
                </div>
                <div className="flex flex-col gap-1.5">
                  <Label htmlFor="payment-date">Date</Label>
                  <Input id="payment-date" type="date" {...paymentForm.register("payment_date")} />
                  {paymentForm.formState.errors.payment_date && (
                    <p className="text-sm text-destructive">{paymentForm.formState.errors.payment_date.message}</p>
                  )}
                </div>
                <div className="flex flex-col gap-1.5">
                  <Label htmlFor="payment-method">Method</Label>
                  <Input id="payment-method" placeholder="e.g. bank_transfer" {...paymentForm.register("method")} />
                  {paymentForm.formState.errors.method && (
                    <p className="text-sm text-destructive">{paymentForm.formState.errors.method.message}</p>
                  )}
                </div>
                <div className="flex min-w-[160px] flex-1 flex-col gap-1.5">
                  <Label htmlFor="payment-reference">Reference (optional)</Label>
                  <Input id="payment-reference" {...paymentForm.register("reference")} />
                </div>
              </div>
              <div className="flex flex-col gap-1.5">
                <Label htmlFor="payment-notes">Notes (optional)</Label>
                <Textarea id="payment-notes" {...paymentForm.register("notes")} />
              </div>
              {paymentError && (
                <p role="alert" className="text-sm text-destructive">
                  {paymentError}
                </p>
              )}
              <Button type="submit" size="sm" className="self-start" disabled={paymentForm.formState.isSubmitting}>
                {paymentForm.formState.isSubmitting ? "Recording…" : "Record payment"}
              </Button>
            </form>
          )}
        </div>
      </div>
    </main>
  );
}

function Field({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex flex-col gap-0.5">
      <span className="text-xs font-medium uppercase tracking-wide text-foreground/50">{label}</span>
      <span className="text-sm">{value}</span>
    </div>
  );
}

function TotalRow({ label, value, emphasize }: { label: string; value: string; emphasize?: boolean }) {
  return (
    <div className={`flex items-center justify-between ${emphasize ? "border-t border-border pt-1 font-semibold" : ""}`}>
      <span>{label}</span>
      <span>{value}</span>
    </div>
  );
}
