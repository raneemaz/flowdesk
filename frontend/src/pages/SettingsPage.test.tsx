import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, describe, expect, it, vi } from "vitest";
import { createMemoryRouter, RouterProvider } from "react-router-dom";

import * as authApi from "@/api/auth";
import { ApiError } from "@/api/client";
import * as organizationsApi from "@/api/organizations";
import * as settingsApi from "@/api/settings";
import { AuthProvider } from "@/contexts/AuthContext";
import { OrganizationProvider } from "@/contexts/OrganizationContext";
import { SettingsPage } from "@/pages/SettingsPage";
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

const MEMBERS: settingsApi.MemberPublic[] = [
  { membership_id: "m1", user_id: "u1", name: "Ada", email: "ada@example.com", role: "owner", status: "active", joined_at: "now" },
  { membership_id: "m2", user_id: "u2", name: "Bea", email: "bea@example.com", role: "employee", status: "active", joined_at: "now" },
  { membership_id: "m3", user_id: "u3", name: "Cy", email: "cy@example.com", role: "manager", status: "active", joined_at: "now" },
];

function renderPage(initial = "/settings") {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const router = createMemoryRouter([{ path: "/settings", element: <SettingsPage /> }], { initialEntries: [initial] });
  render(
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <OrganizationProvider>
          <RouterProvider router={router} />
        </OrganizationProvider>
      </AuthProvider>
    </QueryClientProvider>,
  );
}

function mockAuthenticated(role: MembershipPublic["role"]) {
  vi.spyOn(authApi, "getCurrentUser").mockResolvedValue(USER);
  vi.spyOn(organizationsApi, "listOrganizations").mockResolvedValue([
    { organization: ORG, role, status: "active", joined_at: "now" },
  ]);
  sessionStorage.setItem("flowdesk:csrf_token", "csrf-abc");
}

