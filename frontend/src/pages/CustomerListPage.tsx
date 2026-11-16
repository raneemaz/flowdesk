import { useState, type FormEvent } from "react";
import { zodResolver } from "@hookform/resolvers/zod";
import { useForm } from "react-hook-form";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";

import { ApiError } from "@/api/client";
import { createCustomer, listCustomers } from "@/api/customers";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { useAuth } from "@/contexts/AuthContext";
import { useOrganization } from "@/contexts/OrganizationContext";
import { createCustomerSchema, type CreateCustomerFormValues } from "@/features/customers/schemas";
import type { CustomerStatus } from "@/types/customer";

const PER_PAGE = 20;

interface Filters {
  search: string;
  status: CustomerStatus | "";
}

const EMPTY_FILTERS: Filters = { search: "", status: "" };

// Deliberately minimal (no sidebar yet - FD-053 builds the real
// dashboard shell). Reached from HomePage's own "Customers" link.
// Only Owner/Manager/Accountant/CustomerSupport ever reach this page -
// ProtectedRoute-level gating isn't needed since HomePage simply never
// links here for an Employee, and the backend independently 403s
// CUSTOMER_MANAGE=none regardless.
export function CustomerListPage() {
  const { csrfToken } = useAuth();
  const { activeMembership } = useOrganization();
  const organizationId = activeMembership?.organization.id ?? "";
  const queryClient = useQueryClient();

  const [draftFilters, setDraftFilters] = useState<Filters>(EMPTY_FILTERS);
  const [appliedFilters, setAppliedFilters] = useState<Filters>(EMPTY_FILTERS);
  const [page, setPage] = useState(1);
  const [isCreateOpen, setIsCreateOpen] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);

  const customersQueryKey = ["customers", organizationId, appliedFilters, page];
  const { data, isPending, isError, error } = useQuery({
    queryKey: customersQueryKey,
    queryFn: () =>
      listCustomers(organizationId, {
        search: appliedFilters.search || undefined,
        status: appliedFilters.status || undefined,
        page,
        perPage: PER_PAGE,
      }),
    enabled: Boolean(organizationId),
  });

  const customers = data?.customers ?? [];
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
  } = useForm<CreateCustomerFormValues>({
    resolver: zodResolver(createCustomerSchema),
    defaultValues: { name: "", email: "", phone: "", company: "", address: "", notes: "" },
  });

  const onCreate = async (values: CreateCustomerFormValues) => {
    if (!csrfToken) {
      setCreateError("Your session is missing a CSRF token - please log in again.");
      return;
    }
    setCreateError(null);
    try {
      await createCustomer(
        organizationId,
        {
          name: values.name,
          email: values.email || undefined,
          phone: values.phone || undefined,
          company: values.company || undefined,
          address: values.address || undefined,
          notes: values.notes || undefined,
        },
        csrfToken,
      );
      reset();
      setIsCreateOpen(false);
      await queryClient.invalidateQueries({ queryKey: ["customers", organizationId] });
    } catch (submitError) {
      setCreateError(submitError instanceof ApiError ? submitError.message : "Something went wrong. Please try again.");
    }
  };

  return (
    <main className="min-h-screen bg-background px-4 py-8 text-foreground">
      <div className="mx-auto flex max-w-5xl flex-col gap-6">
        <div className="flex items-center justify-between">
          <h1 className="text-2xl font-semibold">Customers</h1>
          <Link to="/" className="text-sm font-medium text-primary hover:underline">
            Back to home
          </Link>
        </div>

        <div>
          {!isCreateOpen && (
            <Button type="button" variant="outline" onClick={() => setIsCreateOpen(true)}>
              + New customer
            </Button>
          )}
          {isCreateOpen && (
            <form
              className="flex flex-col gap-4 rounded-md border border-border bg-card p-6"
              onSubmit={handleSubmit(onCreate)}
              noValidate
            >
              <h2 className="text-lg font-medium">New customer</h2>
              <div className="flex flex-col gap-1.5">
                <Label htmlFor="new-name">Name</Label>
                <Input id="new-name" aria-invalid={errors.name ? "true" : "false"} {...register("name")} />
                {errors.name && <p className="text-sm text-destructive">{errors.name.message}</p>}
              </div>
              <div className="flex flex-wrap gap-4">
                <div className="flex flex-col gap-1.5">
                  <Label htmlFor="new-email">Email (optional)</Label>
                  <Input id="new-email" type="email" {...register("email")} />
                </div>
                <div className="flex flex-col gap-1.5">
                  <Label htmlFor="new-phone">Phone (optional)</Label>
                  <Input id="new-phone" {...register("phone")} />
                </div>
                <div className="flex flex-col gap-1.5">
                  <Label htmlFor="new-company">Company (optional)</Label>
                  <Input id="new-company" {...register("company")} />
                </div>
              </div>
              <div className="flex flex-col gap-1.5">
                <Label htmlFor="new-address">Address (optional)</Label>
                <Textarea id="new-address" {...register("address")} />
              </div>
              <div className="flex flex-col gap-1.5">
                <Label htmlFor="new-notes">Notes (optional)</Label>
                <Textarea id="new-notes" {...register("notes")} />
              </div>
              {createError && (
                <p role="alert" className="text-sm text-destructive">
                  {createError}
                </p>
              )}
              <div className="flex gap-3">
                <Button type="submit" disabled={isSubmitting}>
                  {isSubmitting ? "Creating…" : "Create customer"}
                </Button>
                <Button type="button" variant="outline" onClick={() => setIsCreateOpen(false)}>
                  Cancel
                </Button>
              </div>
            </form>
          )}
        </div>

        <form className="flex flex-wrap items-end gap-3 rounded-md border border-border bg-card p-4" onSubmit={applyFilters}>
          <div className="flex min-w-[180px] flex-1 flex-col gap-1.5">
            <Label htmlFor="search">Search</Label>
            <Input
              id="search"
              placeholder="Name, email, phone, or company"
              value={draftFilters.search}
              onChange={(event) => setDraftFilters((prev) => ({ ...prev, search: event.target.value }))}
            />
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="status-filter">Status</Label>
            <Select
              id="status-filter"
              value={draftFilters.status}
              onChange={(event) => setDraftFilters((prev) => ({ ...prev, status: event.target.value as CustomerStatus | "" }))}
            >
              <option value="">All statuses</option>
              <option value="active">Active</option>
              <option value="archived">Archived</option>
            </Select>
          </div>
          <Button type="submit">Search</Button>
          <Button type="button" variant="outline" onClick={clearFilters}>
            Clear
          </Button>
        </form>

        {isPending && <p className="text-sm text-foreground/70">Loading customers…</p>}

        {isError && (
          <p role="alert" className="text-sm text-destructive">
            {error instanceof ApiError ? error.message : "Something went wrong loading customers."}
          </p>
        )}

        {!isPending && !isError && customers.length === 0 && (
          <p className="text-sm text-foreground/70">No customers match these filters.</p>
        )}

        {!isPending && !isError && customers.length > 0 && (
          <div className="overflow-hidden rounded-md border border-border">
            <table className="w-full text-left text-sm">
              <thead className="bg-card">
                <tr>
                  <th className="px-4 py-2 font-medium">Name</th>
                  <th className="px-4 py-2 font-medium">Email</th>
                  <th className="px-4 py-2 font-medium">Phone</th>
                  <th className="px-4 py-2 font-medium">Company</th>
                  <th className="px-4 py-2 font-medium">Status</th>
                </tr>
              </thead>
              <tbody>
                {customers.map((customer) => (
                  <tr key={customer.id} className="border-t border-border">
                    <td className="px-4 py-2">
                      <Link to={`/customers/${customer.id}`} className="font-medium text-primary hover:underline">
                        {customer.name}
                      </Link>
                    </td>
                    <td className="px-4 py-2">{customer.email ?? "—"}</td>
                    <td className="px-4 py-2">{customer.phone ?? "—"}</td>
                    <td className="px-4 py-2">{customer.company ?? "—"}</td>
                    <td className="px-4 py-2">{customer.status === "archived" ? "Archived" : "Active"}</td>
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
