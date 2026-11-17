# FlowDesk Frontend

React + TypeScript SPA for FlowDesk. Feature pages (auth, dashboards,
domain modules) are added incrementally per the backlog in
[`docs/FlowDesk_Specification.md`](../docs/FlowDesk_Specification.md);
the application skeleton (FD-003), authentication - login/register,
protected routes, auth state (FD-017), organization onboarding -
creation flow, org switcher (FD-018), the employee frontend -
directory, profile, department management (FD-024), the task
frontend - list/board/calendar/My Tasks, assignment, comments, history
(FD-032), the customer & request frontend - directory, profile, queue,
assignment, status controls (FD-039), and the invoice frontend -
editor, payment form, balance/status refresh, PDF access (FD-046) -
exist so far.

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
      invoice.ts               InvoicePublic/InvoiceLineItemPublic/FinancialSummaryPublic - same (FD-046)
      payment.ts               PaymentPublic/PaymentRecordedData - same (FD-046)
    api/
      client.ts             apiFetch() - hybrid success/error envelope, ApiError;
                             apiFetchWithMeta() - same, plus the `meta` sibling a
                             paginated list response carries (FD-024)
      auth.ts                register/login/logout/getCurrentUser
      organizations.ts       createOrganization/listOrganizations
      employees.ts            listEmployees/getEmployee/updateEmployeeProfile (FD-024)
      departments.ts          createDepartment/listDepartments/updateDepartment/deactivateDepartment (FD-024)
      invoices.ts              listInvoices/getInvoice/listInvoiceLineItems/createInvoice/
                                updateInvoice/issueInvoice/cancelInvoice/getFinancialSummary/
                                invoicePdfUrl (FD-046)
      payments.ts              listPayments/recordPayment (FD-046)
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
      invoices/
        constants.ts             status labels/options, discount-type options (FD-046)
        permissions.ts           canManageInvoices/canViewFinancialReports/canEditInvoice/
                                  canIssueInvoice/canCancelInvoice/canRecordPayment - UI-only (FD-046)
        schemas.ts               Zod schemas for the invoice editor and payment forms (FD-046)
        calculations.ts          previewInvoiceTotals/formatMoney/sumMoney - explicitly
                                  non-authoritative display-only arithmetic (FD-046)
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
      InvoiceListPage.tsx            search/filter/paginate invoices + financial summary (FD-046)
      InvoiceFormPage.tsx             create/edit an invoice, incl. the line-item editor (FD-046)
      InvoiceDetailPage.tsx           view/issue/cancel + payment ledger/form + PDF link (FD-046)
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

## Task frontend - list/board/calendar/My Tasks, assignment, comments, history (FD-032)

- **No new backend calls** - this task is pure frontend, consuming the
  already-reviewed FD-026 through FD-031 endpoints (`app/tasks/`) as-is.
  `api/tasks.ts` adds the usual thin wrapper functions (`listTasks`,
  `getTask`, `createTask`, `updateTask`, `assignTask`, `updateTaskStatus`,
  `listTaskComments`, `createTaskComment`, `listTaskHistory`), all scoped
  by the current organization's id from `OrganizationContext` - never a
  user-editable value.
- **`TasksNav`** - shared tab bar (List/Board/Calendar/My Tasks) reused
  by all four pages, consistent with how `HomePage`'s own nav works.
  `HomePage` gained an unconditional "Tasks" link (unlike "Departments",
  every role can see *some* task list, even if the backend's own
  `assigned`-scope restriction means an Employee's lists only ever show
  their own tasks).
- **`TaskListView`** - the shared list/filter/inline-create component
  behind both `TaskListPage` (`/tasks`) and `MyTasksPage` (`/tasks/mine`),
  parameterized by `{title, lockedAssigneeId?}` so `MyTasksPage` is a
  thin wrapper that locks the assignee filter to the viewer's own
  membership instead of duplicating the list UI.
- **Resolving "my own membership_id"** - `MembershipPublic` (from
  `OrganizationContext`) never exposes the viewer's own membership id
  directly. For a non-manager, this is a non-problem: reaching a task's
  detail page at all already proves assignee status (the backend's
  `TASK_VIEW_UPDATE` `assigned` scope would 403 otherwise), and the list
  pages lean entirely on the backend's own `assigned`-scope
  auto-restriction rather than filtering client-side. The one case that
  still needs it - an Owner/Manager viewing `/tasks/mine` - resolves it
  by matching the logged-in user's `email` against the employee
  directory response (`EMPLOYEE_DIRECTORY_VIEW` never grants `none`, so
  `name`/`email` are always available), never by trusting anything
  client-supplied.
