import { z } from "zod";

// Deliberately minimal (spec Section 32: never duplicate backend
// business logic) - app/invoices/schemas.py remains the source of
// truth for every real constraint (e.g. a percentage discount capped
// at 100, the sum of payments never exceeding the balance). These
// only catch the obviously-malformed case early, as a UX nicety.
export const lineItemSchema = z.object({
  description: z.string().min(1, "Description is required."),
  quantity: z.string().min(1, "Quantity is required."),
  unit_price: z.string().min(1, "Unit price is required."),
  tax_rate: z.string().optional().or(z.literal("")),
});

export type LineItemFormValues = z.infer<typeof lineItemSchema>;

export const invoiceFormSchema = z.object({
  customer_id: z.string().min(1, "Customer is required."),
  currency: z
    .string()
    .trim()
    .length(3, "Currency must be a 3-letter code.")
    .transform((value) => value.toUpperCase()),
  issue_date: z.string().optional().or(z.literal("")),
  due_date: z.string().optional().or(z.literal("")),
  notes: z.string().optional().or(z.literal("")),
  payment_terms: z.string().optional().or(z.literal("")),
  discount_type: z.enum(["flat", "percentage"]),
  discount_value: z.string().optional().or(z.literal("")),
  line_items: z.array(lineItemSchema),
});

export type InvoiceFormValues = z.infer<typeof invoiceFormSchema>;

export const createPaymentSchema = z.object({
  amount: z.string().min(1, "Amount is required."),
  payment_date: z.string().min(1, "Payment date is required."),
  method: z.string().min(1, "Method is required.").max(50),
  reference: z.string().max(255).optional().or(z.literal("")),
  notes: z.string().optional().or(z.literal("")),
});

export type CreatePaymentFormValues = z.infer<typeof createPaymentSchema>;
