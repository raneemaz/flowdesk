import { TaskListView } from "@/components/TaskListView";

// Deliberately minimal (no page-level nav of its own). Reached via
// the dashboard shell's "Tasks" sidebar link (FD-053).
export function TaskListPage() {
  return <TaskListView title="Tasks" />;
}
