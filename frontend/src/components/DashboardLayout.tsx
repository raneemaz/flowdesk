import { useState } from "react";
import { Outlet } from "react-router-dom";

import { Sidebar } from "@/components/Sidebar";
import { TopBar } from "@/components/TopBar";

// FD-053's own dashboard shell (spec Section 12.2), wrapping every
// `ProtectedRoute` child in routes/router.tsx - replaces the
// "deliberately minimal, no sidebar yet" convention every page built
// before this task followed. Sidebar hides itself with no active
// membership (e.g. a brand-new user on /organizations/new); TopBar
// always renders, since logging out should work even then.
//
// FD-063: below the `md` breakpoint the Sidebar is an off-canvas panel
// (NFR-011 - a real browser viewport test caught it permanently
// occupying 224px on a 375px-wide screen, pushing every page's content
// into horizontal overflow) rather than the always-visible column it
// is at `md` and above; this layout owns the open/closed state since
// both Sidebar (the panel) and TopBar (the toggle button) need it.
export function DashboardLayout() {
  const [isMobileNavOpen, setIsMobileNavOpen] = useState(false);

  return (
    <div className="flex min-h-screen bg-background text-foreground">
      <Sidebar open={isMobileNavOpen} onClose={() => setIsMobileNavOpen(false)} />
      <div className="flex min-w-0 flex-1 flex-col">
        <TopBar onMenuClick={() => setIsMobileNavOpen(true)} />
        <main className="flex-1 overflow-y-auto">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