describe("SettingsPage", () => {
  afterEach(() => {
    vi.restoreAllMocks();
    sessionStorage.clear();
    localStorage.clear();
  });

  it("shows Organization, Members and My account to an owner", async () => {
    mockAuthenticated("owner");
    renderPage();

    expect(await screen.findByRole("button", { name: "Members" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "My account" })).toBeInTheDocument();
    expect(screen.getByLabelText("Name")).toHaveValue("Acme Inc");
  });

  it("shows an employee a read-only organization profile and no Members section", async () => {
    mockAuthenticated("employee");
    renderPage();

    expect(await screen.findByLabelText("Name")).toBeDisabled();
    expect(screen.getByLabelText("Phone")).toBeDisabled();
    expect(screen.queryByRole("button", { name: "Members" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Save changes" })).not.toBeInTheDocument();
  });

  it("sends only the fields the owner changed", async () => {
    mockAuthenticated("owner");
    const updateSpy = vi.spyOn(settingsApi, "updateOrganization").mockResolvedValue({ ...ORG, phone: "+1 555 0100" });
    const user = userEvent.setup();
    renderPage();

    await user.type(await screen.findByLabelText("Phone"), "+1 555 0100");
    await user.click(screen.getByRole("button", { name: "Save changes" }));

    await waitFor(() => expect(updateSpy).toHaveBeenCalledWith("org-1", { phone: "+1 555 0100" }, "csrf-abc"));
    expect(await screen.findByText("Changes saved.")).toBeInTheDocument();
  });

  it("lets a manager edit contact details but not owner-only fields", async () => {
    mockAuthenticated("manager");
    const updateSpy = vi.spyOn(settingsApi, "updateOrganization").mockResolvedValue({ ...ORG, address: "1 Main St" });
    const user = userEvent.setup();
    renderPage();

    expect(await screen.findByLabelText("Name")).toBeDisabled();
    expect(screen.getByLabelText("Currency")).toBeDisabled();
    await user.type(screen.getByLabelText("Address"), "1 Main St");
    await user.click(screen.getByRole("button", { name: "Save changes" }));

    await waitFor(() => expect(updateSpy).toHaveBeenCalledWith("org-1", { address: "1 Main St" }, "csrf-abc"));
  });

  it("changes a member's role", async () => {
    mockAuthenticated("owner");
    vi.spyOn(settingsApi, "listMembers").mockResolvedValue(MEMBERS);
    const updateSpy = vi.spyOn(settingsApi, "updateMember").mockResolvedValue({ ...MEMBERS[1], role: "accountant" });
    const user = userEvent.setup();
    renderPage("/settings?section=members");

    await user.selectOptions(await screen.findByLabelText("Role for Bea"), "accountant");

    await waitFor(() => expect(updateSpy).toHaveBeenCalledWith("org-1", "m2", { role: "accountant" }, "csrf-abc"));
    // Your own row is never editable.
    expect(screen.queryByLabelText("Role for Ada")).not.toBeInTheDocument();
  });

  it("removes a member's access only after confirming", async () => {
    mockAuthenticated("owner");
    vi.spyOn(settingsApi, "listMembers").mockResolvedValue(MEMBERS);
    const updateSpy = vi.spyOn(settingsApi, "updateMember").mockResolvedValue({ ...MEMBERS[1], status: "inactive" });
    const user = userEvent.setup();
    renderPage("/settings?section=members");

    const beaRow = (await screen.findByText("bea@example.com")).closest("li")!;
    await user.click(within(beaRow).getByRole("button", { name: "Remove access" }));
    expect(updateSpy).not.toHaveBeenCalled();
    await user.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Remove access" }));

    await waitFor(() => expect(updateSpy).toHaveBeenCalledWith("org-1", "m2", { status: "inactive" }, "csrf-abc"));
  });

  it("shows why a role change was refused", async () => {
    mockAuthenticated("owner");
    vi.spyOn(settingsApi, "listMembers").mockResolvedValue(MEMBERS);
    vi.spyOn(settingsApi, "updateMember").mockRejectedValue(
      new ApiError(409, "LAST_OWNER", "The organization must keep at least one active owner.", {}),
    );
    const user = userEvent.setup();
    renderPage("/settings?section=members");

    await user.selectOptions(await screen.findByLabelText("Role for Cy"), "employee");

    expect(await screen.findByRole("alert")).toHaveTextContent("at least one active owner");
  });

  it("does not let a manager change an owner or another manager", async () => {
    mockAuthenticated("manager");
    vi.spyOn(settingsApi, "listMembers").mockResolvedValue([
      MEMBERS[0],
      MEMBERS[1],
      { ...MEMBERS[2], user_id: "u9", name: "Dee", email: "dee@example.com", membership_id: "m9" },
    ]);
    renderPage("/settings?section=members");

    expect(await screen.findByLabelText("Role for Bea")).toBeInTheDocument();
    expect(screen.queryByLabelText("Role for Ada")).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Role for Dee")).not.toBeInTheDocument();
  });

  it("updates the signed-in user's name", async () => {
    mockAuthenticated("employee");
    const updateSpy = vi.spyOn(settingsApi, "updateProfile").mockResolvedValue({ ...USER, name: "Ada Lovelace" });
    const user = userEvent.setup();
    renderPage("/settings?section=account");

    const name = await screen.findByLabelText("Your name");
    await user.clear(name);
    await user.type(name, "Ada Lovelace");
    await user.click(screen.getByRole("button", { name: "Save name" }));

    await waitFor(() => expect(updateSpy).toHaveBeenCalledWith({ name: "Ada Lovelace" }, "csrf-abc"));
    expect(await screen.findByText("Name saved.")).toBeInTheDocument();
    expect(screen.getByLabelText("Email")).toBeDisabled();
  });

  it("changes the password and reports a wrong current password", async () => {
    mockAuthenticated("employee");
    const changeSpy = vi
      .spyOn(settingsApi, "changePassword")
      .mockRejectedValueOnce(
        new ApiError(400, "INVALID_CURRENT_PASSWORD", "Your current password is incorrect.", {
          current_password: "Incorrect password.",
        }),
      )
      .mockResolvedValueOnce(null);
    const user = userEvent.setup();
    renderPage("/settings?section=account");

    await user.type(await screen.findByLabelText("Current password"), "wrong one");
    await user.type(screen.getByLabelText("New password"), "brand new password");
    await user.type(screen.getByLabelText("Confirm new password"), "brand new password");
    await user.click(screen.getByRole("button", { name: "Change password" }));
    expect(await screen.findByText("That's not your current password.")).toBeInTheDocument();

    const current = screen.getByLabelText("Current password");
    await user.clear(current);
    await user.type(current, "right one");
    await user.click(screen.getByRole("button", { name: "Change password" }));

    await waitFor(() =>
      expect(changeSpy).toHaveBeenLastCalledWith(
        { current_password: "right one", new_password: "brand new password" },
        "csrf-abc",
      ),
    );
    expect(await screen.findByText("Password changed.")).toBeInTheDocument();
  });

  it("checks that the two new passwords match before sending", async () => {
    mockAuthenticated("employee");
    const changeSpy = vi.spyOn(settingsApi, "changePassword").mockResolvedValue(null);
    const user = userEvent.setup();
    renderPage("/settings?section=account");

    await user.type(await screen.findByLabelText("Current password"), "current one");
    await user.type(screen.getByLabelText("New password"), "brand new password");
    await user.type(screen.getByLabelText("Confirm new password"), "different password");
    await user.click(screen.getByRole("button", { name: "Change password" }));

    expect(await screen.findByText("The two new passwords don't match.")).toBeInTheDocument();
    expect(changeSpy).not.toHaveBeenCalled();
  });
});
