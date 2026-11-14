import { render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { App } from "@/App";
import * as authApi from "@/api/auth";

describe("App", () => {
  it("redirects an unauthenticated visitor from the protected root route to /login", async () => {
    vi.spyOn(authApi, "getCurrentUser").mockRejectedValue(new Error("401"));

    render(<App />);

    await waitFor(() => {
      expect(screen.getByRole("heading", { name: "Log in to FlowDesk" })).toBeInTheDocument();
    });
  });
});
