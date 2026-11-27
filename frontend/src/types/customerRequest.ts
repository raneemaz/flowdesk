// Mirrors backend/openapi.yaml's CustomerRequestPublic/RequestCommentPublic/
// RequestHistoryPublic exactly (CustomerRequest/RequestComment/RequestHistory.to_public_dict).
export type RequestStatus = "new" | "assigned" | "in_progress" | "waiting_for_customer" | "resolved" | "closed";
export type RequestPriority = "low" | "medium" | "high" | "urgent";

export interface CustomerRequestPublic {
  id: string;
  organization_id: string;
  customer_id: string;
  title: string;
  description: string | null;
  category: string | null;
  status: RequestStatus;
  priority: RequestPriority;
  creator_membership_id: string;
  assignee_membership_id: string | null;
  due_date: string | null;
  resolution_notes: string | null;
  created_at: string;
}

export interface RequestCommentPublic {
  id: string;
  request_id: string;
  author_membership_id: string | null;
  body: string;
  created_at: string;
  /** Set once the comment has been edited. */
  edited_at?: string | null;
}

export interface RequestHistoryPublic {
  id: string;
  request_id: string;
  actor_membership_id: string | null;
  event_type: string;
  previous_value: string | null;
  new_value: string | null;
  created_at: string;
}
