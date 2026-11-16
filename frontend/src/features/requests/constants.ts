import type { RequestPriority, RequestStatus } from "@/types/customerRequest";

export const STATUS_LABELS: Record<RequestStatus, string> = {
  new: "New",
  assigned: "Assigned",
  in_progress: "In Progress",
  waiting_for_customer: "Waiting for Customer",
  resolved: "Resolved",
  closed: "Closed",
};

// Natural left-to-right workflow order (FR-019).
export const STATUS_ORDER: RequestStatus[] = [
  "new",
  "assigned",
  "in_progress",
  "waiting_for_customer",
  "resolved",
  "closed",
];

export const STATUS_OPTIONS: { value: RequestStatus; label: string }[] = STATUS_ORDER.map((value) => ({
  value,
  label: STATUS_LABELS[value],
}));

export const PRIORITY_LABELS: Record<RequestPriority, string> = {
  low: "Low",
  medium: "Medium",
  high: "High",
  urgent: "Urgent",
};

export const PRIORITY_OPTIONS: { value: RequestPriority; label: string }[] = [
  { value: "low", label: "Low" },
  { value: "medium", label: "Medium" },
  { value: "high", label: "High" },
  { value: "urgent", label: "Urgent" },
];
