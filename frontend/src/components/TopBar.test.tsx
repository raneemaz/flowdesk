import { render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router-dom";

import * as authApi from "@/api/auth";
import * as notificationsApi from "@/api/notifications";
import * as organizationsApi from "@/api/organizations";
import { TopBar } from "@/components/TopBar";
import { AuthProvider } from "@/contexts/AuthContext";
import { OrganizationProvider } from "@/contexts/OrganizationContext";
import type { MembershipPublic, OrganizationPublic } from "@/types/organization";
import type { UserPublic } from "@/types/user";

const USER: UserPublic = { id: "u1", name: "Ada", email: "ada@example.com", status: "active", created_at: "now" };
const ORG: OrganizationPublic = {
  id: "org-1",
  name: "Acme Inc",
  slug: "acme-inc",
  logo: null,
  email: null,
  phone: null,
  address: null,
  currency: "USD",
  timezone: "UTC",
  date_format: null,
  created_at: "now",
};
const MEMBERSHIP: MembershipPublic = { organization: ORG, role: "owner", status: "active", joined_at: "now" };

function renderTopBar() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <OrganizationProvider>
          <MemoryRouter>
            <TopBar />
          </MemoryRouter>
        </OrganizationProvider>
      </AuthProvider>
    </QueryClientProvider>,
  );
}

describe("TopBar", () => {
  afterEach(() => {
    vi.restoreAllMocks();
    sessionStorage.clear();
    localStorage.clear();
  });

  it("shows the org switcher, unread notification badge, user name/role, and a logout button", async () => {
    vi.spyOn(authApi, "getCurrentUser").mockResolvedValue(USER);
    vi.spyOn(organizationsApi, "listOrganizations").mockResolvedValue([MEMBERSHIP]);
    vi.spyOn(notificationsApi, "listNotifications").mockResolvedValue({
      notifications: [],
      meta: { page: 1, per_page: 1, total: 2, total_pages: 2 },
    });

    renderTopBar();

    expect(await screen.findByLabelText("Current organization")).toBeInTheDocument();
    expect(await screen.findByRole("link", { name: "Notifications (2)" })).toHaveAttribute("href", "/notifications");
    await waitFor(() => expect(screen.getByTestId("topbar-user")).toHaveTextContent("Ada · Owner"));
    expect(screen.getByRole("button", { name: "Log out" })).toBeInTheDocument();
  });

  it("still renders a logout button with no active organization", async () => {
    vi.spyOn(authApi, "getCurrentUser").mockResolvedValue(USER);
    vi.spyOn(organizationsApi, "listOrganizations").mockResolvedValue([]);

    renderTopBar();

    expect(await screen.findByRole("button", { name: "Log out" })).toBeInTheDocument();
    expect(screen.queryByLabelText("Current organization")).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /Notifications/ })).not.toBeInTheDocument();
  });
});
