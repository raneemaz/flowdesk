# FlowDesk API Conventions

This is the human-readable companion to the contract in
[`backend/openapi.yaml`](../backend/openapi.yaml), served live at
`GET /api/v1/openapi.json` (interactive docs at `GET /api/v1/docs`).
Update **both** whenever an endpoint is added or changed — mandatory rule
#6 in the specification (Section 32).

## Versioning

All endpoints are path-versioned under `/api/v1`. Non-breaking additions
(new optional fields, new endpoints) stay on `v1`. A breaking change
(removing/renaming a field, changing a status code's meaning) gets a new
`/api/v2` prefix rather than silently changing `v1`'s behavior — see
Section 32 mandatory rule #9 ("preserve backward compatibility when
modifying existing endpoints").

## Response envelope

Every response uses one of two shapes, established in FD-002.

**Success:**

```json
{
  "success": true,
  "message": "Task created successfully",
  "data": { "id": "uuid", "title": "Prepare monthly report" }
}
```

**Error** (hybrid shape, chosen in FD-002 to reconcile the spec's two
conflicting examples — see `app/errors.py`):

```json
{
  "success": false,
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Validation failed",
    "details": { "due_date": "Due date cannot be earlier than start date" }
  }
}
```

Route/service code raises `app.errors.APIError(message, status_code, code, details)`
for expected, user-facing failures. Unhandled exceptions and standard
HTTP errors (404, 405, etc.) are converted to this same shape
automatically by the central error handlers — never build an error
response by hand.

## Pagination

Established in FD-007, ahead of any list endpoint that would need it,
so every one is consistent from the start. `GET /organizations` and
`GET /organizations/{organization_id}/invitations` (FD-013/FD-014/FD-016)
predate it being applied retroactively - small, inherently bounded
lists (the caller's own orgs; one org's invitations) where
NFR-010 ("large collections are paginated") doesn't really bite -
and `GET .../departments` (FD-021) is the same way. **First actually
implemented by `GET /organizations/{organization_id}/employees`
(FD-022, below)**, the first list that can realistically grow past a
page.

List endpoints that implement it accept `page` (default `1`) and
`per_page` (default `20`, max `100`) query params, plus endpoint-specific
`search` and filter params. The response adds a `meta` object alongside
`data`:

```json
{
  "success": true,
  "message": "Employees retrieved",
  "data": [ { "membership_id": "uuid", "name": "..." } ],
  "meta": { "page": 1, "per_page": 20, "total": 134, "total_pages": 7 }
}
```

## Status codes

| Code | Meaning |
|---|---|
| 200 | Read/update success |
| 201 | Created |
| 204 | Success, no body |
| 400 | Malformed input |
| 401 | Unauthenticated |
| 403 | Authenticated but unauthorized |
| 404 | Missing or inaccessible (including cross-tenant records — never 403, to avoid confirming existence) |
| 405 | Method not allowed |
| 409 | Conflict |
| 422 | Semantic validation failure |
| 500 | Unexpected server error (never leaks internals — NFR-007) |

## Authentication

Server-side (Redis-backed) sessions, decided in FD-010 per Section 35
open decision #3 — see `docs/DATABASE.md`-adjacent reasoning in
`backend/app/auth/service.py`'s docstrings for the full rationale. Short
version:

- `POST /auth/login` verifies credentials and returns a session cookie
  (`HttpOnly`; `Secure`/`SameSite` configurable via env, see
  `backend/README.md`) plus a `csrf_token` in the response body.
- Authenticated, state-changing requests must send that token back as
  an `X-CSRF-Token` header. `GET` requests don't need it (nothing to
  protect — CSRF only matters for requests that change state).
- `POST /auth/logout` requires both the session cookie and a valid
  `X-CSRF-Token`, and destroys the session server-side immediately (not
  just a client-side cookie deletion — a copied/stolen session cookie
  stops working the instant logout is called, which is the whole point
  of choosing server-side over client-side sessions).
- Login/register themselves are **not** CSRF-protected — no session
  exists yet at that point to protect.
- On login, the session ID is rotated (not just its contents) to prevent
  session fixation; found and fixed during FD-010's own review, see the
  docstring on `create_session()`.
