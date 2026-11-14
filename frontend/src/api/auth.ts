import { apiFetch } from "@/api/client";
import type { UserPublic } from "@/types/user";

export interface RegisterInput {
  name: string;
  email: string;
  password: string;
}

export interface LoginInput {
  email: string;
  password: string;
}

export interface LoginResult {
  user: UserPublic;
  csrf_token: string;
}

// Register does not start a session (backend/docs/API.md) - the caller
// must log in separately afterward. No request/response field here
// duplicates backend validation (e.g. password length) beyond what's
// needed for the request body's shape; the backend remains the source
// of truth and its error messages are surfaced as-is on failure.
export function register(input: RegisterInput): Promise<UserPublic> {
  return apiFetch<UserPublic>("/auth/register", { method: "POST", body: input });
}

export function login(input: LoginInput): Promise<LoginResult> {
  return apiFetch<LoginResult>("/auth/login", { method: "POST", body: input });
}

export function logout(csrfToken: string): Promise<null> {
  return apiFetch<null>("/auth/logout", { method: "POST", csrfToken });
}

export function getCurrentUser(): Promise<UserPublic> {
  return apiFetch<UserPublic>("/auth/me");
}
