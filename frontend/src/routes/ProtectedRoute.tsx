import { Navigate, Outlet, useLocation } from "react-router-dom";

import { useAuth } from "@/contexts/AuthContext";

// Route visibility is never the real security boundary (spec Section
// 7's "hiding a button in the UI is never a security control", applied
// here to whole pages) - every protected page's own data still comes
// from endpoints the backend independently authenticates and
// authorizes. This component only spares a logged-out user from seeing
// a page that would just immediately 401 anyway.
export function ProtectedRoute() {
  const { status } = useAuth();
  const location = useLocation();

  if (status === "loading") {
    return (
      <main className="flex min-h-screen items-center justify-center bg-background text-foreground">
        <p className="text-sm text-foreground/70">Loading…</p>
      </main>
    );
  }

  if (status === "unauthenticated") {
    return <Navigate to="/login" replace state={{ from: location }} />;
  }

  return <Outlet />;
}