- On every authenticated request, the account's `status` is re-checked,
  not just at login — a session created while active stops working
  immediately once the account is suspended, not only on the next login
  attempt.

**Registration (FD-009) does not start a session.** `POST /auth/register`
only creates the `User` row and returns it; the caller must then call
login separately. This is a deliberate reading of the backlog's
dependency map over FR-001's prose — FR-001 describes registration as
atomically creating a business workspace too, but FD-013 (organization
creation) depends on FD-010 (login), meaning organization creation is
intentionally a separate, authenticated step, not part of registration
itself. Revisit if that scoping turns out to be wrong.

## Authorization (RBAC)

Centralized in `backend/app/authz/` (FD-015) - never a scattered
role-name check in a route handler (spec Section 7.3). Three pieces:

- **`app/authz/permissions.py`** - `Permission` (one entry per
  capability in spec Section 7.2) and `PermissionScope`
  (`full` / `limited` / `own` / `assigned` / `none`), joined by
  `ROLE_PERMISSIONS: dict[MembershipRole, dict[Permission, PermissionScope]]`
  - a fully resolved matrix with **every** cell explicit, no implicit
  defaults.
- **`app/authz/service.py`** - object-level checks: `get_active_membership_or_404(user, organization_id)`
  (the one place that answers "is this user currently an active member
  of this org?"), `check_scope_allows(scope, ...)` (does a granted
  scope cover one specific record), `can_assign_role(...)` (the
  role-change guard below).
- **`app/authz/decorators.py`** - `require_permission(permission)`,
  applied to a view *inside* (i.e. below) `@login_required`. It reads
  `organization_id` from the view's own URL path parameter only -
  never from the request body or query string, so an org can't be
  switched by forging a field - resolves it to an active membership via
  `get_active_membership_or_404`, and rejects with `403 FORBIDDEN` if
  the role's scope for that permission is `none`. On success it sets
  `g.current_membership` and `g.permission_scope` for the view/service
  to use (e.g. filtering a list query by `assignee_id` when the scope
  is `assigned`).

**A missing membership, a membership in a different organization, and
an inactive/suspended membership are all indistinguishable `404`s** -
never `403` - consistent with the "never confirm existence" rule in the
status-code table above. Only once an *active* membership is confirmed
does a role's lack of permission become a `403`.

**Permission baseline matrix** (spec Section 7.2, with every "Limited" /
"As granted" / "If assigned" / "Own-limited" / "Relevant subset" cell
resolved per Section 35 open decision #9 - resolved now, ahead of the
features that will consume most of them, at the user's explicit
direction):

| Capability | Owner | Manager | Employee | Accountant | Customer Support |
|---|---|---|---|---|---|
| Organization settings | Full | Limited¹ | None | None | None |
| Invite/manage memberships | Full | Limited² | None | None | None |
| View employee directory | Full | Full | Limited³ | Limited³ | Limited³ |
| Manage employee profile/status¹¹ | Full | Limited¹¹ | None | None | None |
| Manage departments | Full | Full | None | None | None |
| Create/assign tasks | Full | Full | None⁴ | None | None |
| View/update own assigned task | Full | Full | Assigned | Assigned | Assigned |
| Manage customers | Full | Full | None⁵ | Full | Full |
| Manage customer requests | Full | Full | Assigned | None | Full |
| Manage invoices/payments | Full | None | None | Full | None |
| View financial reports | Full | None | None | Full | None |
| View operational analytics | Full | Full | Own⁶ | Limited⁷ | Limited⁸ |
| View activity history | Full | Full | Own⁹ | Limited¹⁰ | Limited¹⁰ |

1. Manager may edit `logo`/`email`/`phone`/`address`/`date_format` but
   never `name`/`slug`/`currency`/`timezone`, and can never delete the
   org or transfer ownership - those are identity/financial-impacting
   fields reserved for the Owner.
2. Manager may invite members and assign/change roles only among
   Employee/Accountant/CustomerSupport, and only for a target whose
   *current* role is also one of those three - can never touch an
   Owner or another Manager, and can never promote anyone to Owner or
   Manager. See `can_assign_role()`.
