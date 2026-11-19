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

## Tasks (FD-026 through FD-031, FD-033)

Centralized in `backend/app/tasks/`. Creation, retrieval, assignment/
reassignment, the status workflow, general editing, comments, and
history retrieval - the full Task & Workflow Management module (spec
Section 8 Module 3) is now built. Assignment (FD-027) was the first
action to actually record a `TaskHistory` row - creation (FD-026)
deliberately doesn't; status changes (FD-028) were the second, editing
(FD-029) the third. Comments (FD-030) don't write to `TaskHistory` at
all - a comment *is* its own record (`TaskComment`), not a change to
the task's own fields. **There is no endpoint that creates a
`TaskHistory` row directly** - FD-031 (below) is read-only by design;
every row it returns was written as a side effect of FD-027/FD-028/
FD-029's own actions.

**`is_overdue` (FD-033, FR-016)** - a computed, read-only field present
on every `Task` response (creation, list, single-task, edit, assign,
status-change), not a stored column: `true` when `due_date` has passed
**in the organization's own timezone** (`Organization.timezone`, an
IANA zone name defaulting to `"UTC"` - FD-013) and `status` is neither
`completed` nor `cancelled`; `false` in every other case, including no
`due_date` at all. "Passed" is inclusive of the due date itself - a
task due *today* isn't overdue until tomorrow, in the organization's
own local calendar. An unrecognized `timezone` value falls back to UTC
rather than erroring the request. Computed fresh on every response from
the task's current `due_date`/`status` and the organization's current
`timezone` - never cached, so completing or cancelling a task clears
`is_overdue` in that same response, and nothing about it is written to
`TaskHistory` (it isn't a field that changes by itself; it's a
real-time judgment about two fields that already do).

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

**`PATCH /organizations/{organization_id}/tasks/{task_id}/assign` -
gated by `TASK_CREATE_ASSIGN`** (same permission as creation - the
baseline matrix's "Create/assign tasks" row covers both, with no
object-level reach restriction the way `EMPLOYEE_MANAGE` has for
Manager-vs-Owner: any Owner/Manager may assign/reassign any task in
their organization). Body: `{"assignee_membership_id": "uuid" |
null}` - **required**, not optional-to-omit like the partial-update
schemas elsewhere, since this endpoint does exactly one thing and the
caller always states the intended result; `null` unassigns. Must
reference an *active* membership in this organization if non-null
(`422 INVALID_ASSIGNEE` otherwise - missing, cross-org, and inactive
all rejected identically, same pattern as `department_id` above).
`404` for a missing or cross-organization `task_id` (`get_task_or_404`,
same as the retrieval endpoints above).

**Writes a `TaskHistory` row** (`event_type: "assignee_changed"`,
`previous_value`/`new_value` as the raw assignee `membership_id`
strings or `null`, `actor_membership_id` always the caller's own
membership) - this task's own acceptance criterion ("reassignment
keeps prior assignments in history"). **Idempotent**: reassigning to
the assignee a task already has (including re-unassigning an
already-unassigned one) is a `200` no-op that writes **no** history
row, same convention `DELETE /departments/{id}`'s soft-deactivate
already established - validation still runs first, so a no-op can't
be used to skip `INVALID_ASSIGNEE` checking.

