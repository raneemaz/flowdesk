import { useState } from "react";
import { zodResolver } from "@hookform/resolvers/zod";
import { useForm } from "react-hook-form";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";

import { ApiError } from "@/api/client";
import { createDepartment, deactivateDepartment, listDepartments, updateDepartment } from "@/api/departments";
import { listEmployees } from "@/api/employees";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { useAuth } from "@/contexts/AuthContext";
import { useOrganization } from "@/contexts/OrganizationContext";
import { canManageDepartments } from "@/features/employees/permissions";
import {
  createDepartmentSchema,
  updateDepartmentSchema,
  type CreateDepartmentFormValues,
  type UpdateDepartmentFormValues,
} from "@/features/departments/schemas";
import type { DepartmentPublic } from "@/types/department";

export function DepartmentsPage() {
  const { csrfToken } = useAuth();
  const { activeMembership } = useOrganization();
  const organizationId = activeMembership?.organization.id ?? "";
  const queryClient = useQueryClient();

  const canManage = activeMembership ? canManageDepartments(activeMembership.role) : false;

  const departmentsQueryKey = ["departments", organizationId];
  const { data: departments, isPending, isError, error } = useQuery({
    queryKey: departmentsQueryKey,
    queryFn: () => listDepartments(organizationId),
    enabled: Boolean(organizationId) && canManage,
  });

  // DepartmentPublic only exposes manager_membership_id as a raw id
  // (docs/API.md) - resolved to a display name here via the directory
  // this viewer already has full access to, rather than showing a
  // bare UUID in the table.
  const { data: employeesForNames } = useQuery({
    queryKey: ["employees-for-manager-names", organizationId],
    queryFn: () => listEmployees(organizationId, { perPage: 100 }),
    enabled: Boolean(organizationId) && canManage,
  });
  const managerNameById = new Map((employeesForNames?.employees ?? []).map((e) => [e.membership_id, e.name]));

  const invalidate = () => queryClient.invalidateQueries({ queryKey: departmentsQueryKey });

  if (!canManage) {
    return (
      <main className="flex min-h-screen flex-col items-center justify-center gap-3 bg-background text-foreground">
        <p role="alert" className="text-sm text-destructive">
          You don&apos;t have access to department management.
        </p>
        <Link to="/" className="text-sm font-medium text-primary hover:underline">
          Back to home
        </Link>
      </main>
    );
  }

  return (
    <main className="min-h-screen bg-background px-4 py-8 text-foreground">
      <div className="mx-auto flex max-w-2xl flex-col gap-6">
        <div className="flex items-center justify-between">
          <h1 className="text-2xl font-semibold">Departments</h1>
          <Link to="/" className="text-sm font-medium text-primary hover:underline">
            Back to home
          </Link>
        </div>

        <CreateDepartmentForm
          organizationId={organizationId}
          csrfToken={csrfToken}
          managerOptions={employeesForNames?.employees ?? []}
          onCreated={invalidate}
        />

        {isPending && <p className="text-sm text-foreground/70">Loading departments…</p>}

        {isError && (
          <p role="alert" className="text-sm text-destructive">
            {error instanceof ApiError ? error.message : "Something went wrong loading departments."}
          </p>
        )}

        {!isPending && !isError && departments && departments.length === 0 && (
          <p className="text-sm text-foreground/70">No departments yet.</p>
        )}

        {!isPending && !isError && departments && departments.length > 0 && (
          <ul className="flex flex-col gap-3">
            {departments.map((department) => (
              <DepartmentRow
                key={department.id}
                department={department}
                managerName={department.manager_membership_id ? managerNameById.get(department.manager_membership_id) : undefined}
                managerOptions={employeesForNames?.employees ?? []}
                organizationId={organizationId}
                csrfToken={csrfToken}
                onChanged={invalidate}
              />
            ))}
          </ul>
        )}
      </div>
    </main>
  );
}

function CreateDepartmentForm({
  organizationId,
  csrfToken,
  managerOptions,
  onCreated,
}: {
  organizationId: string;
  csrfToken: string | null;
  managerOptions: { membership_id: string; name: string }[];
  onCreated: () => void;
}) {
  const [isOpen, setIsOpen] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const {
    register,
    handleSubmit,
    reset,
    formState: { errors, isSubmitting },
  } = useForm<CreateDepartmentFormValues>({
    resolver: zodResolver(createDepartmentSchema),
    defaultValues: { name: "", description: "", manager_membership_id: "" },
  });

  if (!isOpen) {
    return (
      <Button type="button" variant="outline" className="self-start" onClick={() => setIsOpen(true)}>
        + New department
      </Button>
    );
  }

  const onSubmit = async (values: CreateDepartmentFormValues) => {
    if (!csrfToken) {
      setFormError("Your session is missing a CSRF token - please log in again.");
      return;
    }
    setFormError(null);
    try {
      await createDepartment(
        organizationId,
        {
          name: values.name,
          description: values.description || undefined,
          manager_membership_id: values.manager_membership_id || undefined,
        },
        csrfToken,
      );
      reset();
      setIsOpen(false);
      onCreated();
    } catch (submitError) {
      setFormError(submitError instanceof ApiError ? submitError.message : "Something went wrong. Please try again.");
    }
  };

  return (
    <form className="flex flex-col gap-4 rounded-md border border-border bg-card p-6" onSubmit={handleSubmit(onSubmit)} noValidate>
      <h2 className="text-lg font-medium">New department</h2>

      <div className="flex flex-col gap-1.5">
        <Label htmlFor="new-name">Name</Label>
        <Input id="new-name" aria-invalid={errors.name ? "true" : "false"} {...register("name")} />
        {errors.name && <p className="text-sm text-destructive">{errors.name.message}</p>}
      </div>

      <div className="flex flex-col gap-1.5">
        <Label htmlFor="new-description">Description (optional)</Label>
        <Textarea id="new-description" {...register("description")} />
      </div>

      <div className="flex flex-col gap-1.5">
        <Label htmlFor="new-manager">Manager (optional)</Label>
        <Select id="new-manager" {...register("manager_membership_id")}>
          <option value="">No manager</option>
          {managerOptions.map((candidate) => (
            <option key={candidate.membership_id} value={candidate.membership_id}>
              {candidate.name}
            </option>
          ))}
        </Select>
      </div>

      {formError && (
        <p role="alert" className="text-sm text-destructive">
          {formError}
        </p>
      )}

      <div className="flex gap-3">
        <Button type="submit" disabled={isSubmitting}>
          {isSubmitting ? "Creating…" : "Create department"}
        </Button>
        <Button type="button" variant="outline" onClick={() => setIsOpen(false)}>
          Cancel
        </Button>
      </div>
    </form>
  );
}