3. Name, role, and status of other active members only - never another
   member's email/phone/other contact details (reserved for
   Owner/Manager).
4. Resolves Section 35 open decision #8: employees may not create or
   assign tasks in V1, only act on tasks already assigned to them.
5. Resolved toward the stricter reading of the matrix's "Limited/No" -
   least privilege, no stated business need; Accountant/CustomerSupport
   already cover the customer-facing and financial roles.
6. Personal productivity analytics only (e.g. "my tasks this week"),
   never an org-wide dashboard.
7. The financial analytics subset (revenue, invoices, payments trends).
8. The customer/request analytics subset (volume, resolution time).
9. Activity entries about the employee's own actions/records only.
10. Accountant: activity tied to invoices/payments/financial records.
    CustomerSupport: activity tied to customers/requests.
11. FD-023 addition, not one of the original 12 Section 7.2 rows -
    resolved with the user at FD-023 time (`Permission.EMPLOYEE_MANAGE`).
    Editing job_title/department_id/manager_membership_id/status is an
    action over a *person*, not operational data like a department
    record, so it reuses `MEMBERSHIP_MANAGE`'s existing Manager reach
    restriction rather than `DEPARTMENT_MANAGE`'s unrestricted
    full/full/none/none/none shape: a Manager may only edit a target
    whose role is Employee/Accountant/CustomerSupport, never an Owner's
    or another Manager's profile - including their own, since Manager
    is never in that target set. See `can_manage_employee_profile()`.
    Owner's `full` scope has no such restriction, including self-edit -
    unlike a role change, editing these fields grants no extra system
    access, so there's no self-escalation risk to guard against.

**No one may ever change their own role**, regardless of scope -
resolves spec Section 13's mandatory scenario ("Employee tries to
change their own role -> `403`"), generalized to every role (an Owner
can't self-demote out of their own org either). Enforced by
`can_assign_role()`, not yet wired to an endpoint (no membership-role-change
endpoint is assigned to any task yet).

