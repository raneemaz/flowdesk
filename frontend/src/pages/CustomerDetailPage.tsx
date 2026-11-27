import { useEffect, useState } from "react";
import { zodResolver } from "@hookform/resolvers/zod";
import { useForm } from "react-hook-form";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";

import { ApiError } from "@/api/client";
import { archiveCustomer, getCustomer, updateCustomer } from "@/api/customers";
import { listRequests } from "@/api/customerRequests";
import { ConfirmDialog } from "@/components/ConfirmDialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { useAuth } from "@/contexts/AuthContext";
import { useOrganization } from "@/contexts/OrganizationContext";
import { canAccessRequests } from "@/features/requests/permissions";
import { STATUS_LABELS as REQUEST_STATUS_LABELS } from "@/features/requests/constants";
import { updateCustomerSchema, type UpdateCustomerFormValues } from "@/features/customers/schemas";

export function CustomerDetailPage() {
  const { customerId } = useParams<{ customerId: string }>();
  const { csrfToken } = useAuth();
  const { activeMembership } = useOrganization();
  const organizationId = activeMembership?.organization.id ?? "";
  const queryClient = useQueryClient();
  const [isEditing, setIsEditing] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  const customerQueryKey = ["customer", organizationId, customerId];
  const { data: customer, isPending, isError, error } = useQuery({
    queryKey: customerQueryKey,
    queryFn: () => getCustomer(organizationId, customerId!),
    enabled: Boolean(organizationId && customerId),
  });

  // FR-022: "customer profile shows request + invoice history" -
  // invoices don't exist yet (a later epic), so this is the request
  // half. Gated on canAccessRequests - Accountant can view a customer
  // profile (CUSTOMER_MANAGE includes them) but has no
  // CUSTOMER_REQUEST_MANAGE reach at all, so this query would just
  // 403 for that role if it ran unconditionally.
  const canSeeRequests = activeMembership ? canAccessRequests(activeMembership.role) : false;
  const { data: requestsData } = useQuery({
    queryKey: ["requests-for-customer", organizationId, customerId],
    queryFn: () => listRequests(organizationId, { customerId, perPage: 50 }),
    enabled: canSeeRequests && Boolean(organizationId && customerId),
  });

  const {
    register,
    handleSubmit,
    reset,
    formState: { errors, isSubmitting },
  } = useForm<UpdateCustomerFormValues>({
    resolver: zodResolver(updateCustomerSchema),
    defaultValues: { name: "", email: "", phone: "", company: "", address: "", notes: "", status: "active" },
  });

  useEffect(() => {
    if (customer && isEditing) {
      reset({
        name: customer.name,
        email: customer.email ?? "",
        phone: customer.phone ?? "",
        company: customer.company ?? "",
        address: customer.address ?? "",
        notes: customer.notes ?? "",
        status: customer.status,
      });
    }
  }, [customer, isEditing, reset]);

  const onSubmit = async (values: UpdateCustomerFormValues) => {
    if (!csrfToken || !customerId) return;
    setFormError(null);
    try {
      await updateCustomer(
        organizationId,
        customerId,
        {
          name: values.name,
          email: values.email || null,
          phone: values.phone || null,
          company: values.company || null,
          address: values.address || null,
          notes: values.notes || null,
          status: values.status,
        },
        csrfToken,
      );
      await queryClient.invalidateQueries({ queryKey: customerQueryKey });
      setIsEditing(false);
    } catch (submitError) {
      setFormError(submitError instanceof ApiError ? submitError.message : "Something went wrong. Please try again.");
    }
  };

  const [isConfirmingArchive, setIsConfirmingArchive] = useState(false);
  const onArchive = async () => {
    if (!csrfToken || !customerId || !customer) return;
    try {
      await archiveCustomer(organizationId, customerId, csrfToken);
    } catch {
      throw new Error("Could not archive this customer. Please try again.");
    }
    await queryClient.invalidateQueries({ queryKey: customerQueryKey });
  };

  if (isPending) {
    return (
      <div className="flex items-center justify-center px-6 py-24">
        <p className="text-sm text-foreground/70">Loading customer…</p>
      </div>
    );
  }

  if (isError || !customer) {
    return (
      <div className="flex flex-col items-center justify-center gap-3 px-6 py-24">
        <p role="alert" className="text-sm text-destructive">
          {error instanceof ApiError ? error.message : "Customer not found."}
        </p>
        <Link to="/customers" className="text-sm font-medium text-primary hover:underline">
          Back to directory
        </Link>
      </div>
    );
  }

  return (
    <div className="px-4 py-6 sm:px-6 sm:py-8 lg:px-10">
      <div className="flex max-w-3xl flex-col gap-6">
        <ConfirmDialog
          open={isConfirmingArchive}
          onOpenChange={setIsConfirmingArchive}
          title={`Archive ${customer.name}?`}
          description="They'll be hidden from active customer lists and can't get new requests or invoices. Existing requests and invoices that reference them are kept."
          confirmLabel="Archive customer"
          destructive
          onConfirm={onArchive}
        />
        <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2">
          <h1 className="text-2xl font-semibold">
            {customer.name} {customer.status === "archived" && <span className="text-sm font-normal text-foreground/50">(archived)</span>}
          </h1>
          <Link to="/customers" className="text-sm font-medium text-primary hover:underline">
            Back to directory
          </Link>
        </div>

        {!isEditing && (
          <div className="flex flex-col gap-3 rounded-md border border-border bg-card p-4 sm:p-6">
            <Field label="Email" value={customer.email ?? "—"} />
            <Field label="Phone" value={customer.phone ?? "—"} />
            <Field label="Company" value={customer.company ?? "—"} />
            <Field label="Address" value={customer.address ?? "—"} />
            <Field label="Notes" value={customer.notes ?? "—"} />

            {formError && (
              <p role="alert" className="text-sm text-destructive">
                {formError}
              </p>
            )}

            <div className="mt-2 flex gap-3">
              <Button onClick={() => setIsEditing(true)}>Edit customer</Button>
              {customer.status === "active" && (
                <Button type="button" variant="destructive" onClick={() => setIsConfirmingArchive(true)}>
                  Archive
                </Button>
              )}
            </div>
          </div>
        )}

        {isEditing && (
          <form
            className="flex flex-col gap-4 rounded-md border border-border bg-card p-4 sm:p-6"
            onSubmit={handleSubmit(onSubmit)}
            noValidate
          >
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="name">Name</Label>
              <Input id="name" aria-invalid={errors.name ? "true" : "false"} {...register("name")} />
              {errors.name && <p className="text-sm text-destructive">{errors.name.message}</p>}
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="email">Email</Label>
              <Input id="email" type="email" {...register("email")} />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="phone">Phone</Label>
              <Input id="phone" {...register("phone")} />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="company">Company</Label>
              <Input id="company" {...register("company")} />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="address">Address</Label>
              <Textarea id="address" {...register("address")} />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="notes">Notes</Label>
              <Textarea id="notes" {...register("notes")} />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="status">Status</Label>
              <Select id="status" {...register("status")}>
                <option value="active">Active</option>
                <option value="archived">Archived</option>
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

        {canSeeRequests && (
          <div className="flex flex-col gap-3 rounded-md border border-border bg-card p-4 sm:p-6">
            <h2 className="text-lg font-medium">Requests</h2>
            {(requestsData?.requests ?? []).length === 0 && <p className="text-sm text-foreground/70">No requests yet.</p>}
            <ul className="flex flex-col gap-2">
              {(requestsData?.requests ?? []).map((request) => (
                <li key={request.id} className="rounded-md border border-border p-3">
                  <Link to={`/requests/${request.id}`} className="font-medium text-primary hover:underline">
                    {request.title}
                  </Link>
                  <p className="text-sm text-foreground/70">{REQUEST_STATUS_LABELS[request.status]}</p>
                </li>
              ))}
            </ul>
          </div>
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
