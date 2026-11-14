import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, describe, expect, it, vi } from "vitest";
import { createMemoryRouter, RouterProvider } from "react-router-dom";

import * as authApi from "@/api/auth";
import * as organizationsApi from "@/api/organizations";
import { ApiError } from "@/api/client";
import { AuthProvider } from "@/contexts/AuthContext";
import { OrganizationProvider } from "@/contexts/OrganizationContext";
import { CreateOrganizationPage } from "@/pages/CreateOrganizationPage";
import type { UserPublic } from "@/types/user";

const USER: UserPublic = { id: "u1", name: "Ada", email: "ada@example.com", status: "active", created_at: "now" };

function renderPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const router = createMemoryRouter(
    [
      { path: "/organizations/new", element: <CreateOrganizationPage /> },
      { path: "/", element: <div>Home page</div> },
    ],
    { initialEntries: ["/organizations/new"] },
  );

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

function mockAuthenticated() {
  sessionStorage.setItem("flowdesk:csrf_token", "csrf-abc");
  vi.spyOn(authApi, "getCurrentUser").mockResolvedValue(USER);
}

describe("CreateOrganizationPage", () => {
  afterEach(() => {
    vi.restoreAllMocks();
    sessionStorage.clear();
    localStorage.clear();
  });

  it("rejects an empty name without calling the API", async () => {
    mockAuthenticated();
    vi.spyOn(organizationsApi, "listOrganizations").mockResolvedValue([]);
    const createSpy = vi.spyOn(organizationsApi, "createOrganization");
    const user = userEvent.setup();

    renderPage();
    await waitFor(() => expect(screen.getByRole("heading", { name: "Create an organization" })).toBeInTheDocument());

    await user.click(screen.getByRole("button", { name: "Create organization" }));

    expect(await screen.findByText("Organization name is required.")).toBeInTheDocument();
    expect(createSpy).not.toHaveBeenCalled();
  });

  it("creates the organization, makes it active, and navigates home", async () => {
    mockAuthenticated();
    vi.spyOn(organizationsApi, "listOrganizations").mockResolvedValue([]);
    const createSpy = vi.spyOn(organizationsApi, "createOrganization").mockResolvedValue({
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
    });
    const user = userEvent.setup();

    renderPage();
    await waitFor(() => expect(screen.getByRole("heading", { name: "Create an organization" })).toBeInTheDocument());

    await user.type(screen.getByLabelText("Organization name"), "Acme Inc");
    await user.click(screen.getByRole("button", { name: "Create organization" }));

    await waitFor(() => expect(screen.getByText("Home page")).toBeInTheDocument());
    expect(createSpy).toHaveBeenCalledWith(
      { name: "Acme Inc", email: undefined, currency: "USD", timezone: "UTC" },
      "csrf-abc",
    );
    expect(localStorage.getItem(`flowdesk:active_org:${USER.id}`)).toBe("org-1");
  });

  it("surfaces a validation error from the backend", async () => {
    mockAuthenticated();
    vi.spyOn(organizationsApi, "listOrganizations").mockResolvedValue([]);
    vi.spyOn(organizationsApi, "createOrganization").mockRejectedValue(
      new ApiError(422, "VALIDATION_ERROR", "Validation failed", {}),
    );
    const user = userEvent.setup();

    renderPage();
    await waitFor(() => expect(screen.getByRole("heading", { name: "Create an organization" })).toBeInTheDocument());

    await user.type(screen.getByLabelText("Organization name"), "Acme Inc");
    await user.click(screen.getByRole("button", { name: "Create organization" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Validation failed");
  });

  it("does not offer a Cancel link when this is the user's first organization", async () => {
    mockAuthenticated();
    vi.spyOn(organizationsApi, "listOrganizations").mockResolvedValue([]);

    renderPage();
    await waitFor(() => expect(screen.getByRole("heading", { name: "Create an organization" })).toBeInTheDocument());

    expect(screen.queryByRole("link", { name: "Cancel" })).not.toBeInTheDocument();
  });
});
