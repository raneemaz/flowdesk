import { useState, type FormEvent } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";

import { ApiError } from "@/api/client";
import { listCustomers } from "@/api/customers";
import { getFinancialSummary, listInvoices } from "@/api/invoices";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { useOrganization } from "@/contexts/OrganizationContext";
import { STATUS_LABELS, STATUS_OPTIONS } from "@/features/invoices/constants";
import { canManageInvoices, canViewFinancialReports } from "@/features/invoices/permissions";
import type { InvoiceStatus } from "@/types/invoice";

const PER_PAGE = 20;

interface Filters {
  status: InvoiceStatus | "";
  customerId: string;
  dueDateFrom: string;
  dueDateTo: string;
}

const EMPTY_FILTERS: Filters = { status: "", customerId: "", dueDateFrom: "", dueDateTo: "" };

// Deliberately minimal (no page-level nav of its own), same
// convention CustomerListPage/RequestListPage already established.
// Reached via the dashboard shell's "Invoices" sidebar link (FD-053),
// shown only to canManageInvoices - an Employee/Manager/CustomerSupport
// hitting this route directly would just get 403s from every request
// it makes (INVOICE_PAYMENT_MANAGE is none for those roles).
export function InvoiceListPage() {
  const { activeMembership } = useOrganization();
  const organizationId = activeMembership?.organization.id ?? "";
  const canSeeFinancials = activeMembership ? canViewFinancialReports(activeMembership.role) : false;

  const [draftFilters, setDraftFilters] = useState<Filters>(EMPTY_FILTERS);
  const [appliedFilters, setAppliedFilters] = useState<Filters>(EMPTY_FILTERS);
  const [page, setPage] = useState(1);

  const { data: customersData } = useQuery({
    queryKey: ["customers-for-invoice-names", organizationId],
    queryFn: () => listCustomers(organizationId, { perPage: 100 }),
    enabled: Boolean(organizationId),
  });
  const customerNameById = new Map((customersData?.customers ?? []).map((c) => [c.id, c.name]));

  const { data: summary } = useQuery({
    queryKey: ["invoices-financial-summary", organizationId],
    queryFn: () => getFinancialSummary(organizationId),
    enabled: canSeeFinancials && Boolean(organizationId),
  });

  const { data, isPending, isError, error } = useQuery({
    queryKey: ["invoices", organizationId, appliedFilters, page],
    queryFn: () =>
      listInvoices(organizationId, {
        status: appliedFilters.status || undefined,
        customerId: appliedFilters.customerId || undefined,
        dueDateFrom: appliedFilters.dueDateFrom || undefined,
        dueDateTo: appliedFilters.dueDateTo || undefined,
        page,
        perPage: PER_PAGE,
      }),
    enabled: Boolean(organizationId),
  });

  const invoices = data?.invoices ?? [];
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

  return (
    <main className="min-h-screen bg-background px-4 py-8 text-foreground">
      <div className="mx-auto flex max-w-5xl flex-col gap-6">
        <div className="flex items-center justify-between">
          <h1 className="text-2xl font-semibold">Invoices</h1>
          <Link to="/" className="text-sm font-medium text-primary hover:underline">
            Back to home
          </Link>
        </div>

        {canSeeFinancials && summary && (
          <div className="grid grid-cols-2 gap-3 rounded-md border border-border bg-card p-4 sm:grid-cols-4">
            <SummaryStat label="Invoiced" value={summary.total_invoiced} />
            <SummaryStat label="Collected" value={summary.total_collected} />
            <SummaryStat label="Outstanding" value={summary.outstanding_balance} />
            <SummaryStat label="Overdue invoices" value={String(summary.overdue_invoice_count)} />
          </div>
        )}

        {activeMembership && canManageInvoices(activeMembership.role) && (
          <div>
            <Button asChild variant="outline">
              <Link to="/invoices/new">+ New invoice</Link>
            </Button>
          </div>
        )}

        <form className="flex flex-wrap items-end gap-3 rounded-md border border-border bg-card p-4" onSubmit={applyFilters}>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="status-filter">Status</Label>
            <Select
              id="status-filter"
              value={draftFilters.status}
              onChange={(event) => setDraftFilters((prev) => ({ ...prev, status: event.target.value as InvoiceStatus | "" }))}
            >
              <option value="">All statuses</option>
              {STATUS_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </Select>
          </div>
          {customersData && customersData.customers.length > 0 && (
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

        {isPending && <p className="text-sm text-foreground/70">Loading invoices…</p>}

        {isError && (
          <p role="alert" className="text-sm text-destructive">
            {error instanceof ApiError ? error.message : "Something went wrong loading invoices."}
          </p>
        )}

        {!isPending && !isError && invoices.length === 0 && (
          <p className="text-sm text-foreground/70">No invoices match these filters.</p>
        )}

        {!isPending && !isError && invoices.length > 0 && (
          <div className="overflow-hidden rounded-md border border-border">
            <table className="w-full text-left text-sm">
              <thead className="bg-card">
                <tr>
                  <th className="px-4 py-2 font-medium">Number</th>
                  <th className="px-4 py-2 font-medium">Customer</th>
                  <th className="px-4 py-2 font-medium">Status</th>
                  <th className="px-4 py-2 font-medium">Due date</th>
                  <th className="px-4 py-2 font-medium">Total</th>
                </tr>
              </thead>
              <tbody>
                {invoices.map((invoice) => (
                  <tr key={invoice.id} className="border-t border-border">
                    <td className="px-4 py-2">
                      <Link to={`/invoices/${invoice.id}`} className="font-medium text-primary hover:underline">
                        {invoice.invoice_number}
                      </Link>
                    </td>
                    <td className="px-4 py-2">{customerNameById.get(invoice.customer_id) ?? "—"}</td>
                    <td className="px-4 py-2">{STATUS_LABELS[invoice.status]}</td>
                    <td className="px-4 py-2">{invoice.due_date ?? "—"}</td>
                    <td className="px-4 py-2">
                      {invoice.currency} {invoice.total}
                    </td>
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

function SummaryStat({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex flex-col gap-0.5">
      <span className="text-xs font-medium uppercase tracking-wide text-foreground/50">{label}</span>
      <span className="text-lg font-semibold">{value}</span>
    </div>
  );
}