- **`TaskBoardPage`** (`/tasks/board`) - Kanban columns grouped by
  `STATUS_ORDER`, with click-based "move to" buttons instead of
  drag-and-drop (a deliberate scope simplification, not a Section 35
  item). Each button is gated by `statusOptionsFor` - a **UI-only hint**
  mirroring the backend's `_STATUS_TRANSITIONS`/
  `_ASSIGNEE_ALLOWED_TRANSITIONS` tables (`app/tasks/service.py`) exactly
  - so a non-manager assignee only ever sees the one or two
  forward-progress moves they're actually allowed, never the manager-only
  ones (e.g. `cancelled`).
- **`TaskCalendarPage`** (`/tasks/calendar`) - a custom month grid (plain
  `Date` arithmetic, 42 cells) rather than pulling in a calendar library;
  Prev/Next re-fetch with the new month's due-date range. Board and
  Calendar both fetch up to 100 tasks unpaginated - an accepted
  limitation at this project's seed-data scale, confirmed by the
  reviewer to still be organization-scoped (never a global fetch) and
  not an avenue into unauthorized data, just a UX cap worth revisiting if
  a real org's task count grows past it.
- **`TaskDetailPage`** (`/tasks/:taskId`) - view/edit/assign/status/
  comments/history in one page. Edit, Assignee select, and the status
  "Move to" buttons are all gated by `canManageTasks`/`statusOptionsFor`
  (UI hints only - the backend independently re-validates every field on
  every write, per spec Section 32's "never trust frontend role checks
  as authorization"). A single `invalidateTask()` helper refetches both
  the task query and its history query together, since editing,
  assigning, *and* changing status can each write a `TaskHistory` row
  (FD-027/FD-028/FD-029) - invalidating only one of the two left history
  stale after an assignment until some other action happened to refresh
  it (see bugs below).
- **`features/tasks/permissions.ts`** - `canManageTasks` mirrors
  `TASK_CREATE_ASSIGN`; `legalNextStatuses`/`statusOptionsFor` mirror
  `_STATUS_TRANSITIONS`/`_ASSIGNEE_ALLOWED_TRANSITIONS` line for line.
  Reviewed by `tenant-security-reviewer`: every API call is
  organization-scoped from context, no component trusts a task's own
  embedded fields (or anything else client-supplied) for an authorization
  decision, and no request body ever smuggles in a field the current UI
  hides.

**Two real bugs found and fixed during live-browser verification**
(neither caught by the unit tests, which mock every API call and so
never exercise the real interaction between two mutations' cache scope,
or the real shape of a raw backend response):

1. **Stale history after assigning.** `onAssign` originally invalidated
   only the task query, not the history query, so the History section
   kept showing "No history yet." after an assignment even though the
   backend had already written the `assignee_changed` row - the next
   unrelated action (e.g. a status change) would refetch history and
   suddenly show both entries at once. Fixed by consolidating all three
   mutation paths onto the shared `invalidateTask()` helper above.
2. **Raw, unresolved history text.** History entries render
   `previous_value`/`new_value` exactly as the backend stores them - raw
   `membership_id` UUIDs for `assignee_changed`, raw enum values for
   `status_changed`/`priority_changed` (`docs/API.md`'s Tasks section) -
   so the page originally showed strings like "changed assignee changed
   from — to 0b696a82-...". Fixed with a `describeHistoryValue()` helper
   that resolves assignee ids via the already-fetched employee map and
   enum values via the existing label maps, plus stripping the
   `_changed` suffix from `event_type` before building the sentence.

**Verified against the real backend in a real browser**, as both the
Owner and a freshly-added Employee-role member of the same organization:
creating a task from the List page; the Board page's click-to-move
buttons (confirmed the Owner sees every legal move while the Employee
assignee sees only the forward-progress ones); the Calendar page's
month navigation and a task landing on its due-date cell; editing a
task's fields (title, priority, dates, estimated/actual hours) and
confirming the save persists and appears in History; assigning a task
and posting a comment; `My Tasks` for the Owner (resolved via the
directory email-match) and for the Employee (backed entirely by the
server's own `assigned`-scope restriction, no client-side filtering
needed); and, on `HomePage`, that "Departments" is hidden but "Tasks" is
shown for the Employee role, and that `/tasks`, `/tasks/board`,
`/tasks/calendar`, and `/tasks/mine` all correctly show only that
Employee's own assigned task. One environmental snag during this pass
was not a product bug: a long debugging session's full-page reloads
left the in-memory CSRF token (`AuthContext`, FD-017) desynced from
`sessionStorage` for one tab, which made every mutation's existing
`if (!csrfToken) return;` guard silently no-op - re-logging in restored
it immediately, and a real user never hits this outside of this kind of
heavy manual reload-testing.

## Customer & request frontend - directory/profile/queue/assignment/status (FD-039)

- **No new backend calls** - pure frontend, consuming the already-reviewed
  FD-034 through FD-038 endpoints (`app/customers/`, `app/customer_requests/`)
  as-is. `api/customers.ts` and `api/customerRequests.ts` add the usual thin
  wrapper functions, all scoped by the current organization's id from
  `OrganizationContext`.
- **`CustomerListPage`/`CustomerDetailPage`** (`/customers`,
  `/customers/:customerId`) - directory (search/filter/inline-create) and
  profile (view/edit/archive). The profile's "Requests" section is FR-022's
  "customer profile shows request + invoice history" - just the request
  half for now, since invoices don't exist yet.
- **`RequestListPage`/`RequestDetailPage`** (`/requests`,
  `/requests/:requestId`) - queue (search/filter/inline-create) and detail
  (assign/status/resolution notes/comments/history). No separate "My
  Requests" view, unlike Task's `MyTasksPage` - `GET /customer-requests`
  already auto-restricts an Employee (`assigned` scope) to their own
  requests server-side, so the one queue page serves every role without
  client-side filtering, the same reasoning `TaskListPage` itself (not a
  locked view) already relies on.
- **The one real design decision this task required**: `CUSTOMER_MANAGE`
  is `none` for Employee (`app/authz/permissions.py`, reviewed at FD-035)
  - an Employee literally cannot fetch *any* customer record via the API,
  including the one tied to a request assigned to them. `RequestDetailPage`
  and `RequestListPage` gate every `getCustomer`/`listCustomers` call
  behind `canManageCustomers(viewerRole)` and simply omit the Customer
  field/column for an Employee viewer, rather than attempting the fetch
  (which would just 403) or working around it - the same "hide a field a
  viewer's role can't resolve" pattern `TaskDetailPage` already uses for
  its own Department field.
- **`features/requests/permissions.ts`** - `canManageRequests` mirrors the
  backend's inline `_require_full_scope` checks (`CUSTOMER_REQUEST_MANAGE`
  has no separate create-only permission the way Task's
  `TASK_CREATE_ASSIGN` does, so create/assign are gated by the same
  `full`-scope predicate used for everything else); `canAccessRequests`
  mirrors "not `none`" (everyone except Accountant); `legalNextStatuses`/
  `statusOptionsFor` mirror `_REQUEST_TRANSITIONS`/
  `_ASSIGNEE_ALLOWED_TRANSITIONS` line for line, including that resolving
  and closing are `full`-scope only.
- **Resolution notes** - a standalone textarea + "Save notes" button on
  `RequestDetailPage`, visible to anyone who can view the request
  (including an Employee on their own assigned request) - the backend's
  `update_request_status` applies `resolution_notes` independently of
  whether `status` itself changes, so this calls the same endpoint with
  the request's current status unchanged.
- Reviewed by `tenant-security-reviewer`: every API call is
  organization-scoped from context, no request body construction smuggles
  in a field the current UI hides, the UI-only permission hints never
  substitute for the backend's own re-validation, and the unpaginated
  `perPage: 100` name-resolution fetches (customers/employees-for-names)
  follow the exact same accepted pattern Task's own department/employee
  lookups already established.

**Verified against the real backend in a real browser**, as both the
Owner and a freshly-added Employee-role member of the same organization:
creating a customer from the directory, viewing/editing its profile,
archiving it; creating a request against that customer from the queue and
confirming the customer name resolves correctly in the list; assigning an
unassigned (`new`) request and confirming status auto-advanced to
`assigned` with both a resolved `assignee_changed` and `status_changed`
history entry; moving the request through `in_progress`; reassigning it
to the Employee and confirming status did *not* regress; saving
resolution notes and confirming the value persists across a reload;
posting a comment; and, logged in as the Employee, confirming `/`
shows "Requests" but not "Customers", the queue shows only their own
request with no Customer column and "You" as the assignee, and the
detail page shows no Customer field, no Assignee control, and only the
one legal forward-progress status button - with no `GET .../customers`
network request made at any point in that session.

## Invoice frontend - editor, payment form, balance/status refresh, PDF access (FD-046)

- **A real backend gap was found and fixed *before* writing any
  frontend code**, not after: no endpoint anywhere returned an
  invoice's individual line items (description/quantity/unit_price/
  tax_rate) - `InvoicePublic` only ever carried the computed
  aggregates (`subtotal`/`tax_total`/...), which an editor cannot work
  from (it needs to show a caller what they'd previously entered, not
  just a total). Added `GET .../invoices/{invoice_id}/line-items`
  (read-only, mirroring the comments/history sub-resource pattern
  rather than embedding the list in `InvoicePublic` itself, which
  would otherwise force an N+1 query on every row of the plain list
  endpoint) - see `docs/API.md`'s Invoices section and
  `backend/tests/test_invoices_line_items.py`. Reviewed by
  `tenant-security-reviewer`: clean.