**First consumed by a real endpoint in FD-016** (invitations, below),
then FD-021 (departments, below) - organization creation/listing
(FD-013/FD-014) predate RBAC and aren't org-scoped by nature (creating
a brand-new org, or listing the caller's own memberships).
`DEPARTMENT_MANAGE` only ever grants `full` or `none` (no
`limited`/`own`/`assigned` cell to implement), so FD-021 needed no
scope-based field/query filtering of its own. **`EMPLOYEE_DIRECTORY_VIEW`
(FD-022, below) is the first permission to actually implement a
`limited` cell** - footnote 3's "name, role, and status... only" is
taken literally: the `limited` response has exactly those four keys
(`membership_id`/`name`/`role`/`status`), nothing else, not even a
`null`-valued placeholder for the fields a `full`-scope caller gets.
**`EMPLOYEE_MANAGE` (FD-023, below) is the first permission whose
`limited` cell needs an object-level reach check beyond the scope
itself** - `can_manage_employee_profile()` (`app/authz/service.py`),
mirroring the reach check `can_assign_role()` already established for
`MEMBERSHIP_MANAGE`. **`TASK_VIEW_UPDATE` (FD-026, below) is the first
permission whose `assigned` scope is translated into a list-query row
filter**, not a field-visibility filter like `EMPLOYEE_DIRECTORY_VIEW`'s
`limited` cell - every caller who can see a task sees every one of its
fields, the scope only decides *which* tasks are visible at all
(`app/tasks/service.py`'s `list_tasks`/`get_task`). Later tasks nesting
routes under `/organizations/<organization_id>/...` - FD-035
(customers), FD-042 (invoices), FD-047/FD-048 (activity logs/
notifications) - still need their own scope-based filtering; the
matrix above is the contract, not the implementation, for the
resources that don't exist yet.

## Invitations (FD-016)

Centralized in `backend/app/invitations/`, gated by
`require_permission(Permission.MEMBERSHIP_MANAGE)` from the
Authorization section above. Resolves Section 35 open decision #4
(delivery provider/templates): real SMTP email delivery, chosen over a
vendor-specific SDK so development and production share the exact same
code path (`backend/app/email/client.py`) - only `SMTP_*` env vars
differ. **Not reachable from a real mail server in this dev
environment** (same documented gap as Docker/Redis) - `SMTP_HOST` is
unset here, so sends are logged instead; `ProductionConfig` refuses to
start without it.

**The raw invitation token is never returned in an API response** -
only emailed. Once real delivery exists, the inviter (who is already
authorized to send the invite) gaining the raw token too would widen
the token's exposure (logs, browser history, XSS) beyond the one
channel - the invitee's inbox - that's supposed to be the only way to
obtain it. If delivery fails, the admin's recourse is to cancel and
re-invite (no separate "resend" endpoint exists - out of this task's
scope).

- `POST /organizations/{organization_id}/invitations` - create and
  email an invitation. Requires `MEMBERSHIP_MANAGE` (Owner: any role;
  Manager: only Employee/Accountant/CustomerSupport). `422` on an
  unknown role or extra fields; `409 ALREADY_A_MEMBER` if the email
  already has an active membership in this org; `409
  INVITATION_ALREADY_PENDING` if an unexpired, unaccepted,
  uncancelled invitation already exists for that email (a narrow,
  documented check-then-insert race - see `docs/DATABASE.md`). Response
  includes `"email_delivery": "sent" | "failed"` - a failed send never
  rolls back the invitation row (Section 14's "a failed [external] call
  must never corrupt business data," applied to email instead of the AI
  provider it was written for).
- `GET /organizations/{organization_id}/invitations` - list every
  invitation for the org (any status - history isn't hidden, same
  convention as membership listing). Requires `MEMBERSHIP_MANAGE`.
- `DELETE /organizations/{organization_id}/invitations/{invitation_id}`
  - cancel a pending invitation. `404` if it doesn't exist or belongs to
  a different organization (object-level check, never distinguishable
  from "doesn't exist"); `403` if the caller's `MEMBERSHIP_MANAGE` scope
  doesn't reach the invitation's role (a Manager can't cancel an
  Owner/Manager-role invite, same restriction as creating one); `409
  INVITATION_NOT_PENDING` if it's already accepted/cancelled/expired.
- `POST /invitations/accept` - accept an invitation by its raw token.
  **Not** nested under `/organizations/{organization_id}/...` and
  **not** gated by `require_permission` - the invitee isn't an org
  member yet, so there's nothing for that gate to check; only
  `login_required` + `csrf_protect` apply. The invitee must already
  have an account (register, then log in, same as any other authenticated
  action) with the exact email the invitation targeted:
  - `404 INVITATION_NOT_FOUND` - token doesn't match any invitation.
  - `409 INVITATION_CANCELLED` / `409 INVITATION_ALREADY_ACCEPTED` / `409
    INVITATION_EXPIRED` - token is real but no longer usable. Unlike
    membership lookups, these are intentionally specific (not a generic
    404) - correctly presenting the one true random 256-bit token
    already proves legitimate possession of it, so there's no
    enumeration risk in saying *why* it didn't work.
  - `403 INVITATION_EMAIL_MISMATCH` - authenticated as the wrong person.
  - `409 ALREADY_A_MEMBER` - caller is already an active member of that
    org.
  - On success: creates the `Membership` (role = the invited role,
    status = active) and marks the invitation accepted, atomically.

## Departments (FD-021)

Centralized in `backend/app/departments/`, all four endpoints gated by
`require_permission(Permission.DEPARTMENT_MANAGE)` from the
Authorization section above (`full` for Owner/Manager, `none` for
everyone else - already finalized by FD-015, nothing added to the
matrix here). No list-specific permission exists: an Employee/
Accountant/CustomerSupport gets `403` on `GET` too, not just the
write endpoints - departments only has one capability row in spec
Section 7.2 ("Manage departments"), not a separate "view" one.

**`DELETE` is a soft deactivate, never a real row delete** - this
task's own wording ("safe-deletion policy") and spec Section 10.3 rule
#5 (never destroy history without a retention policy). It sets
`status` to `inactive`; the row, and every historical
`EmployeeProfile.department_id` reference to it, survive untouched.
`PATCH` can set `status` back to `active` (reactivation) - there's no
separate "reactivate" endpoint, since the four HTTP verbs the spec's
endpoint table lists already cover it as an ordinary field update.

**`manager_membership_id` is validated against the caller's own
organization in the service layer** - `Department.manager_membership_id`
(FD-019, `docs/DATABASE.md`) explicitly deferred this check here, since
the model alone can't DB-enforce it without a `SET NULL` FK conflicting
with `organization_id` staying required. Must resolve to a real,
*active* `Membership` with that exact `organization_id` - a missing,
cross-organization, or inactive one is rejected the same way
(`422 INVALID_MANAGER_MEMBERSHIP`), so a caller can't distinguish "no
such membership" from "that membership belongs to someone else's org."

- `POST /organizations/{organization_id}/departments` - create. Body:
  `{"name": "...", "description"?: "...", "manager_membership_id"?: "uuid"}`.
  `name` is required and trimmed (a whitespace-only name is a `422`,
  not silently accepted); `status` isn't accepted here - a new
  department always starts `active`.
- `GET /organizations/{organization_id}/departments` - list every
  department for the org, any status (deactivation never hides
  history, same convention as membership/invitation listing), sorted
  by name.
- `PATCH /organizations/{organization_id}/departments/{department_id}`
  - partial update. Only fields actually present in the request body
  are changed (`model_dump(exclude_unset=True)`, never a plain
  `model_dump()`) - `description` and `manager_membership_id` accept an
  explicit `null` to clear them, but `name` and `status` don't (neither
  is a "clearable" concept) and return `422` if sent as `null`. `404`
  if the department doesn't exist or belongs to a different
  organization - indistinguishable from "doesn't exist", same
  object-level-check convention as invitations.
