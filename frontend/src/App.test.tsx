import { render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { App } from "@/App";
import * as authApi from "@/api/auth";

describe("App", () => {
  it("shows the public landing page to an unauthenticated visitor at the root", async () => {
    vi.spyOn(authApi, "getCurrentUser").mockRejectedValue(new Error("401"));

    render(<App />);

    await waitFor(() => {
      expect(screen.getByRole("heading", { level: 1, name: "Run your whole business in one flow." })).toBeInTheDocument();
    });
  });
});
