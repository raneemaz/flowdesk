// Mirrors backend's ActivityLog.to_public_dict (FD-047; docs/API.md's
// Activity log section) - there is no dedicated schema for this in
// backend/openapi.yaml yet (FD-047 predates the project's openapi.yaml
// coverage growing past the customer-requests endpoints), so this is
// hand-mirrored from the route's own documented response shape instead.
export interface ActivityLogPublic {
  id: string;
  organization_id: string;
  actor_membership_id: string | null;
  action: string;
  entity_type: string;
  entity_id: string;
  metadata: Record<string, unknown>;
  created_at: string;
}
