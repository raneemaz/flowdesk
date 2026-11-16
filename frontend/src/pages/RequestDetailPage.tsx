import { useState, type ReactNode } from "react";
import { zodResolver } from "@hookform/resolvers/zod";
import { useForm } from "react-hook-form";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";

import { ApiError } from "@/api/client";
import { getCustomer } from "@/api/customers";
import {
  assignRequest,
  createRequestComment,
  getRequest,
  listRequestComments,
  listRequestHistory,
  updateRequestStatus,
} from "@/api/customerRequests";
import { listEmployees } from "@/api/employees";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { useAuth } from "@/contexts/AuthContext";
import { useOrganization } from "@/contexts/OrganizationContext";
import { canManageCustomers } from "@/features/customers/permissions";
import { PRIORITY_OPTIONS, STATUS_LABELS } from "@/features/requests/constants";
import { canManageRequests, statusOptionsFor } from "@/features/requests/permissions";
import {
  createRequestCommentSchema,
  resolutionNotesSchema,
  type CreateRequestCommentFormValues,
  type ResolutionNotesFormValues,
} from "@/features/requests/schemas";
import type { RequestStatus } from "@/types/customerRequest";

export function RequestDetailPage() {
  const { requestId } = useParams<{ requestId: string }>();
  const { csrfToken } = useAuth();
  const { activeMembership } = useOrganization();
  const organizationId = activeMembership?.organization.id ?? "";
  const canManage = activeMembership ? canManageRequests(activeMembership.role) : false;
  const canSeeCustomer = activeMembership ? canManageCustomers(activeMembership.role) : false;
  const queryClient = useQueryClient();

  const [assignError, setAssignError] = useState<string | null>(null);
  const [statusError, setStatusError] = useState<string | null>(null);
  const [notesError, setNotesError] = useState<string | null>(null);
  const [commentError, setCommentError] = useState<string | null>(null);

  const requestQueryKey = ["request", organizationId, requestId];
  const { data: request, isPending, isError, error } = useQuery({
    queryKey: requestQueryKey,
    queryFn: () => getRequest(organizationId, requestId!),
    enabled: Boolean(organizationId && requestId),
  });

  // Only a canManageCustomers viewer may ever call this - an Employee's
  // CUSTOMER_MANAGE scope is `none`, so even for a request assigned to
  // them, they can't resolve their own request's customer record
  // through this API (docs/API.md's Customers section). The field is
  // simply omitted below for that viewer, same pattern TaskDetailPage
  // already uses for its own Department field.
  const { data: customer } = useQuery({
    queryKey: ["customer-for-request", organizationId, request?.customer_id],
    queryFn: () => getCustomer(organizationId, request!.customer_id),
    enabled: canSeeCustomer && Boolean(organizationId && request),
  });

  // Every authenticated member can look up names - EMPLOYEE_DIRECTORY_VIEW
  // never grants `none`, and `name` is present even at `limited` scope.
  const { data: employeesForNames } = useQuery({
    queryKey: ["employees-for-request-detail-names", organizationId],
    queryFn: () => listEmployees(organizationId, { perPage: 100 }),
    enabled: Boolean(organizationId),
  });
  const nameById = new Map((employeesForNames?.employees ?? []).map((e) => [e.membership_id, e.name]));

  const { data: commentsData } = useQuery({
    queryKey: ["request-comments", organizationId, requestId],
    queryFn: () => listRequestComments(organizationId, requestId!, 1, 100),
    enabled: Boolean(organizationId && requestId && request),
  });

  const { data: historyData } = useQuery({
    queryKey: ["request-history", organizationId, requestId],
    queryFn: () => listRequestHistory(organizationId, requestId!, 1, 100),
    enabled: Boolean(organizationId && requestId && request),
  });

  const commentForm = useForm<CreateRequestCommentFormValues>({
    resolver: zodResolver(createRequestCommentSchema),
    defaultValues: { body: "" },
  });

  const notesForm = useForm<ResolutionNotesFormValues>({
    resolver: zodResolver(resolutionNotesSchema),
    values: { resolution_notes: request?.resolution_notes ?? "" },
  });

  // Assigning and changing status can both write a RequestHistory row
  // (FD-037), so every mutation refreshes the request itself and its
  // history, not just whichever one a given action happens to touch
  // most visibly - same convention TaskDetailPage's invalidateTask()
  // already established.
  const invalidateRequest = async () => {
    await queryClient.invalidateQueries({ queryKey: requestQueryKey });
    await queryClient.invalidateQueries({ queryKey: ["request-history", organizationId, requestId] });
  };

  const onAssign = async (assigneeMembershipId: string) => {
    if (!csrfToken || !requestId) return;
    setAssignError(null);
    try {
      await assignRequest(organizationId, requestId, assigneeMembershipId || null, csrfToken);
      await invalidateRequest();
    } catch (submitError) {
      setAssignError(submitError instanceof ApiError ? submitError.message : "Could not update the assignee.");
    }
  };

  const onStatusChange = async (nextStatus: RequestStatus) => {
    if (!csrfToken || !requestId) return;
    setStatusError(null);
    try {
      await updateRequestStatus(organizationId, requestId, nextStatus, csrfToken);
      await invalidateRequest();
    } catch (submitError) {
      setStatusError(submitError instanceof ApiError ? submitError.message : "Could not update the status.");
    }
  };

  const onSaveNotes = async (values: ResolutionNotesFormValues) => {
    if (!csrfToken || !requestId || !request) return;
    setNotesError(null);
    try {
      await updateRequestStatus(organizationId, requestId, request.status, csrfToken, values.resolution_notes || null);
      await invalidateRequest();
    } catch (submitError) {
      setNotesError(submitError instanceof ApiError ? submitError.message : "Could not save resolution notes.");
    }
  };

  const onCommentSubmit = async (values: CreateRequestCommentFormValues) => {
    if (!csrfToken || !requestId) return;
    setCommentError(null);
    try {
      await createRequestComment(organizationId, requestId, values.body, csrfToken);
      commentForm.reset({ body: "" });
      await queryClient.invalidateQueries({ queryKey: ["request-comments", organizationId, requestId] });
    } catch (submitError) {
      setCommentError(submitError instanceof ApiError ? submitError.message : "Could not post your comment.");
    }
  };

  if (isPending) {
    return (
      <main className="flex min-h-screen items-center justify-center bg-background text-foreground">
        <p className="text-sm text-foreground/70">Loading request…</p>
      </main>
    );
  }

  if (isError || !request) {
    return (
      <main className="flex min-h-screen flex-col items-center justify-center gap-3 bg-background text-foreground">
        <p role="alert" className="text-sm text-destructive">
          {error instanceof ApiError ? error.message : "Request not found."}
        </p>
        <Link to="/requests" className="text-sm font-medium text-primary hover:underline">
          Back to requests
        </Link>
      </main>
    );
  }

  const nextStatuses = statusOptionsFor(request.status, canManage);

  // RequestHistory stores raw values (a membership_id string for
  // "assignee_changed", a status enum value for "status_changed" -
  // docs/API.md's Customer requests section) - resolved to something
  // readable here rather than showing a bare UUID or snake_case value.
  const describeHistoryValue = (fieldLabel: string, raw: string | null): string => {
    if (raw === null) return fieldLabel === "assignee" ? "Unassigned" : "—";
    if (fieldLabel === "assignee") return nameById.get(raw) ?? raw;
    if (fieldLabel === "status") return STATUS_LABELS[raw as RequestStatus] ?? raw;
    if (fieldLabel === "priority") return PRIORITY_OPTIONS.find((option) => option.value === raw)?.label ?? raw;
    return raw;
  };

  return (
    <main className="min-h-screen bg-background px-4 py-8 text-foreground">
      <div className="mx-auto flex max-w-2xl flex-col gap-6">
        <div className="flex items-center justify-between">
          <h1 className="text-2xl font-semibold">{request.title}</h1>
          <Link to="/requests" className="text-sm font-medium text-primary hover:underline">
            Back to requests
          </Link>
        </div>

        <div className="flex flex-col gap-3 rounded-md border border-border bg-card p-6">
          {canSeeCustomer && (
            <Field
              label="Customer"
              value={
                customer ? (
                  <Link to={`/customers/${customer.id}`} className="text-primary hover:underline">
                    {customer.name}
                  </Link>
                ) : (
                  "—"
                )
              }
            />
          )}
          <Field label="Status" value={STATUS_LABELS[request.status]} />
          <Field label="Priority" value={PRIORITY_OPTIONS.find((o) => o.value === request.priority)?.label ?? request.priority} />
          <Field label="Description" value={request.description ?? "—"} />
          <Field label="Category" value={request.category ?? "—"} />
          <Field
            label="Assignee"
            value={request.assignee_membership_id ? (nameById.get(request.assignee_membership_id) ?? "—") : "Unassigned"}
          />
          <Field label="Due date" value={request.due_date ?? "—"} />
        </div>

        {canManage && (
          <div className="flex flex-col gap-1.5 rounded-md border border-border bg-card p-6">
            <Label htmlFor="assign-select">Assignee</Label>
            <Select
              id="assign-select"
              value={request.assignee_membership_id ?? ""}
              onChange={(event) => void onAssign(event.target.value)}
            >
              <option value="">Unassigned</option>
              {(employeesForNames?.employees ?? []).map((candidate) => (
                <option key={candidate.membership_id} value={candidate.membership_id}>
                  {candidate.name}
                </option>
              ))}
            </Select>
            {assignError && (
              <p role="alert" className="text-sm text-destructive">
                {assignError}
              </p>
            )}
          </div>
        )}

        <div className="flex flex-col gap-2 rounded-md border border-border bg-card p-6">
          <p className="text-sm font-medium">Move to:</p>
          <div className="flex flex-wrap gap-2">
            {nextStatuses.length === 0 && <p className="text-sm text-foreground/70">No further status changes available.</p>}
            {nextStatuses.map((nextStatus) => (
              <Button key={nextStatus} type="button" variant="outline" size="sm" onClick={() => void onStatusChange(nextStatus)}>
                {STATUS_LABELS[nextStatus]}
              </Button>
            ))}
          </div>
          {statusError && (
            <p role="alert" className="text-sm text-destructive">
              {statusError}
            </p>
          )}
        </div>

        <form
          className="flex flex-col gap-2 rounded-md border border-border bg-card p-6"
          onSubmit={notesForm.handleSubmit(onSaveNotes)}
          noValidate
        >
          <Label htmlFor="resolution-notes">Resolution notes</Label>
          <Textarea id="resolution-notes" {...notesForm.register("resolution_notes")} />
          {notesError && (
            <p role="alert" className="text-sm text-destructive">
              {notesError}
            </p>
          )}
          <Button type="submit" size="sm" className="self-start" disabled={notesForm.formState.isSubmitting}>
            {notesForm.formState.isSubmitting ? "Saving…" : "Save notes"}
          </Button>
        </form>

        <div className="flex flex-col gap-3 rounded-md border border-border bg-card p-6">
          <h2 className="text-lg font-medium">Comments</h2>
          <div className="flex flex-col gap-3">
            {(commentsData?.comments ?? []).length === 0 && <p className="text-sm text-foreground/70">No comments yet.</p>}
            {(commentsData?.comments ?? []).map((comment) => (
              <div key={comment.id} className="rounded-md border border-border p-3">
                <p className="text-xs font-medium text-foreground/70">
                  {comment.author_membership_id ? (nameById.get(comment.author_membership_id) ?? "Unknown") : "Unknown"} ·{" "}
                  {new Date(comment.created_at).toLocaleString()}
                </p>
                <p className="text-sm">{comment.body}</p>
              </div>
            ))}
          </div>
          <form className="flex flex-col gap-2" onSubmit={commentForm.handleSubmit(onCommentSubmit)} noValidate>
            <Label htmlFor="comment-body" className="sr-only">
              Add a comment
            </Label>
            <Textarea id="comment-body" placeholder="Add a comment…" {...commentForm.register("body")} />
            {commentForm.formState.errors.body && (
              <p className="text-sm text-destructive">{commentForm.formState.errors.body.message}</p>
            )}
            {commentError && (
              <p role="alert" className="text-sm text-destructive">
                {commentError}
              </p>
            )}
            <Button type="submit" className="self-start" disabled={commentForm.formState.isSubmitting}>
              {commentForm.formState.isSubmitting ? "Posting…" : "Post comment"}
            </Button>
          </form>
        </div>

        <div className="flex flex-col gap-3 rounded-md border border-border bg-card p-6">
          <h2 className="text-lg font-medium">History</h2>
          {(historyData?.entries ?? []).length === 0 && <p className="text-sm text-foreground/70">No history yet.</p>}
          <ul className="flex flex-col gap-2">
            {(historyData?.entries ?? []).map((entry) => {
              const fieldLabel = entry.event_type.replace(/_changed$/, "").replace(/_/g, " ");
              return (
                <li key={entry.id} className="text-sm text-foreground/70">
                  <span className="font-medium text-foreground">
                    {entry.actor_membership_id ? (nameById.get(entry.actor_membership_id) ?? "Someone") : "Someone"}
                  </span>{" "}
                  changed {fieldLabel} from{" "}
                  <span className="font-medium text-foreground">{describeHistoryValue(fieldLabel, entry.previous_value)}</span>{" "}
                  to{" "}
                  <span className="font-medium text-foreground">{describeHistoryValue(fieldLabel, entry.new_value)}</span> on{" "}
                  {new Date(entry.created_at).toLocaleString()}
                </li>
              );
            })}
          </ul>
        </div>
      </div>
    </main>
  );
}

function Field({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div className="flex flex-col gap-0.5">
      <span className="text-xs font-medium uppercase tracking-wide text-foreground/50">{label}</span>
      <span className="text-sm">{value}</span>
    </div>
  );
}
