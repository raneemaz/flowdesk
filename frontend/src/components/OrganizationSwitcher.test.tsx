import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router-dom";

import * as authApi from "@/api/auth";
import * as organizationsApi from "@/api/organizations";
import { OrganizationSwitcher } from "@/components/OrganizationSwitcher";
import { AuthProvider } from "@/contexts/AuthContext";
import { OrganizationProvider } from "@/contexts/OrganizationContext";
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

function renderSwitcher() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <OrganizationProvider>
          <MemoryRouter>
            <OrganizationSwitcher />
          </MemoryRouter>
        </OrganizationProvider>
      </AuthProvider>
    </QueryClientProvider>,
  );
}

describe("OrganizationSwitcher", () => {
  afterEach(() => {
    vi.restoreAllMocks();
    sessionStorage.clear();
    localStorage.clear();
  });

  it("renders nothing while there is no active organization", async () => {
    vi.spyOn(authApi, "getCurrentUser").mockResolvedValue(USER);
    vi.spyOn(organizationsApi, "listOrganizations").mockResolvedValue([]);

    const { container } = render(
      <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
        <AuthProvider>
          <OrganizationProvider>
            <MemoryRouter>
              <OrganizationSwitcher />
            </MemoryRouter>
          </OrganizationProvider>
        </AuthProvider>
      </QueryClientProvider>,
    );

    await waitFor(() => expect(container.querySelector("select")).not.toBeInTheDocument());
  });

  it("lists only active memberships and switches the active organization on selection", async () => {
    vi.spyOn(authApi, "getCurrentUser").mockResolvedValue(USER);
    vi.spyOn(organizationsApi, "listOrganizations").mockResolvedValue([
      membership("org-1", "Acme"),
      membership("org-2", "Globex"),
      membership("org-3", "Suspended Co", "suspended"),
    ]);
    const user = userEvent.setup();

    renderSwitcher();

    const select = await screen.findByLabelText("Current organization");
    expect(screen.queryByText(/Suspended Co/)).not.toBeInTheDocument();
    expect(select).toHaveValue("org-1");

    await user.selectOptions(select, "org-2");

    expect(select).toHaveValue("org-2");
    expect(localStorage.getItem(`flowdesk:active_org:${USER.id}`)).toBe("org-2");
  });
});
