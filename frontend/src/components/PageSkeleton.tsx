// Placeholder shown while a page's code chunk downloads (routes are
// code-split - routes/router.tsx). It mirrors the shared page frame
// (title row, then content blocks) so the real page lands in the same
// place instead of jumping. Pulse only when the viewer allows motion.
function Block({ className }: { className: string }) {
  return <div className={`rounded-md bg-muted motion-safe:animate-pulse ${className}`} />;
}

export function PageSkeleton() {
  return (
    <div className="px-4 py-6 sm:px-6 sm:py-8 lg:px-10" role="status" aria-label="Loading page">
      <div className="flex max-w-7xl flex-col gap-6">
        <Block className="h-8 w-56" />
        <WidgetsSkeleton />
        <Block className="h-64 w-full" />
      </div>
    </div>
  );
}

export function WidgetsSkeleton() {
  return (
    <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4" aria-hidden="true">
      <Block className="h-24" />
      <Block className="h-24" />
      <Block className="h-24" />
      <Block className="h-24" />
    </div>
  );
}

// Login and register have no dashboard shell around them.
export function AuthPageSkeleton() {
  return (
    <div className="flex min-h-screen items-center justify-center bg-background px-4" role="status" aria-label="Loading page">
      <div className="flex w-full max-w-sm flex-col gap-4">
        <Block className="h-8 w-40" />
        <Block className="h-10 w-full" />
        <Block className="h-10 w-full" />
        <Block className="h-10 w-full" />
      </div>
    </div>
  );
}
