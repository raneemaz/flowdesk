import { Suspense, useState } from "react";
import { Outlet } from "react-router-dom";

import { PageSkeleton } from "@/components/PageSkeleton";
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
//
// `h-screen`, not `min-h-screen`, on the outer wrapper - `min-h-screen`
// only sets a FLOOR, so a page whose content is taller than the
// viewport just grows the whole wrapper past 100vh instead of
// `<main>`'s own `overflow-y-auto` actually containing that overflow -
// the real bug behind "the sidebar scrolls away with the page". Fixing
// the height at exactly the viewport is what makes `<main>` the only
// thing that scrolls, with the Sidebar/TopBar staying fixed in place.
export function DashboardLayout() {
  const [isMobileNavOpen, setIsMobileNavOpen] = useState(false);

  return (
    <div className="flex h-screen bg-background text-foreground">
      <Sidebar open={isMobileNavOpen} onClose={() => setIsMobileNavOpen(false)} />
      <div className="flex min-w-0 flex-1 flex-col">
        <TopBar onMenuClick={() => setIsMobileNavOpen(true)} />
        {/* `relative` makes <main> the containing block for anything
            absolutely positioned inside a page - e.g. a visually hidden
            (`sr-only`) form label. Without it such an element was placed
            against the whole document instead, far below the fold, and
            stretched the window into scrolling the sidebar out of view. */}
        <main className="relative flex-1 overflow-y-auto">
          {/* Pages are code-split (routes/router.tsx): the shell above
              stays put while a page's chunk loads for the first time. */}
          <Suspense fallback={<PageSkeleton />}>
            <Outlet />
          </Suspense>
        </main>
      </div>
    </div>
  );
}
