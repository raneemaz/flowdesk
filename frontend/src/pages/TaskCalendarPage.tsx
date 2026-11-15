import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";

import { ApiError } from "@/api/client";
import { listTasks } from "@/api/tasks";
import { Button } from "@/components/ui/button";
import { TasksNav } from "@/components/TasksNav";
import { useOrganization } from "@/contexts/OrganizationContext";
import type { TaskPublic } from "@/types/task";

const WEEKDAY_LABELS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];

function toIsoDate(date: Date): string {
  return date.toISOString().slice(0, 10);
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
  const [monthStart, setMonthStart] = useState(() => new Date(new Date().getFullYear(), new Date().getMonth(), 1));

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

  return (
    <main className="min-h-screen bg-background px-4 py-8 text-foreground">
      <div className="mx-auto flex max-w-5xl flex-col gap-6">
        <div className="flex items-center justify-between">
          <h1 className="text-2xl font-semibold">Tasks</h1>
          <Link to="/" className="text-sm font-medium text-primary hover:underline">
            Back to home
          </Link>
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
                  className={`flex min-h-[90px] flex-col gap-1 bg-background p-1 ${inMonth ? "" : "opacity-40"}`}
                >
                  <span className="text-xs text-foreground/50">{day.getDate()}</span>
                  {dayTasks.map((task) => (
                    <Link
                      key={task.id}
                      to={`/tasks/${task.id}`}
                      className="truncate rounded bg-primary/10 px-1 text-xs text-primary hover:underline"
                      title={task.title}
                    >
                      {task.title}
                    </Link>
                  ))}
                </div>
              );
            })}
          </div>
        )}
      </div>
    </main>
  );
}
