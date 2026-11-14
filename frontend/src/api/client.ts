// Thin wrapper around fetch for the hybrid envelope every FlowDesk
// endpoint uses (see docs/API.md):
//   success: {"success": true, "message": "...", "data": {...}}
//   error:   {"success": false, "error": {"code", "message", "details"}}
//
// Dev requests go through Vite's dev-server proxy (see vite.config.ts)
// rather than straight to the backend's own origin: the backend runs on
// a different port than the Vite dev server, and the session cookie is
// HttpOnly + not SameSite=None, so a real browser (unlike curl/pytest,
// which don't enforce any of this) would not reliably send/receive it
// across those two origins without CORS-with-credentials configured on
// the backend. Proxying makes every request same-origin from the
// browser's point of view, which needs no backend change at all. This
// only covers local development - the real cross-origin setup for
// production (frontend on Vercel, backend on Render) is still an open
// question per Section 35 decision #13 (see backend/README.md).
const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "/api/v1";

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly details: Record<string, string>;

  constructor(status: number, code: string, message: string, details: Record<string, string>) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.details = details;
  }
}

interface SuccessEnvelope<T> {
  success: true;
  message: string;
  data: T;
  // Only present on paginated list endpoints (docs/API.md's Pagination
  // section) - untyped here since apiFetch's own callers never need it
  // (they only ever want `data`); apiFetchWithMeta below is the one
  // that cares, and types it properly for its own caller.
  meta?: unknown;
}

interface ErrorEnvelope {
  success: false;
  error: { code: string; message: string; details: Record<string, string> };
}

export interface ApiRequestOptions {
  method?: "GET" | "POST" | "DELETE" | "PATCH";
  body?: unknown;
  csrfToken?: string | null;
}

async function request<T>(path: string, options: ApiRequestOptions = {}): Promise<SuccessEnvelope<T>> {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (options.csrfToken) {
    headers["X-CSRF-Token"] = options.csrfToken;
  }

  const response = await fetch(`${API_BASE_URL}${path}`, {
    method: options.method ?? "GET",
    headers,
    credentials: "include",
    body: options.body !== undefined ? JSON.stringify(options.body) : undefined,
  });

  // Every response from this API is JSON (see docs/API.md) - including
  // errors, so there's no "ok vs. not ok" branch before parsing.
  const body = (await response.json()) as SuccessEnvelope<T> | ErrorEnvelope;

  if (!body.success) {
    throw new ApiError(response.status, body.error.code, body.error.message, body.error.details);
  }

  return body;
}

export async function apiFetch<T>(path: string, options: ApiRequestOptions = {}): Promise<T> {
  const body = await request<T>(path, options);
  return body.data;
}

// For the one family of endpoints that return a `meta` sibling to
// `data` (paginated lists, docs/API.md's Pagination section) - a
// separate function rather than overloading apiFetch's return type for
// every caller that never needs `meta`.
export async function apiFetchWithMeta<T, M>(
  path: string,
  options: ApiRequestOptions = {},
): Promise<{ data: T; meta: M }> {
  const body = await request<T>(path, options);
  return { data: body.data, meta: body.meta as M };
}
