import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { createMemoryRouter, RouterProvider } from "react-router-dom";

import * as authApi from "@/api/auth";
import { ApiError } from "@/api/client";
import { AuthProvider } from "@/contexts/AuthContext";
import { LandingPage } from "@/pages/LandingPage";
import type { UserPublic } from "@/types/user";

const USER: UserPublic = { id: "u1", name: "Ada", email: "ada@example.com", status: "active", created_at: "now" };

function renderPage() {
  const router = createMemoryRouter(
    [
      { path: "/welcome", element: <LandingPage /> },
      { path: "/login", element: <div>Login page</div> },
      { path: "/register", element: <div>Register page</div> },
      { path: "/", element: <div>Dashboard</div> },
    ],
    { initialEntries: ["/welcome"] },
  );
  render(
    <AuthProvider>
      <RouterProvider router={router} />
    </AuthProvider>,
  );
}

describe("LandingPage", () => {
  afterEach(() => vi.restoreAllMocks());

  it("offers sign-up and log-in to a signed-out visitor", async () => {
    vi.spyOn(authApi, "getCurrentUser").mockRejectedValue(new ApiError(401, "UNAUTHENTICATED", "nope", {}));
    const user = userEvent.setup();
    renderPage();

    expect(await screen.findByRole("heading", { level: 1, name: "Run your whole business in one flow." })).toBeInTheDocument();
    expect(screen.getAllByRole("link", { name: "Create your workspace" })[0]).toHaveAttribute("href", "/register");
    await user.click(screen.getAllByRole("link", { name: "Log in" })[0]);
    expect(await screen.findByText("Login page")).toBeInTheDocument();
  });

  it("switches the product tour when a tab is picked", async () => {
    vi.spyOn(authApi, "getCurrentUser").mockRejectedValue(new ApiError(401, "UNAUTHENTICATED", "nope", {}));
    const user = userEvent.setup();
    renderPage();

    const tabs = await screen.findByRole("tablist", { name: "Screens" });
    expect(within(tabs).getByRole("tab", { name: "Overview" })).toHaveAttribute("aria-selected", "true");
    await user.click(within(tabs).getByRole("tab", { name: "Invoices" }));

    expect(within(tabs).getByRole("tab", { name: "Invoices" })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByRole("tabpanel")).toHaveTextContent("Line items, totals and payment status for every invoice.");
  });

  it("points a signed-in visitor straight back into the app", async () => {
    vi.spyOn(authApi, "getCurrentUser").mockResolvedValue(USER);
    renderPage();

    const open = await screen.findAllByRole("link", { name: /Open FlowDesk/ });
    expect(open[0]).toHaveAttribute("href", "/");
    expect(screen.queryByRole("link", { name: "Log in" })).not.toBeInTheDocument();
  });

  it("lists the demo chapters", async () => {
    vi.spyOn(authApi, "getCurrentUser").mockRejectedValue(new ApiError(401, "UNAUTHENTICATED", "nope", {}));
    renderPage();

    const chapters = await screen.findByRole("list", { name: "Video chapters" });
    expect(within(chapters).getAllByRole("button").map((b) => b.textContent)).toEqual([
      "Overview0:13",
      "Planning0:19",
      "Support0:33",
      "Billing0:39",
      "Analytics0:45",
      "Team0:50",
    ]);
  });
});
