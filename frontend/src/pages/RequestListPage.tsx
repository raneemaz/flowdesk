import { useState, type FormEvent } from "react";
import { zodResolver } from "@hookform/resolvers/zod";
import { useForm } from "react-hook-form";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";

import { ApiError } from "@/api/client";
import { listCustomers } from "@/api/customers";
import { createRequest, listRequests } from "@/api/customerRequests";
import { listEmployees } from "@/api/employees";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { useAuth } from "@/contexts/AuthContext";
import { useOrganization } from "@/contexts/OrganizationContext";
import { canManageCustomers } from "@/features/customers/permissions";
import { PRIORITY_OPTIONS, STATUS_OPTIONS } from "@/features/requests/constants";
import { canManageRequests } from "@/features/requests/permissions";
import { createRequestSchema, type CreateRequestFormValues } from "@/features/requests/schemas";
import type { RequestPriority, RequestStatus } from "@/types/customerRequest";

const PER_PAGE = 20;

interface Filters {
  status: RequestStatus | "";
  priority: RequestPriority | "";
  customerId: string;
  assigneeMembershipId: string;
  dueDateFrom: string;
  dueDateTo: string;
}

const EMPTY_FILTERS: Filters = {
  status: "",
  priority: "",
  customerId: "",
  assigneeMembershipId: "",
  dueDateFrom: "",
  dueDateTo: "",
};