**`PATCH /organizations/{organization_id}/tasks/{task_id}/status` -
gated by `TASK_VIEW_UPDATE`**, which never grants `none`, so the real
authorization lives entirely in the service layer
(`app/tasks/service.py`'s `update_task_status`), checked in order:

1. **Object-level reach** (`check_scope_allows`, same as the
   single-task `GET`) - an `assigned`-scope caller acting on a task
   that isn't theirs is `403`, before anything else - including before
   the idempotency check below, so a non-assignee can't use a
   same-status request as a free oracle for a task's current status.
2. **Idempotent no-op** - requesting the status a task already has is
   a `200` that writes no `TaskHistory` row.
3. **Transition-graph validity** (`422 INVALID_STATUS_TRANSITION`) -
   checked for *every* caller, Owner/Manager included: FR-012's `to_do
   → in_progress → under_review → completed` happy path, plus
   `under_review → in_progress` ("managers can return tasks for
   revision" - FR-012's own words) and `* → cancelled` from any
   non-terminal status. `completed` and `cancelled` are both terminal
   - the spec states this explicitly only for `cancelled`; treating
   `completed` the same way is a judgment call (the conservative
   default for an unspecified "reopen" concept, reversible later since
   nothing about it is migration-dependent). No stage-skipping (e.g.
   `to_do → completed` directly) is legal for anyone.
4. **Role reach for *this* transition** (`403`) - only `assigned`-scope
   callers are restricted further, to the two "forward progress" moves
   an assignee drives themselves (`to_do → in_progress`, `in_progress
   → under_review`); approving (`→ completed`), returning for revision,
   and cancelling are Owner/Manager-only, grounded in spec Section
   7.2's own "View/update own assigned task" baseline-matrix row and
   `app/authz/permissions.py`'s existing comment that `TASK_VIEW_UPDATE`
   is how an employee "act[s] on tasks already assigned to them."

Body: `{"status": "to_do"|"in_progress"|"under_review"|"completed"|"cancelled"}`
- required (every task always has exactly one status; there's no
"clear it" concept the way assignment has `null`). `404` for a
missing or cross-organization `task_id`. A real transition writes a
`TaskHistory` row (`event_type: "status_changed"`, raw `previous_value`/
`new_value` status strings, `actor_membership_id` the caller) - FR-012's
"every change records actor + timestamp."

**`PATCH /organizations/{organization_id}/tasks/{task_id}` - general
editing, gated by `TASK_CREATE_ASSIGN`** (same permission as creation/
assignment, **not** `TASK_VIEW_UPDATE`'s `assigned` scope). FR-011
bundles "set deadline/priority/instructions" together with assignment
itself ("Assignment: assign/reassign, set deadline/priority/
instructions"), framing editing as the same administrative capability
as assigning a task - distinct from status progression (FD-028),
which is explicitly what the baseline matrix's "View/update own
assigned task" row means for an assignee. An Employee/Accountant/
CustomerSupport gets `403` here even when editing a task assigned to
them.

Body (partial update - only fields present are applied):
`{"title"?: "...", "description"?: "...", "priority"?: "low"|"medium"|
"high"|"urgent", "department_id"?: "uuid", "start_date"?: "YYYY-MM-DD",
"due_date"?: "YYYY-MM-DD", "estimated_hours"?: "0.00"-"9999.99",
"actual_hours"?: "0.00"-"9999.99"}`. **Never accepts
`assignee_membership_id` or `status`** - both `422` (unknown field),
steering the caller to `/assign`/`/status` instead. `title`/`priority`
reject an explicit `null` (neither is "clearable"); the rest accept
one. `department_id` is validated the same way as creation
(`422 INVALID_DEPARTMENT` for missing/cross-org/inactive).

**Date validation** checks both within the request (if `start_date`
and `due_date` are both given together, same as creation) *and*
against the task's **resulting merged state** - a request that only
changes one of the two dates is still checked against whichever one
it didn't touch (the task's existing value), `422 INVALID_DATE_RANGE`
either way. This is the one validation FD-026's creation-time check
couldn't need, since there was no existing task to merge against yet.

**History on change**: one `TaskHistory` row **per field whose stored
value actually changes** (`event_type: "<field>_changed"`, e.g.
`title_changed`, `priority_changed`) - not one row per key in the
request body. Compared *after* mutation, not before, so a value that
only differs from the current one by representation (e.g. `title`'s
own model-level whitespace-stripping) doesn't produce a spurious
history entry for a field that didn't really change. A request that
changes nothing is a `200` no-op with no history written at all, same
convention `/assign`/`/status` already established.

**`POST`/`GET /organizations/{organization_id}/tasks/{task_id}/comments`
- both gated by `TASK_VIEW_UPDATE`**, reusing `get_task`'s own
object-level reach check (404 missing/cross-organization, 403 for an
`assigned`-scope caller whose task isn't theirs) as this task's own
"access-restricted" acceptance criterion: posting or reading a task's
comments needs exactly the same access as viewing the task itself,
nothing more and nothing less - `full` scope (Owner/Manager) on any
task, `assigned` scope only on a task actually assigned to the caller.

- `POST` body: `{"body": "..."}` - required, non-blank (same
  `@validates`-backed rule as every other free-text field in this
  project). `author_membership_id` is always the caller's own
  membership, never accepted from the request body. No `attachment`
  field - same documented gap as `Task` itself (Section 10.1's
  `Attachment` entity has no backlog task yet).
- `GET` - paginated with the usual contract, ordered **chronologically,
  oldest first** (a conversation thread) - the opposite of the tasks
  list's own newest-first default, which is about triage, not reading
  a discussion in order.
- No edit or delete endpoint - FD-030's own scope is posting and
  reading comments, not revising or removing them once posted.

**`GET /organizations/{organization_id}/tasks/{task_id}/history` -
gated by `TASK_VIEW_UPDATE`**, same object-level reach check as
comments and the single-task view (`full` scope any task, `assigned`
scope only a task assigned to the caller). **Read-only by design** -
there is no corresponding `POST`; "append-only" means every row comes
from assignment/status/editing's own side effects (FD-027/FD-028/
FD-029), never a direct write through this endpoint. Paginated,
ordered **chronologically, oldest first**, same convention as
comments and `Task.history`'s own relationship ordering (FD-025). No
filters (e.g. by `event_type`) - not asked for by this task, easy to
add later if a real need shows up. Each entry is the raw
`TaskHistory` row (`event_type`, `previous_value`/`new_value` as
stored strings, `actor_membership_id`, `created_at`) - no resolved
display names, consistent with how assignment/status/editing store
these values (docs/DATABASE.md's `task_histories` section explains
why `event_type` is a plain string rather than a closed enum).

## Customers (FD-035)

Centralized in `backend/app/customers/`, all five endpoints gated by
`require_permission(Permission.CUSTOMER_MANAGE)` from the
Authorization section above (`full` for Owner/Manager/Accountant/
CustomerSupport, `none` for Employee - already finalized by FD-015,
nothing added to the matrix here). Unlike `TASK_VIEW_UPDATE`, this
permission has no scope other than `full`/`none` for any role, so
there's no per-record reach restriction to apply beyond the
`require_permission` gate itself - the same simple shape as
`DEPARTMENT_MANAGE`.

**`DELETE` is a soft archive, never a real row delete** - spec Section
10.3 rule #5 and Section 26's own acceptance criterion ("archived
customers stay linked to historical requests/invoices"). It sets
`status` to `archived`; the row survives untouched, so a future
`CustomerRequest`/`Invoice` (FD-036+) can still reference it. `PATCH`
can set `status` back to `active` (reactivation) - there's no separate
"reactivate" endpoint, same convention `DELETE /departments/{id}`
already established.

- `POST /organizations/{organization_id}/customers` - create. Body:
  `{"name": "...", "email"?: "...", "phone"?: "...", "company"?: "...",
  "address"?: "...", "notes"?: "..."}`. `name` is required and
  trimmed (a whitespace-only name is a `422`, not silently accepted);
  every other field is optional (FD-034's own judgment call - see
  `docs/DATABASE.md`'s customers section). `email`, if given, must be a
  syntactically valid address. `status` isn't accepted here - a new
  customer always starts `active`.
- `GET /organizations/{organization_id}/customers` - search, filter,
  paginate. **`search`** matches `name`/`email`/`phone`/`company` (an
  `OR` across all four, case-insensitive) - the columns FD-034's own
  model docstring indexed specifically for this; `address`/`notes` are
  never searched (free-form, not indexed). **`status`** filters to
  `active` or `archived`; omitted, the list includes both - archiving
  never hides history, same convention `list_departments`/the employee
  directory's own unfiltered `status` default already established.
  Sorted by name. **Pagination** uses the contract from the Pagination
  section above.
- `GET /organizations/{organization_id}/customers/{customer_id}` -
  view one. Same gate as the list endpoint - viewing one customer
  isn't a different capability from viewing many. `404` if the
  customer doesn't exist or belongs to a different organization.
- `PATCH /organizations/{organization_id}/customers/{customer_id}` -
  partial update. Only fields actually present in the request body are
  changed (`model_dump(exclude_unset=True)`, never a plain
  `model_dump()`) - `email`/`phone`/`company`/`address`/`notes` accept
  an explicit `null` to clear them, but `name` and `status` don't
  (neither is a "clearable" concept) and return `422` if sent as
  `null`. Same `404` behavior as `GET` for a missing/cross-tenant
  customer.
- `DELETE /organizations/{organization_id}/customers/{customer_id}` -
  archive (see above). Idempotent - archiving an already-archived
  customer is a `200` no-op, not an error. Same `404` behavior as
  `PATCH` for a missing/cross-tenant customer.

## Customer requests (FD-037)

Centralized in `backend/app/customer_requests/`. Create/retrieve,
assignment, and the status workflow, all in one task - unlike Task's
module, the backlog has no separate "request creation/retrieval" task
(FD-026's equivalent), so FD-037 bundles what FD-026/FD-027/FD-028 did
separately for tasks. Comments and history retrieval are FD-038, a
separate future task (the `RequestComment`/`RequestHistory` models
already exist from FD-036, but nothing writes or reads them yet beyond
this module's own automatic history entries).

**Every endpoint is gated by a single `require_permission(Permission.CUSTOMER_REQUEST_MANAGE)`**
(`full` for Owner/Manager/CustomerSupport, `assigned` for Employee,
`none` for Accountant - already finalized by FD-015). Unlike Task's
two-permission split (`TASK_CREATE_ASSIGN` vs `TASK_VIEW_UPDATE`),
there's only one permission here, so **creating and assigning a
request both explicitly require `full` scope** (checked in
`app/customer_requests/service.py`, not by the decorator, since
`assigned` is a real granted scope here, not `none`) - an `assigned`-scope
caller (Employee) gets `403` from creation/assignment even though the
same decorator lets them reach the list/detail/status endpoints.

**`POST /organizations/{organization_id}/customer-requests`** - create.
Body: `{"customer_id": "uuid", "title": "...", "description"?: "...",
"category"?: "...", "priority"?: "low"|"medium"|"high"|"urgent",
"due_date"?: "YYYY-MM-DD"}`. `customer_id` must reference an *active*
`Customer` in this organization (`422 INVALID_CUSTOMER` otherwise -
missing, cross-org, and archived all rejected identically) - a new
request can't be logged against an archived customer, though an
existing request stays fully usable if its customer is archived later.
Deliberately does not accept `assignee_membership_id` (FR-020's own
"assign" is a separate action) or `status` (always starts `new`).
`creator_membership_id` is always the caller's own membership, never
accepted from the request body.

**`GET /organizations/{organization_id}/customer-requests`** - search,
filter, paginate. Filters: `customer_id`, `assignee_membership_id`,
`category`, `priority`, `status`, `due_date_from`/`due_date_to`
(inclusive range, `422` if inverted) - all optional. `assigned` scope
forces the query to the caller's own requests regardless of any
`assignee_membership_id` supplied, same oracle-prevention convention
Task's own list endpoint established. Sorted by `created_at`
descending. **Pagination** uses the contract from the Pagination
section above.

**`GET /organizations/{organization_id}/customer-requests/{request_id}`**
- view one. Same object-level reach as the list endpoint
(`check_scope_allows`): a request outside the caller's `assigned`
reach is `403`, not `404` - same `can_assign_role`-style distinction
established throughout this project.

**`PATCH /organizations/{organization_id}/customer-requests/{request_id}/assign`**
- assign/reassign/unassign. Body: `{"assignee_membership_id": "uuid" |
null}` - required, `null` unassigns. `full` scope only. Must reference
an *active* membership in this organization if non-null (`422
INVALID_ASSIGNEE` otherwise). Idempotent - reassigning to the
assignee a request already has is a `200` no-op with no history
written.

**Assignment and status are not fully independent here**, unlike Task:
`assigned` is itself one of `RequestStatus`'s values (FR-019). The
*first* time a request gets a real assignee while still `new`, status
auto-advances to `assigned` too (its own `status_changed` history
entry, alongside `assignee_changed`). Reassigning a request already
past `new` never regresses its status - it's just an assignee swap.

**`PATCH /organizations/{organization_id}/customer-requests/{request_id}/status`**
- the workflow itself (FR-019: `new → assigned → in_progress →
waiting_for_customer → resolved → closed`). Body: `{"status": "...",
"resolution_notes"?: "..."}`. Checked in order:

1. **Object-level reach** - same as the detail endpoint; an
   `assigned`-scope caller acting on a request that isn't theirs is
   `403` before anything else.
2. **`resolution_notes`**, if given, is applied regardless of whether
   `status` itself changes (its own `resolution_notes_changed` history
   entry if the value actually changed) - there's no separate
   general-editing endpoint for requests to carry it instead.
3. **Idempotent no-op on status** - requesting the status a request
   already has writes no `status_changed` entry (`resolution_notes`
   may still have been applied in step 2).
4. **Transition-graph validity** (`422 INVALID_STATUS_TRANSITION`) -
   strictly linear, no skipping a stage and no backward move (FR-019
   states a single chain with no named exception, unlike Task's own
   workflow which explicitly names one backward loop and an any-state
   escape hatch - neither exists here, so neither is invented).
5. **`assigned`-scope callers are further restricted** to the two
   "forward progress" moves an assignee drives themselves (`assigned →
   in_progress`, `in_progress → waiting_for_customer`); resolving and
   closing are `full`-scope only - this task's own acceptance criterion
   ("unauthorized users can't close requests").
6. **Data integrity**: transitioning to `assigned` requires
   `assignee_membership_id` to already be set (`422
   INVALID_STATUS_TRANSITION` otherwise) - guards against reaching an
   inconsistent `status=assigned` with no actual assignee through this
   endpoint directly, bypassing `/assign`'s own auto-advance.

A real transition writes a `RequestHistory` row (`event_type:
"status_changed"`, raw `previous_value`/`new_value` status strings,
`actor_membership_id` the caller).

**`POST`/`GET /organizations/{organization_id}/customer-requests/{request_id}/comments`
- both gated by `CUSTOMER_REQUEST_MANAGE`**, reusing `get_request`'s
own object-level reach check (404 missing/cross-organization, 403 for
an `assigned`-scope caller whose request isn't theirs) as this task's
own "access-restricted" acceptance criterion - posting or reading a
request's comments needs exactly the same access as viewing the
request itself.

- `POST` body: `{"body": "..."}` - required, non-blank.
  `author_membership_id` is always the caller's own membership, never
  accepted from the request body.
- `GET` - paginated with the usual contract, ordered
  **chronologically, oldest first** (a conversation thread).
- No edit or delete endpoint - posting and reading comments only.

**"Internal comments never customer-exposed"** (this task's own
title) is satisfied by construction, not by an access-control flag:
`RequestComment` has no `is_internal` column (FD-036's own model
docstring explains why) because there is no customer-facing surface
anywhere in this backlog for a comment to ever be exposed *to* in the
first place - every comment reachable through this staff-only,
`CUSTOMER_REQUEST_MANAGE`-gated endpoint is implicitly internal.

**`GET /organizations/{organization_id}/customer-requests/{request_id}/history`
- gated by `CUSTOMER_REQUEST_MANAGE`**, same object-level reach check
as comments and the single-request view. **Read-only by design** -
there is no corresponding `POST`; every row comes from `/assign`'s and
`/status`'s own side effects (FD-037), never a direct write through
this endpoint. Paginated, ordered **chronologically, oldest first**.
Each entry is the raw `RequestHistory` row (`event_type`,
`previous_value`/`new_value` as stored strings, `actor_membership_id`,
`created_at`) - no resolved display names, same convention Task's own
history endpoint already established.

## Invoices (FD-042)

Centralized in `backend/app/invoices/`. The first task to expose any
invoice HTTP API - FD-040 built the models, FD-041 built pure
calculation functions (`app/invoices/service.py`'s
`recalculate_invoice`/`compute_line_total`/`build_line_item`) with no
routes at all. **Every endpoint is gated by a single
`require_permission(Permission.INVOICE_PAYMENT_MANAGE)`** - `full` for
Owner/Accountant, `none` (`403`) for Manager/Employee/CustomerSupport
(already finalized by FD-015). Unlike `CUSTOMER_REQUEST_MANAGE`, this
permission has no `assigned`/`limited` scope for any role, so there's
no per-record reach restriction beyond the decorator's own gate - the
same simple shape as `CUSTOMER_MANAGE`.

**Section 35 open decision #7** ("void-only vs. credit-note
corrections") was resolved with the user in favor of **credit-note-style
corrections** for an issued invoice - but that needs a new entity
beyond FD-040's schema, which is new scope outside this task's own
"lifecycle + controlled editing" title and isn't in the original
65-task backlog. **This task implements the locking half only**: once
issued, financial details are immutable here. The correction mechanism
itself is necessary follow-up work for a future task, not built now.

**`POST /organizations/{organization_id}/invoices`** - create. Body:
`{"customer_id": "uuid", "currency": "USD", "issue_date"?: "...",
"due_date"?: "...", "notes"?: "...", "payment_terms"?: "...",
"discount_type"?: "flat"|"percentage", "discount_value"?: "0.00",
"line_items"?: [{"description": "...", "quantity": "1", "unit_price":
"10.00", "tax_rate"?: "8.25"}]}`. Always starts `draft` - `status` and
`invoice_number` are never accepted. `invoice_number` is
server-generated, sequential per organization (`INV-0001`, `INV-0002`,
...) - see `docs/DATABASE.md`'s invoices section for the generation
scheme and its collision-retry. `customer_id` must reference an
*active* customer in this organization (`422 INVALID_CUSTOMER`,
identical rejection for missing/cross-org/archived - same convention
as Customer Requests). `line_items` may be empty - a Draft may
legitimately have none yet (`PATCH .../issue` is what requires at
least one). Every line item's `quantity` must be `> 0`,
`unit_price`/`tax_rate` `>= 0` (`tax_rate` also `<= 100`) - rejected at
the schema layer, not just by `recalculate_invoice`'s own downstream
checks. `subtotal`/`tax_total`/`discount_total`/`total`/each line's
`line_total` are always server-computed (FD-041) and never accepted
from the client. `discount_value` must be `>= 0`, and `<= 100` when
`discount_type` is `percentage` (`422 INVALID_DISCOUNT` either way); a
discount that would drive `total` negative is `422 NEGATIVE_TOTAL`.
`created_by` is always the caller's own membership.

**`GET /organizations/{organization_id}/invoices`** - search, filter,
paginate. Filters: `customer_id`, `status`, `due_date_from`/`due_date_to`
(inclusive range, `422` if inverted) - all optional. Sorted by
`created_at` descending. **Pagination** uses the contract from the
Pagination section above. **Before the filtered query runs, every
`sent`/`partially_paid` invoice in the organization whose `due_date`
has passed is bulk-transitioned to `overdue`** (see `docs/DATABASE.md`'s
invoices section) - so a `status=overdue` filter sees every row that's
actually overdue, not only whichever single invoice a caller happened
to `GET` individually.

**`GET /organizations/{organization_id}/invoices/{invoice_id}`** -
view one. Same overdue auto-refresh as the list endpoint, scoped to
this one invoice. `404` if the invoice doesn't exist or belongs to a
different organization.

**`PATCH /organizations/{organization_id}/invoices/{invoice_id}`** -
edit. **Draft-only** - the spec's "Important invoice rule" ("once
issued, an invoice's financial details are never silently
overwritten"): any other status is `422 INVOICE_LOCKED` regardless of
what's sent. Partial update (`model_dump(exclude_unset=True)`) - only
fields actually present are applied; `customer_id`/`currency`/
`discount_type`/`discount_value`/`line_items` may not be sent as
explicit `null` (`422` if they are), every other field accepts `null`
to clear it. `invoice_number` and `status` are never accepted - status
changes go through `/issue`/`/cancel` only. `line_items`, if present,
**replaces the entire set** (delete-orphan cascade handles the old
rows) rather than exposing separate add/remove/edit-one-line
sub-endpoints - the simplest shape that still lets a Draft be fully
reworked before issuing. Totals are unconditionally recalculated after
any change, same validation (`INVALID_CUSTOMER`/`INVALID_DISCOUNT`/
`NEGATIVE_TOTAL`) as creation.

**`GET /organizations/{organization_id}/invoices/{invoice_id}/line-items`**
- the invoice's individual line items (description/quantity/unit_price/
tax_rate/line_total), in creation order. **FD-046** - added because no
endpoint previously returned these: `InvoicePublic` only ever carried
the computed aggregates (`subtotal`/`tax_total`/...), enough for a
list/summary view but not for the invoice *editor* (this task's own
job) to show a caller what they'd previously entered. Read-only, not
paginated (an invoice's own line items never need it) - mirrors the
comments/history sub-resource pattern elsewhere in this codebase
rather than embedding the list in `InvoicePublic` itself, which would
otherwise force an N+1 query on every row of the plain `GET .../invoices`
list (which never needs this).

**`PATCH /organizations/{organization_id}/invoices/{invoice_id}/issue`**
- draft → sent, the action that locks financial details going
forward. Only legal from `draft`; requires at least one line item
(`422 EMPTY_INVOICE` otherwise). **Not idempotent** - re-issuing an
already-sent invoice is `422 INVALID_STATUS_TRANSITION`, not a no-op
(issuing is a meaningful one-time action, unlike archiving).

**`PATCH /organizations/{organization_id}/invoices/{invoice_id}/cancel`**
- → cancelled. Allowed from `draft`/`sent`/`overdue`; blocked from
`partially_paid`/`paid` (`422 INVALID_STATUS_TRANSITION`) since money
has already moved - a correction to a paid-against invoice is the
future credit-note mechanism above, never a cancellation of this one.
**Idempotent** on an already-cancelled invoice (`200` no-op, same
convention `DELETE /customers/{id}` already established), unlike
`/issue`.

## Payments (FD-043)

Centralized in `backend/app/payments/`. Both endpoints are gated by
the same `require_permission(Permission.INVOICE_PAYMENT_MANAGE)` as
Invoices - there is no separate "payment" permission in the matrix.

**Two Section 35-adjacent money decisions were resolved with the
user via `AskUserQuestion`, not guessed** (Epic E06's acceptance
criteria name both as open: "no duplicate transaction created";
"total payments can never exceed the outstanding balance absent an
approved overpayment policy"):
- **Duplicate-payment prevention uses a client-supplied
  `idempotency_key`**, not a server-side heuristic (e.g. matching
  amount/method/reference within a time window).
- **Overpayment is rejected**, not allowed - the sum of an invoice's
  recorded payments can never exceed its `total`.

**`POST /organizations/{organization_id}/invoices/{invoice_id}/payments`**
- record a payment. Body: `{"amount": "40.00", "payment_date": "...",
"method": "...", "reference"?: "...", "notes"?: "...",
"idempotency_key": "..."}`. `amount` must be `> 0`; `idempotency_key`
is **required**, not optional - an idempotency scheme only works if
every caller participates. `recorded_by` is always the caller's own
membership.

The invoice must be **payable** (`sent`/`partially_paid`/`overdue`) -
`draft` and `cancelled` are `422 INVOICE_NOT_PAYABLE`; `paid` is
excluded by the same set. The payment amount must not exceed the
invoice's current outstanding balance (`total` minus every payment
already recorded) - `422 OVERPAYMENT` otherwise. On success, the
invoice transitions to `paid` (balance reaches `0`) or
`partially_paid` (balance remains positive) in the **same transaction**
as the payment insert (NFR-006).

**Idempotency**, in order:
1. A replay with the **same** `idempotency_key` and the **same**
   `invoice_id`/`amount`/`payment_date`/`method`/`reference`/`notes`
   as an existing payment in this organization returns that original
   payment (`200`, not `201`) - no second row inserted.
2. The same key reused with **any different** detail, or against a
   **different** `invoice_id`, is `409 IDEMPOTENCY_KEY_CONFLICT` - a
   client bug, never silently accepted and never silently returning
   mismatched data.
3. A genuine **race** between two concurrent requests using the same
   brand-new key resolves the same way as (1): the loser's insert
   hits the `(organization_id, idempotency_key)` unique constraint,
   and is recovered into a `200` replay rather than a `500`.

**Response shape** (both `201` new and `200` replay): `data` is
`{"payment": {...}, "invoice": {...}, "amount_paid": "...",
"balance_due": "..."}` - the invoice and balance are included so the
caller can observe the "transactional balance update" this task's own
title promises, without a second request.

**`GET /organizations/{organization_id}/invoices/{invoice_id}/payments`**
- list, paginated, ordered **chronologically, oldest first** (a
running ledger) - same convention as comments/history lists
elsewhere. `404` if the invoice doesn't exist or belongs to a
different organization.

## Financial reports (FD-044)

Added to `backend/app/invoices/` (FR-028/FR-029) rather than a new
domain package - a financial summary is purely an aggregate view over
`Invoice`/`Payment` data already owned by this module, and the
spec's own suggested repository layout (Section 9.3) has no separate
slot for it; the broader cross-entity analytics service (tasks,
requests, employees, *and* finance together) is FD-051/FD-052's own
future `analytics` domain, not this one.

**`GET /organizations/{organization_id}/invoices/financial-summary`**
- gated by **`require_permission(Permission.FINANCIAL_REPORTS_VIEW)`**,
deliberately **not** `INVOICE_PAYMENT_MANAGE` (the permission every
other endpoint in this module uses) - FR-029 ("only Owner and
authorized financial roles see sensitive financial data") names
*financial reports* as its own restriction target. Both permissions
happen to be `full` for Owner/Accountant and `none` for everyone else
in today's matrix, but using the semantically correct one means a
future role change to either doesn't silently affect the other.

Query params: `period_start`/`period_end` (optional, must be given
**together** or not at all, `422` if only one is present or the range
is inverted) - defaults to the **current calendar month** in the
organization's own timezone when omitted. This is deliberately not
the full FR-034 date-filter taxonomy (last 7/30/90 days, arbitrary
custom ranges) - that belongs to FD-052's Analytics API; this
endpoint only overrides the one period-scoped metric below.

Response `data`:
- **`total_invoiced`** / **`total_collected`** / **`outstanding_balance`**
  - all-time cumulative, not period-scoped (FR-028's own wording
  singles out only "monthly revenue collected" as period-scoped).
  `total_invoiced` sums every invoice ever actually issued and not
  voided (`sent`/`partially_paid`/`overdue`/`paid`) - a `draft` was
  never billed, and a `cancelled` invoice is withdrawn billing, not
  revenue. `outstanding_balance` = `total_invoiced - total_collected`,
  exact rather than approximate: every `Payment` in an organization
  is necessarily attached to an invoice in that same status set (a
  payment can only ever be recorded against
  `sent`/`partially_paid`/`overdue`, per FD-043, and a full payment
  only ever advances one of those to `paid` - also in the set), so
  the two sums are always over consistent underlying invoices.
- **`overdue_invoice_count`** - computed *after* the same lazy
  overdue auto-refresh `GET .../invoices` already applies (FD-042),
  so this is never stale.
- **`monthly_revenue_collected`** - sum of `Payment.amount` where
  `payment_date` (not `created_at` - when the money was dated, not
  when the record was entered) falls within `period_start`/
  `period_end` inclusive.
- **`recent_payments`** - the latest 10 payments across the whole
  organization (not paginated/filterable - a dashboard widget, not a
  payments browser; drill into one invoice's full history via
  `GET .../invoices/{id}/payments` instead), newest first.

All four money fields are decimal strings, computed purely from
already-server-computed `Invoice.total`/`Payment.amount` - there is
no request-body total anywhere in this read-only endpoint for a
client to even attempt to override.

## Invoice PDF (FD-045)

**`GET /organizations/{organization_id}/invoices/{invoice_id}/pdf`**
- gated by the same `INVOICE_PAYMENT_MANAGE` as the plain JSON detail
view (`GET .../invoices/{invoice_id}`) - downloading the PDF isn't a
different capability from viewing the invoice. Returns
`Content-Type: application/pdf` with the raw PDF bytes (not the usual
JSON success/error envelope - a binary document, not an API resource
response); `404` if the invoice doesn't exist or belongs to a
different organization, same as the JSON detail endpoint.

Per FR-027: logo, business info, customer info, line items,
taxes/discounts, totals, and payment status (status label + amount
paid + balance due, the latter via FD-043's `get_invoice_balance`) -
rendered from `backend/app/invoices/pdf.py`'s `build_invoice_pdf_html`
(a pure HTML-string function, independently testable) and handed to
WeasyPrint by `generate_invoice_pdf`. Every value comes from
already-server-computed columns or a fresh balance query, never from
request input - there's nothing in this endpoint for a client to
submit at all.

**`organization.logo` (FD-012, a bare URL string with no
format/scheme validation at the model level) gets two independent
layers of defense before being embedded as a live image fetch
target** - a single scheme check alone isn't enough, since a
*legitimate* `http(s)` URL can still point at an internal/private
address:
1. Only an `http(s)://` URL is ever turned into an `<img>` tag at all
   (`file://`, `data:`, `javascript:`, anything else renders with no
   image).
2. A custom WeasyPrint `url_fetcher` resolves the hostname and
   refuses to fetch anything private/loopback/link-local/reserved/
   multicast/unspecified - closing the gap a tenant-security review
   found in an earlier pass of this task (a `http://169.254.169.254/...`
   cloud-metadata URL would have passed layer 1 untouched). Redirects
   are disabled entirely rather than re-validated per hop. This does
   **not** close a DNS-rebinding race (resolve-safe, then connect to a
   different IP) - a known, named residual gap, not something this
   module claims to fully solve; see `pdf.py`'s own docstring.

Every other admin/customer-supplied free-text field interpolated into
the document (customer name/company/email/phone/address, invoice
notes/payment terms, organization name/email/phone/address) is
HTML-escaped - this is a generated document, not a live page, but the
escaping is still the correct default rather than trusting any of
that text to be safe to interpolate raw.

## Activity log (FD-047)

Centralized in `backend/app/activity/`. There is no write endpoint -
every row is written as a side effect of the business action it
describes (FR-037: immutable through the normal application
interface); see `docs/DATABASE.md`'s own `activity_logs` section for
the full list of wired trigger points and the one named, deliberately
unwired gap ("role-changed").

**`GET /organizations/{organization_id}/activity`** - gated by
**`require_permission(Permission.ACTIVITY_HISTORY_VIEW)`**. Query
params: `page`/`per_page` (same pagination convention as every other
list endpoint). Response `data` is a list of
`{"id", "organization_id", "actor_membership_id", "action",
"entity_type", "entity_id", "metadata", "created_at"}` objects, newest
first.

**Scope determines which entries are visible, not which fields**
(same shape as Tasks' `assigned` scope):
- **`full`** (Owner/Manager) - every entry in the organization.
- **`own`** (Employee) - only entries where the caller themselves is
  the recorded actor.
- **`limited`** (Accountant **or** CustomerSupport) - this permission's
  one scope value means two *different* filters depending on role,
  since the baseline matrix grants both roles `limited` for different
  reasons: Accountant sees only `invoice`/`payment` entity-type
  entries; CustomerSupport sees only `customer`/`customer_request`
  entity-type entries. `app.activity.service.list_activity` takes the
  caller's role alongside the resolved scope to disambiguate, and
  fails closed (matches nothing) for any other role a future
  permissions change might grant `limited` to, rather than falling
  through to an unfiltered result.

## Notifications (FD-048/FD-049)

Centralized in `backend/app/notifications/`. These three endpoints are
the model's read/mark-read side (FR-039); see `docs/DATABASE.md`'s
`notifications` section for the full list of FD-049's wired trigger
points (task/request assignment, task/request comments, request
status changes, invoice paid) and its two named, deliberately unwired
gaps ("invitation received", "deadline approaching/overdue").

**No `Permission` gates any of these endpoints** - unlike every other
organization-scoped resource in this API, Section 7.2's baseline
matrix has no notification row. Each endpoint instead only confirms
the caller is an active member of `organization_id` (`404` for
missing/inactive/cross-tenant membership, same convention as
everywhere else) and then unconditionally scopes the result to that
membership's own id - nobody, not even Owner/Manager, can see or
mark-read another member's notifications.

**`GET /organizations/{organization_id}/notifications`** - list,
paginated, newest first. Query params: `page`/`per_page` (standard
convention) and `unread_only` (optional, default `false`) - a caller
gets their own unread count by reading `meta.total` on a request with
`unread_only=true`, rather than this task adding a separate dedicated
count endpoint. Response `data` is a list of
`{"id", "organization_id", "recipient_membership_id", "type", "title",
"body", "entity_type", "entity_id", "read_at", "created_at"}` objects.

**`PATCH /organizations/{organization_id}/notifications/{notification_id}/read`**
- mark one notification read. Idempotent (marking an already-read
notification read again changes nothing). `404` if the notification
doesn't exist *or* belongs to a different recipient - both cases are
indistinguishable to the caller, same "never confirm existence of
something you have no reach over" convention used everywhere else in
this API.

**`PATCH /organizations/{organization_id}/notifications/read-all`** -
mark every one of the caller's own unread notifications read in a
single bulk update. Response `data` is `{"updated_count": N}` (`0` if
nothing was unread). Both PATCH endpoints use `PATCH`, not the spec
outline's own literal `POST` - a deliberate judgment call for
consistency with every other idempotent state-change endpoint in this
API (Tasks' assign/status, Invoices' issue/cancel).

## Analytics (FD-051/FD-052/FD-054)

Centralized in `backend/app/analytics/`. FD-051 built the service
layer (`app/analytics/service.py`) as four deterministic, org-scoped
functions requiring already-resolved `period_start`/`period_end`
dates; FD-052 adds the four HTTP endpoints below plus the FR-034
date-filter taxonomy that resolves a named window into those dates
(`resolve_period_filter`). All four are gated by
**`require_permission(Permission.ANALYTICS_VIEW)`**; which scope each
caller gets is Section 7.2's baseline matrix (Owner/Manager `full`,
Employee `own`, Accountant `limited`, CustomerSupport `limited`), but
each endpoint below additionally restricts *which* scopes it actually
honors, per FR-030 through FR-033, not per `ANALYTICS_VIEW`'s own
scope comments - see `app/analytics/service.py`'s module docstring for
why the four categories are drawn this way, and for the deliberate,
documented gap that CustomerSupport's own `limited` grant (a
customer/request analytics subset) has no matching endpoint: no FR
asks for one, and FD-037's own `GET .../customer-requests` with its
filters already serves that role's real-time dashboard.

