import { useEffect, useState } from "react";
import { zodResolver } from "@hookform/resolvers/zod";
import { useFieldArray, useForm } from "react-hook-form";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useNavigate, useParams } from "react-router-dom";

import { ApiError } from "@/api/client";
import { listCustomers } from "@/api/customers";
import { createInvoice, getInvoice, listInvoiceLineItems, updateInvoice } from "@/api/invoices";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { useAuth } from "@/contexts/AuthContext";
import { useOrganization } from "@/contexts/OrganizationContext";
import { formatMoney, previewInvoiceTotals } from "@/features/invoices/calculations";
import { DISCOUNT_TYPE_OPTIONS } from "@/features/invoices/constants";
import { canEditInvoice } from "@/features/invoices/permissions";
import { invoiceFormSchema, type InvoiceFormValues } from "@/features/invoices/schemas";

const EMPTY_LINE_ITEM = { description: "", quantity: "1", unit_price: "0.00", tax_rate: "" };

// One page for both create (/invoices/new) and edit (/invoices/:invoiceId/edit) -
// editing is draft-only server-side (app.invoices.service.update_invoice,
// 422 INVOICE_LOCKED otherwise), enforced below only as a friendlier
// "this invoice is locked" message, never as the real boundary.
export function InvoiceFormPage() {
  const { invoiceId } = useParams<{ invoiceId: string }>();
  const isEditing = Boolean(invoiceId);
  const navigate = useNavigate();
  const { csrfToken } = useAuth();
  const { activeMembership } = useOrganization();
  const organizationId = activeMembership?.organization.id ?? "";
  const queryClient = useQueryClient();

  const [submitError, setSubmitError] = useState<string | null>(null);

  const { data: customersData } = useQuery({
    queryKey: ["customers-for-invoice-form", organizationId],
    queryFn: () => listCustomers(organizationId, { perPage: 100, status: "active" }),
    enabled: Boolean(organizationId),
  });

  const { data: existingInvoice, isPending: isInvoicePending } = useQuery({
    queryKey: ["invoice", organizationId, invoiceId],
    queryFn: () => getInvoice(organizationId, invoiceId!),
    enabled: isEditing && Boolean(organizationId && invoiceId),
  });

  const { data: existingLineItems, isPending: isLineItemsPending } = useQuery({
    queryKey: ["invoice-line-items", organizationId, invoiceId],
    queryFn: () => listInvoiceLineItems(organizationId, invoiceId!),
    enabled: isEditing && Boolean(organizationId && invoiceId),
  });

  const form = useForm<InvoiceFormValues>({
    resolver: zodResolver(invoiceFormSchema),
    defaultValues: {
      customer_id: "",
      currency: "USD",
      issue_date: "",
      due_date: "",
      notes: "",
      payment_terms: "",
      discount_type: "flat",
      discount_value: "",
      line_items: [],
    },
  });
  const {
    register,
    handleSubmit,
    control,
    watch,
    formState: { errors, isSubmitting },
  } = form;

  const { fields, append, remove } = useFieldArray({ control, name: "line_items" });

  // Populates the form once an existing invoice's own fields *and*
  // line items have both loaded - `reset`, not react-hook-form's
  // `values` option, since this should only ever happen once per
  // invoice: re-syncing on every background refetch would clobber an
  // edit in progress with whatever the server happened to return.
  useEffect(() => {
    if (!isEditing || !existingInvoice || !existingLineItems) return;
    form.reset({
      customer_id: existingInvoice.customer_id,
      currency: existingInvoice.currency,
      issue_date: existingInvoice.issue_date ?? "",
      due_date: existingInvoice.due_date ?? "",
      notes: existingInvoice.notes ?? "",
      payment_terms: existingInvoice.payment_terms ?? "",
      discount_type: existingInvoice.discount_type,
      discount_value: existingInvoice.discount_value,
      line_items: existingLineItems.map((item) => ({
        description: item.description,
        quantity: item.quantity,
        unit_price: item.unit_price,
        tax_rate: item.tax_rate ?? "",
      })),
    });
    // Only re-run when the invoice being edited changes, or once its
    // data finishes loading - not on every `form` re-render.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isEditing, existingInvoice, existingLineItems]);

  // A live, non-authoritative PREVIEW only (features/invoices/calculations.ts's
  // own docstring) - the real totals are whatever
  // app.invoices.service.recalculate_invoice returns after this form
  // actually submits.
  const watchedLineItems = watch("line_items");
  const watchedDiscountType = watch("discount_type");
  const watchedDiscountValue = watch("discount_value");
  const watchedCurrency = watch("currency") || "USD";
  const preview = previewInvoiceTotals(watchedLineItems, watchedDiscountType, watchedDiscountValue);

  const onSubmit = async (values: InvoiceFormValues) => {
    if (!csrfToken) {
      setSubmitError("Your session is missing a CSRF token - please log in again.");
      return;
    }
    setSubmitError(null);
    const payload = {
      customer_id: values.customer_id,
      currency: values.currency,
      issue_date: values.issue_date || undefined,
      due_date: values.due_date || undefined,
      notes: values.notes || undefined,
      payment_terms: values.payment_terms || undefined,
      discount_type: values.discount_type,
      discount_value: values.discount_value || "0.00",
      line_items: values.line_items.map((item) => ({
        description: item.description,
        quantity: item.quantity,
        unit_price: item.unit_price,
        tax_rate: item.tax_rate || undefined,
      })),
    };
    try {
      const invoice =
        isEditing && invoiceId
          ? await updateInvoice(organizationId, invoiceId, payload, csrfToken)
          : await createInvoice(organizationId, payload, csrfToken);
      await queryClient.invalidateQueries({ queryKey: ["invoices", organizationId] });
      if (isEditing && invoiceId) {
        await queryClient.invalidateQueries({ queryKey: ["invoice", organizationId, invoiceId] });
        await queryClient.invalidateQueries({ queryKey: ["invoice-line-items", organizationId, invoiceId] });
      }
      navigate(`/invoices/${invoice.id}`);
    } catch (error) {
      setSubmitError(error instanceof ApiError ? error.message : "Something went wrong. Please try again.");
    }
  };

  if (isEditing && (isInvoicePending || isLineItemsPending)) {
    return (
      <main className="flex min-h-screen items-center justify-center bg-background text-foreground">
        <p className="text-sm text-foreground/70">Loading invoice…</p>
      </main>
    );
  }

  if (isEditing && existingInvoice && !canEditInvoice(existingInvoice.status)) {
    return (
      <main className="flex min-h-screen flex-col items-center justify-center gap-3 bg-background text-foreground">
        <p role="alert" className="text-sm text-destructive">
          Only a draft invoice can be edited - this invoice has already been issued.
        </p>
        <Link to={`/invoices/${invoiceId}`} className="text-sm font-medium text-primary hover:underline">
          Back to invoice
        </Link>
      </main>
    );
  }

  return (
    <main className="min-h-screen bg-background px-4 py-8 text-foreground">
      <div className="mx-auto flex max-w-3xl flex-col gap-6">
        <div className="flex items-center justify-between">
          <h1 className="text-2xl font-semibold">{isEditing ? "Edit invoice" : "New invoice"}</h1>
          <Link to="/invoices" className="text-sm font-medium text-primary hover:underline">
            Back to invoices
          </Link>
        </div>

        <form className="flex flex-col gap-6" onSubmit={handleSubmit(onSubmit)} noValidate>
          <div className="flex flex-col gap-4 rounded-md border border-border bg-card p-6">
            <div className="flex flex-wrap gap-4">
              <div className="flex min-w-[220px] flex-1 flex-col gap-1.5">
                <Label htmlFor="customer_id">Customer</Label>
                <Select id="customer_id" aria-invalid={errors.customer_id ? "true" : "false"} {...register("customer_id")}>
                  <option value="">Select a customer…</option>
                  {(customersData?.customers ?? []).map((customer) => (
                    <option key={customer.id} value={customer.id}>
                      {customer.name}
                    </option>
                  ))}
                </Select>
                {errors.customer_id && <p className="text-sm text-destructive">{errors.customer_id.message}</p>}
              </div>
              <div className="flex w-28 flex-col gap-1.5">
                <Label htmlFor="currency">Currency</Label>
                <Input id="currency" maxLength={3} aria-invalid={errors.currency ? "true" : "false"} {...register("currency")} />
                {errors.currency && <p className="text-sm text-destructive">{errors.currency.message}</p>}
              </div>
            </div>
            <div className="flex flex-wrap gap-4">
              <div className="flex flex-col gap-1.5">
                <Label htmlFor="issue_date">Issue date (optional)</Label>
                <Input id="issue_date" type="date" {...register("issue_date")} />
              </div>
              <div className="flex flex-col gap-1.5">
                <Label htmlFor="due_date">Due date (optional)</Label>
                <Input id="due_date" type="date" {...register("due_date")} />
              </div>
              <div className="flex min-w-[180px] flex-1 flex-col gap-1.5">
                <Label htmlFor="payment_terms">Payment terms (optional)</Label>
                <Input id="payment_terms" placeholder="e.g. Net 30" {...register("payment_terms")} />
              </div>
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="notes">Notes (optional)</Label>
              <Textarea id="notes" {...register("notes")} />
            </div>
          </div>

          <div className="flex flex-col gap-3 rounded-md border border-border bg-card p-6">
            <div className="flex items-center justify-between">
              <h2 className="text-lg font-medium">Line items</h2>
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={() => append({ ...EMPTY_LINE_ITEM })}
              >
                + Add line
              </Button>
            </div>

            {fields.length === 0 && (
              <p className="text-sm text-foreground/70">No line items yet - a draft may be saved without any.</p>
            )}

            {fields.map((field, index) => (
              <div key={field.id} className="flex flex-wrap items-start gap-3 rounded-md border border-border p-3">
                <div className="flex min-w-[200px] flex-1 flex-col gap-1.5">
                  <Label htmlFor={`line_items.${index}.description`}>Description</Label>
                  <Input
                    id={`line_items.${index}.description`}
                    aria-invalid={errors.line_items?.[index]?.description ? "true" : "false"}
                    {...register(`line_items.${index}.description`)}
                  />
                  {errors.line_items?.[index]?.description && (
                    <p className="text-sm text-destructive">{errors.line_items[index]?.description?.message}</p>
                  )}
                </div>
                <div className="flex w-24 flex-col gap-1.5">
                  <Label htmlFor={`line_items.${index}.quantity`}>Qty</Label>
                  <Input
                    id={`line_items.${index}.quantity`}
                    inputMode="decimal"
                    aria-invalid={errors.line_items?.[index]?.quantity ? "true" : "false"}
                    {...register(`line_items.${index}.quantity`)}
                  />
                </div>
                <div className="flex w-28 flex-col gap-1.5">
                  <Label htmlFor={`line_items.${index}.unit_price`}>Unit price</Label>
                  <Input
                    id={`line_items.${index}.unit_price`}
                    inputMode="decimal"
                    aria-invalid={errors.line_items?.[index]?.unit_price ? "true" : "false"}
                    {...register(`line_items.${index}.unit_price`)}
                  />
                </div>
                <div className="flex w-24 flex-col gap-1.5">
                  <Label htmlFor={`line_items.${index}.tax_rate`}>Tax % (opt.)</Label>
                  <Input id={`line_items.${index}.tax_rate`} inputMode="decimal" {...register(`line_items.${index}.tax_rate`)} />
                </div>
                <div className="flex flex-col gap-1.5 self-end">
                  <Button type="button" variant="destructive" size="sm" onClick={() => remove(index)}>
                    Remove
                  </Button>
                </div>
              </div>
            ))}
          </div>

          <div className="flex flex-col gap-3 rounded-md border border-border bg-card p-6">
            <h2 className="text-lg font-medium">Discount</h2>
            <div className="flex flex-wrap gap-4">
              <div className="flex flex-col gap-1.5">
                <Label htmlFor="discount_type">Type</Label>
                <Select id="discount_type" {...register("discount_type")}>
                  {DISCOUNT_TYPE_OPTIONS.map((option) => (
                    <option key={option.value} value={option.value}>
                      {option.label}
                    </option>
                  ))}
                </Select>
              </div>
              <div className="flex w-32 flex-col gap-1.5">
                <Label htmlFor="discount_value">{watchedDiscountType === "percentage" ? "Percent" : "Amount"}</Label>
                <Input id="discount_value" inputMode="decimal" placeholder="0.00" {...register("discount_value")} />
              </div>
            </div>
          </div>

          <div className="flex flex-col gap-1 rounded-md border border-border bg-card p-6 text-sm">
            <p className="mb-1 text-xs font-medium uppercase tracking-wide text-foreground/50">
              Estimated totals (the saved invoice's own totals are always server-computed)
            </p>
            <TotalRow label="Subtotal" value={formatMoney(preview.subtotal, watchedCurrency)} />
            <TotalRow label="Tax" value={formatMoney(preview.taxTotal, watchedCurrency)} />
            <TotalRow label="Discount" value={`-${formatMoney(preview.discountTotal, watchedCurrency)}`} />
            <TotalRow label="Total" value={formatMoney(preview.total, watchedCurrency)} emphasize />
          </div>

          {submitError && (
            <p role="alert" className="text-sm text-destructive">
              {submitError}
            </p>
          )}

          <div className="flex gap-3">
            <Button type="submit" disabled={isSubmitting}>
              {isSubmitting ? "Saving…" : isEditing ? "Save changes" : "Create invoice"}
            </Button>
            <Button type="button" variant="outline" asChild>
              <Link to={isEditing ? `/invoices/${invoiceId}` : "/invoices"}>Cancel</Link>
            </Button>
          </div>
        </form>
      </div>
    </main>
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
