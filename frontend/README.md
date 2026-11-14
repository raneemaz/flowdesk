# FlowDesk Frontend

React + TypeScript SPA for FlowDesk. Feature pages (auth, dashboards,
domain modules) are added incrementally per the backlog in
[`docs/FlowDesk_Specification.md`](../docs/FlowDesk_Specification.md);
the application skeleton (FD-003) and authentication - login/register,
protected routes, auth state (FD-017) - exist so far.

## Stack

Vite, React 19, TypeScript (strict mode), React Router, TanStack Query,
React Hook Form + Zod, Tailwind CSS v4, shadcn/ui primitives, Vitest +
React Testing Library.

## Structure

```
frontend/
  index.html
  vite.config.ts / vitest.config.ts     dev-server proxy lives in vite.config.ts (see below)
  tsconfig.json / tsconfig.app.json / tsconfig.node.json
  components.json        shadcn/ui CLI config (so `npx shadcn add <component>` works)
  src/
    main.tsx             React entry point
    App.tsx               QueryClientProvider + AuthProvider + RouterProvider
    vite-env.d.ts          Vite client types + ImportMetaEnv augmentation (VITE_API_BASE_URL)
    index.css             Tailwind import + design tokens (spec Section 12.1)
    lib/
      utils.ts            cn() class-merging helper
      queryClient.ts       shared TanStack Query client
    types/
      user.ts              UserPublic - mirrors backend/openapi.yaml exactly
    api/
      client.ts             apiFetch() - hybrid success/error envelope, ApiError
      auth.ts                register/login/logout/getCurrentUser
    contexts/
      AuthContext.tsx        AuthProvider + useAuth() - current user, session status, CSRF token
    features/
      auth/
        schemas.ts            Zod schemas for the login/register forms (frontend UX validation only)
    routes/
      router.tsx           route table: /login, /register, protected "/"
      ProtectedRoute.tsx    redirects to /login when there's no session
    pages/
      LoginPage.tsx
      RegisterPage.tsx
      HomePage.tsx           minimal protected placeholder - not the real dashboard, see below
    components/ui/
      button.tsx / input.tsx / label.tsx   shadcn primitives
    test/setup.ts           Vitest + jest-dom setup
```

Design tokens in `src/index.css` map directly to the colors in the spec's
design direction table (primary `#4F46E5`, background `#F8FAFC`, sidebar
`#111827`, etc.). Dark theme is explicitly optional in the spec and is not
implemented yet.

## Authentication (FD-017)

- **Auth state** lives in `AuthContext` (`status`: `loading` /
  `authenticated` / `unauthenticated`, plus the current user and CSRF
  token), populated on app load via `GET /auth/me` so a real session
  cookie survives a page refresh.
- **CSRF token persistence.** The backend only ever returns the CSRF
  token once, in `POST /auth/login`'s response body (there's no
  endpoint that hands it back out again). It's cached in
  `sessionStorage` (not `localStorage` - cleared on tab close, and
  deliberately not the kind of long-lived storage NFR's "avoid tokens
  in localStorage" guidance was written to avoid, since a CSRF token is
  useless without the HttpOnly session cookie alongside it) so a page
  refresh doesn't strand an otherwise-valid session unable to make any
  state-changing request. **Known limitation:** a second tab opened
  without logging in there directly sees the user as authenticated
  (via the cookie) but has no CSRF token of its own until that tab logs
  in itself.
- **Protected routes** (`ProtectedRoute`) redirect to `/login` when
  there's no session - this only spares a logged-out visitor from
  seeing a page that would immediately 401 anyway; it is never the real
  security boundary (spec Section 7 - every page's actual data still
  comes from endpoints the backend independently authenticates).
- **Registration never logs in** (`docs/API.md`) - `RegisterPage`
  redirects to `/login` on success rather than starting a session.
- **`HomePage` is a deliberately minimal placeholder** (shows the
  logged-in user + a logout button) - FD-017's scope is auth state and
  routing, not the real dashboard. The actual home/dashboard experience
  comes later, after organization onboarding (FD-018+).

### Dev-server proxy for the session cookie

The backend runs on a different port than the Vite dev server, and the
session cookie is `HttpOnly` and not `SameSite=None` - a real browser
(unlike `curl`/pytest, which don't enforce any of this) would not
reliably send/receive it across those two origins without
CORS-with-credentials configured on the backend. `vite.config.ts`'s
`server.proxy` forwards `/api` to `http://localhost:5000` instead,
which makes every request same-origin from the browser's point of view
and needs no backend change at all - `src/api/client.ts` calls
`VITE_API_BASE_URL` (default `/api/v1`), which goes through that proxy.
This only covers local development; the real cross-origin setup for
production (frontend on Vercel, backend on Render) is still open per
Section 35 decision #13 (see `backend/README.md`).

**Verified against the real backend in a real browser** (not just the
component tests, which mock the API layer): register → duplicate-email
error → log in → wrong-password error → protected home page → page
refresh keeps the session → log out → redirected to `/login`. Run with
`FLASK_ENV=testing` on the backend, since this dev environment has no
Redis (`FLASK_ENV=development`'s session store needs a real one - see
`backend/README.md`); `testing` uses `fakeredis`, same as the backend's
own test suite.

## Setup

```bash
cd frontend
npm install
```

Backend API base URL is read from `VITE_API_BASE_URL` (see the root
`.env.example`) - leave it unset in local dev to use the proxy above.

## Running

```bash
npm run dev
```

## Type-checking, testing, building

```bash
npm run typecheck
npm run test
npm run build
```
