// FR-039 "navigate to the related record" - entity_type is a plain,
// open-ended string server-side (docs/DATABASE.md's notifications
// section), but FD-049 only ever emits the three below. An unrecognized
// future entity_type (a later task wiring a new trigger) falls back to
// no link at all, rather than guessing a route that doesn't exist.
const ENTITY_ROUTES: Record<string, string> = {
  task: "/tasks",
  customer_request: "/requests",
  invoice: "/invoices",
};

export function entityDetailPath(entityType: string, entityId: string): string | null {
  const base = ENTITY_ROUTES[entityType];
  return base ? `${base}/${entityId}` : null;
}
