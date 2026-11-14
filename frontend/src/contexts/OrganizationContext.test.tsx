import { act, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import * as authApi from "@/api/auth";
import * as organizationsApi from "@/api/organizations";
import { ApiError } from "@/api/client";
import { AuthProvider } from "@/contexts/AuthContext";
import { OrganizationProvider, useOrganization } from "@/contexts/OrganizationContext";
import type { MembershipPublic } from "@/types/organization";
import type { UserPublic } from "@/types/user";

const USER: UserPublic = { id: "u1", name: "Ada", email: "ada@example.com", status: "active", created_at: "now" };

function membership(id: string, name: string, status: MembershipPublic["status"] = "active"): MembershipPublic {
  return {
    organization: {
      id,
      name,
      slug: name.toLowerCase(),
      logo: null,
      email: null,
      phone: null,
      address: null,
      currency: "USD",
      timezone: "UTC",
      date_format: null,
      created_at: "now",
    },
    role: "owner",
    status,
    joined_at: "now",
  };
}

function Probe() {
  const { memberships, activeMembership, isLoading, switchOrganization } = useOrganization();
  return (
    <div>
      <span data-testid="loading">{String(isLoading)}</span>
      <span data-testid="count">{memberships.length}</span>
      <span data-testid="active">{activeMembership?.organization.id ?? "none"}</span>
      <button onClick={() => switchOrganization("org-2")}>switch</button>
    </div>
  );
}

function renderWithProviders() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <OrganizationProvider>
          <Probe />
        </OrganizationProvider>
      </AuthProvider>
    </QueryClientProvider>,
  );
}

describe("OrganizationProvider", () => {
  beforeEach(() => {
    sessionStorage.clear();
    localStorage.clear();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("never fetches organizations for an unauthenticated user", async () => {
    vi.spyOn(authApi, "getCurrentUser").mockRejectedValue(new ApiError(401, "UNAUTHENTICATED", "nope", {}));
    const listSpy = vi.spyOn(organizationsApi, "listOrganizations");

    renderWithProviders();

    await waitFor(() => expect(screen.getByTestId("active").textContent).toBe("none"));
    expect(listSpy).not.toHaveBeenCalled();
  });

  it("defaults to the first active membership when nothing is stored yet", async () => {
    vi.spyOn(authApi, "getCurrentUser").mockResolvedValue(USER);
    vi.spyOn(organizationsApi, "listOrganizations").mockResolvedValue([
      membership("org-1", "Acme"),
      membership("org-2", "Globex"),
    ]);

    renderWithProviders();

    await waitFor(() => expect(screen.getByTestId("active").textContent).toBe("org-1"));
    expect(screen.getByTestId("count").textContent).toBe("2");
  });

  it("skips an inactive membership when picking the default active organization", async () => {
    vi.spyOn(authApi, "getCurrentUser").mockResolvedValue(USER);
    vi.spyOn(organizationsApi, "listOrganizations").mockResolvedValue([
      membership("org-1", "Acme", "inactive"),
      membership("org-2", "Globex"),
    ]);

    renderWithProviders();

    await waitFor(() => expect(screen.getByTestId("active").textContent).toBe("org-2"));
  });

  it("restores the previously-active organization from localStorage", async () => {
    localStorage.setItem(`flowdesk:active_org:${USER.id}`, "org-2");
    vi.spyOn(authApi, "getCurrentUser").mockResolvedValue(USER);
    vi.spyOn(organizationsApi, "listOrganizations").mockResolvedValue([
      membership("org-1", "Acme"),
      membership("org-2", "Globex"),
    ]);

    renderWithProviders();

    await waitFor(() => expect(screen.getByTestId("active").textContent).toBe("org-2"));
  });

  it("has no active organization when the user has zero memberships", async () => {
    vi.spyOn(authApi, "getCurrentUser").mockResolvedValue(USER);
    vi.spyOn(organizationsApi, "listOrganizations").mockResolvedValue([]);

    renderWithProviders();

    await waitFor(() => expect(screen.getByTestId("loading").textContent).toBe("false"));
    expect(screen.getByTestId("active").textContent).toBe("none");
  });

  it("switchOrganization updates the active membership and persists it per-user", async () => {
    vi.spyOn(authApi, "getCurrentUser").mockResolvedValue(USER);
    vi.spyOn(organizationsApi, "listOrganizations").mockResolvedValue([
      membership("org-1", "Acme"),
      membership("org-2", "Globex"),
    ]);

    renderWithProviders();
    await waitFor(() => expect(screen.getByTestId("active").textContent).toBe("org-1"));

    await act(async () => {
      screen.getByRole("button", { name: "switch" }).click();
    });

    expect(screen.getByTestId("active").textContent).toBe("org-2");
    expect(localStorage.getItem(`flowdesk:active_org:${USER.id}`)).toBe("org-2");
  });
});
