import { useState, type FormEvent } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";

import { listDepartments } from "@/api/departments";
import { ApiError } from "@/api/client";
import { listEmployees } from "@/api/employees";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { useOrganization } from "@/contexts/OrganizationContext";
import { EMPLOYEE_STATUS_OPTIONS, ROLE_LABELS, ROLE_OPTIONS } from "@/features/employees/constants";
import { canManageDepartments } from "@/features/employees/permissions";
import type { EmployeeProfileStatus } from "@/types/employee";
import type { MembershipRole } from "@/types/organization";

const PER_PAGE = 20;

interface Filters {
  search: string;
  role: MembershipRole | "";
  status: EmployeeProfileStatus | "";
  departmentId: string;
}

const EMPTY_FILTERS: Filters = { search: "", role: "", status: "", departmentId: "" };

// Deliberately minimal (no page-level nav of its own). Reached via
// the dashboard shell's "Employees" sidebar link (FD-053).
export function EmployeeDirectoryPage() {
  const { activeMembership } = useOrganization();
  const organizationId = activeMembership?.organization.id ?? "";

  const [draftFilters, setDraftFilters] = useState<Filters>(EMPTY_FILTERS);
  const [appliedFilters, setAppliedFilters] = useState<Filters>(EMPTY_FILTERS);
  const [page, setPage] = useState(1);

  // Only Owner/Manager can list departments (DEPARTMENT_MANAGE has no
  // "limited view" cell, docs/API.md) - everyone else simply doesn't
  // get a department filter, rather than this query 403ing on every
  // directory visit.
  const canSeeDepartments = activeMembership ? canManageDepartments(activeMembership.role) : false;
  const { data: departments } = useQuery({
    queryKey: ["departments", organizationId],
    queryFn: () => listDepartments(organizationId),
    enabled: canSeeDepartments,
  });

  const { data, isPending, isError, error } = useQuery({
    queryKey: ["employees", organizationId, appliedFilters, page],
    queryFn: () =>
      listEmployees(organizationId, {
        search: appliedFilters.search || undefined,
        role: appliedFilters.role || undefined,
        status: appliedFilters.status || undefined,
        departmentId: appliedFilters.departmentId || undefined,
        page,
        perPage: PER_PAGE,
      }),
    enabled: Boolean(organizationId),
  });

  const employees = data?.employees ?? [];
  const meta = data?.meta;
  // The response's field set depends on the caller's scope
  // (docs/API.md) - detected from the data itself (does a record carry
  // "email") rather than re-deriving the scope from role client-side,
  // so the table always matches what was actually returned, with the
  // viewer's role only as a fallback for an empty page.
  const isFullScope =
    employees.length > 0 ? "email" in employees[0] : activeMembership?.role === "owner" || activeMembership?.role === "manager";

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
      <div className="mx-auto flex max-w-4xl flex-col gap-6">
        <div className="flex items-center justify-between">
          <h1 className="text-2xl font-semibold">Employee directory</h1>
          <Link to="/" className="text-sm font-medium text-primary hover:underline">
            Back to home
          </Link>
        </div>

        <form className="flex flex-wrap items-end gap-3 rounded-md border border-border bg-card p-4" onSubmit={applyFilters}>
          <div className="flex min-w-[180px] flex-1 flex-col gap-1.5">
            <Label htmlFor="search">Search by name</Label>
            <Input
              id="search"
              value={draftFilters.search}
              onChange={(event) => setDraftFilters((prev) => ({ ...prev, search: event.target.value }))}
            />
          </div>

          <div className="flex flex-col gap-1.5">
            <Label htmlFor="role-filter">Role</Label>
            <Select
              id="role-filter"
              value={draftFilters.role}
              onChange={(event) => setDraftFilters((prev) => ({ ...prev, role: event.target.value as MembershipRole | "" }))}
            >
              <option value="">All roles</option>
              {ROLE_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </Select>
          </div>

          <div className="flex flex-col gap-1.5">
            <Label htmlFor="status-filter">Status</Label>
            <Select
              id="status-filter"
              value={draftFilters.status}
              onChange={(event) =>
                setDraftFilters((prev) => ({ ...prev, status: event.target.value as EmployeeProfileStatus | "" }))
              }
            >
              <option value="">All statuses</option>
              {EMPLOYEE_STATUS_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </Select>
          </div>

          {canSeeDepartments && departments && departments.length > 0 && (
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="department-filter">Department</Label>
              <Select
                id="department-filter"
                value={draftFilters.departmentId}
                onChange={(event) => setDraftFilters((prev) => ({ ...prev, departmentId: event.target.value }))}
              >
                <option value="">All departments</option>
                {departments.map((department) => (
                  <option key={department.id} value={department.id}>
                    {department.name}
                  </option>
                ))}
              </Select>
            </div>
          )}

          <Button type="submit">Search</Button>
          <Button type="button" variant="outline" onClick={clearFilters}>
            Clear
          </Button>
        </form>

        {isPending && <p className="text-sm text-foreground/70">Loading employees…</p>}

        {isError && (
          <p role="alert" className="text-sm text-destructive">
            {error instanceof ApiError ? error.message : "Something went wrong loading the directory."}
          </p>
        )}

        {!isPending && !isError && employees.length === 0 && (
          <p className="text-sm text-foreground/70">No employees match these filters.</p>
        )}

        {!isPending && !isError && employees.length > 0 && (
          <div className="overflow-hidden rounded-md border border-border">
            <table className="w-full text-left text-sm">
              <thead className="bg-card">
                <tr>
                  <th className="px-4 py-2 font-medium">Name</th>
                  <th className="px-4 py-2 font-medium">Role</th>
                  <th className="px-4 py-2 font-medium">Status</th>
                  {isFullScope && <th className="px-4 py-2 font-medium">Job title</th>}
                  {isFullScope && <th className="px-4 py-2 font-medium">Department</th>}
                </tr>
              </thead>
              <tbody>
                {employees.map((employee) => (
                  <tr key={employee.membership_id} className="border-t border-border">
                    <td className="px-4 py-2">
                      <Link to={`/employees/${employee.membership_id}`} className="font-medium text-primary hover:underline">
                        {employee.name}
                      </Link>
                    </td>
                    <td className="px-4 py-2">{ROLE_LABELS[employee.role]}</td>
                    <td className="px-4 py-2">{employee.status ?? "—"}</td>
                    {isFullScope && <td className="px-4 py-2">{employee.job_title ?? "—"}</td>}
                    {isFullScope && <td className="px-4 py-2">{employee.department?.name ?? "—"}</td>}
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
