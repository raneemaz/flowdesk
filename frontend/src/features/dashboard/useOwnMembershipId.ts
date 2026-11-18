import { useQuery } from "@tanstack/react-query";

import { listEmployees } from "@/api/employees";
import { useAuth } from "@/contexts/AuthContext";

// Same lookup pages/MyTasksPage.tsx already established:
// OrganizationContext's MembershipPublic doesn't carry the caller's
// own membership_id, so it's resolved by matching the employee
// directory entry whose email matches the logged-in user.
export function useOwnMembershipId(organizationId: string, enabled: boolean) {
  const { user } = useAuth();
  return useQuery({
    queryKey: ["own-membership-id", organizationId, user?.email],
    queryFn: async () => {
      const { employees } = await listEmployees(organizationId, { perPage: 100 });
      return employees.find((employee) => employee.email === user?.email)?.membership_id ?? null;
    },
    enabled: enabled && Boolean(organizationId) && Boolean(user),
  });
}
