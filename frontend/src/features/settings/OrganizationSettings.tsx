import { useEffect, useMemo, useState } from "react";
import { zodResolver } from "@hookform/resolvers/zod";
import { useForm } from "react-hook-form";
import { useQueryClient } from "@tanstack/react-query";

import { ApiError } from "@/api/client";
import { updateOrganization, type UpdateOrganizationInput } from "@/api/settings";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { useAuth } from "@/contexts/AuthContext";
import { ORGANIZATIONS_QUERY_KEY } from "@/contexts/OrganizationContext";
import { organizationSettingsSchema, type OrganizationSettingsValues } from "@/features/settings/schemas";
import type { MembershipRole, OrganizationPublic } from "@/types/organization";

const DATE_FORMATS = [
  { value: "", label: "Browser default" },
  { value: "YYYY-MM-DD", label: "2026-11-27" },
  { value: "DD/MM/YYYY", label: "27/11/2026" },
  { value: "MM/DD/YYYY", label: "11/27/2026" },
];

// Owner: every field. Manager: contact details and date format (the
// backend's LIMITED scope). Everyone else sees the profile read-only.
const OWNER_ONLY: (keyof OrganizationSettingsValues)[] = ["name", "currency", "timezone"];

function toValues(organization: OrganizationPublic): OrganizationSettingsValues {
  return {
    name: organization.name,
    email: organization.email ?? "",
    phone: organization.phone ?? "",
    address: organization.address ?? "",
    currency: organization.currency,
    timezone: organization.timezone,
    date_format: organization.date_format ?? "",
  };
}

export function OrganizationSettings({ organization, role }: { organization: OrganizationPublic; role: MembershipRole }) {
  const { csrfToken } = useAuth();
  const queryClient = useQueryClient();
  const [saved, setSaved] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);

  const isOwner = role === "owner";
  const canEdit = role === "owner" || role === "manager";

  const timezones = useMemo(() => {
    const zones = Intl.supportedValuesOf("timeZone");
    return zones.includes(organization.timezone) ? zones : [organization.timezone, ...zones];
  }, [organization.timezone]);

  const {
    register,
    handleSubmit,
    reset,
    setError,
    formState: { errors, isSubmitting, dirtyFields, isDirty },
  } = useForm<OrganizationSettingsValues>({
    resolver: zodResolver(organizationSettingsSchema),
    defaultValues: toValues(organization),
  });

  useEffect(() => reset(toValues(organization)), [organization, reset]);

  const onSubmit = async (values: OrganizationSettingsValues) => {
    if (!csrfToken) return;
    setSaved(false);
    setSubmitError(null);
    // Only what changed - so a manager never sends an owner-only field.
    const changed: UpdateOrganizationInput = {};
    for (const key of Object.keys(dirtyFields) as (keyof OrganizationSettingsValues)[]) {
      const value = values[key].trim();
      if (key === "name" || key === "currency" || key === "timezone") changed[key] = key === "currency" ? value.toUpperCase() : value;
      else changed[key] = value === "" ? null : value;
    }
    try {
      const updated = await updateOrganization(organization.id, changed, csrfToken);
      await queryClient.invalidateQueries({ queryKey: ORGANIZATIONS_QUERY_KEY });
      reset(toValues(updated));
      setSaved(true);
    } catch (error) {
      if (error instanceof ApiError) {
        for (const [field, message] of Object.entries(error.details)) {
          if (field in values) setError(field as keyof OrganizationSettingsValues, { message });
        }
        setSubmitError(error.message);
      } else {
        setSubmitError("Something went wrong. Please try again.");
      }
    }
  };

  const ownerOnlyHint = !isOwner && canEdit ? "Only the owner can change this." : undefined;
  const disabled = (field: keyof OrganizationSettingsValues) => !canEdit || (!isOwner && OWNER_ONLY.includes(field));

  return (
    <form className="flex flex-col gap-5 rounded-md border border-border bg-card p-4 sm:p-6" onSubmit={handleSubmit(onSubmit)} noValidate>
      <div>
        <h2 className="text-lg font-medium">Organization profile</h2>
        <p className="text-sm text-muted-foreground">
          {canEdit
            ? "Shown on invoices and used for dates, deadlines and amounts across FlowDesk."
            : "Only the owner and managers can change these details."}
        </p>
      </div>

      <Field id="org-name" label="Name" error={errors.name?.message} hint={ownerOnlyHint}>
        <Input id="org-name" disabled={disabled("name")} {...register("name")} />
      </Field>

      <div className="grid gap-5 sm:grid-cols-2">
        <Field id="org-email" label="Contact email" error={errors.email?.message}>
          <Input id="org-email" type="email" disabled={disabled("email")} {...register("email")} />
        </Field>
        <Field id="org-phone" label="Phone" error={errors.phone?.message}>
          <Input id="org-phone" disabled={disabled("phone")} {...register("phone")} />
        </Field>
      </div>

      <Field id="org-address" label="Address" error={errors.address?.message}>
        <Textarea id="org-address" rows={3} disabled={disabled("address")} {...register("address")} />
      </Field>

      <div className="grid gap-5 sm:grid-cols-3">
        <Field id="org-currency" label="Currency" error={errors.currency?.message} hint={ownerOnlyHint}>
          <Input id="org-currency" maxLength={3} className="uppercase" disabled={disabled("currency")} {...register("currency")} />
        </Field>
        <Field id="org-timezone" label="Timezone" error={errors.timezone?.message} hint={ownerOnlyHint}>
          <Select id="org-timezone" disabled={disabled("timezone")} {...register("timezone")}>
            {timezones.map((zone) => (
              <option key={zone} value={zone}>
                {zone.replaceAll("_", " ")}
              </option>
            ))}
          </Select>
        </Field>
        <Field id="org-date-format" label="Date format" error={errors.date_format?.message}>
          <Select id="org-date-format" disabled={disabled("date_format")} {...register("date_format")}>
            {DATE_FORMATS.map((format) => (
              <option key={format.value} value={format.value}>
                {format.label}
              </option>
            ))}
          </Select>
        </Field>
      </div>

      {submitError && (
        <p role="alert" className="text-sm text-destructive">
          {submitError}
        </p>
      )}

      {canEdit && (
        <div className="flex items-center gap-3">
          <Button type="submit" disabled={isSubmitting || !isDirty}>
            {isSubmitting ? "Saving…" : "Save changes"}
          </Button>
          {saved && !isDirty && <p className="text-sm text-success" role="status">Changes saved.</p>}
        </div>
      )}
    </form>
  );
}

function Field({
  id,
  label,
  error,
  hint,
  children,
}: {
  id: string;
  label: string;
  error?: string;
  hint?: string;
  children: React.ReactNode;
}) {
  return (
    <div className="flex flex-col gap-1.5">
      <Label htmlFor={id}>{label}</Label>
      {children}
      {error ? (
        <p className="text-sm text-destructive">{error}</p>
      ) : (
        hint && <p className="text-xs text-muted-foreground">{hint}</p>
      )}
    </div>
  );
}
