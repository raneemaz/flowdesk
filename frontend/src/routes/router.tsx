import { createBrowserRouter } from "react-router-dom";

import { Button } from "@/components/ui/button";

function RootStatusPage() {
  return (
    <main className="flex min-h-screen flex-col items-center justify-center gap-4 bg-background text-foreground">
      <h1 className="text-2xl font-semibold">FlowDesk</h1>
      <p className="text-sm text-foreground/70">Frontend scaffold is wired up and running.</p>
      <Button>It works</Button>
    </main>
  );
}

export const router = createBrowserRouter([
  {
    path: "/",
    element: <RootStatusPage />,
  },
]);
