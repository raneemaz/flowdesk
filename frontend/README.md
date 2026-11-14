# FlowDesk Frontend

React + TypeScript SPA for FlowDesk. Feature pages (auth, dashboards,
domain modules) are added incrementally per the backlog in
[`docs/FlowDesk_Specification.md`](../docs/FlowDesk_Specification.md);
the application skeleton (FD-003), authentication - login/register,
protected routes, auth state (FD-017), organization onboarding -
creation flow, org switcher (FD-018), and the employee frontend -
directory, profile, department management (FD-024) - exist so far.

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
      employee.ts            EmployeePublic/EmployeeProfilePublic/PaginationMeta - same (FD-024)
      department.ts           DepartmentPublic - same (FD-024)
    api/
      client.ts             apiFetch() - hybrid success/error envelope, ApiError;
                             apiFetchWithMeta() - same, plus the `meta` sibling a
                             paginated list response carries (FD-024)
      auth.ts                register/login/logout/getCurrentUser
      organizations.ts       createOrganization/listOrganizations
      employees.ts            listEmployees/getEmployee/updateEmployeeProfile (FD-024)
      departments.ts          createDepartment/listDepartments/updateDepartment/deactivateDepartment (FD-024)
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
      employees/
        constants.ts           role/employee-status labels and <select> option lists (FD-024)
        permissions.ts          canManageEmployeeProfile/canManageDepartments - UI-only
                                 show/hide hints, never the real authorization boundary (FD-024)
        schemas.ts              Zod schema for the profile-edit form (FD-024)
      departments/
        schemas.ts              Zod schemas for the create/update department forms (FD-024)
    routes/
      router.tsx           route table: /login, /register, protected "/", "/organizations/new",
                            "/employees", "/employees/:membershipId", "/departments" (FD-024)
      ProtectedRoute.tsx    redirects to /login when there's no session
    pages/
      LoginPage.tsx
      RegisterPage.tsx
      HomePage.tsx           onboarding prompt or active-org summary - not the real dashboard, see below
      CreateOrganizationPage.tsx  the organization creation form (FD-018)
      EmployeeDirectoryPage.tsx    search/filter/paginate the employee directory (FD-024)
      EmployeeProfilePage.tsx      view/edit one employee's profile and status (FD-024)
      DepartmentsPage.tsx          list/create/edit/deactivate departments (FD-024)
    components/
      OrganizationSwitcher.tsx  dropdown of the caller's active memberships (FD-018)
      ui/
        button.tsx / input.tsx / label.tsx / select.tsx / textarea.tsx   shadcn primitives
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

## Employee directory, profiles & department management (FD-024)

- **No sidebar/dashboard shell yet** - FD-053 (after the analytics API,
  FD-052) builds the real one; `HomePage` keeps its own minimal
  `nav` with an "Employees" link (shown to every active member -
  `EMPLOYEE_DIRECTORY_VIEW` never grants `none`) and a "Departments"
  link (shown only for Owner/Manager).
- **`EmployeeDirectoryPage`** (`/employees`) - search (name only, debounced
  by requiring a "Search" submit rather than per-keystroke), role/status
  filters, and a department filter that only appears for a viewer who can
  also list departments (Owner/Manager) - populated from a real
  `GET /departments` call, not a guessed list. Table columns are decided
  by **whether a fetched record actually has the `email` key**, not by
  re-deriving the viewer's scope from their role client-side - the
  backend's `full`/`limited` response shape is the only source of truth
  for what's visible (spec Section 32: never duplicate backend business
  logic). Pagination uses the response's own `meta` via the new
  `apiFetchWithMeta` (`api/client.ts`) - `apiFetch` alone only ever
  returns `data`, and this is the first endpoint whose response needs
  both.
- **`EmployeeProfilePage`** (`/employees/:membershipId`) - renders
  whatever fields the `GET` response contains (same key-presence
  approach as the directory). An "Edit profile" button/form appears only
  when `canManageEmployeeProfile` (a **UI-only hint**, see below) says
  so; submitting always goes through the real `PATCH`, which the backend
  independently re-authorizes - a wrong or stale hint only means a
  button that 403s when clicked, never a security gap. An empty
  `<select>` value (job title/department/manager) maps to an explicit
  `null` in the request body to clear that field, matching the
  backend's partial-update semantics (`docs/API.md`).
- **`DepartmentsPage`** (`/departments`) - gated entirely by
  `canManageDepartments`; an Employee/Accountant/CustomerSupport viewer
  sees a plain "you don't have access" message instead of the page ever
  calling the department API (which would 403 - `DEPARTMENT_MANAGE` has
  no `limited` view cell). Resolves `DepartmentPublic.manager_membership_id`
  (a raw id - the backend never promised a resolved name here, unlike
  `EmployeePublic.manager`) to a display name via the employee directory
  this viewer already has full access to. Deactivation asks for a native
  `window.confirm` before calling `DELETE` - a UX guard, not a security
  one (the backend's own deactivation is already a safe, idempotent soft
  update, `docs/API.md`'s Departments section).
- **`features/employees/permissions.ts`** - `canManageEmployeeProfile`/
  `canManageDepartments` mirror `app/authz/permissions.py`'s
  `EMPLOYEE_MANAGE`/`DEPARTMENT_MANAGE` and
  `app/authz/service.py`'s `can_manage_employee_profile` **for UI
  show/hide decisions only** - spec Section 7.3/32's "never trust
  frontend role checks as authorization," the same principle
  `ProtectedRoute.tsx` already documents for whole pages. Reviewed by
  `tenant-security-reviewer`: every new TanStack Query key includes
  `organizationId`, so switching the active organization can never leave
  stale cross-org data visible; no write path ever treats a passing
  permission hint as a substitute for the real `PATCH`/`POST`/`DELETE`
  call actually succeeding.
- **Known test-coverage gap** (flagged by the reviewer, not treated as
  blocking): no automated test exercises switching the active
  organization while one of these pages is mounted and asserting the
  previous organization's rows disappear before the new one's data
  arrives. In this app's actual navigation, the org switcher only lives
  on `HomePage` - these pages are never mounted at the same time as it -
  so the scenario doesn't correspond to a real user flow today; revisit
  if/when a persistent nav shell (FD-053) puts the switcher and these
  pages on screen together.

**Verified against the real backend in a real browser**, as both an
Owner and a freshly-added Employee-role member of the same organization:
directory search/role/status/department filters and pagination; own-
profile self-view (full fields, no edit button - Employee role has no
`EMPLOYEE_MANAGE` reach even over itself) vs. viewing another member
(limited fields, no edit button) vs. Owner editing a profile (upserts a
not-yet-existing `EmployeeProfile` row, job title/status changes persist);
department create → edit (rename, re-resolves the manager's name) →
Deactivate button clicked, confirmation declined (no request sent,
department unchanged) - the browser pane's automation dismisses native
`window.confirm` dialogs, so the *accepted* path is covered by
`DepartmentsPage.test.tsx` mocking `window.confirm` instead, not by this
manual pass; `/departments` shows the access-denied state directly for
the Employee account, and its nav link is hidden on `HomePage` for that
role.

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