**Query params, shared by all four endpoints:**
- **`period`** (required) - one of `last_7_days`, `last_30_days`,
  `last_90_days`, `current_month`, `previous_month`, `custom`. The
  named windows are resolved in the organization's own timezone:
  `last_N_days` is inclusive of today (`today - (N-1)` through
  `today`); `current_month`/`previous_month` are the *full* calendar
  month (1st through last day), the same convention
  `app.invoices.service._current_month_bounds` (FD-044) already
  established for its own default - never bounded to "today" partway
  through the month.
- **`period_start`/`period_end`** - **required together, and only**
  when `period=custom` (`422` otherwise, either for `custom` missing
  either bound, or for a named `period` value given either bound at
  all - a caller never has an explicit range silently ignored in
  favor of a named one). Must not be inverted.

**`GET /organizations/{organization_id}/analytics/overview`** (FR-030)
- **`full` scope only** (Owner/Manager; `403` for every other role).
Response `data`: `employee_count`/`active_tasks`/`overdue_tasks`/
`open_requests` (current-state snapshots, not period-scoped) plus
`completed_tasks`/`monthly_invoiced`/`monthly_collected` (scoped to
the resolved period) and the resolved `period_start`/`period_end`
themselves.

**`GET /organizations/{organization_id}/analytics/employees`** (FR-031)
- **`full`** (Owner/Manager) may add `target_membership_id` to scope
to one employee, or omit it for every active employee in the org; a
`target_membership_id` that doesn't resolve to an active membership
*in this organization* is `404` (checked by the route itself before
calling the service, which would otherwise just return an empty
list - no existence oracle for a cross-tenant id either way). **`own`**
(Employee) is always silently forced to the caller's own membership,
regardless of any `target_membership_id` given - never a `403`, same
convention `GET .../tasks`' own `assigned` scope already established.
Any other scope (Accountant/CustomerSupport's `limited`) is `403`.
Response `data` is a list of `{"membership_id", "name",
"assigned_tasks", "completed_tasks", "overdue_tasks",
"completion_rate", "avg_completion_time_hours"}` - the rate/average
are `null`, never `0`, when no task was assigned/completed in the
period (no signal to report, not a fabricated zero).

**`GET /organizations/{organization_id}/analytics/departments`** (FR-032)
- **`full` scope only**. Optional `department_id` scopes to one
department, `404` if it doesn't belong to this organization (same
route-level check as above). Response `data` is a list of
`{"department_id", "department_name", "active_tasks",
"completed_tasks", "overdue_tasks", "request_volume"}` - one entry per
department (or just the one given), plus a trailing
`department_id: null` entry for genuinely department-less tasks when
no `department_id` filter was given. `request_volume` is derived via
each request's *assignee's own* department (`CustomerRequest` has no
department column of its own) and has no "unassigned" bucket of its
own - a request with no assignee, or an assignee with no employee
profile yet, isn't counted anywhere.

