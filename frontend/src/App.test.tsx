import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { App } from "@/App";

describe("App", () => {
  it("renders the root route via the router and query provider", () => {
    render(<App />);

    expect(screen.getByRole("heading", { name: "FlowDesk" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "It works" })).toBeInTheDocument();
  });
});
