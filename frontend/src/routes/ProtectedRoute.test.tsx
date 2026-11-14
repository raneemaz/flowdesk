import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { createMemoryRouter, RouterProvider } from "react-router-dom";

import * as authApi from "@/api/auth";
import { ApiError } from "@/api/client";
import { AuthProvider } from "@/contexts/AuthContext";
import { ProtectedRoute } from "@/routes/ProtectedRoute";
import type { UserPublic } from "@/types/user";

const USER: UserPublic = { id: "u1", name: "Ada", email: "ada@example.com", status: "active", created_at: "now" };

function renderWithRouter() {
  const router = createMemoryRouter(
    [
      { path: "/login", element: <div>Login page</div> },
      { element: <ProtectedRoute />, children: [{ path: "/", element: <div>Protected home</div> }] },
    ],
    { initialEntries: ["/"] },
  );

  render(
    <AuthProvider>
      <RouterProvider router={router} />
    </AuthProvider>,
  );
}

describe("ProtectedRoute", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("redirects to /login when there is no session", async () => {
    vi.spyOn(authApi, "getCurrentUser").mockRejectedValue(new ApiError(401, "UNAUTHENTICATED", "nope", {}));

    renderWithRouter();

    await waitFor(() => expect(screen.getByText("Login page")).toBeInTheDocument());
  });

  it("renders the protected content once a session is confirmed", async () => {
    vi.spyOn(authApi, "getCurrentUser").mockResolvedValue(USER);

    renderWithRouter();

    await waitFor(() => expect(screen.getByText("Protected home")).toBeInTheDocument());
  });
});
