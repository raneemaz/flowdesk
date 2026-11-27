import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";

import * as authApi from "@/api/auth";
import { ApiError } from "@/api/client";
import type { UserPublic } from "@/types/user";

// The CSRF token is only ever returned once, in POST /auth/login's
// response body (docs/API.md) - there is no endpoint that hands it back
// out again. Without persisting it somewhere JS can read, a page
// refresh would leave an otherwise-valid session (the HttpOnly cookie
// survives refreshes just fine) unable to make any state-changing
// request until the user logs in again.
//
// sessionStorage, not localStorage: it's cleared when the tab closes,
// matching how long a "page session" should reasonably keep this value
// around, and it's deliberately not the kind of long-lived storage
// NFR's "avoid tokens in localStorage" guidance was written to avoid -
// that guidance is about long-lived *auth* tokens replacing the
// HttpOnly session cookie (e.g. a JWT), not a CSRF token that is
// useless without that cookie (which JS can never read) alongside it.
// Known limitation: a second tab opened after login (not itself
// through a fresh login in that tab) sees the user as authenticated
// via the cookie but has no CSRF token in its own sessionStorage, so a
// mutation there (e.g. logout) will fail until that tab's own login.
const CSRF_STORAGE_KEY = "flowdesk:csrf_token";

type AuthStatus = "loading" | "authenticated" | "unauthenticated";

interface AuthContextValue {
  user: UserPublic | null;
  status: AuthStatus;
  csrfToken: string | null;
  login: (email: string, password: string, turnstileToken?: string) => Promise<void>;
  register: (name: string, email: string, password: string, turnstileToken?: string) => Promise<void>;
  logout: () => Promise<void>;
  /** Swap in the user record a profile update returned (Settings > My account). */
  replaceUser: (updated: UserPublic) => void;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<UserPublic | null>(null);
  const [status, setStatus] = useState<AuthStatus>("loading");
  const [csrfToken, setCsrfToken] = useState<string | null>(null);

  useEffect(() => {
    let isMounted = true;

    authApi
      .getCurrentUser()
      .then((currentUser) => {
        if (!isMounted) return;
        setUser(currentUser);
        setCsrfToken(sessionStorage.getItem(CSRF_STORAGE_KEY));
        setStatus("authenticated");
      })
      .catch(() => {
        if (!isMounted) return;
        setUser(null);
        setStatus("unauthenticated");
      });

    return () => {
      isMounted = false;
    };
  }, []);

  const login = useCallback(async (email: string, password: string, turnstileToken?: string) => {
    const result = await authApi.login({ email, password, turnstile_token: turnstileToken });
    sessionStorage.setItem(CSRF_STORAGE_KEY, result.csrf_token);
    setCsrfToken(result.csrf_token);
    setUser(result.user);
    setStatus("authenticated");
  }, []);

  const register = useCallback(async (name: string, email: string, password: string, turnstileToken?: string) => {
    // Does not log in - registration never starts a session
    // (backend/docs/API.md). The caller is responsible for navigating
    // to the login page afterward.
    await authApi.register({ name, email, password, turnstile_token: turnstileToken });
  }, []);

  const logout = useCallback(async () => {
    try {
      if (csrfToken) {
        await authApi.logout(csrfToken);
      }
    } catch (error) {
      // A 401 here means the session was already gone server-side
      // (expired, or revoked elsewhere) - nothing left to destroy, so
      // this isn't a failure from the user's point of view. Any other
      // error still clears local state below rather than leaving the
      // UI stuck showing a now-useless session.
      if (!(error instanceof ApiError && error.status === 401)) {
        console.error("Logout request failed; clearing local session state anyway.", error);
      }
    } finally {
      sessionStorage.removeItem(CSRF_STORAGE_KEY);
      setCsrfToken(null);
      setUser(null);
      setStatus("unauthenticated");
    }
  }, [csrfToken]);

  const replaceUser = useCallback((updated: UserPublic) => setUser(updated), []);

  const value = useMemo(
    () => ({ user, status, csrfToken, login, register, logout, replaceUser }),
    [user, status, csrfToken, login, register, logout, replaceUser],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error("useAuth must be used within an AuthProvider.");
  }
  return context;
}
