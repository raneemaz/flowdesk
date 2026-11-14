import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";

import { listOrganizations } from "@/api/organizations";
import { useAuth } from "@/contexts/AuthContext";
import type { MembershipPublic } from "@/types/organization";

export const ORGANIZATIONS_QUERY_KEY = ["organizations"] as const;

// A non-"active" membership (Membership.status) carries no capabilities
// server-side (app/authz/service.py's get_active_membership_or_404 requires
// ACTIVE) and the API still lists it for history (docs/API.md) - so it's
// excluded here as something to actually switch into, not hidden from the
// raw `memberships` list this context exposes.
function usableMemberships(memberships: MembershipPublic[]): MembershipPublic[] {
  return memberships.filter((m) => m.status === "active");
}

// There's no server-side concept of a "current" organization (every
// org-scoped endpoint takes organization_id from the URL path, never a
// session - app/authz/decorators.py) - which one is "active" is a purely
// client-side UX preference. Persisted in localStorage (not sessionStorage)
// because "which org was I last looking at" is reasonable to carry across
// browser restarts, unlike the CSRF token in AuthContext; keyed per user id
// so one person's choice on a shared machine never leaks into another's.
function storageKey(userId: string): string {
  return `flowdesk:active_org:${userId}`;
}

interface OrganizationContextValue {
  memberships: MembershipPublic[];
  activeMembership: MembershipPublic | null;
  isLoading: boolean;
  switchOrganization: (organizationId: string) => void;
}

const OrganizationContext = createContext<OrganizationContextValue | null>(null);

export function OrganizationProvider({ children }: { children: ReactNode }) {
  const { user, status: authStatus } = useAuth();
  const queryClient = useQueryClient();
  const [activeOrganizationId, setActiveOrganizationId] = useState<string | null>(null);

  // isPending (not isLoading) deliberately: v5's isLoading is false while a
  // query is disabled (fetchStatus "idle"), which this query is until
  // authStatus becomes "authenticated" - using it here would let a
  // zero-memberships "create your first organization" prompt flash on
  // screen before the real request has even gone out. isPending instead
  // just tracks "no data yet", which stays true through that whole gap and
  // only turns false once a real response has come back.
  const { data, isPending } = useQuery({
    queryKey: ORGANIZATIONS_QUERY_KEY,
    queryFn: listOrganizations,
    enabled: authStatus === "authenticated",
  });

  const memberships = data ?? [];

  useEffect(() => {
    if (authStatus !== "authenticated" || !user) {
      setActiveOrganizationId(null);
      return;
    }
    const stored = localStorage.getItem(storageKey(user.id));
    setActiveOrganizationId(stored);
  }, [authStatus, user]);

  useEffect(() => {
    if (authStatus !== "authenticated") {
      queryClient.removeQueries({ queryKey: ORGANIZATIONS_QUERY_KEY });
    }
  }, [authStatus, queryClient]);

  const switchOrganization = useCallback(
    (organizationId: string) => {
      if (!user) return;
      localStorage.setItem(storageKey(user.id), organizationId);
      setActiveOrganizationId(organizationId);
    },
    [user],
  );

  const activeMembership = useMemo(() => {
    const usable = usableMemberships(memberships);
    if (usable.length === 0) return null;
    const stored = usable.find((m) => m.organization.id === activeOrganizationId);
    // Falls back to the first usable membership if nothing is stored yet,
    // or the stored id no longer matches one (e.g. a different browser, or
    // that membership stopped being active) - never leaves an authenticated
    // user with memberships stuck on no active organization at all.
    return stored ?? usable[0];
  }, [memberships, activeOrganizationId]);

  // The freshly-created (or newly-active) organization becomes "active" in
  // storage too, so a later session picks up where this one left off
  // instead of silently reverting to whatever was stored before.
  useEffect(() => {
    if (activeMembership && user && activeMembership.organization.id !== activeOrganizationId) {
      localStorage.setItem(storageKey(user.id), activeMembership.organization.id);
    }
  }, [activeMembership, activeOrganizationId, user]);

  const value = useMemo(
    () => ({ memberships, activeMembership, isLoading: isPending, switchOrganization }),
    [memberships, activeMembership, isPending, switchOrganization],
  );

  return <OrganizationContext.Provider value={value}>{children}</OrganizationContext.Provider>;
}

export function useOrganization(): OrganizationContextValue {
  const context = useContext(OrganizationContext);
  if (!context) {
    throw new Error("useOrganization must be used within an OrganizationProvider.");
  }
  return context;
}
