import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { ApiError } from "@/api/client";
import { listMembers, updateMember, type MemberPublic } from "@/api/settings";
import { ConfirmDialog } from "@/components/ConfirmDialog";
import { Button } from "@/components/ui/button";
import { Select } from "@/components/ui/select";
import { useAuth } from "@/contexts/AuthContext";
import { ROLE_LABELS } from "@/features/employees/constants";
import { canManageEmployeeProfile, invitableRoles } from "@/features/employees/permissions";
import { InviteEmployeeDialog } from "@/features/invitations/InviteEmployeeDialog";
import type { MembershipRole } from "@/types/organization";

// Owner/Manager only (the page doesn't render this section for anyone
// else). Reach mirrors the backend's can_assign_role: never yourself; a
// manager only for Employee/Accountant/Customer Support members. Removing
// access is reversible - the member keeps their history and can be
// restored from this same list.
export function MembersSettings({ organizationId, viewerRole }: { organizationId: string; viewerRole: MembershipRole }) {
  const { user, csrfToken } = useAuth();
  const queryClient = useQueryClient();
  const [rowError, setRowError] = useState<{ membershipId: string; message: string } | null>(null);
  const [removing, setRemoving] = useState<MemberPublic | null>(null);

  const queryKey = ["members", organizationId];
  const { data: members, isPending, isError } = useQuery({
    queryKey,
    queryFn: () => listMembers(organizationId),
    enabled: Boolean(organizationId),
  });

  const refresh = () =>
    Promise.all([
      queryClient.invalidateQueries({ queryKey }),
      queryClient.invalidateQueries({ queryKey: ["employees", organizationId] }),
    ]);

  const roleMutation = useMutation({
    mutationFn: ({ member, role }: { member: MemberPublic; role: MembershipRole }) =>
      updateMember(organizationId, member.membership_id, { role }, csrfToken ?? ""),
    onMutate: () => setRowError(null),
    onSuccess: () => refresh(),
    onError: (error, { member }) =>
      setRowError({
        membershipId: member.membership_id,
        message: error instanceof ApiError ? error.message : "Could not change the role.",
      }),
  });

  const restoreMutation = useMutation({
    mutationFn: (member: MemberPublic) =>
      updateMember(organizationId, member.membership_id, { status: "active" }, csrfToken ?? ""),
    onMutate: () => setRowError(null),
    onSuccess: () => refresh(),
    onError: (error, member) =>
      setRowError({
        membershipId: member.membership_id,
        message: error instanceof ApiError ? error.message : "Could not restore access.",
      }),
  });

  const assignable = invitableRoles(viewerRole);

  return (
    <div className="flex flex-col gap-4 rounded-md border border-border bg-card p-4 sm:p-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-lg font-medium">Members</h2>
          <p className="text-sm text-muted-foreground">Change what people can do, or remove their access.</p>
        </div>
        <InviteEmployeeDialog organizationId={organizationId} viewerRole={viewerRole} />
      </div>

      {isPending && <p className="text-sm text-muted-foreground">Loading members…</p>}
      {isError && (
        <p role="alert" className="text-sm text-destructive">
          Could not load members.
        </p>
      )}

      {members && (
        // One responsive list rather than a table: stacked cards on phones,
        // aligned columns from sm up (the header row is visual only there).
        <div>
          <div
            aria-hidden="true"
            className="hidden border-b border-border pb-2 text-sm font-medium text-muted-foreground sm:grid sm:grid-cols-[minmax(0,1fr)_11rem_5.5rem_8.5rem] sm:gap-4"
          >
            <span>Name</span>
            <span>Role</span>
            <span>Access</span>
            <span />
          </div>
          <ul className="flex flex-col" aria-label="Members">
            {members.map((member) => {
              const isSelf = member.user_id === user?.id;
              const canManage = !isSelf && canManageEmployeeProfile(viewerRole, member.role);
              const isActive = member.status === "active";
              return (
                <li
                  key={member.membership_id}
                  className="grid grid-cols-[minmax(0,1fr)_auto] gap-x-3 gap-y-2 border-b border-border py-3 text-sm last:border-0 sm:grid-cols-[minmax(0,1fr)_11rem_5.5rem_8.5rem] sm:items-center sm:gap-4"
                >
                  <div className="col-span-2 min-w-0 sm:col-span-1">
                    <p className="font-medium">
                      {member.name}
                      {isSelf && <span className="ml-2 text-xs font-normal text-muted-foreground">You</span>}
                      <span className="ml-2 text-xs font-normal text-muted-foreground sm:hidden">
                        {isActive ? "" : "Removed"}
                      </span>
                    </p>
                    <p className="break-all text-muted-foreground">{member.email}</p>
                    {rowError?.membershipId === member.membership_id && (
                      <p role="alert" className="mt-1 text-destructive">
                        {rowError.message}
                      </p>
                    )}
                  </div>
                  <div className="min-w-0">
                    {canManage && isActive ? (
                      <Select
                        aria-label={`Role for ${member.name}`}
                        value={member.role}
                        disabled={roleMutation.isPending}
                        onChange={(event) => roleMutation.mutate({ member, role: event.target.value as MembershipRole })}
                      >
                        {assignable.map((role) => (
                          <option key={role} value={role}>
                            {ROLE_LABELS[role]}
                          </option>
                        ))}
                      </Select>
                    ) : (
                      <span className="text-foreground/80">{ROLE_LABELS[member.role]}</span>
                    )}
                  </div>
                  <div className="hidden sm:block">
                    {isActive ? "Active" : <span className="text-muted-foreground">Removed</span>}
                  </div>
                  <div className="justify-self-end">
                    {canManage &&
                      (isActive ? (
                        <Button type="button" variant="outline" size="sm" className="text-destructive" onClick={() => setRemoving(member)}>
                          Remove access
                        </Button>
                      ) : (
                        <Button
                          type="button"
                          variant="outline"
                          size="sm"
                          disabled={restoreMutation.isPending}
                          onClick={() => restoreMutation.mutate(member)}
                        >
                          Restore access
                        </Button>
                      ))}
                  </div>
                </li>
              );
            })}
          </ul>
        </div>
      )}

      <ConfirmDialog
        open={removing !== null}
        onOpenChange={(open) => !open && setRemoving(null)}
        title={`Remove ${removing?.name ?? "this member"}'s access?`}
        description="They'll be signed out of this organization and can't see or change anything in it. Their tasks, comments and history stay. You can restore their access at any time."
        confirmLabel="Remove access"
        destructive
        onConfirm={async () => {
          if (!removing) return;
          try {
            await updateMember(organizationId, removing.membership_id, { status: "inactive" }, csrfToken ?? "");
          } catch (error) {
            throw new Error(error instanceof ApiError ? error.message : "Could not remove access.");
          }
          await refresh();
        }}
      />
    </div>
  );
}