**`GET /organizations/{organization_id}/analytics/finance`** (FR-033)
- **`full`, or `limited` when the caller's role is Accountant**
specifically (`403` for CustomerSupport's own `limited`, and for
Employee's `own`) - the same scope-plus-role disambiguation the
Activity log's own `limited` value already needed. Response `data` is
`app.invoices.service.get_financial_summary`'s own fields
(`total_invoiced`/`total_collected`/`outstanding_balance`/
`overdue_invoice_count`/`monthly_revenue_collected`/`recent_payments`,
all-time vs. period-scoped exactly as documented in the Financial
reports section above) merged with two period-scoped fields:
`revenue_by_day` (`[{"date", "amount"}, ...]`, one entry per day that
actually had a payment - never zero-filled) and
`invoice_distribution` (`{"draft": N, "sent": N, ...}`, a count of
this organization's invoices grouped by status, issued within the
period).

### CSV/PDF export (FD-054)

Each of the four endpoints above has an `.../export` sibling taking
the exact same query params plus a required **`format`** (`csv` or
`pdf`) - same permission (`Permission.ANALYTICS_VIEW`), same
per-endpoint scope restriction, same period taxonomy, same cross-org
`404`s for `target_membership_id`/`department_id`, same `422`s for a
bad `period`/`format`. The export route is never anything but its
JSON sibling's own call sequence (query validation, period
resolution, existence check, service call) handed to
`app.analytics.export` for rendering instead of `jsonify` - no
business logic is duplicated between the two.