- `DELETE /organizations/{organization_id}/departments/{department_id}`
  - deactivate (see above). Idempotent - deactivating an
  already-inactive department is a `200` no-op, not an error. Same
  `404` behavior as `PATCH` for a missing/cross-tenant department.

## Employee directory (FD-022)

`GET /organizations/{organization_id}/employees` - gated by
`EMPLOYEE_DIRECTORY_VIEW` (Authorization section above), which never
grants `none` - every active member can see *some* version of the
directory, never a flat `403`. Read-only; the single-record view and
edit endpoints are documented below (FD-023).

**Membership-centric, not profile-centric.** Lists every row with an
*active* `Membership` in the org (deactivated/suspended memberships are
excluded entirely, not just hidden - they aren't "on the team" the way
a deactivated-but-still-a-member `EmployeeProfile` is), left-joining
`EmployeeProfile` for `job_title`/`department`/`manager`/employment
`status` - which may not exist yet for a given membership (nothing in
the codebase auto-creates one; that's a future task). Those fields are
`null` rather than a fabricated default, including `status`, which
means `status` is *not* the same thing as `Membership.status` here -
see `docs/DATABASE.md`'s `employee_profiles` section for why those are
two intentionally independent concepts.

**Field set depends on the caller's `EMPLOYEE_DIRECTORY_VIEW` scope**
(see the Authorization section's footnote 3 - taken literally):

| Field | `full` (Owner/Manager) | `limited` (Employee/Accountant/CustomerSupport) |
|---|---|---|
| `membership_id`, `name`, `role`, `status` | yes | yes - **and nothing else** |
| `email`, `job_title`, `joined_at` | yes | not present in the response at all |
| `department` (`{id, name}` or `null`) | yes | not present |
| `manager` (`{membership_id, name}` or `null`) | yes | not present |

**`search` matches the member's name only - never email, for any
scope.** Even for a `full`-scope caller, matching email would let
`?search=someone@example.com` returning a result confirm that address
exists in the org - an oracle the `limited` response body itself was
specifically built to prevent, so the search behavior stays uniform
regardless of who's asking rather than depending on it.

**A cross-organization `manager_membership_id` or `department_id` can
never leak a name**, even though nothing write-side validates either
field yet (no employee-profile write endpoint exists - a future task's
job): before resolving a manager's name or a department's name for
display, each lookup is re-filtered by `organization_id` rather than
trusting the ORM relationship traversal directly, so a reference that
somehow pointed outside this org just renders as `manager: null` /
`department: null` instead of showing someone else's employee or
department.

**Filters** (`department_id`, `role`, `status` - all optional, exact
match) apply regardless of scope - filtering by e.g. department doesn't
expose anything a `limited`-scope caller couldn't already reasonably
know, even though `department` isn't a field in their response.
**Pagination** uses the contract from the Pagination section above -
this is the endpoint that actually implements it. `422` on an unknown
query param, an out-of-range `page`/`per_page`, or a malformed
`department_id`.

## Employee profile & status management (FD-023)

`GET` and `PATCH /organizations/{organization_id}/employees/{membership_id}`
- `membership_id` names the *target employee's* `Membership`, not the
caller's own. Both verbs resolve the target the same way
(`get_target_membership_or_404`): a missing, cross-organization, or
inactive (status != `active`) membership is a `404`, indistinguishable
from any other reason the row can't be reached.

**`GET` - gated by `EMPLOYEE_DIRECTORY_VIEW`, same as the list
endpoint** (never `none`). Returns the directory's `full` field shape
if the caller has `full` scope **or is viewing their own profile**,
otherwise the `limited` shape - a self-view exception, since it's the
caller's own data and grants no new access to anyone else's. Reuses
the list endpoint's own cross-org-safe manager/department name
resolution (`_resolve_manager_names`/`_resolve_departments`) rather
than a separate serialization path, so this can't independently regress
the leak FD-022's review caught.

**`PATCH` - gated by a new `EMPLOYEE_MANAGE` permission** (see the
Authorization section's footnote 11): `full` for Owner, `limited` for
Manager (restricted to Employee/Accountant/CustomerSupport targets,
checked by the object-level `can_manage_employee_profile()` *after*
the target membership is fetched - the permission decorator alone only
confirms the caller's role has *some* reach, never that it reaches
this specific target), `none` for everyone else - an Employee can't
edit their own profile through this endpoint, only view it.

Body (all optional - partial update): `{"job_title"?: "...", "department_id"?:
"uuid", "manager_membership_id"?: "uuid", "status"?: "active"|"inactive"|"suspended"}`.
`job_title`/`department_id`/`manager_membership_id` accept an explicit
`null` to clear them; `status` doesn't (`422` if sent as `null`).
**Upserts** - nothing else in the codebase creates an `EmployeeProfile`
row yet (FD-022's own note), so the first `PATCH` for a membership
creates one; a later `PATCH` on the same membership updates it.
`department_id` must reference an *active* department in this
organization (`422 INVALID_DEPARTMENT` otherwise - missing, cross-org,
and inactive are all rejected the same way, never distinguishable from
each other); `manager_membership_id` must reference an *active*
membership in this organization and can't equal the target's own
`membership_id` (`422 INVALID_MANAGER_MEMBERSHIP` otherwise, covering
missing/cross-org/inactive/self-as-own-manager identically).

## Tasks (FD-026)

Centralized in `backend/app/tasks/`. Creation/retrieval only - task
assignment/reassignment is FD-027, the status workflow is FD-028,
editing and deadline validation is FD-029, comments are FD-030, and
history is FD-031, all separate future tasks. No field on this
endpoint family ever records a `TaskHistory` row yet - that starts
once FD-027/FD-028/FD-029 (the actions that actually change
something) exist.

**`POST /organizations/{organization_id}/tasks` - gated by
`TASK_CREATE_ASSIGN`** (`full` for Owner/Manager, `none` for everyone
else - resolves Section 35 open decision #8, already finalized by
FD-015). Body: `{"title": "...", "description"?: "...", "priority"?:
"low"|"medium"|"high"|"urgent", "department_id"?: "uuid", "start_date"?:
"YYYY-MM-DD", "due_date"?: "YYYY-MM-DD", "estimated_hours"?: "0.00"-"9999.99"}`.
**Deliberately does not accept `assignee_membership_id`** - FR-011
treats assignment as its own action, separate from creation (FD-027's
job); every new task starts unassigned. Nor `status` (always starts
`to_do`, the model's own default) or `actual_hours` (accrues as work
happens). `creator_membership_id` is always the caller's own
membership (`g.current_membership.id`) - never accepted from the
request body, so it can't be spoofed. `department_id`, if given, must
reference an *active* department in this organization (`422
INVALID_DEPARTMENT` otherwise - missing, cross-org, and inactive all
rejected identically, mirroring FD-023's `_validate_department`). A
basic `due_date >= start_date` sanity check applies at creation
(`422` if violated) - distinct from FD-029's later "date validation on
change," which governs *editing* an existing task's dates.

**`GET /organizations/{organization_id}/tasks` and `GET
.../tasks/{task_id}` - both gated by `TASK_VIEW_UPDATE`**, which never
grants `none` (`full` for Owner/Manager, `assigned` for Employee/
Accountant/CustomerSupport). Unlike `EMPLOYEE_DIRECTORY_VIEW`'s
`limited` cell, `TASK_VIEW_UPDATE` never restricts *fields* - every
caller who can see a task sees every one of its fields. `assigned`
scope restricts *which* tasks are visible: the list endpoint forces
the query to `assignee_membership_id == caller's own membership id`
**regardless of any `assignee_membership_id` the caller supplies** -
silently overridden, not rejected, so a non-matching filter value
never confirms or denies whether some other assignee has tasks in this
org. The single-task endpoint applies the same restriction as an
object-level check (`check_scope_allows`): a task that exists in the
caller's own organization but isn't assigned to them is `403`, not
`404` - same `can_assign_role`-style distinction already established
for membership management (exists-but-you-can't-reach-it is `403`;
missing-or-cross-organization is `404`, indistinguishable from each
other).

**Filters** (`assignee_membership_id`, `department_id`, `priority`,
`status`, `due_date_from`/`due_date_to`, `created_from`/`created_to` -
all optional; FR-014) apply regardless of scope, same reasoning as the
employee directory's own filters - a non-matching filter value simply
returns zero rows, never an error that would confirm something exists
in a different organization. `due_date_from`/`due_date_to` and
`created_from`/`created_to` are inclusive day-level ranges (`422` if
either pair is inverted). **Pagination** uses the contract from the
Pagination section above, sorted by `created_at` descending (a
judgment call - newest tasks first, the conventional default for an
issue tracker).

## Current endpoints

| Method | Path | Purpose | Added in |
|---|---|---|---|
| POST | `/api/v1/auth/register` | Create a `User` account (no session, no organization) | FD-009 |
| POST | `/api/v1/auth/login` | Verify credentials, start a session, return a CSRF token | FD-010 |
| POST | `/api/v1/auth/logout` | Destroy the session (requires session + CSRF token) | FD-010 |
| GET | `/api/v1/auth/me` | Current user's profile (no memberships yet — see below) | FD-011 |
| POST | `/api/v1/organizations` | Create a business workspace, creator becomes Owner | FD-013 |
| GET | `/api/v1/organizations` | List the caller's own organization memberships | FD-014 |
| POST | `/api/v1/organizations/{organization_id}/invitations` | Create and email an invitation | FD-016 |
| GET | `/api/v1/organizations/{organization_id}/invitations` | List every invitation for the org | FD-016 |
| DELETE | `/api/v1/organizations/{organization_id}/invitations/{invitation_id}` | Cancel a pending invitation | FD-016 |
| POST | `/api/v1/invitations/accept` | Accept an invitation by its raw token | FD-016 |
| POST | `/api/v1/organizations/{organization_id}/departments` | Create a department | FD-021 |
| GET | `/api/v1/organizations/{organization_id}/departments` | List every department for the org | FD-021 |
| PATCH | `/api/v1/organizations/{organization_id}/departments/{department_id}` | Update a department | FD-021 |
| DELETE | `/api/v1/organizations/{organization_id}/departments/{department_id}` | Deactivate a department (soft) | FD-021 |
| GET | `/api/v1/organizations/{organization_id}/employees` | Search/filter/paginate the org's employee directory | FD-022 |
| GET | `/api/v1/organizations/{organization_id}/employees/{membership_id}` | View one employee's full or limited profile | FD-023 |
| PATCH | `/api/v1/organizations/{organization_id}/employees/{membership_id}` | Update (and implicitly create) an employee's profile/status | FD-023 |
| POST | `/api/v1/organizations/{organization_id}/tasks` | Create a task (always unassigned, creator is the caller) | FD-026 |
| GET | `/api/v1/organizations/{organization_id}/tasks` | Search/filter/paginate the org's tasks (full or assigned-only scope) | FD-026 |
| GET | `/api/v1/organizations/{organization_id}/tasks/{task_id}` | View one task | FD-026 |
| GET | `/api/v1/health` | Liveness + DB connectivity check | FD-002, FD-004 |
| GET | `/api/v1/openapi.json` | This contract, as JSON | FD-007 |
| GET | `/api/v1/docs` | Interactive Swagger UI | FD-007 |

**`GET /auth/me` specifics:**
- Requires a valid session (no CSRF token needed — it's a read, not a state change)
- Returns only the profile today; no `memberships` field. The `Membership` model exists since FD-012, but adding it to this response isn't part of any assigned task yet — don't add an empty placeholder array speculatively; extend this once a task explicitly calls for it.

**`POST /organizations` specifics:**
- Requires a valid session + CSRF token (state-changing)
- Request: `{"name": "...", ...optional: logo/email/phone/address/currency/timezone/date_format}` — only `name` is required (Section 35 open decision #1, resolved with the user); `currency`/`timezone` default to `USD`/`UTC` if omitted
- Unknown/extra fields (e.g. `role`, `user_id`, `organization_id`) are rejected with `422`, not silently dropped — there's no way to specify a different owner or inject a role
- `slug` is auto-generated from `name` (collision-handled with `-2`, `-3`, ... suffixes) — not accepted in the request
- The `Organization` row and the creator's `Membership(role=owner)` row commit together in one transaction; a failure on either leaves neither persisted
- No `GET`/`PATCH /organizations/{id}` yet — Section 11.1's endpoint outline lists them, but the backlog's own Epic E02 table has no separate task for them; only creation was assigned to FD-013. Flagging this as a backlog gap rather than inventing scope.

**`GET /organizations` specifics (FD-014):**
- Requires a valid session (no CSRF token — it's a read)
- Lists only the caller's *own* memberships, each with the organization's public data, the caller's `role` in it, `status`, and `joined_at` — scoped by `g.current_user`, never by a client-supplied `user_id`/`org_id`, so there's no cross-tenant surface by construction
- A membership with status `inactive`/`suspended` still appears (with that status shown), rather than being silently filtered out — mirrors FR-009's "deactivation never deletes historical visibility," applied to membership here. This endpoint doesn't grant *access* to anything; once FD-015 (RBAC) builds org-scoped read/write endpoints, those must check `status == active` themselves — a non-active membership showing up in this list is not the same as it granting access elsewhere
- Deliberately does **not** implement listing the *members of* a given organization (`GET /organizations/{id}/members`) — that requires deciding who can see other members, which is a permissions question for FD-015, not this task

**Registration (`POST /auth/register`) specifics:**
- Request: `{"name": "...", "email": "...", "password": "..."}` — `password` is 8–128 characters, no forced complexity rules (follows NIST 800-63B rather than inventing a policy the spec doesn't specify)
- Email is normalized (trimmed, lowercased) before uniqueness is checked or stored
- Duplicate email → `409 EMAIL_ALREADY_REGISTERED`, checked via the database's own unique constraint (not a check-then-insert) so concurrent duplicate registrations can't both succeed
- Response never includes `password_hash`

**Login (`POST /auth/login`) specifics:**
- Request: `{"email": "...", "password": "..."}`
- Wrong password and unknown email return the **identical** `401 INVALID_CREDENTIALS` response — including response *timing*: the Argon2 verification always runs (against a fixed dummy hash when no account matches), so a non-existent email can't be distinguished from a wrong password by how long the request takes
- Account status (`inactive`/`suspended`) is only revealed with a specific `403 ACCOUNT_<STATUS>` once credentials are already proven correct — not before, to avoid leaking account state to a guessing attacker

See `backend/openapi.yaml` for the full machine-readable contract.
