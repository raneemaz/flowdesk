import { Link, useLocation } from "react-router-dom";

import { cn } from "@/lib/utils";

const TABS = [
  { to: "/tasks", label: "List" },
  { to: "/tasks/board", label: "Board" },
  { to: "/tasks/calendar", label: "Calendar" },
  { to: "/tasks/mine", label: "My Tasks" },
];

// Tabs for FR-015's four task views - a separate concern from the
// dashboard shell's own "Tasks" sidebar link (FD-053), which only
// gets you to one of these four; this is what lets you reach the
// other three from any of them.
export function TasksNav() {
  const location = useLocation();

  return (
    <nav className="flex gap-1 overflow-x-auto whitespace-nowrap border-b border-border [scrollbar-width:none]">
      {TABS.map((tab) => {
        const isActive = location.pathname === tab.to;
        return (
          <Link
            key={tab.to}
            to={tab.to}
            className={cn(
              "border-b-2 px-3 py-2 text-sm font-medium",
              isActive
                ? "border-primary text-primary"
                : "border-transparent text-foreground/70 hover:text-foreground",
            )}
          >
            {tab.label}
          </Link>
        );
      })}
    </nav>
  );
}