- **`InvoiceListPage`** (`/invoices`) - search/filter/paginate, plus a
  financial-summary stats bar (invoiced/collected/outstanding/overdue
  count) shown only to a viewer with `canViewFinancialReports`
  (Owner/Accountant) - the same organization-scoped `GET .../invoices/financial-summary`
  call FD-044 already built, not a new aggregate computed here.
- **`InvoiceFormPage`** (`/invoices/new` and `/invoices/:invoiceId/edit`)
  - one page for both create and edit, since they share the same
  fields and the same `useFieldArray`-driven line-item editor. Editing
  is **draft-only** server-side (`422 INVOICE_LOCKED` otherwise,
  FD-042); this page only mirrors that as a friendlier "this invoice
  is locked" message for a direct `/edit` hit on a non-draft invoice,
  never the real boundary. Shows a **live, explicitly non-authoritative
  total preview** (`features/invoices/calculations.ts`) as line items
  are typed - plain JS-number arithmetic, never sent to the API and
  never trusted as the real total (spec Section 32 - the saved
  invoice's own totals, shown on the detail page afterward, are
  whatever `app.invoices.service.recalculate_invoice` actually
  returned).
- **`InvoiceDetailPage`** (`/invoices/:invoiceId`) - fields, line items
  (fetched via the new endpoint above), totals, and status-appropriate
  actions (`Edit`/`Issue`/`Cancel`, each gated by a UI-only hint
  mirroring the backend's own status gates in `app/invoices/service.py`
  and `app/payments/service.py`), a `View PDF` link (a plain
  `target="_blank"` anchor straight at the backend's PDF endpoint -
  the browser's own cookie-bearing same-origin navigation handles
  auth, no JS fetch/blob dance needed), and the payment ledger +
  record-payment form. **Amount paid/balance due are computed from the
  real, already-recorded payments** (`features/invoices/calculations.ts`'s
  `sumMoney`), not a separate aggregate call - the same "display-only
  sum of server-validated numbers" category as showing `invoice.total`
  without recomputing tax.