- **`GET .../analytics/overview/export`**, **`GET .../analytics/employees/export`**,
  **`GET .../analytics/departments/export`**, **`GET .../analytics/finance/export`**.
- Response is `text/csv` or `application/pdf` with
  `Content-Disposition: attachment; filename="<report>-<period_start>-to-<period_end>.<ext>"`.
- **CSV injection defense:** any cell whose text starts with `=`, `+`,
  `-`, `@`, a tab, or a CR is prefixed with a leading `'` before being
  written - the standard defusing prefix spreadsheet programs treat as
  "this is text, not a formula" - since a department/employee display
  name is organization-controlled free text with no character
  restriction at the model level. The CSV also starts with a UTF-8 BOM
  so Excel doesn't mis-decode a non-ASCII name.
- The Finance export's CSV/PDF has four sections (summary, revenue by
  day, invoice distribution, recent payments), mirroring the JSON
  response's own shape rather than flattening it into one table; every
  other export is a single table with the same fields as its JSON
  sibling's own `data`.
- No frontend consumes these yet - same documented gap as every other
  FD-053 sidebar entry with no FR actually asking for it; `AnalyticsPage`
  has no export button.

## AI Reporting Service (FD-055/FD-056)

**Design only - no HTTP endpoint yet.** Centralized in
`backend/app/ai/`: `providers.py` (the swappable `AIProvider`
abstraction + the one real implementation, `AnthropicProvider`),
`schemas.py` (`WeeklyReportInput`/`WeeklyReportOutput`, FR-040/
FR-042's contract), `service.py` (`generate_weekly_report`, which
ties the two together), `snapshot.py` (FD-056's
`build_weekly_metrics_snapshot`, the one producer of a concrete
`metrics_snapshot` shape). FD-057 (actual weekly summary generation),
FD-058 (persistence), FD-059 (scheduling), and FD-060 (frontend) build
on this - none of them exist yet, so there is nothing to call this
from in a real request yet.

