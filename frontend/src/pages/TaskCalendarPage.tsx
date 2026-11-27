import { useState } from "react";
import { useQuery } from "@tanstack/react-query";

import { Plus } from "lucide-react";

import { ApiError } from "@/api/client";
import { listTasks } from "@/api/tasks";
import { Button } from "@/components/ui/button";
import { TasksNav } from "@/components/TasksNav";
import { useOrganization } from "@/contexts/OrganizationContext";
import { CreateTaskDialog } from "@/features/tasks/CreateTaskDialog";
import { EditTaskDialog } from "@/features/tasks/EditTaskDialog";
import { STATUS_LABELS } from "@/features/tasks/constants";
import { canManageTasks } from "@/features/tasks/permissions";
import { PHONE_QUERY, useMediaQuery } from "@/lib/useMediaQuery";
import type { TaskPublic } from "@/types/task";

const WEEKDAY_LABELS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];

// Local date components, not `.toISOString()` - every `Date` here
// (monthGridDays, the grid cell's own `day.getDate()` label) is built
// and read in the viewer's LOCAL time. `.toISOString()` converts to
// UTC first, which silently shifts the result a day off local
// midnight whenever the viewer isn't in UTC+0 - the cell labeled "13"
// would get "2026-11-12" instead of "2026-11-13" in any UTC+ timezone,
// so a click, or a task's own due_date, would land one cell away from
// what the viewer actually sees. Found via a real click in a non-UTC
// browser once "click a day to add a task" made the mismatch visible.
function toIsoDate(date: Date): string {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

// A lightweight month grid, built with plain Date arithmetic rather
// than a calendar library - FR-015 just asks for a "calendar" view,
// not a specific library or interaction model (e.g. drag-and-drop),
// and this project's dependency list (frontend/README.md) doesn't
// carry one yet.
function monthGridDays(monthStart: Date): Date[] {
  const firstOfMonth = new Date(monthStart.getFullYear(), monthStart.getMonth(), 1);
  const startOffset = firstOfMonth.getDay();
  const gridStart = new Date(firstOfMonth);
  gridStart.setDate(gridStart.getDate() - startOffset);

  const days: Date[] = [];
  for (let i = 0; i < 42; i += 1) {
    const day = new Date(gridStart);
    day.setDate(gridStart.getDate() + i);
    days.push(day);
  }
  return days;
}

export function TaskCalendarPage() {
  const { activeMembership } = useOrganization();
  const organizationId = activeMembership?.organization.id ?? "";
  const canCreate = activeMembership ? canManageTasks(activeMembership.role) : false;
  const [monthStart, setMonthStart] = useState(() => new Date(new Date().getFullYear(), new Date().getMonth(), 1));
  const [createDialogDay, setCreateDialogDay] = useState<string | null>(null);
  const [openTask, setOpenTask] = useState<TaskPublic | null>(null);

  const days = monthGridDays(monthStart);
  const rangeFrom = toIsoDate(days[0]);
  const rangeTo = toIsoDate(days[days.length - 1]);

  const { data, isPending, isError, error } = useQuery({
    queryKey: ["tasks-calendar", organizationId, rangeFrom, rangeTo],
    queryFn: () => listTasks(organizationId, { dueDateFrom: rangeFrom, dueDateTo: rangeTo, perPage: 100 }),
    enabled: Boolean(organizationId),
  });

  const tasksByDay = new Map<string, TaskPublic[]>();
  for (const task of data?.tasks ?? []) {
    if (!task.due_date) continue;
    const list = tasksByDay.get(task.due_date) ?? [];
    list.push(task);
    tasksByDay.set(task.due_date, list);
  }

  const monthLabel = monthStart.toLocaleDateString(undefined, { month: "long", year: "numeric" });
  // On phones seven columns leave no room for task names: cells show a
  // dot per task and an agenda list below carries the names instead.
  const isPhone = useMediaQuery(PHONE_QUERY);
  const chipClass = (task: TaskPublic) =>
    task.status === "cancelled"
      ? "bg-muted text-muted-foreground line-through"
      : task.status === "completed"
        ? "bg-success/15 text-success"
        : "bg-primary/10 text-primary";
  const monthTasks = [...tasksByDay.entries()]
    .filter(([iso]) => iso.slice(0, 7) === toIsoDate(monthStart).slice(0, 7))
    .sort(([a], [b]) => a.localeCompare(b));

  return (
    <div className="px-4 py-6 sm:px-6 sm:py-8 lg:px-10">
      <div className="flex max-w-7xl flex-col gap-6">
        <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2">
          <h1 className="text-2xl font-semibold">Tasks</h1>
        </div>

        <TasksNav />

        <div className="flex items-center justify-center gap-4">
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={() => setMonthStart((m) => new Date(m.getFullYear(), m.getMonth() - 1, 1))}
          >
            Previous
          </Button>
          <p className="text-sm font-medium">{monthLabel}</p>
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={() => setMonthStart((m) => new Date(m.getFullYear(), m.getMonth() + 1, 1))}
          >
            Next
          </Button>
        </div>

        {isPending && <p className="text-sm text-foreground/70">Loading calendar…</p>}
        {isError && (
          <p role="alert" className="text-sm text-destructive">
            {error instanceof ApiError ? error.message : "Something went wrong loading the calendar."}
          </p>
        )}

        {!isPending && !isError && (
          <div className="grid grid-cols-7 gap-px overflow-hidden rounded-md border border-border bg-border">
            {WEEKDAY_LABELS.map((label) => (
              <div key={label} className="bg-card px-2 py-1 text-center text-xs font-medium text-foreground/70">
                {label}
              </div>
            ))}
            {days.map((day) => {
              const iso = toIsoDate(day);
              const inMonth = day.getMonth() === monthStart.getMonth();
              const dayTasks = tasksByDay.get(iso) ?? [];
              return (
                <div
                  key={iso}
                  // The empty part of a day is itself the "add a task"
                  // target for managers; the + button is its keyboard-
                  // and screen-reader-reachable twin.
                  onClick={canCreate ? () => setCreateDialogDay(iso) : undefined}
                  className={`group flex min-h-[52px] flex-col gap-1 bg-background p-1 sm:min-h-[90px] ${inMonth ? "" : "opacity-40"} ${
                    canCreate ? "cursor-pointer hover:bg-card" : ""
                  }`}
                >
                  <div className="flex items-center justify-between">
                    <span className="text-xs text-foreground/50">{day.getDate()}</span>
                    {canCreate && (
                      <button
                        type="button"
                        aria-label={`Add a task for ${iso}`}
                        title="Add a task"
                        className="flex h-5 w-5 cursor-pointer items-center justify-center rounded text-muted-foreground/60 hover:bg-primary/10 hover:text-primary group-hover:text-primary"
                        onClick={(event) => {
                          event.stopPropagation();
                          setCreateDialogDay(iso);
                        }}
                      >
                        <Plus className="h-3.5 w-3.5" aria-hidden="true" />
                      </button>
                    )}
                  </div>
                  {isPhone && dayTasks.length > 0 && (
                    <div className="flex flex-wrap gap-0.5" aria-hidden="true">
                      {dayTasks.slice(0, 4).map((task) => (
                        <span
                          key={task.id}
                          className={`h-1.5 w-1.5 rounded-full ${task.status === "completed" ? "bg-success" : task.status === "cancelled" ? "bg-muted-foreground/50" : "bg-primary"}`}
                        />
                      ))}
                    </div>
                  )}
                  {!isPhone && dayTasks.map((task) => (
                    <button
                      key={task.id}
                      type="button"
                      onClick={(event) => {
                        event.stopPropagation();
                        setOpenTask(task);
                      }}
                      className={`cursor-pointer truncate rounded px-1 text-left text-xs hover:underline ${chipClass(task)}`}
                      title={`${task.title} (${STATUS_LABELS[task.status]})`}
                    >
                      {task.title}
                    </button>
                  ))}
                </div>
              );
            })}
          </div>
        )}

        {!isPending && !isError && isPhone && (
          <section aria-label={`Tasks in ${monthLabel}`} className="flex flex-col gap-4">
            {monthTasks.length === 0 && <p className="text-sm text-muted-foreground">No tasks due this month.</p>}
            {monthTasks.map(([iso, list]) => (
              <div key={iso}>
                <h3 className="mb-2 text-sm font-semibold text-foreground/75">
                  {new Date(`${iso}T00:00:00`).toLocaleDateString(undefined, { weekday: "short", month: "short", day: "numeric" })}
                </h3>
                <ul className="flex flex-col gap-1.5">
                  {list.map((task) => (
                    <li key={task.id}>
                      <button
                        type="button"
                        onClick={() => setOpenTask(task)}
                        className={`w-full cursor-pointer rounded-md px-3 py-2.5 text-left text-sm font-medium ${chipClass(task)}`}
                      >
                        {task.title}
                        <span className="mt-0.5 block text-xs font-normal opacity-80">{STATUS_LABELS[task.status]}</span>
                      </button>
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </section>
        )}

        {canCreate && (
          <CreateTaskDialog
            open={createDialogDay !== null}
            onOpenChange={(nextOpen) => setCreateDialogDay(nextOpen ? createDialogDay : null)}
            defaultDueDate={createDialogDay ?? undefined}
          />
        )}

        <EditTaskDialog task={openTask} onOpenChange={(nextOpen) => !nextOpen && setOpenTask(null)} />
      </div>
    </div>
  );
}