function DepartmentRow({
  department,
  managerName,
  managerOptions,
  organizationId,
  csrfToken,
  onChanged,
}: {
  department: DepartmentPublic;
  managerName: string | undefined;
  managerOptions: { membership_id: string; name: string }[];
  organizationId: string;
  csrfToken: string | null;
  onChanged: () => void;
}) {
  const [isEditing, setIsEditing] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<UpdateDepartmentFormValues>({
    resolver: zodResolver(updateDepartmentSchema),
    defaultValues: {
      name: department.name,
      description: department.description ?? "",
      manager_membership_id: department.manager_membership_id ?? "",
      status: department.status,
    },
  });

  const onSubmit = async (values: UpdateDepartmentFormValues) => {
    if (!csrfToken) {
      setFormError("Your session is missing a CSRF token - please log in again.");
      return;
    }
    setFormError(null);
    try {
      await updateDepartment(
        organizationId,
        department.id,
        {
          name: values.name,
          description: values.description || null,
          manager_membership_id: values.manager_membership_id || null,
          status: values.status,
        },
        csrfToken,
      );
      setIsEditing(false);
      onChanged();
    } catch (submitError) {
      setFormError(submitError instanceof ApiError ? submitError.message : "Something went wrong. Please try again.");
    }
  };

  const onDeactivate = async () => {
    if (!csrfToken) return;
    if (!window.confirm(`Deactivate ${department.name}? Existing employee/task history referencing it is kept.`)) return;
    try {
      await deactivateDepartment(organizationId, department.id, csrfToken);
      onChanged();
    } catch {
      setFormError("Could not deactivate this department. Please try again.");
    }
  };

  if (isEditing) {
    return (
      <li className="rounded-md border border-border bg-card p-4">
        <form className="flex flex-col gap-4" onSubmit={handleSubmit(onSubmit)} noValidate>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor={`name-${department.id}`}>Name</Label>
            <Input id={`name-${department.id}`} aria-invalid={errors.name ? "true" : "false"} {...register("name")} />
            {errors.name && <p className="text-sm text-destructive">{errors.name.message}</p>}
          </div>

          <div className="flex flex-col gap-1.5">
            <Label htmlFor={`description-${department.id}`}>Description</Label>
            <Textarea id={`description-${department.id}`} {...register("description")} />
          </div>

          <div className="flex flex-col gap-1.5">
            <Label htmlFor={`manager-${department.id}`}>Manager</Label>
            <Select id={`manager-${department.id}`} {...register("manager_membership_id")}>
              <option value="">No manager</option>
              {managerOptions.map((candidate) => (
                <option key={candidate.membership_id} value={candidate.membership_id}>
                  {candidate.name}
                </option>
              ))}
            </Select>
          </div>

          <div className="flex flex-col gap-1.5">
            <Label htmlFor={`status-${department.id}`}>Status</Label>
            <Select id={`status-${department.id}`} {...register("status")}>
              <option value="active">Active</option>
              <option value="inactive">Inactive</option>
            </Select>
          </div>

          {formError && (
            <p role="alert" className="text-sm text-destructive">
              {formError}
            </p>
          )}

          <div className="flex gap-3">
            <Button type="submit" disabled={isSubmitting}>
              {isSubmitting ? "Saving…" : "Save changes"}
            </Button>
            <Button type="button" variant="outline" onClick={() => setIsEditing(false)}>
              Cancel
            </Button>
          </div>
        </form>
      </li>
    );
  }

  return (
    <li className="flex items-center justify-between rounded-md border border-border bg-card p-4">
      <div className="flex flex-col gap-0.5">
        <p className="font-medium">
          {department.name}{" "}
          {department.status === "inactive" && <span className="text-xs font-normal text-foreground/50">(inactive)</span>}
        </p>
        {department.description && <p className="text-sm text-foreground/70">{department.description}</p>}
        <p className="text-sm text-foreground/50">Manager: {managerName ?? "—"}</p>
        {formError && (
          <p role="alert" className="text-sm text-destructive">
            {formError}
          </p>
        )}
      </div>
      <div className="flex gap-2">
        <Button type="button" variant="outline" size="sm" onClick={() => setIsEditing(true)}>
          Edit
        </Button>
        {department.status === "active" && (
          <Button type="button" variant="destructive" size="sm" onClick={() => void onDeactivate()}>
            Deactivate
          </Button>
        )}
      </div>
    </li>
  );
}
