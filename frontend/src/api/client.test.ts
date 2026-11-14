import { afterEach, describe, expect, it, vi } from "vitest";

import { apiFetch, apiFetchWithMeta, ApiError } from "@/api/client";

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

describe("apiFetchWithMeta", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("returns both data and meta from a paginated success envelope", async () => {
    mockFetchOnce({
      success: true,
      message: "ok",
      data: [{ id: "1" }],
      meta: { page: 1, per_page: 20, total: 1, total_pages: 1 },
    });

    const result = await apiFetchWithMeta<{ id: string }[], { page: number; per_page: number; total: number; total_pages: number }>(
      "/whatever",
    );

    expect(result.data).toEqual([{ id: "1" }]);
    expect(result.meta).toEqual({ page: 1, per_page: 20, total: 1, total_pages: 1 });
  });

  it("throws the same ApiError as apiFetch on an error envelope", async () => {
    mockFetchOnce({ success: false, error: { code: "NOT_FOUND", message: "Not found.", details: {} } }, 404);

    await expect(apiFetchWithMeta("/whatever")).rejects.toBeInstanceOf(ApiError);
  });
});
