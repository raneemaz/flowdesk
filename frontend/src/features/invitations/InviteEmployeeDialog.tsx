import { useState } from "react";
import { zodResolver } from "@hookform/resolvers/zod";
import { useForm } from "react-hook-form";
import { useQueryClient } from "@tanstack/react-query";

import { createInvitation } from "@/api/invitations";
import { ApiError } from "@/api/client";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { useAuth } from "@/contexts/AuthContext";
import { ROLE_OPTIONS } from "@/features/employees/constants";
import { invitableRoles } from "@/features/employees/permissions";
import { inviteEmployeeSchema, type InviteEmployeeFormValues } from "@/features/invitations/schemas";
import type { MembershipRole } from "@/types/organization";

interface InviteEmployeeDialogProps {
  organizationId: string;
  viewerRole: MembershipRole;
}

// The one place in this app so far where "+ New X" opens as a dialog
// over the current page rather than replacing it - every list page
// this invite lives on (the employee directory) stays visible and
// searchable underneath, instead of navigating away to a separate form
// screen the way customers/departments/tasks currently do.
export function InviteEmployeeDialog({ organizationId, viewerRole }: InviteEmployeeDialogProps) {
  const { csrfToken } = useAuth();
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);

  const allowedRoles = invitableRoles(viewerRole);
  const roleOptions = ROLE_OPTIONS.filter((option) => allowedRoles.includes(option.value));

  const {
    register,
    handleSubmit,
    reset,
    formState: { errors, isSubmitting },
  } = useForm<InviteEmployeeFormValues>({
    resolver: zodResolver(inviteEmployeeSchema),
    defaultValues: { email: "", role: roleOptions[0]?.value ?? "employee" },
  });

  const onSubmit = async (values: InviteEmployeeFormValues) => {
    if (!csrfToken) {
      setFormError("Your session is missing a CSRF token - please log in again.");
      return;
    }
    setFormError(null);
    setSuccessMessage(null);
    try {
      const invitation = await createInvitation(organizationId, values, csrfToken);
      await queryClient.invalidateQueries({ queryKey: ["invitations", organizationId] });
      setSuccessMessage(`Invitation sent to ${invitation.email}.`);
      reset({ email: "", role: roleOptions[0]?.value ?? "employee" });
    } catch (error) {
      setFormError(error instanceof ApiError ? error.message : "Something went wrong. Please try again.");
    }
  };

  if (roleOptions.length === 0) {
    // Mirrors canInviteEmployees - nothing to render for a role that
    // can never invite anyone (never a disabled/broken-looking button).
    return null;
  }

  return (
    <Dialog
      open={open}
      onOpenChange={(nextOpen) => {
        setOpen(nextOpen);
        if (!nextOpen) {
          setFormError(null);
          setSuccessMessage(null);
        }
      }}
    >
      <DialogTrigger asChild>
        <Button type="button">+ Invite employee</Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Invite someone to your organization</DialogTitle>
          <DialogDescription>
            They'll get an email with a link to accept. The invitation expires after a few days if unused.
          </DialogDescription>
        </DialogHeader>

        <form className="flex flex-col gap-4" onSubmit={handleSubmit(onSubmit)} noValidate>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="invite-email">Email</Label>
            <Input
              id="invite-email"
              type="email"
              autoComplete="email"
              aria-invalid={errors.email ? "true" : "false"}
              {...register("email")}
            />
            {errors.email && <p className="text-sm text-destructive">{errors.email.message}</p>}
          </div>

          <div className="flex flex-col gap-1.5">
            <Label htmlFor="invite-role">Role</Label>
            <Select id="invite-role" aria-invalid={errors.role ? "true" : "false"} {...register("role")}>
              {roleOptions.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </Select>
            {errors.role && <p className="text-sm text-destructive">{errors.role.message}</p>}
          </div>

          {formError && (
            <p role="alert" className="text-sm text-destructive">
              {formError}
            </p>
          )}
          {successMessage && <p className="text-sm text-success">{successMessage}</p>}

          <DialogFooter>
            <Button type="submit" disabled={isSubmitting}>
              {isSubmitting ? "Sending…" : "Send invitation"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
