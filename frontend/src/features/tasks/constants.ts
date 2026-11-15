import type { TaskPriority, TaskStatus } from "@/types/task";

export const STATUS_LABELS: Record<TaskStatus, string> = {
  to_do: "To Do",
  in_progress: "In Progress",
  under_review: "Under Review",
  completed: "Completed",
  cancelled: "Cancelled",
};

// Board column order - also the natural left-to-right workflow order
// (FR-012), with the terminal states last.
export const STATUS_ORDER: TaskStatus[] = ["to_do", "in_progress", "under_review", "completed", "cancelled"];

export const STATUS_OPTIONS: { value: TaskStatus; label: string }[] = STATUS_ORDER.map((value) => ({
  value,
  label: STATUS_LABELS[value],
}));

export const PRIORITY_LABELS: Record<TaskPriority, string> = {
  low: "Low",
  medium: "Medium",
  high: "High",
  urgent: "Urgent",
};

export const PRIORITY_OPTIONS: { value: TaskPriority; label: string }[] = [
  { value: "low", label: "Low" },
  { value: "medium", label: "Medium" },
  { value: "high", label: "High" },
  { value: "urgent", label: "Urgent" },
];
