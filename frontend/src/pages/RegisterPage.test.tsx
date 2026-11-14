import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { createMemoryRouter, RouterProvider } from "react-router-dom";

import * as authApi from "@/api/auth";
import { ApiError } from "@/api/client";
import { AuthProvider } from "@/contexts/AuthContext";
import { RegisterPage } from "@/pages/RegisterPage";

function renderRegisterPage() {
  const router = createMemoryRouter(
    [
      { path: "/register", element: <RegisterPage /> },
      { path: "/login", element: <div>Login page</div> },
    ],
    { initialEntries: ["/register"] },
  );

  render(
    <AuthProvider>
      <RouterProvider router={router} />
    </AuthProvider>,
  );
}

describe("RegisterPage", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("rejects a password shorter than 8 characters without calling the API", async () => {
    vi.spyOn(authApi, "getCurrentUser").mockRejectedValue(new ApiError(401, "UNAUTHENTICATED", "nope", {}));
    const registerSpy = vi.spyOn(authApi, "register");
    const user = userEvent.setup();

    renderRegisterPage();
    await waitFor(() =>
      expect(screen.getByRole("heading", { name: "Create your FlowDesk account" })).toBeInTheDocument(),
    );

    await user.type(screen.getByLabelText("Name"), "Ada Lovelace");
    await user.type(screen.getByLabelText("Email"), "ada@example.com");
    await user.type(screen.getByLabelText("Password"), "short");
    await user.type(screen.getByLabelText("Confirm password"), "short");
    await user.click(screen.getByRole("button", { name: "Create account" }));

    expect(await screen.findByText("Password must be at least 8 characters.")).toBeInTheDocument();
    expect(registerSpy).not.toHaveBeenCalled();
  });

  it("rejects mismatched password confirmation without calling the API", async () => {
    vi.spyOn(authApi, "getCurrentUser").mockRejectedValue(new ApiError(401, "UNAUTHENTICATED", "nope", {}));
    const registerSpy = vi.spyOn(authApi, "register");
    const user = userEvent.setup();

    renderRegisterPage();
    await waitFor(() =>
      expect(screen.getByRole("heading", { name: "Create your FlowDesk account" })).toBeInTheDocument(),
    );

    await user.type(screen.getByLabelText("Name"), "Ada Lovelace");
    await user.type(screen.getByLabelText("Email"), "ada@example.com");
    await user.type(screen.getByLabelText("Password"), "correct horse battery");
    await user.type(screen.getByLabelText("Confirm password"), "does not match");
    await user.click(screen.getByRole("button", { name: "Create account" }));

    expect(await screen.findByText("Passwords do not match.")).toBeInTheDocument();
    expect(registerSpy).not.toHaveBeenCalled();
  });

  it("navigates to /login on successful registration without starting a session", async () => {
    vi.spyOn(authApi, "getCurrentUser").mockRejectedValue(new ApiError(401, "UNAUTHENTICATED", "nope", {}));
    const registerSpy = vi.spyOn(authApi, "register").mockResolvedValue({
      id: "u1",
      name: "Ada Lovelace",
      email: "ada@example.com",
      status: "active",
      created_at: "now",
    });
    const user = userEvent.setup();

    renderRegisterPage();
    await waitFor(() =>
      expect(screen.getByRole("heading", { name: "Create your FlowDesk account" })).toBeInTheDocument(),
    );

    await user.type(screen.getByLabelText("Name"), "Ada Lovelace");
    await user.type(screen.getByLabelText("Email"), "ada@example.com");
    await user.type(screen.getByLabelText("Password"), "correct horse battery");
    await user.type(screen.getByLabelText("Confirm password"), "correct horse battery");
    await user.click(screen.getByRole("button", { name: "Create account" }));

    await waitFor(() => expect(screen.getByText("Login page")).toBeInTheDocument());
    expect(registerSpy).toHaveBeenCalledWith({
      name: "Ada Lovelace",
      email: "ada@example.com",
      password: "correct horse battery",
    });
  });

  it("surfaces a duplicate-email error from the backend", async () => {
    vi.spyOn(authApi, "getCurrentUser").mockRejectedValue(new ApiError(401, "UNAUTHENTICATED", "nope", {}));
    vi.spyOn(authApi, "register").mockRejectedValue(
      new ApiError(409, "EMAIL_ALREADY_REGISTERED", "An account with this email already exists.", {}),
    );
    const user = userEvent.setup();

    renderRegisterPage();
    await waitFor(() =>
      expect(screen.getByRole("heading", { name: "Create your FlowDesk account" })).toBeInTheDocument(),
    );

    await user.type(screen.getByLabelText("Name"), "Ada Lovelace");
    await user.type(screen.getByLabelText("Email"), "ada@example.com");
    await user.type(screen.getByLabelText("Password"), "correct horse battery");
    await user.type(screen.getByLabelText("Confirm password"), "correct horse battery");
    await user.click(screen.getByRole("button", { name: "Create account" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("An account with this email already exists.");
  });
});
