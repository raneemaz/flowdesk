import { TaskListView } from "@/components/TaskListView";

// Deliberately minimal (no sidebar yet - FD-053 builds the real
// dashboard shell). Reached from HomePage's own "Tasks" link.
export function TaskListPage() {
  return <TaskListView title="Tasks" />;
}
