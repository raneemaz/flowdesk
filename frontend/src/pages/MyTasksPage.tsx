import { useQuery } from "@tanstack/react-query";

import { listEmployees } from "@/api/employees";
import { TaskListView } from "@/components/TaskListView";
import { useAuth } from "@/contexts/AuthContext";
import { useOrganization } from "@/contexts/OrganizationContext";
import { canManageTasks } from "@/features/tasks/permissions";

// For an Owner/Manager, GET /tasks sees every task in the org by
// default, so "My Tasks" has to explicitly filter to the viewer's own
// assignee_membership_id - resolved here by matching the directory
// entry whose email matches the logged-in user (MembershipPublic,
// from OrganizationContext, doesn't carry the caller's own
// membership_id - see docs/frontend README.md's Tasks section).
// For every other role, TASK_VIEW_UPDATE's `assigned` scope already
// auto-restricts GET /tasks to the caller's own tasks server-side, so
// this page and the plain task list are already identical without
// any extra filter - no lookup needed.
export function MyTasksPage() {
  const { user } = useAuth();
  const { activeMembership } = useOrganization();
  const organizationId = activeMembership?.organization.id ?? "";
  const canManage = activeMembership ? canManageTasks(activeMembership.role) : false;

  const { data: ownMembershipId, isPending } = useQuery({
    queryKey: ["own-membership-id", organizationId, user?.email],
    queryFn: async () => {
      const { employees } = await listEmployees(organizationId, { perPage: 100 });
      return employees.find((employee) => employee.email === user?.email)?.membership_id ?? null;
    },
    enabled: canManage && Boolean(organizationId) && Boolean(user),
  });

  return (
    <TaskListView
      title="My Tasks"
      lockedAssigneeId={canManage ? (ownMembershipId ?? undefined) : undefined}
      lockedAssigneeLoading={canManage && isPending}
    />
  );
}
