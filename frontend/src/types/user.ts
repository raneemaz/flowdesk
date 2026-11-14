// Mirrors backend/openapi.yaml's UserPublic schema exactly - never add a
// field here the backend doesn't actually return (e.g. password_hash).
export interface UserPublic {
  id: string;
  name: string;
  email: string;
  status: "active" | "inactive" | "suspended";
  created_at: string;
}