**Weekly metrics aggregation** (`app/ai/snapshot.py`,
`build_weekly_metrics_snapshot`): combines FD-051's four already-
deterministic analytics functions (overview/employees/departments/
finance) into one JSON-serializable dict for one organization and one
already-resolved period - no new query, no new aggregation logic of
its own. Always calls them with `PermissionScope.FULL` (there is no
HTTP caller to scope to; a weekly summary is inherently org-wide, per
FR-040). `finance.recent_payments` is trimmed to `payment_date`/
`amount`/`method`/`reference` only - not `id`/`idempotency_key`/
`recorded_by`/`notes`, the same minimization FD-054's CSV/PDF export
already applied before sending payment data outside the system. Pure
and side-effect-free (no database write) - calling it twice for the
same organization+period over an unchanged database returns an
identical result, which is this task's own "idempotent" (retrying it
is always safe; the *persisted* idempotency a scheduled job needs -
never writing a duplicate `AIReport` row - is FD-058's job, since this
function writes nothing of its own to deduplicate).

This resolves spec Section 35 open decision #12 ("AI provider,
budget limits, privacy terms, and model selection"): **Anthropic's
Messages API** via plain stdlib `urllib` (no vendor SDK - same
reasoning `app/email/client.py` already used for choosing SMTP over a
vendor SDK), model configurable via `ANTHROPIC_MODEL` (default
`claude-haiku-5-5`, a cost-effective choice since this will
eventually run on a recurring per-organization schedule); **no hard
per-report budget cap**, only a bounded `AI_MAX_TOKENS` + a request
timeout (`AI_REQUEST_TIMEOUT_SECONDS`); and the AI provider **only
ever receives `WeeklyReportInput.metrics_snapshot`** - an
already-computed dict from the deterministic Analytics Service
(FD-051), never a database session, ORM object, or another
organization's data. This directly satisfies Epic E08's own
acceptance criterion ("AI never queries the database directly and
never receives another organization's data").

**Timeout/retry rules** (`complete_with_retries`): retries only
transient failures - request timeout, rate limit (429), the
provider's own 5xx/unreachable, or a 2xx reply this module couldn't
parse - with exponential backoff, up to `AI_MAX_RETRIES` (default 2).
It never retries an authentication failure (401/403) or a request
this codebase itself sent maliciously/malformed (400/422), since
retrying either can't succeed.

**Output validation** (`generate_weekly_report`): the provider's raw
text is parsed as JSON and validated against `WeeklyReportOutput` by
pydantic; any parse/validation failure raises
`AIReportGenerationError` rather than guessing or returning a partial
result - satisfying the Epic's "a failed generation never produces a
misleading 'successful' report." `period_start`/`period_end`/`model`
on the output always come from the trusted input/response metadata,
never from the AI's own response text, so a misbehaving provider
can't claim a period or model it didn't actually use.

Env vars (`.env.example`): `ANTHROPIC_API_KEY` (empty = nothing can
call `AnthropicProvider` yet - no production-startup requirement,
unlike `SMTP_HOST`, since nothing is wired to call it yet),
`ANTHROPIC_MODEL`, `AI_REQUEST_TIMEOUT_SECONDS`, `AI_MAX_RETRIES`,
`AI_MAX_TOKENS`.

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
| PATCH | `/api/v1/organizations/{organization_id}/tasks/{task_id}/assign` | Assign/reassign/unassign a task, recording history | FD-027 |
| PATCH | `/api/v1/organizations/{organization_id}/tasks/{task_id}/status` | Move a task through its status workflow, recording history | FD-028 |
| PATCH | `/api/v1/organizations/{organization_id}/tasks/{task_id}` | Edit a task's fields (not assignee/status), recording history | FD-029 |
| POST | `/api/v1/organizations/{organization_id}/tasks/{task_id}/comments` | Post a comment on a task | FD-030 |
| GET | `/api/v1/organizations/{organization_id}/tasks/{task_id}/comments` | List a task's comments, chronologically | FD-030 |
| GET | `/api/v1/organizations/{organization_id}/tasks/{task_id}/history` | List a task's history, chronologically (read-only) | FD-031 |
| POST | `/api/v1/organizations/{organization_id}/customers` | Create a customer | FD-035 |
| GET | `/api/v1/organizations/{organization_id}/customers` | Search/filter/paginate the org's customers | FD-035 |
| GET | `/api/v1/organizations/{organization_id}/customers/{customer_id}` | View one customer | FD-035 |
| PATCH | `/api/v1/organizations/{organization_id}/customers/{customer_id}` | Update a customer | FD-035 |
| DELETE | `/api/v1/organizations/{organization_id}/customers/{customer_id}` | Archive a customer (soft) | FD-035 |
| POST | `/api/v1/organizations/{organization_id}/customer-requests` | Create a customer request | FD-037 |
| GET | `/api/v1/organizations/{organization_id}/customer-requests` | Search/filter/paginate the org's customer requests | FD-037 |
| GET | `/api/v1/organizations/{organization_id}/customer-requests/{request_id}` | View one customer request | FD-037 |
| PATCH | `/api/v1/organizations/{organization_id}/customer-requests/{request_id}/assign` | Assign/reassign/unassign a request | FD-037 |
| PATCH | `/api/v1/organizations/{organization_id}/customer-requests/{request_id}/status` | Move a request through its status workflow | FD-037 |
| POST | `/api/v1/organizations/{organization_id}/customer-requests/{request_id}/comments` | Post a comment on a customer request | FD-038 |
| GET | `/api/v1/organizations/{organization_id}/customer-requests/{request_id}/comments` | List a customer request's comments, chronologically | FD-038 |
| GET | `/api/v1/organizations/{organization_id}/customer-requests/{request_id}/history` | List a customer request's history, chronologically (read-only) | FD-038 |
| POST | `/api/v1/organizations/{organization_id}/invoices` | Create a draft invoice (with line items) | FD-042 |
| GET | `/api/v1/organizations/{organization_id}/invoices` | Search/filter/paginate the org's invoices (overdue auto-refreshed first) | FD-042 |
| GET | `/api/v1/organizations/{organization_id}/invoices/{invoice_id}` | View one invoice | FD-042 |
| PATCH | `/api/v1/organizations/{organization_id}/invoices/{invoice_id}` | Edit a draft invoice (locked once issued) | FD-042 |
| GET | `/api/v1/organizations/{organization_id}/invoices/{invoice_id}/line-items` | List an invoice's individual line items | FD-046 |
| PATCH | `/api/v1/organizations/{organization_id}/invoices/{invoice_id}/issue` | Issue a draft invoice (draft → sent) | FD-042 |
| PATCH | `/api/v1/organizations/{organization_id}/invoices/{invoice_id}/cancel` | Cancel an invoice (not once a payment is recorded) | FD-042 |
| POST | `/api/v1/organizations/{organization_id}/invoices/{invoice_id}/payments` | Record a payment (idempotent, rejects overpayment) | FD-043 |
| GET | `/api/v1/organizations/{organization_id}/invoices/{invoice_id}/payments` | List an invoice's payments, chronologically | FD-043 |
| GET | `/api/v1/organizations/{organization_id}/invoices/financial-summary` | Invoiced/collected/outstanding, overdue count, monthly revenue, recent payments | FD-044 |
| GET | `/api/v1/organizations/{organization_id}/invoices/{invoice_id}/pdf` | Invoice as a PDF (logo, items, totals, payment status) | FD-045 |
| GET | `/api/v1/organizations/{organization_id}/activity` | Search/paginate the org's centralized activity log (role/scope-filtered) | FD-047 |
| GET | `/api/v1/organizations/{organization_id}/notifications` | List the caller's own notifications, paginated, optionally unread-only | FD-048 |
| PATCH | `/api/v1/organizations/{organization_id}/notifications/{notification_id}/read` | Mark one of the caller's own notifications read | FD-048 |
| PATCH | `/api/v1/organizations/{organization_id}/notifications/read-all` | Mark every one of the caller's own unread notifications read | FD-048 |
| GET | `/api/v1/organizations/{organization_id}/analytics/overview` | Org-wide overview metrics for a resolved period (full scope only) | FD-052 |
| GET | `/api/v1/organizations/{organization_id}/analytics/employees` | Per-employee performance for a resolved period (full/own scope) | FD-052 |
| GET | `/api/v1/organizations/{organization_id}/analytics/departments` | Per-department breakdown for a resolved period (full scope only) | FD-052 |
| GET | `/api/v1/organizations/{organization_id}/analytics/finance` | Financial analytics for a resolved period (full/Accountant-limited) | FD-052 |
| GET | `/api/v1/organizations/{organization_id}/analytics/overview/export` | Overview metrics as a sanitized CSV or PDF | FD-054 |
| GET | `/api/v1/organizations/{organization_id}/analytics/employees/export` | Employee performance as a sanitized CSV or PDF | FD-054 |
| GET | `/api/v1/organizations/{organization_id}/analytics/departments/export` | Department analytics as a sanitized CSV or PDF | FD-054 |
| GET | `/api/v1/organizations/{organization_id}/analytics/finance/export` | Financial report as a sanitized CSV or PDF | FD-054 |
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