- **The idempotency key** FD-043's payment endpoint requires is
  generated client-side (`crypto.randomUUID()`) and never shown to the
  user - it's a retry-safety mechanism, not a business field. Generated
  once per *attempt* and only replaced after a submission actually
  succeeds, so retrying a failed submission (e.g. a network hiccup)
  reuses the same key rather than risking a second payment.
- **`features/invoices/permissions.ts`** - `canManageInvoices`/
  `canViewFinancialReports` mirror `INVOICE_PAYMENT_MANAGE`/
  `FINANCIAL_REPORTS_VIEW` as two separate functions even though
  today's matrix makes them identical (Owner/Accountant only) - the
  same "don't collapse two permissions the backend deliberately kept
  separate" reasoning `docs/API.md`'s Financial reports section
  documents. `canEditInvoice`/`canIssueInvoice`/`canCancelInvoice`/
  `canRecordPayment` mirror each service function's own status gate
  line for line.

**Verified against the real backend in a real browser** (`FLASK_ENV=testing`
on the backend - this dev environment has no Redis for
`FLASK_ENV=development`'s session store, see `backend/README.md`):
created an organization and customer, created a draft invoice with a
line item and confirmed the live total preview updated as it was
typed, saved it and confirmed the detail page showed the server's own
(not the preview's) totals; issued it (draft → sent, confirmed
`Edit`/`Issue` disappeared and the payment form appeared); recorded a
partial payment and confirmed status became "Partially Paid", amount
paid/balance due updated, the payment appeared in the ledger, and
`Cancel` disappeared (blocked once money has moved, FD-043); opened
the PDF link and confirmed a real file download was triggered (the
full WeasyPrint pipeline, not just a 200 response); created a second
draft invoice with no line items, added one via `Edit`, and confirmed
the editor correctly pre-populated the existing customer selection and
line item from the new `line-items` endpoint before saving the change.

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