// Deliberately minimal (no page-level nav of its own). Reached via
// the dashboard shell's "Requests" sidebar link (FD-053). No
// separate "My Requests" view - GET /customer-requests already
// auto-restricts an Employee (assigned scope) to their own requests
// server-side, the same reasoning TaskListPage (not a locked
// MyTasksPage) relies on for its own default view.
export function RequestListPage() {
  const { csrfToken } = useAuth();
  const { activeMembership } = useOrganization();
  const organizationId = activeMembership?.organization.id ?? "";
  const canManage = activeMembership ? canManageRequests(activeMembership.role) : false;
  const canSeeCustomers = activeMembership ? canManageCustomers(activeMembership.role) : false;
  const queryClient = useQueryClient();

  const [draftFilters, setDraftFilters] = useState<Filters>(EMPTY_FILTERS);
  const [appliedFilters, setAppliedFilters] = useState<Filters>(EMPTY_FILTERS);
  const [page, setPage] = useState(1);
  const [isCreateOpen, setIsCreateOpen] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);

  // Only a canManageCustomers viewer may ever call this - an Employee's
  // CUSTOMER_MANAGE scope is `none` and this query would just 403
  // (docs/API.md's Customers section), so it's gated the same way the
  // department filter is gated on canManage elsewhere in this codebase.
  const { data: customersData } = useQuery({
    queryKey: ["customers-for-request-names", organizationId],
    queryFn: () => listCustomers(organizationId, { perPage: 100 }),
    enabled: canSeeCustomers && Boolean(organizationId),
  });
  const customerNameById = new Map((customersData?.customers ?? []).map((c) => [c.id, c.name]));

  const { data: employeesForNames } = useQuery({
    queryKey: ["employees-for-request-names", organizationId],
    queryFn: () => listEmployees(organizationId, { perPage: 100 }),
    enabled: canManage && Boolean(organizationId),
  });
  const employeeNameById = new Map((employeesForNames?.employees ?? []).map((e) => [e.membership_id, e.name]));

  const requestsQueryKey = ["requests", organizationId, appliedFilters, page];
  const { data, isPending, isError, error } = useQuery({
    queryKey: requestsQueryKey,
    queryFn: () =>
      listRequests(organizationId, {
        status: appliedFilters.status || undefined,
        priority: appliedFilters.priority || undefined,
        customerId: appliedFilters.customerId || undefined,
        assigneeMembershipId: appliedFilters.assigneeMembershipId || undefined,
        dueDateFrom: appliedFilters.dueDateFrom || undefined,
        dueDateTo: appliedFilters.dueDateTo || undefined,
        page,
        perPage: PER_PAGE,
      }),
    enabled: Boolean(organizationId),
  });

  const requests = data?.requests ?? [];
  const meta = data?.meta;

  const applyFilters = (event: FormEvent) => {
    event.preventDefault();
    setAppliedFilters(draftFilters);
    setPage(1);
  };

  const clearFilters = () => {
    setDraftFilters(EMPTY_FILTERS);
    setAppliedFilters(EMPTY_FILTERS);
    setPage(1);
  };

  const {
    register,
    handleSubmit,
    reset,
    formState: { errors, isSubmitting },
  } = useForm<CreateRequestFormValues>({
    resolver: zodResolver(createRequestSchema),
    defaultValues: { customer_id: "", title: "", description: "", category: "", priority: "medium", due_date: "" },
  });

  const onCreate = async (values: CreateRequestFormValues) => {
    if (!csrfToken) {
      setCreateError("Your session is missing a CSRF token - please log in again.");
      return;
    }
    setCreateError(null);
    try {
      await createRequest(
        organizationId,
        {
          customer_id: values.customer_id,
          title: values.title,
          description: values.description || undefined,
          category: values.category || undefined,
          priority: values.priority,
          due_date: values.due_date || undefined,
        },
        csrfToken,
      );
      reset();
      setIsCreateOpen(false);
      await queryClient.invalidateQueries({ queryKey: ["requests", organizationId] });
    } catch (submitError) {
      setCreateError(submitError instanceof ApiError ? submitError.message : "Something went wrong. Please try again.");
    }
  };

  return (
    <main className="min-h-screen bg-background px-4 py-8 text-foreground">
      <div className="mx-auto flex max-w-5xl flex-col gap-6">
        <div className="flex items-center justify-between">
          <h1 className="text-2xl font-semibold">Requests</h1>
          <Link to="/" className="text-sm font-medium text-primary hover:underline">
            Back to home
          </Link>
        </div>

        {canManage && (
          <div>
            {!isCreateOpen && (
              <Button type="button" variant="outline" onClick={() => setIsCreateOpen(true)}>
                + New request
              </Button>
            )}
            {isCreateOpen && (
              <form
                className="flex flex-col gap-4 rounded-md border border-border bg-card p-6"
                onSubmit={handleSubmit(onCreate)}
                noValidate
              >
                <h2 className="text-lg font-medium">New request</h2>
                <div className="flex flex-col gap-1.5">
                  <Label htmlFor="new-customer">Customer</Label>
                  <Select id="new-customer" aria-invalid={errors.customer_id ? "true" : "false"} {...register("customer_id")}>
                    <option value="">Select a customer…</option>
                    {(customersData?.customers ?? [])
                      .filter((customer) => customer.status === "active")
                      .map((customer) => (
                        <option key={customer.id} value={customer.id}>
                          {customer.name}
                        </option>
                      ))}
                  </Select>
                  {errors.customer_id && <p className="text-sm text-destructive">{errors.customer_id.message}</p>}
                </div>
                <div className="flex flex-col gap-1.5">
                  <Label htmlFor="new-title">Title</Label>
                  <Input id="new-title" aria-invalid={errors.title ? "true" : "false"} {...register("title")} />
                  {errors.title && <p className="text-sm text-destructive">{errors.title.message}</p>}
                </div>
                <div className="flex flex-col gap-1.5">
                  <Label htmlFor="new-description">Description (optional)</Label>
                  <Textarea id="new-description" {...register("description")} />
                </div>
                <div className="flex flex-wrap gap-4">
                  <div className="flex flex-col gap-1.5">
                    <Label htmlFor="new-category">Category (optional)</Label>
                    <Input id="new-category" {...register("category")} />
                  </div>
                  <div className="flex flex-col gap-1.5">
                    <Label htmlFor="new-priority">Priority</Label>
                    <Select id="new-priority" {...register("priority")}>
                      {PRIORITY_OPTIONS.map((option) => (
                        <option key={option.value} value={option.value}>
                          {option.label}
                        </option>
                      ))}
                    </Select>
                  </div>
                  <div className="flex flex-col gap-1.5">
                    <Label htmlFor="new-due-date">Due date (optional)</Label>
                    <Input id="new-due-date" type="date" {...register("due_date")} />
                  </div>
                </div>
                {createError && (
                  <p role="alert" className="text-sm text-destructive">
                    {createError}
                  </p>
                )}
                <div className="flex gap-3">
                  <Button type="submit" disabled={isSubmitting}>
                    {isSubmitting ? "Creating…" : "Create request"}
                  </Button>
                  <Button type="button" variant="outline" onClick={() => setIsCreateOpen(false)}>
                    Cancel
                  </Button>
                </div>
              </form>
            )}
          </div>
        )}

        <form className="flex flex-wrap items-end gap-3 rounded-md border border-border bg-card p-4" onSubmit={applyFilters}>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="status-filter">Status</Label>
            <Select
              id="status-filter"
              value={draftFilters.status}
              onChange={(event) => setDraftFilters((prev) => ({ ...prev, status: event.target.value as RequestStatus | "" }))}
            >
              <option value="">All statuses</option>
              {STATUS_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </Select>
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="priority-filter">Priority</Label>
            <Select
              id="priority-filter"
              value={draftFilters.priority}
              onChange={(event) => setDraftFilters((prev) => ({ ...prev, priority: event.target.value as RequestPriority | "" }))}
            >
              <option value="">All priorities</option>
              {PRIORITY_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </Select>
          </div>
          {canSeeCustomers && customersData && customersData.customers.length > 0 && (
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="customer-filter">Customer</Label>
              <Select
                id="customer-filter"
                value={draftFilters.customerId}
                onChange={(event) => setDraftFilters((prev) => ({ ...prev, customerId: event.target.value }))}
              >
                <option value="">Any customer</option>
                {customersData.customers.map((customer) => (
                  <option key={customer.id} value={customer.id}>
                    {customer.name}
                  </option>
                ))}
              </Select>
            </div>
          )}
          {canManage && employeesForNames && (
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="assignee-filter">Assignee</Label>
              <Select
                id="assignee-filter"
                value={draftFilters.assigneeMembershipId}
                onChange={(event) => setDraftFilters((prev) => ({ ...prev, assigneeMembershipId: event.target.value }))}
              >
                <option value="">Anyone</option>
                {employeesForNames.employees.map((e) => (
                  <option key={e.membership_id} value={e.membership_id}>
                    {e.name}
                  </option>
                ))}
              </Select>
            </div>
          )}
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="due-from-filter">Due from</Label>
            <Input
              id="due-from-filter"
              type="date"
              value={draftFilters.dueDateFrom}
              onChange={(event) => setDraftFilters((prev) => ({ ...prev, dueDateFrom: event.target.value }))}
            />
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="due-to-filter">Due to</Label>
            <Input
              id="due-to-filter"
              type="date"
              value={draftFilters.dueDateTo}
              onChange={(event) => setDraftFilters((prev) => ({ ...prev, dueDateTo: event.target.value }))}
            />
          </div>
          <Button type="submit">Search</Button>
          <Button type="button" variant="outline" onClick={clearFilters}>
            Clear
          </Button>
        </form>

        {isPending && <p className="text-sm text-foreground/70">Loading requests…</p>}

        {isError && (
          <p role="alert" className="text-sm text-destructive">
            {error instanceof ApiError ? error.message : "Something went wrong loading requests."}
          </p>
        )}

        {!isPending && !isError && requests.length === 0 && (
          <p className="text-sm text-foreground/70">No requests match these filters.</p>
        )}

        {!isPending && !isError && requests.length > 0 && (
          <div className="overflow-hidden rounded-md border border-border">
            <table className="w-full text-left text-sm">
              <thead className="bg-card">
                <tr>
                  <th className="px-4 py-2 font-medium">Title</th>
                  {canSeeCustomers && <th className="px-4 py-2 font-medium">Customer</th>}
                  <th className="px-4 py-2 font-medium">Status</th>
                  <th className="px-4 py-2 font-medium">Priority</th>
                  <th className="px-4 py-2 font-medium">Assignee</th>
                  <th className="px-4 py-2 font-medium">Due date</th>
                </tr>
              </thead>
              <tbody>
                {requests.map((request) => (
                  <tr key={request.id} className="border-t border-border">
                    <td className="px-4 py-2">
                      <Link to={`/requests/${request.id}`} className="font-medium text-primary hover:underline">
                        {request.title}
                      </Link>
                    </td>
                    {canSeeCustomers && <td className="px-4 py-2">{customerNameById.get(request.customer_id) ?? "—"}</td>}
                    <td className="px-4 py-2">{STATUS_OPTIONS.find((o) => o.value === request.status)?.label}</td>
                    <td className="px-4 py-2">{PRIORITY_OPTIONS.find((o) => o.value === request.priority)?.label}</td>
                    <td className="px-4 py-2">
                      {request.assignee_membership_id
                        ? canManage
                          ? (employeeNameById.get(request.assignee_membership_id) ?? "—")
                          : "You"
                        : "—"}
                    </td>
                    <td className="px-4 py-2">{request.due_date ?? "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {meta && meta.total_pages > 1 && (
          <div className="flex items-center justify-center gap-4">
            <Button type="button" variant="outline" size="sm" disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>
              Previous
            </Button>
            <p className="text-sm text-foreground/70">
              Page {meta.page} of {meta.total_pages}
            </p>
            <Button
              type="button"
              variant="outline"
              size="sm"
              disabled={page >= meta.total_pages}
              onClick={() => setPage((p) => p + 1)}
            >
              Next
            </Button>
          </div>
        )}
      </div>
    </main>
  );
}
