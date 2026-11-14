# FlowDesk Frontend

React + TypeScript SPA for FlowDesk. Feature pages (auth, dashboards,
domain modules) are added incrementally per the backlog in
[`docs/FlowDesk_Specification.md`](../docs/FlowDesk_Specification.md);
the application skeleton (FD-003), authentication - login/register,
protected routes, auth state (FD-017), and organization onboarding -
creation flow, org switcher (FD-018) - exist so far.

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
      organization.ts       OrganizationPublic/MembershipPublic - same
    api/
      client.ts             apiFetch() - hybrid success/error envelope, ApiError
      auth.ts                register/login/logout/getCurrentUser
      organizations.ts       createOrganization/listOrganizations
    contexts/
      AuthContext.tsx        AuthProvider + useAuth() - current user, session status, CSRF token
      OrganizationContext.tsx  OrganizationProvider + useOrganization() - the caller's
                               memberships and which organization is "active" (see below)
    features/
      auth/
        schemas.ts            Zod schemas for the login/register forms (frontend UX validation only)
      organizations/
        schemas.ts             Zod schema for the create-organization form
        constants.ts           curated currency/timezone option lists for that form
    routes/
      router.tsx           route table: /login, /register, protected "/" and "/organizations/new"
      ProtectedRoute.tsx    redirects to /login when there's no session
    pages/
      LoginPage.tsx
      RegisterPage.tsx
      HomePage.tsx           onboarding prompt or active-org summary - not the real dashboard, see below
      CreateOrganizationPage.tsx  the organization creation form (FD-018)
    components/
      OrganizationSwitcher.tsx  dropdown of the caller's active memberships (FD-018)
      ui/
        button.tsx / input.tsx / label.tsx / select.tsx   shadcn primitives
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

## Organization onboarding (FD-018)

- **`OrganizationContext`** fetches the caller's memberships
  (`GET /organizations`) with TanStack Query (the spec's mandated data-
  fetching library - FD-017 didn't need it since `AuthContext`'s one-shot
  bootstrap call is a poor fit for a cache). It uses the query's
  `isPending` flag rather than `isLoading`: in TanStack Query v5,
  `isLoading` is `false` while a query is disabled (this one is, until
  the caller is authenticated), which would otherwise let the
  zero-organizations onboarding prompt flash on screen before the real
  request has even gone out.
- **"Active organization" is a purely client-side concept** - every
  org-scoped backend endpoint takes `organization_id` from the URL path,
  never a session (`backend/app/authz/decorators.py`), so there's
  nothing to ask the server for. It's persisted in `localStorage` (not
  `sessionStorage`, unlike the CSRF token above - "which org was I last
  looking at" is reasonable to carry across browser restarts), keyed per
  user id so one person's choice on a shared machine never becomes
  another's default. Only `active` memberships are selectable - an
  `inactive`/`suspended` one carries no capabilities server-side
  (`get_active_membership_or_404`), so switching into it would just
  produce 403s everywhere; the API still lists them for history, and
  `OrganizationContext.memberships` still exposes them as-is.
- **`CreateOrganizationPage`** (`/organizations/new`) only asks for
  name, business email, currency, and timezone - `logo`/`phone`/
  `address`/`date_format` are real fields `POST /organizations` already
  accepts, but there's no organization-settings page yet to edit them
  afterward (`backend/openapi.yaml` notes no `GET`/`PATCH
  /organizations/{id}` exists), so collecting them now would just be
  data nobody could ever change. On success the new organization becomes
  the active one and the user is sent back to `/`.
- **`HomePage`** shows an onboarding prompt when the caller has no active
  memberships, or the active organization + `OrganizationSwitcher`
  otherwise. It's still a placeholder, not the real dashboard (spec
  Section 12) - that lands incrementally as the domain modules behind it
  get built.

**Verified against the real backend in a real browser:** register → log
in → onboarding prompt (zero organizations) → create first organization
(auto-becomes active, no Cancel link) → create a second (Cancel link now
offered, new org auto-becomes active) → switch back to the first via the
dropdown → hard page refresh keeps that choice → checked at mobile
width.

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
