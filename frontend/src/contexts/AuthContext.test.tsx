import { act, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import * as authApi from "@/api/auth";
import { ApiError } from "@/api/client";
import { AuthProvider, useAuth } from "@/contexts/AuthContext";
import type { UserPublic } from "@/types/user";

const USER: UserPublic = { id: "u1", name: "Ada", email: "ada@example.com", status: "active", created_at: "now" };

function Probe() {
  const { user, status, csrfToken, logout } = useAuth();
  return (
    <div>
      <span data-testid="status">{status}</span>
      <span data-testid="user">{user?.email ?? "none"}</span>
      <span data-testid="csrf">{csrfToken ?? "none"}</span>
      <button onClick={() => void logout()}>logout</button>
    </div>
  );
}

describe("AuthProvider", () => {
  beforeEach(() => {
    sessionStorage.clear();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("starts in loading state, then becomes unauthenticated when there is no session", async () => {
    vi.spyOn(authApi, "getCurrentUser").mockRejectedValue(new ApiError(401, "UNAUTHENTICATED", "nope", {}));

    render(
      <AuthProvider>
        <Probe />
      </AuthProvider>,
    );

    expect(screen.getByTestId("status").textContent).toBe("loading");

    await waitFor(() => expect(screen.getByTestId("status").textContent).toBe("unauthenticated"));
    expect(screen.getByTestId("user").textContent).toBe("none");
  });

  it("becomes authenticated and rehydrates a previously-stored CSRF token when a session already exists", async () => {
    sessionStorage.setItem("flowdesk:csrf_token", "stored-token");
    vi.spyOn(authApi, "getCurrentUser").mockResolvedValue(USER);

    render(
      <AuthProvider>
        <Probe />
      </AuthProvider>,
    );

    await waitFor(() => expect(screen.getByTestId("status").textContent).toBe("authenticated"));
    expect(screen.getByTestId("user").textContent).toBe("ada@example.com");
    expect(screen.getByTestId("csrf").textContent).toBe("stored-token");
  });

  it("logout clears user/csrf state and calls the logout endpoint with the stored token", async () => {
    sessionStorage.setItem("flowdesk:csrf_token", "stored-token");
    vi.spyOn(authApi, "getCurrentUser").mockResolvedValue(USER);
    const logoutSpy = vi.spyOn(authApi, "logout").mockResolvedValue(null);

    render(
      <AuthProvider>
        <Probe />
      </AuthProvider>,
    );
    await waitFor(() => expect(screen.getByTestId("status").textContent).toBe("authenticated"));

    await act(async () => {
      screen.getByRole("button", { name: "logout" }).click();
    });

    expect(logoutSpy).toHaveBeenCalledWith("stored-token");
    expect(screen.getByTestId("status").textContent).toBe("unauthenticated");
    expect(screen.getByTestId("user").textContent).toBe("none");
    expect(sessionStorage.getItem("flowdesk:csrf_token")).toBeNull();
  });

  it("logout still clears local state even if the server call fails", async () => {
    sessionStorage.setItem("flowdesk:csrf_token", "stored-token");
    vi.spyOn(authApi, "getCurrentUser").mockResolvedValue(USER);
    vi.spyOn(authApi, "logout").mockRejectedValue(new Error("network error"));
    vi.spyOn(console, "error").mockImplementation(() => {});

    render(
      <AuthProvider>
        <Probe />
      </AuthProvider>,
    );
    await waitFor(() => expect(screen.getByTestId("status").textContent).toBe("authenticated"));

    await act(async () => {
      screen.getByRole("button", { name: "logout" }).click();
    });

    expect(screen.getByTestId("status").textContent).toBe("unauthenticated");
  });
});
