import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { createMemoryRouter, RouterProvider } from "react-router-dom";

import * as authApi from "@/api/auth";
import { ApiError } from "@/api/client";
import { AuthProvider } from "@/contexts/AuthContext";
import { LoginPage } from "@/pages/LoginPage";

function renderLoginPage() {
  const router = createMemoryRouter(
    [
      { path: "/login", element: <LoginPage /> },
      { path: "/", element: <div>Home page</div> },
    ],
    { initialEntries: ["/login"] },
  );

  render(
    <AuthProvider>
      <RouterProvider router={router} />
    </AuthProvider>,
  );
}

describe("LoginPage", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("shows validation errors without calling the API when fields are empty", async () => {
    vi.spyOn(authApi, "getCurrentUser").mockRejectedValue(new ApiError(401, "UNAUTHENTICATED", "nope", {}));
    const loginSpy = vi.spyOn(authApi, "login");
    const user = userEvent.setup();

    renderLoginPage();
    await waitFor(() => expect(screen.getByRole("heading", { name: "Log in to FlowDesk" })).toBeInTheDocument());

    await user.click(screen.getByRole("button", { name: "Log in" }));

    expect(await screen.findByText("Email is required")).toBeInTheDocument();
    expect(loginSpy).not.toHaveBeenCalled();
  });

  it("navigates to / on a successful login", async () => {
    vi.spyOn(authApi, "getCurrentUser").mockRejectedValue(new ApiError(401, "UNAUTHENTICATED", "nope", {}));
    vi.spyOn(authApi, "login").mockResolvedValue({
      user: { id: "u1", name: "Ada", email: "ada@example.com", status: "active", created_at: "now" },
      csrf_token: "token",
    });
    const user = userEvent.setup();

    renderLoginPage();
    await waitFor(() => expect(screen.getByRole("heading", { name: "Log in to FlowDesk" })).toBeInTheDocument());

    await user.type(screen.getByLabelText("Email"), "ada@example.com");
    await user.type(screen.getByLabelText("Password"), "correct horse battery");
    await user.click(screen.getByRole("button", { name: "Log in" }));

    await waitFor(() => expect(screen.getByText("Home page")).toBeInTheDocument());
  });

  it("surfaces the backend's error message on invalid credentials", async () => {
    vi.spyOn(authApi, "getCurrentUser").mockRejectedValue(new ApiError(401, "UNAUTHENTICATED", "nope", {}));
    vi.spyOn(authApi, "login").mockRejectedValue(
      new ApiError(401, "INVALID_CREDENTIALS", "Invalid email or password.", {}),
    );
    const user = userEvent.setup();

    renderLoginPage();
    await waitFor(() => expect(screen.getByRole("heading", { name: "Log in to FlowDesk" })).toBeInTheDocument());

    await user.type(screen.getByLabelText("Email"), "ada@example.com");
    await user.type(screen.getByLabelText("Password"), "wrong password");
    await user.click(screen.getByRole("button", { name: "Log in" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Invalid email or password.");
  });
});
