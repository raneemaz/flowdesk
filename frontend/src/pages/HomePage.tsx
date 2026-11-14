import { Button } from "@/components/ui/button";
import { useAuth } from "@/contexts/AuthContext";

// Deliberately minimal - FD-017's scope is auth state and protected
// routing, not the real dashboard. This page only exists to prove a
// route can require a session; the actual home/dashboard experience is
// far later in the backlog (after organization onboarding, FD-018+).
export function HomePage() {
  const { user, logout } = useAuth();

  return (
    <main className="flex min-h-screen flex-col items-center justify-center gap-4 bg-background text-foreground">
      <h1 className="text-2xl font-semibold">FlowDesk</h1>
      {user && <p className="text-sm text-foreground/70">Logged in as {user.name} ({user.email})</p>}
      <Button onClick={() => void logout()}>Log out</Button>
    </main>
  );
}
