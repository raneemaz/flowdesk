// Mirrors backend/openapi.yaml's NotificationPublic exactly
// (app/models/notification.py's to_public_dict). No role/scope
// filtering exists for this entity (docs/API.md's Notifications
// section) - every notification this page ever receives already
// belongs to the signed-in caller.
export interface NotificationPublic {
  id: string;
  organization_id: string;
  recipient_membership_id: string;
  type: string;
  title: string;
  body: string;
  entity_type: string;
  entity_id: string;
  read_at: string | null;
  created_at: string;
}
