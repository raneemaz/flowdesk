import { apiFetch, apiFetchWithMeta } from "@/api/client";
import type { PaginationMeta } from "@/types/employee";
import type {
  CustomerRequestPublic,
  RequestCommentPublic,
  RequestHistoryPublic,
  RequestPriority,
  RequestStatus,
} from "@/types/customerRequest";

export interface ListRequestsFilters {
  customerId?: string;
  assigneeMembershipId?: string;
  category?: string;
  priority?: RequestPriority;
  status?: RequestStatus;
  dueDateFrom?: string;
  dueDateTo?: string;
  page?: number;
  perPage?: number;
}

export interface RequestListResult {
  requests: CustomerRequestPublic[];
  meta: PaginationMeta;
}

export async function listRequests(
  organizationId: string,
  filters: ListRequestsFilters = {},
): Promise<RequestListResult> {
  const params = new URLSearchParams();
  if (filters.customerId) params.set("customer_id", filters.customerId);
  if (filters.assigneeMembershipId) params.set("assignee_membership_id", filters.assigneeMembershipId);
  if (filters.category) params.set("category", filters.category);
  if (filters.priority) params.set("priority", filters.priority);
  if (filters.status) params.set("status", filters.status);
  if (filters.dueDateFrom) params.set("due_date_from", filters.dueDateFrom);
  if (filters.dueDateTo) params.set("due_date_to", filters.dueDateTo);
  params.set("page", String(filters.page ?? 1));
  params.set("per_page", String(filters.perPage ?? 20));

  const { data, meta } = await apiFetchWithMeta<CustomerRequestPublic[], PaginationMeta>(
    `/organizations/${organizationId}/customer-requests?${params.toString()}`,
  );
  return { requests: data, meta };
}

export function getRequest(organizationId: string, requestId: string): Promise<CustomerRequestPublic> {
  return apiFetch<CustomerRequestPublic>(`/organizations/${organizationId}/customer-requests/${requestId}`);
}

export interface CreateRequestInput {
  customer_id: string;
  title: string;
  description?: string;
  category?: string;
  priority?: RequestPriority;
  due_date?: string;
}

// Never accepts assignee_membership_id or status - a new request
// always starts unassigned/new (docs/API.md's Customer requests section).
export function createRequest(
  organizationId: string,
  input: CreateRequestInput,
  csrfToken: string,
): Promise<CustomerRequestPublic> {
  return apiFetch<CustomerRequestPublic>(`/organizations/${organizationId}/customer-requests`, {
    method: "POST",
    body: input,
    csrfToken,
  });
}

export function assignRequest(
  organizationId: string,
  requestId: string,
  assigneeMembershipId: string | null,
  csrfToken: string,
): Promise<CustomerRequestPublic> {
  return apiFetch<CustomerRequestPublic>(`/organizations/${organizationId}/customer-requests/${requestId}/assign`, {
    method: "PATCH",
    body: { assignee_membership_id: assigneeMembershipId },
    csrfToken,
  });
}

// resolution_notes is applied regardless of whether status itself
// changes (docs/API.md) - callers that only want to save notes pass
// the request's current status unchanged.
export function updateRequestStatus(
  organizationId: string,
  requestId: string,
  status: RequestStatus,
  csrfToken: string,
  resolutionNotes?: string | null,
): Promise<CustomerRequestPublic> {
  return apiFetch<CustomerRequestPublic>(`/organizations/${organizationId}/customer-requests/${requestId}/status`, {
    method: "PATCH",
    body: resolutionNotes !== undefined ? { status, resolution_notes: resolutionNotes } : { status },
    csrfToken,
  });
}

export interface RequestCommentListResult {
  comments: RequestCommentPublic[];
  meta: PaginationMeta;
}

export async function listRequestComments(
  organizationId: string,
  requestId: string,
  page = 1,
  perPage = 50,
): Promise<RequestCommentListResult> {
  const params = new URLSearchParams({ page: String(page), per_page: String(perPage) });
  const { data, meta } = await apiFetchWithMeta<RequestCommentPublic[], PaginationMeta>(
    `/organizations/${organizationId}/customer-requests/${requestId}/comments?${params.toString()}`,
  );
  return { comments: data, meta };
}

export function createRequestComment(
  organizationId: string,
  requestId: string,
  body: string,
  csrfToken: string,
): Promise<RequestCommentPublic> {
  return apiFetch<RequestCommentPublic>(`/organizations/${organizationId}/customer-requests/${requestId}/comments`, {
    method: "POST",
    body: { body },
    csrfToken,
  });
}

export interface RequestHistoryListResult {
  entries: RequestHistoryPublic[];
  meta: PaginationMeta;
}

export async function listRequestHistory(
  organizationId: string,
  requestId: string,
  page = 1,
  perPage = 50,
): Promise<RequestHistoryListResult> {
  const params = new URLSearchParams({ page: String(page), per_page: String(perPage) });
  const { data, meta } = await apiFetchWithMeta<RequestHistoryPublic[], PaginationMeta>(
    `/organizations/${organizationId}/customer-requests/${requestId}/history?${params.toString()}`,
  );
  return { entries: data, meta };
}

// Permanent: the request, its comments and history are removed (the
// activity log keeps a "request deleted" entry). Owner/Manager only.
export function deleteRequest(organizationId: string, requestId: string, csrfToken: string): Promise<null> {
  return apiFetch<null>(`/organizations/${organizationId}/customer-requests/${requestId}`, { method: "DELETE", csrfToken });
}

// Author only.
export function updateRequestComment(
  organizationId: string,
  requestId: string,
  commentId: string,
  body: string,
  csrfToken: string,
): Promise<RequestCommentPublic> {
  return apiFetch<RequestCommentPublic>(
    `/organizations/${organizationId}/customer-requests/${requestId}/comments/${commentId}`,
    { method: "PATCH", body: { body }, csrfToken },
  );
}

// Author, or an Owner/Manager.
export function deleteRequestComment(
  organizationId: string,
  requestId: string,
  commentId: string,
  csrfToken: string,
): Promise<null> {
  return apiFetch<null>(`/organizations/${organizationId}/customer-requests/${requestId}/comments/${commentId}`, {
    method: "DELETE",
    csrfToken,
  });
}
