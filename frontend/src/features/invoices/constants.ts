import type { DiscountType, InvoiceStatus } from "@/types/invoice";

export const STATUS_LABELS: Record<InvoiceStatus, string> = {
  draft: "Draft",
  sent: "Sent",
  partially_paid: "Partially Paid",
  paid: "Paid",
  overdue: "Overdue",
  cancelled: "Cancelled",
};

export const STATUS_ORDER: InvoiceStatus[] = ["draft", "sent", "partially_paid", "paid", "overdue", "cancelled"];

export const STATUS_OPTIONS: { value: InvoiceStatus; label: string }[] = STATUS_ORDER.map((value) => ({
  value,
  label: STATUS_LABELS[value],
}));

export const DISCOUNT_TYPE_OPTIONS: { value: DiscountType; label: string }[] = [
  { value: "flat", label: "Flat amount" },
  { value: "percentage", label: "Percentage" },
];
