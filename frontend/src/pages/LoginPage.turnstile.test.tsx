import { forwardRef, useImperativeHandle } from "react";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { createMemoryRouter, RouterProvider } from "react-router-dom";

import * as authApi from "@/api/auth";
import { ApiError } from "@/api/client";
import { AuthProvider } from "@/contexts/AuthContext";
import { LoginPage } from "@/pages/LoginPage";

// Turnstile switched on (a site key is configured), with the real widget
// replaced by a button that "solves" the check, and a spy on reset().
const resetSpy = vi.fn();
vi.mock("@/components/Turnstile", () => ({
  TURNSTILE_SITE_KEY: "test-site-key",
  Turnstile: forwardRef<{ reset: () => void }, { action: string; onToken: (t: string | null) => void }>(
    function FakeTurnstile({ action, onToken }, ref) {
      useImperativeHandle(ref, () => ({
        reset: () => {
          resetSpy();
          onToken(null);
        },
      }));
      return (
        <button type="button" onClick={() => onToken(`token-for-${action}`)}>
          Solve security check
        </button>
      );
    },
  ),
}));

function renderPage() {
  const router = createMemoryRouter(
    [
      { path: "/login", element: <LoginPage /> },
      { path: "/", element: <div>Dashboard</div> },
    ],
    { initialEntries: ["/login"] },
  );
  render(
    <AuthProvider>
      <RouterProvider router={router} />
    </AuthProvider>,
  );
}

describe("LoginPage with Turnstile enabled", () => {
  afterEach(() => {
    vi.restoreAllMocks();
    resetSpy.mockClear();
  });

  it("won't submit until the security check is solved, then sends its token", async () => {
    vi.spyOn(authApi, "getCurrentUser").mockRejectedValue(new ApiError(401, "UNAUTHENTICATED", "nope", {}));
    const loginSpy = vi.spyOn(authApi, "login").mockResolvedValue({
      user: { id: "u1", name: "Ada", email: "ada@example.com", status: "active", created_at: "now" },
      csrf_token: "csrf",
    });
    const user = userEvent.setup();
    renderPage();

    await user.type(await screen.findByLabelText("Email"), "ada@example.com");
    await user.type(screen.getByLabelText("Password"), "correct horse battery");
    await user.click(screen.getByRole("button", { name: "Log in" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Please complete the security check first.");
    expect(loginSpy).not.toHaveBeenCalled();

    await user.click(screen.getByRole("button", { name: "Solve security check" }));
    await user.click(screen.getByRole("button", { name: "Log in" }));

    await waitFor(() =>
      expect(loginSpy).toHaveBeenCalledWith({
        email: "ada@example.com",
        password: "correct horse battery",
        turnstile_token: "token-for-login",
      }),
    );
  });

  it("asks for a fresh check after a failed attempt (tokens are single-use)", async () => {
    vi.spyOn(authApi, "getCurrentUser").mockRejectedValue(new ApiError(401, "UNAUTHENTICATED", "nope", {}));
    vi.spyOn(authApi, "login").mockRejectedValue(new ApiError(401, "INVALID_CREDENTIALS", "Invalid email or password.", {}));
    const user = userEvent.setup();
    renderPage();

    await user.type(await screen.findByLabelText("Email"), "ada@example.com");
    await user.type(screen.getByLabelText("Password"), "wrong password");
    await user.click(screen.getByRole("button", { name: "Solve security check" }));
    await user.click(screen.getByRole("button", { name: "Log in" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Invalid email or password.");
    expect(resetSpy).toHaveBeenCalledTimes(1);
  });
});
