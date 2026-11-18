import { Outlet } from "react-router-dom";

import { Sidebar } from "@/components/Sidebar";
import { TopBar } from "@/components/TopBar";

// FD-053's own dashboard shell (spec Section 12.2), wrapping every
// `ProtectedRoute` child in routes/router.tsx - replaces the
// "deliberately minimal, no sidebar yet" convention every page built
// before this task followed. Sidebar hides itself with no active
// membership (e.g. a brand-new user on /organizations/new); TopBar
// always renders, since logging out should work even then.
export function DashboardLayout() {
  return (
    <div className="flex min-h-screen bg-background text-foreground">
      <Sidebar />
      <div className="flex min-w-0 flex-1 flex-col">
        <TopBar />
        <main className="flex-1 overflow-y-auto">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
