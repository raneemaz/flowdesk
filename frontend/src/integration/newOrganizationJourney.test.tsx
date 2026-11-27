// FD-063: cross-module critical journey, driven through the real
// <App/> (real router, real AuthContext/OrganizationContext, real
// Sidebar/TopBar) with only api/* calls mocked - see testHelpers.tsx's
// own header comment for why this is a meaningfully different test
// than this codebase's existing per-page tests. One journey per file
// (see testHelpers.tsx's renderApp() comment for why).
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import * as authApi from "@/api/auth";
import { ApiError } from "@/api/client";
import * as organizationsApi from "@/api/organizations";
import { USER, ORG, membershipOf, mockEveryDashboardDependency, renderApp } from "@/integration/testHelpers";

afterEach(() => {
  vi.restoreAllMocks();
  sessionStorage.clear();
  localStorage.clear();
});

describe("new organization journey", () => {
  it("a brand-new user registers, logs in, creates their first organization, and lands on a fully-wired dashboard", async () => {
    vi.spyOn(authApi, "getCurrentUser").mockRejectedValue(new ApiError(401, "UNAUTHENTICATED", "nope", {}));
    vi.spyOn(authApi, "register").mockResolvedValue(USER);
    vi.spyOn(authApi, "login").mockResolvedValue({ user: USER, csrf_token: "csrf-token-1" });

    // listOrganizations answers "no orgs yet" until createOrganization
    // actually resolves, then "one org, as Owner" - the same
    // before/after shape CreateOrganizationPage's own
    // invalidateQueries triggers for real, never hand-advanced.
    const listOrganizationsSpy = vi.spyOn(organizationsApi, "listOrganizations");
    listOrganizationsSpy.mockResolvedValue([]);
    vi.spyOn(organizationsApi, "createOrganization").mockResolvedValue(ORG);
    mockEveryDashboardDependency();

    const user = userEvent.setup();
    renderApp();

    // Unauthenticated at "/" -> the public landing page, exactly as a
    // real first visit would see; its header leads to sign-up.
    expect(await screen.findByRole("heading", { name: "Run your whole business in one flow." })).toBeInTheDocument();
    await user.click(screen.getAllByRole("link", { name: "Create your workspace" })[0]);

    await waitFor(() => expect(screen.getByRole("heading", { name: "Create your FlowDesk account" })).toBeInTheDocument());
    await user.type(screen.getByLabelText("Name"), "Ada Owner");
    await user.type(screen.getByLabelText("Email"), USER.email);
    await user.type(screen.getByLabelText("Password"), "correct horse battery");
    await user.type(screen.getByLabelText("Confirm password"), "correct horse battery");
    await user.click(screen.getByRole("button", { name: "Create account" }));

    // Registration never starts a session (docs/API.md) - the journey
    // continues on /login, not straight into the app.
    await waitFor(() => expect(screen.getByRole("heading", { name: "Log in to FlowDesk" })).toBeInTheDocument());
    await user.type(screen.getByLabelText("Email"), USER.email);
    await user.type(screen.getByLabelText("Password"), "correct horse battery");
    await user.click(screen.getByRole("button", { name: "Log in" }));

    // Logged in, but with no organization yet.
    await waitFor(() => expect(screen.getByText("You don't belong to an organization yet.")).toBeInTheDocument());

    // After creating one, listOrganizations must answer "one org" -
    // the exact query CreateOrganizationPage's invalidateQueries call
    // triggers a real refetch of.
    listOrganizationsSpy.mockResolvedValue([membershipOf("owner")]);

    await user.click(screen.getByRole("link", { name: "Create your first organization" }));
    await waitFor(() => expect(screen.getByRole("heading", { name: "Create an organization" })).toBeInTheDocument());
    await user.type(screen.getByLabelText("Organization name"), "Acme Inc");
    await user.click(screen.getByRole("button", { name: "Create organization" }));

    // Back on "/", now with the full Sidebar (Owner sees every link)
    // and no more "no organization" prompt - OrganizationContext's own
    // refetch-after-invalidate actually happened, not hand-waved.
    await waitFor(() => expect(screen.queryByText("You don't belong to an organization yet.")).not.toBeInTheDocument());
    expect(await screen.findByRole("link", { name: "Invoices" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Departments" })).toBeInTheDocument();
  });
});
