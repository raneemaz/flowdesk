import { useEffect, useState } from "react";
import { zodResolver } from "@hookform/resolvers/zod";
import { useForm } from "react-hook-form";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";

import { ApiError } from "@/api/client";
import { listDepartments } from "@/api/departments";
import { getEmployee, listEmployees, updateEmployeeProfile } from "@/api/employees";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { useAuth } from "@/contexts/AuthContext";
import { useOrganization } from "@/contexts/OrganizationContext";
import { EMPLOYEE_STATUS_OPTIONS, ROLE_LABELS } from "@/features/employees/constants";
import { canManageEmployeeProfile } from "@/features/employees/permissions";
import { updateEmployeeProfileSchema, type UpdateEmployeeProfileFormValues } from "@/features/employees/schemas";

export function EmployeeProfilePage() {
  const { membershipId } = useParams<{ membershipId: string }>();
  const { csrfToken } = useAuth();
  const { activeMembership } = useOrganization();
  const organizationId = activeMembership?.organization.id ?? "";
  const queryClient = useQueryClient();
  const [isEditing, setIsEditing] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);

  const employeeQueryKey = ["employee", organizationId, membershipId];
  const { data: employee, isPending, isError, error } = useQuery({
    queryKey: employeeQueryKey,
    queryFn: () => getEmployee(organizationId, membershipId!),
    enabled: Boolean(organizationId && membershipId),
  });

  const canEdit = Boolean(activeMembership && employee && canManageEmployeeProfile(activeMembership.role, employee.role));

  // Whoever can edit a profile (Owner/Manager) can also always list
  // departments and the full employee directory (both EMPLOYEE_MANAGE
  // and EMPLOYEE_DIRECTORY_VIEW full/DEPARTMENT_MANAGE are Owner/
  // Manager-only - backend/app/authz/permissions.py), so these picker
  // queries never 403 when they're actually rendered.
  const { data: departments } = useQuery({
    queryKey: ["departments", organizationId],
    queryFn: () => listDepartments(organizationId),
    enabled: canEdit,
  });
  const { data: managerOptions } = useQuery({
    queryKey: ["employees-for-manager-picker", organizationId],
    queryFn: () => listEmployees(organizationId, { perPage: 100 }),
    enabled: canEdit,
  });

  const {
    register,
    handleSubmit,
    reset,
    formState: { errors, isSubmitting },
  } = useForm<UpdateEmployeeProfileFormValues>({
    resolver: zodResolver(updateEmployeeProfileSchema),
    defaultValues: { job_title: "", department_id: "", manager_membership_id: "", status: "active" },
  });

  useEffect(() => {
    if (employee && isEditing) {
      reset({
        job_title: employee.job_title ?? "",
        department_id: employee.department?.id ?? "",
        manager_membership_id: employee.manager?.membership_id ?? "",
        status: employee.status ?? "active",
      });
    }
  }, [employee, isEditing, reset]);

  const onSubmit = async (values: UpdateEmployeeProfileFormValues) => {
    if (!csrfToken || !membershipId) return;
    setFormError(null);
    try {
      await updateEmployeeProfile(
        organizationId,
        membershipId,
        {
          job_title: values.job_title || null,
          department_id: values.department_id || null,
          manager_membership_id: values.manager_membership_id || null,
          status: values.status,
        },
        csrfToken,
      );
      await queryClient.invalidateQueries({ queryKey: employeeQueryKey });
      setIsEditing(false);
      setSuccessMessage("Profile updated.");
    } catch (submitError) {
      setFormError(submitError instanceof ApiError ? submitError.message : "Something went wrong. Please try again.");
    }
  };

  if (isPending) {
    return (
      <div className="flex items-center justify-center px-6 py-24">
        <p className="text-sm text-foreground/70">Loading employee…</p>
      </div>
    );
  }

  if (isError || !employee) {
    return (
      <div className="flex flex-col items-center justify-center gap-3 px-6 py-24">
        <p role="alert" className="text-sm text-destructive">
          {error instanceof ApiError ? error.message : "Employee not found."}
        </p>
        <Link to="/employees" className="text-sm font-medium text-primary hover:underline">
          Back to directory
        </Link>
      </div>
    );
  }

  const isFullScope = "email" in employee;

  return (
    <div className="px-4 py-6 sm:px-6 sm:py-8 lg:px-10">
      <div className="flex max-w-3xl flex-col gap-6">
        <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2">
          <h1 className="text-2xl font-semibold">{employee.name}</h1>
          <Link to="/employees" className="text-sm font-medium text-primary hover:underline">
            Back to directory
          </Link>
        </div>

        {successMessage && <p className="text-sm text-foreground/70">{successMessage}</p>}

        {!isEditing && (
          <div className="flex flex-col gap-3 rounded-md border border-border bg-card p-4 sm:p-6">
            <Field label="Role" value={ROLE_LABELS[employee.role]} />
            <Field label="Status" value={employee.status ?? "Not set"} />
            {isFullScope && <Field label="Email" value={employee.email ?? "—"} />}
            {isFullScope && <Field label="Job title" value={employee.job_title ?? "—"} />}
            {isFullScope && <Field label="Department" value={employee.department?.name ?? "—"} />}
            {isFullScope && <Field label="Manager" value={employee.manager?.name ?? "—"} />}

            {canEdit && (
              <Button className="mt-2 self-start" onClick={() => setIsEditing(true)}>
                Edit profile
              </Button>
            )}
          </div>
        )}

        {isEditing && (
          <form
            className="flex flex-col gap-4 rounded-md border border-border bg-card p-4 sm:p-6"
            onSubmit={handleSubmit(onSubmit)}
            noValidate
          >
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="job_title">Job title</Label>
              <Input id="job_title" {...register("job_title")} />
              {errors.job_title && <p className="text-sm text-destructive">{errors.job_title.message}</p>}
            </div>

            <div className="flex flex-col gap-1.5">
              <Label htmlFor="department_id">Department</Label>
              <Select id="department_id" {...register("department_id")}>
                <option value="">No department</option>
                {departments
                  ?.filter((department) => department.status === "active")
                  .map((department) => (
                    <option key={department.id} value={department.id}>
                      {department.name}
                    </option>
                  ))}
              </Select>
            </div>

            <div className="flex flex-col gap-1.5">
              <Label htmlFor="manager_membership_id">Manager</Label>
              <Select id="manager_membership_id" {...register("manager_membership_id")}>
                <option value="">No manager</option>
                {managerOptions?.employees
                  .filter((candidate) => candidate.membership_id !== membershipId)
                  .map((candidate) => (
                    <option key={candidate.membership_id} value={candidate.membership_id}>
                      {candidate.name}
                    </option>
                  ))}
              </Select>
            </div>

            <div className="flex flex-col gap-1.5">
              <Label htmlFor="status">Employment status</Label>
              <Select id="status" {...register("status")}>
                {EMPLOYEE_STATUS_OPTIONS.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
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
                {isSubmitting ? "Saving…" : "Save changes"}
              </Button>
              <Button type="button" variant="outline" onClick={() => setIsEditing(false)}>
                Cancel
              </Button>
            </div>
          </form>
        )}
      </div>
    </div>
  );
}

function Field({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex flex-col gap-0.5">
      <span className="text-xs font-medium text-muted-foreground">{label}</span>
      <span className="text-sm">{value}</span>
    </div>
  );
}
