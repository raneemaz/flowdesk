import { afterEach, describe, expect, it, vi } from "vitest";

import { apiFetch, ApiError } from "@/api/client";

function mockFetchOnce(body: unknown, status = 200) {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue({
      status,
      json: () => Promise.resolve(body),
    }),
  );
}

describe("apiFetch", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("returns the unwrapped data on a success envelope", async () => {
    mockFetchOnce({ success: true, message: "ok", data: { id: "1" } });

    const result = await apiFetch<{ id: string }>("/whatever");

    expect(result).toEqual({ id: "1" });
  });

  it("throws an ApiError with the code/message/details from an error envelope", async () => {
    mockFetchOnce(
      { success: false, error: { code: "INVALID_CREDENTIALS", message: "Invalid email or password.", details: {} } },
      401,
    );

    await expect(apiFetch("/auth/login")).rejects.toMatchObject({
      name: "ApiError",
      status: 401,
      code: "INVALID_CREDENTIALS",
      message: "Invalid email or password.",
    });
  });

  it("sends the CSRF token header only when one is provided", async () => {
    mockFetchOnce({ success: true, message: "ok", data: null });

    await apiFetch("/auth/logout", { method: "POST", csrfToken: "abc123" });

    const [, options] = (fetch as ReturnType<typeof vi.fn>).mock.calls[0];
    expect(options.headers["X-CSRF-Token"]).toBe("abc123");
  });

  it("sends credentials: include on every request", async () => {
    mockFetchOnce({ success: true, message: "ok", data: null });

    await apiFetch("/auth/me");

    const [, options] = (fetch as ReturnType<typeof vi.fn>).mock.calls[0];
    expect(options.credentials).toBe("include");
  });

  it("is an instance of Error so it is catchable like any other exception", async () => {
    mockFetchOnce({ success: false, error: { code: "NOT_FOUND", message: "Not found.", details: {} } }, 404);

    try {
      await apiFetch("/nope");
      expect.unreachable();
    } catch (error) {
      expect(error).toBeInstanceOf(ApiError);
      expect(error).toBeInstanceOf(Error);
    }
  });
});
