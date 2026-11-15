import { Link, useLocation } from "react-router-dom";

import { cn } from "@/lib/utils";

const TABS = [
  { to: "/tasks", label: "List" },
  { to: "/tasks/board", label: "Board" },
  { to: "/tasks/calendar", label: "Calendar" },
  { to: "/tasks/mine", label: "My Tasks" },
];

// Tabs for FR-015's four task views - deliberately not a sidebar
// (FD-053 builds the real dashboard shell, see HomePage.tsx), just
// enough navigation to reach each view from any of the others.
export function TasksNav() {
  const location = useLocation();

  return (
    <nav className="flex gap-1 border-b border-border">
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
