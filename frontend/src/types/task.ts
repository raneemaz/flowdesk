// Mirrors backend/openapi.yaml's TaskPublic/TaskCommentPublic/
// TaskHistoryPublic exactly (Task/TaskComment/TaskHistory.to_public_dict).
export type TaskStatus = "to_do" | "in_progress" | "under_review" | "completed" | "cancelled";
export type TaskPriority = "low" | "medium" | "high" | "urgent";

export interface TaskPublic {
  id: string;
  organization_id: string;
  title: string;
  description: string | null;
  status: TaskStatus;
  priority: TaskPriority;
  creator_membership_id: string;
  assignee_membership_id: string | null;
  department_id: string | null;
  start_date: string | null;
  due_date: string | null;
  estimated_hours: string | null;
  actual_hours: string | null;
  created_at: string;
}

export interface TaskCommentPublic {
  id: string;
  task_id: string;
  author_membership_id: string | null;
  body: string;
  created_at: string;
}

export interface TaskHistoryPublic {
  id: string;
  task_id: string;
  actor_membership_id: string | null;
  event_type: string;
  previous_value: string | null;
  new_value: string | null;
  created_at: string;
}
