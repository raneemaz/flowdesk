import { useState } from "react";
import { zodResolver } from "@hookform/resolvers/zod";
import { useForm } from "react-hook-form";
import { useQueryClient } from "@tanstack/react-query";
import { Link, useNavigate } from "react-router-dom";

import { createOrganization } from "@/api/organizations";
import { ApiError } from "@/api/client";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { useAuth } from "@/contexts/AuthContext";
import { ORGANIZATIONS_QUERY_KEY, useOrganization } from "@/contexts/OrganizationContext";
import { COMMON_CURRENCIES, COMMON_TIMEZONES } from "@/features/organizations/constants";
import { createOrganizationSchema, type CreateOrganizationFormValues } from "@/features/organizations/schemas";

export function CreateOrganizationPage() {
  const { csrfToken } = useAuth();
  const { memberships, switchOrganization } = useOrganization();
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const [formError, setFormError] = useState<string | null>(null);

  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<CreateOrganizationFormValues>({
    resolver: zodResolver(createOrganizationSchema),
    defaultValues: { currency: "USD", timezone: "UTC" },
  });

  // Creating the very first organization is the one case where it's safe
  // to go straight back to "/" afterward without a confirmation step -
  // anyone who already has at least one has somewhere to cancel back to.
  const hasExistingOrganizations = memberships.length > 0;

  const onSubmit = async (values: CreateOrganizationFormValues) => {
    if (!csrfToken) {
      setFormError("Your session is missing a CSRF token - please log in again.");
      return;
    }
    setFormError(null);
    try {
      const organization = await createOrganization(
        {
          name: values.name,
          email: values.email || undefined,
          currency: values.currency || undefined,
          timezone: values.timezone || undefined,
        },
        csrfToken,
      );
      await queryClient.invalidateQueries({ queryKey: ORGANIZATIONS_QUERY_KEY });
      switchOrganization(organization.id);
      navigate("/", { replace: true });
    } catch (error) {
      setFormError(error instanceof ApiError ? error.message : "Something went wrong. Please try again.");
    }
  };

  return (
    <div className="flex justify-center px-6 py-16">
      <div className="w-full max-w-sm rounded-md border border-border bg-card p-4 sm:p-6 shadow-sm">
        <h1 className="mb-2 text-xl font-semibold">Create an organization</h1>
        <p className="mb-6 text-sm text-foreground/70">
          You&apos;ll become its Owner. Only the name is required - everything else can be added later.
        </p>

        <form className="flex flex-col gap-4" onSubmit={handleSubmit(onSubmit)} noValidate>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="name">Organization name</Label>
            <Input id="name" autoComplete="organization" aria-invalid={errors.name ? "true" : "false"} {...register("name")} />
            {errors.name && <p className="text-sm text-destructive">{errors.name.message}</p>}
          </div>

          <div className="flex flex-col gap-1.5">
            <Label htmlFor="email">Business email (optional)</Label>
            <Input id="email" type="email" aria-invalid={errors.email ? "true" : "false"} {...register("email")} />
            {errors.email && <p className="text-sm text-destructive">{errors.email.message}</p>}
          </div>

          <div className="flex flex-col gap-1.5">
            <Label htmlFor="currency">Currency</Label>
            <Select id="currency" {...register("currency")}>
              {COMMON_CURRENCIES.map((code) => (
                <option key={code} value={code}>
                  {code}
                </option>
              ))}
            </Select>
          </div>

          <div className="flex flex-col gap-1.5">
            <Label htmlFor="timezone">Timezone</Label>
            <Select id="timezone" {...register("timezone")}>
              {COMMON_TIMEZONES.map((zone) => (
                <option key={zone} value={zone}>
                  {zone}
                </option>
              ))}
            </Select>
          </div>

          {formError && (
            <p role="alert" className="text-sm text-destructive">
              {formError}
            </p>
          )}

          <Button type="submit" disabled={isSubmitting}>
            {isSubmitting ? "Creating organization…" : "Create organization"}
          </Button>
        </form>

        {hasExistingOrganizations && (
          <p className="mt-6 text-sm text-foreground/70">
            <Link to="/" className="font-medium text-primary hover:underline">
              Cancel
            </Link>
          </p>
        )}
      </div>
    </div>
  );
}
