import { useState } from "react";
import { zodResolver } from "@hookform/resolvers/zod";
import { useForm } from "react-hook-form";

import { ApiError } from "@/api/client";
import { changePassword, updateProfile } from "@/api/settings";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useAuth } from "@/contexts/AuthContext";
import {
  changePasswordSchema,
  profileSchema,
  type ChangePasswordValues,
  type ProfileValues,
} from "@/features/settings/schemas";

// Settings > My account - available to every role.
export function AccountSettings() {
  return (
    <div className="flex flex-col gap-6">
      <ProfileForm />
      <PasswordForm />
    </div>
  );
}

function ProfileForm() {
  const { user, csrfToken, replaceUser } = useAuth();
  const [saved, setSaved] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const {
    register,
    handleSubmit,
    reset,
    formState: { errors, isSubmitting, isDirty },
  } = useForm<ProfileValues>({ resolver: zodResolver(profileSchema), defaultValues: { name: user?.name ?? "" } });

  const onSubmit = async (values: ProfileValues) => {
    if (!csrfToken) return;
    setSaved(false);
    setSubmitError(null);
    try {
      const updated = await updateProfile({ name: values.name }, csrfToken);
      replaceUser(updated);
      reset({ name: updated.name });
      setSaved(true);
    } catch (error) {
      setSubmitError(error instanceof ApiError ? error.message : "Something went wrong. Please try again.");
    }
  };

  return (
    <form className="flex flex-col gap-5 rounded-md border border-border bg-card p-4 sm:p-6" onSubmit={handleSubmit(onSubmit)} noValidate>
      <h2 className="text-lg font-medium">Profile</h2>
      <div className="flex flex-col gap-1.5">
        <Label htmlFor="account-name">Your name</Label>
        <Input id="account-name" autoComplete="name" {...register("name")} />
        {errors.name && <p className="text-sm text-destructive">{errors.name.message}</p>}
      </div>
      <div className="flex flex-col gap-1.5">
        <Label htmlFor="account-email">Email</Label>
        <Input id="account-email" value={user?.email ?? ""} disabled readOnly />
        <p className="text-xs text-muted-foreground">You sign in with this address, so it can't be changed here.</p>
      </div>
      {submitError && (
        <p role="alert" className="text-sm text-destructive">
          {submitError}
        </p>
      )}
      <div className="flex items-center gap-3">
        <Button type="submit" disabled={isSubmitting || !isDirty}>
          {isSubmitting ? "Saving…" : "Save name"}
        </Button>
        {saved && !isDirty && <p className="text-sm text-success" role="status">Name saved.</p>}
      </div>
    </form>
  );
}

function PasswordForm() {
  const { csrfToken } = useAuth();
  const [changed, setChanged] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const {
    register,
    handleSubmit,
    reset,
    setError,
    formState: { errors, isSubmitting },
  } = useForm<ChangePasswordValues>({
    resolver: zodResolver(changePasswordSchema),
    defaultValues: { current_password: "", new_password: "", confirm_password: "" },
  });

  const onSubmit = async (values: ChangePasswordValues) => {
    if (!csrfToken) return;
    setChanged(false);
    setSubmitError(null);
    try {
      await changePassword({ current_password: values.current_password, new_password: values.new_password }, csrfToken);
      reset();
      setChanged(true);
    } catch (error) {
      if (error instanceof ApiError && error.details.current_password) {
        setError("current_password", { message: "That's not your current password." });
      } else if (error instanceof ApiError && error.details.new_password) {
        setError("new_password", { message: error.details.new_password });
      } else {
        setSubmitError(error instanceof ApiError ? error.message : "Something went wrong. Please try again.");
      }
    }
  };

  return (
    <form className="flex flex-col gap-5 rounded-md border border-border bg-card p-4 sm:p-6" onSubmit={handleSubmit(onSubmit)} noValidate>
      <h2 className="text-lg font-medium">Change password</h2>
      <div className="flex flex-col gap-1.5">
        <Label htmlFor="current-password">Current password</Label>
        <Input id="current-password" type="password" autoComplete="current-password" {...register("current_password")} />
        {errors.current_password && <p className="text-sm text-destructive">{errors.current_password.message}</p>}
      </div>
      <div className="grid gap-5 sm:grid-cols-2">
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="new-password">New password</Label>
          <Input id="new-password" type="password" autoComplete="new-password" {...register("new_password")} />
          {errors.new_password ? (
            <p className="text-sm text-destructive">{errors.new_password.message}</p>
          ) : (
            <p className="text-xs text-muted-foreground">At least 8 characters.</p>
          )}
        </div>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="confirm-password">Confirm new password</Label>
          <Input id="confirm-password" type="password" autoComplete="new-password" {...register("confirm_password")} />
          {errors.confirm_password && <p className="text-sm text-destructive">{errors.confirm_password.message}</p>}
        </div>
      </div>
      {submitError && (
        <p role="alert" className="text-sm text-destructive">
          {submitError}
        </p>
      )}
      <div className="flex items-center gap-3">
        <Button type="submit" disabled={isSubmitting}>
          {isSubmitting ? "Changing…" : "Change password"}
        </Button>
        {changed && <p className="text-sm text-success" role="status">Password changed.</p>}
      </div>
    </form>
  );
}
