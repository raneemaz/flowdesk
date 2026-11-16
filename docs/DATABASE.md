# FlowDesk Database

Grows alongside the backlog: a new section is added whenever a task
creates or changes a model (mandatory rule #6, spec Section 32). Source
of truth for the actual schema is always the Alembic migrations under
`backend/migrations/versions/`, not this document - this is a reference,
not a substitute for reading the migration.

## Conventions (every model)

- **Primary keys:** UUID (`app.models.base.UUIDPrimaryKeyMixin`), generated
  in Python via `uuid.uuid4()` - not server-side, so it never depends on a
  Postgres extension.
- **Timestamps:** `created_at`/`updated_at`, both timezone-aware UTC
  (`app.models.base.TimestampMixin`). **One exception:** `task_histories`
  (FD-025) - an append-only audit trail has no business having an
  `updated_at` that would imply its rows can be edited after the fact,
  so it declares `created_at` alone instead.
- **Constraint/index naming:** Alembic's recommended convention
  (`ix_`/`uq_`/`ck_`/`fk_`/`pk_` prefixes), set on the shared `MetaData` in
  `app/extensions.py`.
- **Enums:** native PostgreSQL enum types via SQLAlchemy's `Enum`, always
  with `values_callable=...` so the stored value is the Python enum
  member's lowercase `.value`, not its uppercase `.name` (SQLAlchemy's
  default behavior, easy to get wrong - see `app/models/user.py`).
  **Downgrade must explicitly drop the enum type** after dropping the
  table - `op.drop_table()` does not do this, and a stale enum type blocks
  the next upgrade with `type "..." already exists`. Found and fixed in
  FD-008's migration.
- **Money:** not used yet (FD-040+); spec mandates decimal/numeric types,
  never floating point, when it is.

## Tables

### `users` (FD-008)

Global identity - not organization-scoped. Organization membership and
role live in `Membership` (FD-012+), not here.

| Column | Type | Notes |
|---|---|---|
| `id` | UUID | PK |
| `name` | varchar(255) | required, trimmed, non-empty |
| `email` | varchar(320) | required, unique, normalized to lowercase + trimmed |
| `password_hash` | varchar(255) | Argon2id via `app.security`, never plaintext |
| `status` | enum (`user_status`) | `active` / `inactive` / `suspended`; defaults to `active` |
| `created_at`, `updated_at` | timestamptz | |

**Password hashing:** Argon2id (`argon2-cffi`), chosen over Werkzeug's
built-in scrypt as the stronger, currently-recommended default (NFR-001
only requires "a modern, maintained algorithm" - doesn't pin a specific
one). `User.set_password()` / `User.verify_password()` wrap
`app.security.hash_password()` / `verify_password()` - never hash or
compare passwords anywhere else.

**`status` values are a judgment call**, not explicit in the product
spec: the spec's `Active/Inactive/Invited/Suspended` enum (FR-009) is
defined for employee/membership status, not the global `User` identity.
`invited` doesn't apply here since invitation state belongs to
`Invitation`/`Membership`. Flag this in review if it should instead
mirror the membership enum exactly.

### `organizations` (FD-012)

A business workspace. Required-field policy is Section 35 open decision
#1, resolved with explicit user sign-off: `name`/`slug` are always
required; `currency`/`timezone` are required but default (USD/UTC) so
creation is never blocked by them; everything else is optional and
fillable later in settings.

| Column | Type | Notes |
|---|---|---|
| `id` | UUID | PK |
| `name` | varchar(255) | required, trimmed, non-empty |
| `slug` | varchar(255) | required, unique, normalized to lowercase; letters/digits/hyphens only. Auto-generated from `name` by `app.organizations.service.create_organization()` (FD-013), with `-2`/`-3`/... collision handling - this model only enforces the column's own format/uniqueness invariants |
| `logo` | varchar(2048) | optional (URL) |
| `email` | varchar(320) | optional, org contact email - distinct from any `User.email` |
| `phone` | varchar(50) | optional |
| `address` | text | optional, unstructured for V1 |
| `currency` | varchar(3) | required, defaults to `'USD'`; normalized to uppercase, must be exactly 3 letters (ISO 4217 format, not validated against a real currency list) |
| `timezone` | varchar(64) | required, defaults to `'UTC'` (IANA zone name expected, not validated) |
| `date_format` | varchar(32) | optional |
| `created_at`, `updated_at` | timestamptz | |

No `owner_id` column - ownership is represented via `Membership.role ==
OWNER`, not a direct reference, matching the spec's own field list for
Organization (Section 10.1) and avoiding a redundant pointer that could
drift from the Membership table.

### `memberships` (FD-012)

Links a `User` to an `Organization` with a role. Unique on
`(organization_id, user_id)` at the DB level (`uq_memberships_organization_id_user_id`)
- a user cannot have two memberships in the same org. Both FK columns
are individually indexed (`ix_memberships_organization_id`,
`ix_memberships_user_id`) since org-scoped queries filtering by either
are the common case everywhere from here on. Also unique on
`(id, organization_id)` (`uq_memberships_id_organization_id`, FD-020) -
`id` is already unique as the PK, but Postgres still requires a unique
constraint covering the *exact* column set a composite FK references;
this is what lets `employee_profiles.(membership_id, organization_id)`
be DB-enforced against this table (see below) instead of relying on
application logic alone.

| Column | Type | Notes |
|---|---|---|
| `id` | UUID | PK |
| `organization_id` | UUID | required, FK -> `organizations.id`, `ON DELETE CASCADE` |
| `user_id` | UUID | required, FK -> `users.id`, `ON DELETE CASCADE` |
| `role` | enum (`membership_role`) | `owner` / `manager` / `employee` / `accountant` / `customer_support` - spec Section 7.1's five roles |
| `status` | enum (`membership_status`) | `active` / `inactive` / `suspended`; defaults to `active` |
| `joined_at` | timestamptz | defaults to creation time |
| `created_at`, `updated_at` | timestamptz | |

**`status` values are a judgment call** (same pattern as `User.status`):
a `Membership` row represents an already-accepted relationship, so it
doesn't need an `invited` state - that will live on the separate
`Invitation` entity (FD-016, not yet built) once it exists.

**Cascade behavior, reviewed by `tenant-security-reviewer`:** deleting
an `Organization` removes only *its own* memberships (scoped by
`organization_id`); deleting a `User` removes only *their* memberships
(scoped by `user_id`) - cascades never cross organizational boundaries,
confirmed by `test_deleting_one_organizations_membership_does_not_touch_another_organizations`.
Both relationships use `passive_deletes=True` so parent deletion relies
on the DB's `ON DELETE CASCADE` instead of SQLAlchemy loading every
child row first; `cascade="all, delete-orphan"` is kept alongside it for
explicit in-session manipulation (e.g. removing an item from
`org.memberships`).

### `invitations` (FD-016)

Fields per spec Section 10.1's Invitation entity, plus `cancelled_at` (a
judgment call - symmetric with `accepted_at` so cancellation doesn't
need its own status enum column). `status` (`pending` / `accepted` /
`cancelled` / `expired`) is a **derived property, never a stored
column** - computed from `accepted_at`/`cancelled_at`/`expires_at` so it
can never drift out of sync with the timestamps that actually define it.

| Column | Type | Notes |
|---|---|---|
| `id` | UUID | PK |
| `organization_id` | UUID | required, FK -> `organizations.id`, `ON DELETE CASCADE`, indexed |
| `email` | varchar(320) | required, normalized to lowercase + trimmed, indexed. Not unique - a cancelled/expired invitation can be followed by a new one for the same address |
| `role` | enum (`membership_role`) | **reuses** the enum type created by `memberships` (FD-012) - the migration explicitly passes `create_type=False` on this column so it neither tries to `CREATE TYPE` again (upgrade) nor drops a type `memberships` still depends on (downgrade); verified with a full downgrade/upgrade round-trip, same review step FD-008 established for enum-owning migrations |
| `token_hash` | varchar(64) | required, unique. SHA-256 hex digest of the raw token - **not** Argon2id (that's for passwords, verified one guess at a time; a token lookup needs a deterministic digest to query by by directly - the raw token's 256 bits of randomness is what makes it unguessable, not a slow hash) |
| `expires_at` | timestamptz | required; `INVITATION_EXPIRY_DAYS` (default 7) after creation |
| `accepted_at` | timestamptz, nullable | set when the invitation is accepted |
| `cancelled_at` | timestamptz, nullable | set when the invitation is cancelled - judgment call, see above |
| `inviter_id` | UUID, nullable | FK -> `users.id`, `ON DELETE SET NULL` - an invitation is organization history and must outlive the inviter's own `User` row if that's ever deleted (no such endpoint exists yet, but the schema doesn't assume one never will) |
| `created_at`, `updated_at` | timestamptz | |

**No partial-unique "one pending invitation per (org, email)" constraint.**
Enforced at the application level (check-then-insert in
`app.invitations.service.create_invitation`) rather than a DB
constraint, since "pending" depends on `expires_at > now()` - a static
partial index can't express a time-dependent predicate. This is a
documented, narrow race: two concurrent invite requests for the same
email could both succeed, leaving a harmless duplicate pending
invitation (whichever is accepted first succeeds normally; the other
stays cancellable) rather than a security issue - unlike the
email/slug-uniqueness races elsewhere in this project, which really do
need to be fully race-closed.

**Email delivery (`app/email/client.py`) is real SMTP**, not a vendor
SDK - see `backend/README.md` and `docs/API.md`'s Authorization-adjacent
Invitations section for the full rationale (Section 35 open decision
#4) and why the raw token is never returned in an API response, only
emailed.

### `departments` (FD-019)

Fields per spec Section 10.1's Department entity. Model + migration
only so far - CRUD routes/service are FD-021, a separate future task.

| Column | Type | Notes |
|---|---|---|
| `id` | UUID | PK |
| `organization_id` | UUID | required, FK -> `organizations.id`, `ON DELETE CASCADE`, indexed |
| `name` | varchar(255) | required, trimmed; **not** unique - nothing in the spec requires distinct department names within an organization |
| `description` | text, nullable | |
| `manager_membership_id` | UUID, nullable | FK -> `memberships.id`, `ON DELETE SET NULL`, indexed. Nullable because FR-008 lists "assign ... managers" as its own action separate from "create" - a department can exist before one is assigned. No ORM `relationship()` of its own, same pattern as `invitations.inviter_id` - a loose, outlive-able reference, not a core identity link |
| `status` | enum (`department_status`) | `active` / `inactive` - two states, not `membership_status`'s three; there's no "suspended department" concept anywhere in the spec. Defaults to `active` |
| `created_at`, `updated_at` | timestamptz | |

**`manager_membership_id` is not DB-constrained to the department's own
organization.** A composite FK `(manager_membership_id, organization_id)
-> memberships(id, organization_id)` was considered and rejected: a
membership and its department-manager row can be deleted together via
two independent `ON DELETE CASCADE` paths off the same `Organization`
(one through `memberships`, one through `departments`), and Postgres
doesn't guarantee which cascade fires first - a composite FK's `ON
DELETE` action would need to be `SET NULL` to tolerate that ordering,
but `organization_id` must stay `NOT NULL`, so that option doesn't
exist. Enforcing "the manager belongs to this organization" is handled
by `app/departments/service.py`'s `_validate_manager_membership` (FD-021,
`docs/API.md`'s Departments section) instead - the same pattern
`app/authz/service.py`'s `can_assign_role` already uses for a
materially identical cross-tenant check. At the model layer itself the
gap remains intentional, not an oversight -
`test_department_model_does_not_itself_block_a_manager_from_a_different_organization`
still documents and locks that in, since a future caller of the model
that bypasses the service layer would otherwise have no protection.

**Cascade behavior:** deleting an `Organization` removes only *its own*
departments (scoped by `organization_id`, `passive_deletes=True` +
`cascade="all, delete-orphan"` on `Organization.departments`, same
pattern as `memberships`/`invitations`) -
`test_deleting_one_organizations_departments_does_not_touch_another_organizations`
confirms cascades never cross organizational boundaries. Deleting a
manager's `Membership` row sets `manager_membership_id` to `NULL`
rather than deleting the department - a department is organization
history and must survive its manager leaving.

### `employee_profiles` (FD-020)

Fields per spec Section 10.1's EmployeeProfile entity, plus
`manager_membership_id` - the task's own title ("linked to membership,
department, manager") names a distinct per-employee "reports to"
reference, separate from (though often equal to) their department's
own `manager_membership_id`; FR-006 lists "manager" as its own
employee-directory column alongside "department". The directory list
API is FD-022; the single-record view/edit API (the first write path
for this table) is FD-023 - both documented in `docs/API.md`.

| Column | Type | Notes |
|---|---|---|
| `id` | UUID | PK |
| `organization_id` | UUID | required, FK -> `organizations.id`, `ON DELETE CASCADE`, indexed - **also** part of the composite FK below |
| `membership_id` | UUID | required, **unique** (`uq_employee_profiles_membership_id` - at most one profile per membership), indexed |
| `department_id` | UUID, nullable | FK -> `departments.id`, `ON DELETE SET NULL`, indexed |
| `manager_membership_id` | UUID, nullable | FK -> `memberships.id`, `ON DELETE SET NULL`, indexed |
| `job_title` | varchar(255), nullable | |
| `status` | enum (`employee_status`) | `active` / `inactive` / `suspended` - see below for why this isn't `membership_status` reused, and why there's no `invited` state despite FR-009 listing one |
| `created_at`, `updated_at` | timestamptz | |

**`status` is deliberately independent of `Membership.status`.**
`Membership.status` governs org access (can this person log in at all
- `app/authz`); `EmployeeProfile.status` governs current employment
(can this person be newly assigned work - FD-023's "deactivation
doesn't break history"). They usually move together but aren't the
same concept, and spec Section 10.1 lists "employment status" as
`EmployeeProfile`'s own column, not a reuse of `Membership`'s.

**No `invited` state**, even though FR-009 lists one: same tension
`MembershipStatus` (FD-012) already resolved identically - an
`EmployeeProfile` requires a real `membership_id`, and nothing is
"invited" yet at the point a `Membership` (and therefore an
`EmployeeProfile`) exists. That state lives entirely on the separate
`Invitation` entity (FD-016), with no corresponding row here.

**`membership_id` is DB-enforced to the correct organization - a
composite FK, not just `FK(membership_id)` alone:**
`ForeignKeyConstraint(['membership_id', 'organization_id'], ['memberships.id',
'memberships.organization_id'], ondelete='CASCADE')`, backed by
`memberships`'s new `uq_memberships_id_organization_id` constraint
(FD-020, see above). Unlike `Department.manager_membership_id`
(FD-019), this one *is* safe to make composite: the action is
`CASCADE`, not `SET NULL` - deleting the row never needs to null out a
`NOT NULL` column, so there's no ordering hazard across the multiple
`ON DELETE CASCADE` paths converging here (`organizations` ->
`employee_profiles` directly, and `organizations` -> `memberships` ->
`employee_profiles`). `test_employee_profile_organization_id_must_match_its_memberships_organization`
proves a mismatched `organization_id` is rejected outright, not just
discouraged - genuine DB-level cross-tenant protection, not merely
application logic.

**`department_id` and `manager_membership_id` are *not* DB-constrained
to this profile's own organization** - same reasoning, and same
accepted gap, as `Department.manager_membership_id` (FD-019): a
composite FK here would need `ON DELETE SET NULL`, which conflicts
with `organization_id` staying `NOT NULL`. Closed at the service layer
by FD-022 (read path: `_resolve_manager_names`/`_resolve_departments`
re-filter by `organization_id` before ever displaying a name) and
FD-023 (write path: `_validate_department`/`_validate_manager_membership`
reject a department/membership that doesn't resolve inside this exact
organization) - the same pattern `app/authz/service.py`'s
`can_assign_role` already uses -
`test_employee_profile_model_does_not_itself_block_a_manager_from_a_different_organization`
documents and locks in that the *model* not enforcing this is
intentional, not an oversight, now that the service layer does.

**Cascade behavior:** deleting a `Membership` **deletes** its
`EmployeeProfile` (`CASCADE`, not `SET NULL` - a profile has no
identity independent of its membership). Deleting a `Department` or a
manager's `Membership` only clears `department_id`/`manager_membership_id`
(`SET NULL`) - a profile is organization history and survives either.
Deleting an `Organization` removes only *its own* profiles, confirmed
by `test_deleting_one_organizations_employee_profiles_does_not_touch_another_organizations`.

### `tasks` (FD-025)

Fields per spec Section 10.1's Task entity. Model + migration only so
far - creation/retrieval, assignment, status workflow, editing,
comments, and history are FD-026 through FD-031, separate future
tasks. No `attachments` column: spec Section 10.1's separate
`Attachment` entity ("metadata for uploaded files, linked to its
entity") is its documented home, and no backlog task builds that
entity yet - a backlog gap, not an oversight here.

| Column | Type | Notes |
|---|---|---|
| `id` | UUID | PK |
| `organization_id` | UUID | required, FK -> `organizations.id`, `ON DELETE CASCADE`, indexed - **also** part of the composite FK below |
| `title` | varchar(255) | required, non-blank (`@validates`) |
| `description` | text, nullable | |
| `status` | enum (`task_status`) | `to_do` / `in_progress` / `under_review` / `completed` / `cancelled` - FR-012's workflow; default `to_do`. Transition enforcement is FD-028's job |
| `priority` | enum (`task_priority`) | `low` / `medium` / `high` / `urgent` - not enumerated anywhere in the spec (FR-010/FR-014 just say "priority"); a judgment call, the conventional four-level scheme (Jira/Linear/Asana), distinct from this *backlog's own* P0-P3 priority column. Default `medium` |
| `creator_membership_id` | UUID | required, indexed - **composite FK**, see below |
| `assignee_membership_id` | UUID, nullable | FK -> `memberships.id`, `ON DELETE SET NULL`, indexed |
| `department_id` | UUID, nullable | FK -> `departments.id`, `ON DELETE SET NULL`, indexed |
| `start_date`, `due_date` | date, nullable | `due_date` indexed (future overdue-detection queries, FD-033) |
| `estimated_hours`, `actual_hours` | numeric(6,2), nullable | decimal, not float (Section 10.3 rule #4, applied here even though hours aren't money) |
| `created_at`, `updated_at` | timestamptz | |

**`creator_membership_id` is DB-enforced to the correct organization -
a composite FK, not just `FK(creator_membership_id)` alone**, the same
technique `EmployeeProfile.membership_id` (FD-020) established:
`ForeignKeyConstraint(['creator_membership_id', 'organization_id'],
['memberships.id', 'memberships.organization_id'])`, backed by
`memberships`'s existing `uq_memberships_id_organization_id`
constraint. Unlike that one, this composite FK has **no `ON DELETE`
clause** (defaults to `RESTRICT`), not `CASCADE`: who created a task is
audit-relevant history (Section 10.3 rule #5) that must never silently
vanish or drag the task down with it - the DB refuses the delete
outright instead, confirmed by
`test_deleting_the_creators_membership_is_blocked_while_it_still_has_tasks`.
`test_task_creator_organization_id_must_match_its_memberships_organization`
proves the cross-tenant case is rejected, mirroring
`test_employee_profile_organization_id_must_match_its_memberships_organization`.

**`assignee_membership_id` and `department_id` are *not* DB-constrained
to this task's own organization** - same accepted gap, same reasoning,
as `Department.manager_membership_id` (FD-019) and
`EmployeeProfile.manager_membership_id`/`department_id` (FD-020): a
composite FK here would need `ON DELETE SET NULL`, which conflicts
with `organization_id` staying `NOT NULL`. Deferred to a future
service layer (FD-026/FD-027), same pattern as those two -
`test_task_model_does_not_itself_block_an_assignee_from_a_different_organization`
and the department equivalent document and lock in that this is
intentional. **No ORM `relationship()` attribute on either column**,
for the same "don't trust the ORM traversal" reason those two don't
have one (the lesson FD-022's tenant-security-reviewer finding already
taught this codebase once).

**Cascade behavior:** deleting an `Organization` **deletes** its tasks
(`CASCADE`). Deleting the assignee's or the task's department's
`Membership`/`Department` only clears `assignee_membership_id`/
`department_id` (`SET NULL`) - a task is organization history and
survives either. Deleting the **creator's** `Membership` is
**blocked** (`RESTRICT`) while it still has tasks - see above.

### `task_comments` / `task_histories` (FD-025)

Both are children of `tasks`, with the same dual-FK pattern
`employee_profiles.organization_id` established (FD-020):
`organization_id` is independently FK'd to `organizations.id`
(`ON DELETE CASCADE`) **and** composite-FK'd to `tasks.(id,
organization_id)` (`ON DELETE CASCADE`) via a `uq_tasks_id_organization_id`
unique constraint on `tasks` mirroring `memberships`'s own. This
DB-enforces that a comment's or history entry's `organization_id` can
never actually diverge from its parent task's real `organization_id` -
two `ON DELETE CASCADE` paths safely converge here (`organizations` ->
`task_comments`/`task_histories` directly, and `organizations` ->
`tasks` -> `task_comments`/`task_histories`), same reasoning
`employee_profiles`'s own section already covers.
`test_task_comment_organization_id_must_match_its_tasks_organization`
and its `task_histories` equivalent prove the cross-tenant case is
rejected.

| Column (`task_comments`) | Type | Notes |
|---|---|---|
| `id` | UUID | PK |
| `organization_id` | UUID | required, dual-FK'd as above, indexed |
| `task_id` | UUID | required, part of the composite FK, indexed |
| `author_membership_id` | UUID, nullable | FK -> `memberships.id`, `ON DELETE SET NULL`, indexed - a comment is history and must outlive its author's membership row, same reasoning as `Invitation.inviter_id`/`Department.manager_membership_id` |
| `body` | text | required, non-blank (`@validates`) |
| `created_at`, `updated_at` | timestamptz | |

| Column (`task_histories`) | Type | Notes |
|---|---|---|
| `id` | UUID | PK |
| `organization_id` | UUID | required, dual-FK'd as above, indexed |
| `task_id` | UUID | required, part of the composite FK, indexed |
| `actor_membership_id` | UUID, nullable | FK -> `memberships.id`, `ON DELETE SET NULL`, indexed - same reasoning as `task_comments.author_membership_id` |
| `event_type` | varchar(100), indexed | plain string, not a closed enum - FD-027/FD-028/FD-029/FD-031 (assignment, status workflow, editing, and history recording itself) haven't been built yet and are what will actually define the event taxonomy; inventing it now risks guessing wrong |
| `previous_value`, `new_value` | text, nullable | free-form - different future event types will need different shapes of "what changed" |
| `created_at` | timestamptz | **no `updated_at`** - see the Conventions section above |

**Cascade behavior (both tables):** deleting a `Task` **deletes** its
comments/history (`CASCADE` - neither has identity independent of its
task). Deleting the author's/actor's `Membership` only clears
`author_membership_id`/`actor_membership_id` (`SET NULL`) - a comment
or history entry is organization history and survives either.
`Task.comments`/`Task.history` are ORM relationships
(`cascade="all, delete-orphan"`), with `Task.history` ordered by
`created_at` (chronological, per FD-031's own task title) -
`test_task_relationship_exposes_its_history_in_chronological_order`
proves it.

### `customers` (FD-034)

Fields per spec Section 10.1's Customer entity and FR-017. Model +
migration only so far - CRUD, search, pagination, and archiving are
FD-035, a separate future task.

| Column | Type | Notes |
|---|---|---|
| `id` | UUID | PK - **also** part of the composite unique constraint below |
| `organization_id` | UUID | required, FK -> `organizations.id`, `ON DELETE CASCADE`, indexed |
| `name` | varchar(255), indexed | required, non-blank (`@validates`) - the only required field (see below) |
| `email` | varchar(320), nullable, indexed | no uniqueness constraint - unlike `users.email`, this carries no login identity |
| `phone` | varchar(50), nullable, indexed | |
| `company` | varchar(255), nullable, indexed | |
| `address` | text, nullable | not indexed - free-form, not an expected FD-035 search target, same treatment as `organizations.address` |
| `notes` | text, nullable | not indexed, same reasoning as `address` |
| `status` | enum (`customer_status`) | `active` / `archived` - exists now so FD-036's `CustomerRequest`/future `Invoice` rows can reference an archived customer (Section 26's "archived customers stay linked to historical requests/invoices"); default `active` |
| `created_at`, `updated_at` | timestamptz | |

**Required-vs-optional is a judgment call** (not a Section 35 open
decision): FR-017 marks only `company`/`address` "(opt.)", but nothing
here rides on customer contact info the way `users.email` rides on
login identity - a real small-business customer record routinely has
only a phone *or* only an email on file. Only `name` is required,
held to the same non-blank bar as every other named entity
(`users.name`, `departments.name`, `tasks.title`).

**`name`/`email`/`phone`/`company` are indexed** - the task's own
title calls out "search indexes" explicitly, unlike the model-only
tasks before it (FD-019/FD-020/FD-025), anticipating FD-035's search.
Plain B-tree indexes, consistent with this codebase's existing
convention (e.g. `users.email`) - no trigram/GIN indexing is used
anywhere in this project, so none is introduced here either.

**`UniqueConstraint(id, organization_id)`** - the same forward-looking
composite key `tasks` (FD-025) and `employee_profiles` (FD-020) each
added before *their* first org-scoped child table existed. FD-036's
`CustomerRequest` will compose a same-organization-enforcing FK against
this pair, the same way `task_comments`/`task_histories` do against
`tasks`. `test_customer_id_organization_id_pair_must_be_unique` checks
the constraint is actually declared.

**Cascade behavior:** deleting an `Organization` **deletes** its
customers (`CASCADE`) -
`test_deleting_an_organization_cascades_to_its_customers` and the
cross-tenant-isolation equivalent prove it.

### `customer_requests` (FD-036)

Fields per spec Section 10.1's CustomerRequest entity and FR-018.
Model + migration only so far - workflow enforcement, assignment, and
comments/history recording are FD-037/FD-038, separate future tasks.

| Column | Type | Notes |
|---|---|---|
| `id` | UUID | PK - **also** part of the composite unique constraint below |
| `organization_id` | UUID | required, FK -> `organizations.id`, `ON DELETE CASCADE`, indexed - **also** part of both composite FKs below |
| `customer_id` | UUID | required, indexed - **composite FK**, see below |
| `title` | varchar(255) | required, non-blank (`@validates`) |
| `description` | text, nullable | |
| `category` | varchar(255), nullable, indexed | free-form, not an enum - FR-018 never implies a fixed set, and FlowDesk is meant to be generic across industries (Section 1); indexed anyway as a filterable facet, unlike `description`/`resolution_notes` |
| `status` | enum (`request_status`) | `new` / `assigned` / `in_progress` / `waiting_for_customer` / `resolved` / `closed` - FR-019's workflow; default `new`. Transition enforcement is FD-037's job |
| `priority` | enum (`request_priority`) | `low` / `medium` / `high` / `urgent` - a judgment call like `task_priority`, kept as its own distinct enum type rather than reusing it (this codebase's convention: one enum per model, e.g. `customer_status` vs `department_status`). Default `medium` |
| `creator_membership_id` | UUID | required, indexed - **composite FK**, see below |
| `assignee_membership_id` | UUID, nullable | FK -> `memberships.id`, `ON DELETE SET NULL`, indexed |
| `due_date` | date, nullable | indexed |
| `resolution_notes` | text, nullable | |
| `created_at`, `updated_at` | timestamptz | |

No `department_id` - unlike `tasks`, FR-018 never lists a department
field for a request.

**`creator_membership_id` is DB-enforced to the correct organization -
a composite FK**, identical technique and reasoning to
`tasks.creator_membership_id` (FD-025): `RESTRICT` (no `ON DELETE`
clause), since who created a request is audit-relevant history that
must never silently vanish or drag the request down with it. Shortened
to `fk_customer_requests_creator_membership_id_organization_id`
(dropping the usual `..._memberships` suffix) - the full name exceeds
Postgres's 63-byte identifier limit once combined with this table's
own (longer) name.

**`customer_id` is also DB-enforced to the correct organization - a
second composite FK**, against `customers.(id, organization_id)` via
that table's own `uq_customers_id_organization_id` constraint (FD-034,
built specifically for this). Also `RESTRICT`: `customer_id` is
`NOT NULL` (every request belongs to exactly one customer), so `CASCADE`
would silently delete request history the moment a `customers` row was
removed (Section 10.3 rule #5's "never cascade-delete... audit
history"), and `SET NULL` isn't possible for a required column. In
practice a `customers` row is never hard-deleted by this app (FD-035's
`DELETE` only archives it), so this mostly guards a hypothetical direct
deletion - but it's exactly what Section 26's acceptance criterion
("archived customers stay linked to historical requests") requires.
`test_deleting_the_customer_is_blocked_while_it_still_has_requests`
proves it.

**`assignee_membership_id` is *not* DB-constrained to this request's
own organization** - same accepted gap as `tasks.assignee_membership_id`
(FD-025): a composite FK here would need `ON DELETE SET NULL`, which
conflicts with `organization_id` staying `NOT NULL`. Deferred to a
future service layer (FD-037), same pattern. **No ORM `relationship()`
attribute**, for the same "don't trust the ORM traversal" reason.

**Cascade behavior:** deleting an `Organization` **deletes** its
customer requests (`CASCADE`). Deleting the assignee's `Membership`
only clears `assignee_membership_id` (`SET NULL`) - a request is
organization history and survives it. Deleting the **creator's**
`Membership`, or the **customer** itself, is **blocked** (`RESTRICT`)
while either still has requests - see above.

### `request_comments` / `request_histories` (FD-036)

Both are children of `customer_requests`, with the exact same shape
and dual-FK pattern as `task_comments`/`task_histories` against
`tasks` (FD-025): `organization_id` is independently FK'd to
`organizations.id` (`ON DELETE CASCADE`) **and** composite-FK'd to
`customer_requests.(id, organization_id)` (`ON DELETE CASCADE`), so
a comment's or history entry's `organization_id` can never actually
diverge from its parent request's real `organization_id`. Both
composite FK names are shortened to
`fk_request_comments_request_id_organization_id` and
`fk_request_histories_request_id_organization_id` respectively (same
63-byte-limit reasoning as `customer_requests.creator_membership_id`
above).
`test_request_comment_organization_id_must_match_its_requests_organization`
and its `request_histories` equivalent prove the cross-tenant case is
rejected.

| Column (`request_comments`) | Type | Notes |
|---|---|---|
| `id` | UUID | PK |
| `organization_id` | UUID | required, dual-FK'd as above, indexed |
| `request_id` | UUID | required, part of the composite FK, indexed |
| `author_membership_id` | UUID, nullable | FK -> `memberships.id`, `ON DELETE SET NULL`, indexed - a comment is history and must outlive its author's membership row |
| `body` | text | required, non-blank (`@validates`) |
| `created_at`, `updated_at` | timestamptz | |

No `is_internal` column - unlike the hint in FD-038's own task title
("internal comments never customer-exposed"), there's no
customer-portal concept anywhere in this backlog for a comment to ever
be exposed *to* in the first place, so every comment here is
implicitly internal; access restriction itself is FD-038's job, not
this model-only task's.

| Column (`request_histories`) | Type | Notes |
|---|---|---|
| `id` | UUID | PK |
| `organization_id` | UUID | required, dual-FK'd as above, indexed |
| `request_id` | UUID | required, part of the composite FK, indexed |
| `actor_membership_id` | UUID, nullable | FK -> `memberships.id`, `ON DELETE SET NULL`, indexed |
| `event_type` | varchar(100), indexed | plain string, not a closed enum - FD-037/FD-038 haven't been built yet and are what will actually define the event taxonomy |
| `previous_value`, `new_value` | text, nullable | free-form |
| `created_at` | timestamptz | **no `updated_at`** - see the Conventions section above |

**Cascade behavior (both tables):** deleting a `CustomerRequest`
**deletes** its comments/history (`CASCADE` - neither has identity
independent of its request). Deleting the author's/actor's
`Membership` only clears `author_membership_id`/`actor_membership_id`
(`SET NULL`). `CustomerRequest.comments`/`.history` are ORM
relationships (`cascade="all, delete-orphan"`), with `.history`
ordered by `created_at` (chronological) -
`test_request_relationship_exposes_its_history_in_chronological_order`
proves it.

### `invoices` (FD-040/FD-041/FD-042)

Fields per spec Section 10.1's Invoice entity and FR-023. Model,
migration, calculations, and now the status lifecycle + controlled
editing (FD-042) - payments (FD-043) are still a separate future task.

| Column | Type | Notes |
|---|---|---|
| `id` | UUID | PK - **also** part of the composite unique constraint below |
| `organization_id` | UUID | required, FK -> `organizations.id`, `ON DELETE CASCADE`, indexed - **also** part of both composite FKs below |
| `customer_id` | UUID | required, indexed - **composite FK**, see below |
| `invoice_number` | varchar(50), indexed | required, non-blank (`@validates`) - unique **per organization**, not globally, see below. Server-generated by FD-042's `create_invoice` (`INV-0001`, `INV-0002`, ... - sequential per organization, counting every invoice ever created including cancelled ones so a number is never reused); never client-supplied |
| `status` | enum (`invoice_status`) | `draft` / `sent` / `partially_paid` / `paid` / `overdue` / `cancelled` - FR-025's six values verbatim; default `draft`. FD-042 implements `draft -> sent` (`issue_invoice`, requires >=1 line item, not idempotent) and `-> cancelled` (`cancel_invoice`, blocked once `partially_paid`/`paid`, idempotent); `sent`/`partially_paid -> overdue` is a bulk, lazily-applied auto-transition (see below); `-> partially_paid`/`-> paid` is FD-043's job entirely, driven by actual payment math, never a generic status-PATCH |
| `issue_date`, `due_date` | date, nullable | `due_date` indexed. Nullable - a Draft invoice may have neither set yet |
| `currency` | varchar(3) | required, no default - always explicitly supplied by whichever service layer creates an invoice. FD-042 added a `@validates("currency")` normalizing case and enforcing the ISO 4217 shape, mirroring `Organization.currency`'s own - added once this column got its first real write path |
| `subtotal`, `tax_total` | numeric(12,2) | required, default `0.00` - never `NULL` (Section 10.3 rule #4); recomputed from `line_items` by `app.invoices.service.recalculate_invoice` (FD-041) |
| `discount_type` | enum (`discount_type`) | `flat` / `percentage` (FD-041) - the *input*: how `discount_value` is interpreted. Default `flat` |
| `discount_value` | numeric(12,2) | required, default `0.00` (FD-041) - the *input*: a flat currency amount, or a percentage of `subtotal`, depending on `discount_type`. Must not be negative - `recalculate_invoice` rejects it with `422 INVALID_DISCOUNT` |
| `discount_total` | numeric(12,2) | required, default `0.00` - the *output*: always a flat currency amount regardless of `discount_type`, recomputed by `recalculate_invoice` |
| `total` | numeric(12,2) | required, default `0.00` - `subtotal + tax_total - discount_total`; `recalculate_invoice` rejects a result `< 0` with `422 NEGATIVE_TOTAL` rather than clamping |
| `notes` | text, nullable | |
| `payment_terms` | varchar(255), nullable | e.g. "Net 30" |
| `created_by` | UUID | required, indexed - **composite FK**, see below |
| `created_at`, `updated_at` | timestamptz | |

**Section 35 open decision #6 (tax/discount rounding) is resolved by
FD-041, at the user's explicit direction** (not a judgment call):
discount supports **both** a flat amount and a percentage of
`subtotal` (`discount_type`/`discount_value`, new in FD-041); per-line
tax amounts are summed at **full decimal precision** across all line
items and only the **final sum** is rounded once to 2 decimals
(`ROUND_HALF_UP`) - never rounded line-by-line before summing. See
`app/invoices/service.py` and
`test_recalculate_invoice_sums_tax_at_full_precision_before_rounding_once`,
which picks amounts where the two policies would disagree, to prove
the right one is implemented.

**Section 35 open decision #5 (multi-currency policy) is deliberately
NOT resolved** - the `currency` column is a schema choice that holds
regardless of which policy a future task enforces (e.g. restricting
invoices to the organization's own currency); the calculation logic is
currency-agnostic.

**Section 35 open decision #7 (void-only vs. credit-note corrections)
is resolved by FD-042, at the user's explicit direction, in favor of
credit-note-style corrections** - but building that entity is new
scope beyond FD-042's own "lifecycle + controlled editing" title and
isn't in the original 65-task backlog, so FD-042 implements only the
*locking* half: once an invoice leaves `draft`, `app.invoices.service.update_invoice`
rejects any edit with `422 INVOICE_LOCKED`, and neither `issue_invoice`
nor `cancel_invoice` ever touches a financial column, only `status`.
The correction mechanism itself (a `CreditNote`-like entity) is
necessary follow-up work for a future task, not built here. `cancelled`
(FR-025) remains the only terminal outcome this task implements, and
it's blocked once a payment has been recorded (`partially_paid`/`paid`) -
money that has already moved is never undone by a plain cancel.

**`created_by` and `customer_id` are both DB-enforced to the correct
organization - composite FKs**, identical technique and `RESTRICT`
reasoning to `customer_requests.creator_membership_id`/`customer_id`
(FD-036): who created an invoice, and which customer it belongs to,
are both audit-relevant financial history that must never silently
vanish - Section 10.3 rule #5 names financial history explicitly as
needing this protection, even more so than a support request.
`test_deleting_the_creators_membership_is_blocked_while_it_still_has_invoices`
and `test_deleting_the_customer_is_blocked_while_it_still_has_invoices`
prove it; the cross-tenant equivalents for both prove the composite
FKs actually enforce same-organization integrity, not just referential
integrity.

**`invoice_number` uniqueness is organization-scoped, not global** -
`UniqueConstraint(organization_id, invoice_number)`, this task's own
title ("unique invoice number per org"), mirroring `memberships`'s own
org-scoped uniqueness pattern (FD-012).
`test_invoice_number_is_unique_per_organization` and
`test_invoice_number_can_repeat_across_different_organizations` prove
both halves. **Generation** (FD-042, `app.invoices.service._generate_invoice_number`):
a flat sequential counter per organization (`INV-0001`, `INV-0002`,
...), simpler than the `INV-2026-0001` year-based example floated
above - nothing requires year-based numbering. `create_invoice` retries
on a uniqueness race (two concurrent creates computing the same
candidate before either commits) by constructing a fresh `Invoice`
with the next candidate number and flushing, catching `IntegrityError`
and rolling back before retrying - the same shape as
`app.organizations.service.create_organization`'s slug-collision
retry.

**The overdue auto-transition** (FD-042, `app.invoices.service._refresh_overdue_invoices`):
unlike `Task`'s own overdue detection (FD-033), which layers a
*computed*, read-only `is_overdue` flag on top of a status that has no
such value, `overdue` here **is** one of `InvoiceStatus`'s six real
stored values (FD-040) - so this actually transitions and persists
`status`. Applied as a bulk `UPDATE` across the whole organization
(`status IN (sent, partially_paid) AND due_date < today`, `today`
computed in the organization's own timezone, mirroring
`app.tasks.service._today_in_timezone`) before every
list/get read, rather than a per-row Python loop - so a `status=overdue`
filter on the list endpoint sees every row that's actually overdue,
not only whichever single invoice a caller happened to fetch
individually. This substitutes for the "scheduled daily" background
job spec Section 14 names, until that scheduler actually exists - the
same bootstrapping rationale FD-033 already established for Task.

**Cascade behavior:** deleting an `Organization` **deletes** its
invoices (`CASCADE`). Deleting the **creator's** `Membership`, or the
**customer** itself, is **blocked** (`RESTRICT`) while either still
has invoices - see above.

### `invoice_line_items` / `payments` (FD-040/FD-043)

Both are children of `invoices`, with the exact same dual-FK pattern
as `request_comments`/`request_histories` against `customer_requests`
(FD-036): `organization_id` is independently FK'd to `organizations.id`
(`ON DELETE CASCADE`) **and** composite-FK'd to `invoices.(id,
organization_id)` (`ON DELETE CASCADE`), so neither table's
`organization_id` can ever actually diverge from its parent invoice's
real one.
`test_line_item_organization_id_must_match_its_invoices_organization`
and its `payments` equivalent prove the cross-tenant case is rejected.

| Column (`invoice_line_items`) | Type | Notes |
|---|---|---|
| `id` | UUID | PK |
| `organization_id` | UUID | required, dual-FK'd as above, indexed |
| `invoice_id` | UUID | required, part of the composite FK, indexed |
| `description` | varchar(500) | required, non-blank (`@validates`) |
| `quantity` | numeric(10,2) | required, no default - a line item's whole reason to exist is to carry a priced amount |
| `unit_price` | numeric(12,2) | required, no default |
| `tax_rate` | numeric(5,2), nullable | a percentage (e.g. `8.25` = 8.25%) - the one field FR-024 itself marks "(opt.)" |
| `line_total` | numeric(12,2) | required, no default - computed by FD-041, never left for the DB to infer |
| `created_at`, `updated_at` | timestamptz | |

| Column (`payments`) | Type | Notes |
|---|---|---|
| `id` | UUID | PK |
| `organization_id` | UUID | required, dual-FK'd as above, indexed |
| `invoice_id` | UUID | required, part of the composite FK, indexed |
| `amount` | numeric(12,2) | required, no default - validated by FD-043 (`app.payments.service.record_payment`): must be `> 0`, and the sum of an invoice's payments can never exceed `invoices.total` (overpayment rejected, `422 OVERPAYMENT` - the user's explicit direction over allowing it) |
| `payment_date` | date | required |
| `method` | varchar(50) | required, non-blank (`@validates`) - plain string, not a closed enum, same "no implied fixed set" reasoning as `customer_requests.category` (FD-036) |
| `reference` | varchar(255), nullable | e.g. a check/transaction number - FR-026's own "(opt.)" field |
| `notes` | text, nullable | |
| `idempotency_key` | varchar(255) | required, non-blank (`@validates`) - **FD-043**. Client-supplied, at the user's explicit direction over a server-side duplicate-detection heuristic - satisfies Section 13's mandatory "duplicate payment request -> no duplicate transaction created" scenario. Unique **per organization** (`UniqueConstraint(organization_id, idempotency_key)`, not per-invoice) - see below |
| `recorded_by` | UUID | required, indexed - **composite FK**, see below |
| `created_at`, `updated_at` | timestamptz | |

**`recorded_by` is DB-enforced to the correct organization - a
composite FK**, identical technique and `RESTRICT` reasoning to
`invoices.created_by` above - who recorded a payment is itself
audit-relevant financial history.
`test_deleting_the_recorders_membership_is_blocked_while_it_still_has_payments`
proves it.

**Idempotency (FD-043, resolved with the user rather than guessed):**
`record_payment` looks up an existing `Payment` by `(organization_id,
idempotency_key)` before doing anything else. A match with the *same*
`invoice_id`/`amount`/`payment_date`/`method`/`reference`/`notes` is a
genuine retry - the original row is returned (`200`), no second row
inserted. A match with any different field, or a different
`invoice_id`, is a client bug (reusing a key for a materially
different request) - rejected as `409 IDEMPOTENCY_KEY_CONFLICT`,
never silently accepted or silently returning mismatched data. A
race between two *concurrent* requests using the same brand-new key is
resolved the same way: the loser's `INSERT` raises `IntegrityError` on
the unique constraint, which is caught, rolled back, and resolved by
re-fetching and returning the winner's row.

**Overpayment and the status transition are protected against a
*different* race** (two concurrent requests against the same invoice
using two different, individually-valid idempotency keys - the unique
constraint above only catches a *repeated* key): `record_payment`
re-fetches the invoice with `SELECT ... FOR UPDATE`
(`app.invoices.service.get_invoice_or_404(..., for_update=True)`)
immediately before the balance check, so a second concurrent request
against the same invoice blocks until the first commits, then
re-reads the now-current balance rather than racing against a stale
one. Every exit path after that lock is acquired - success or a
business-rule `APIError` - explicitly commits or rolls back before
returning; a plain `raise` would otherwise leave the lock held on an
open transaction, which the financial-integrity-reviewer's second pass
caught by way of its *effect* (a later test's cleanup DELETE
blocking indefinitely) rather than the row-lock reasoning itself.

**A payment may only be recorded against a *payable* invoice**
(`status` in `sent`/`partially_paid`/`overdue`) - `draft` (never
issued) and `cancelled` (voided) are rejected with `422
INVOICE_NOT_PAYABLE`; `paid` is excluded by the same set (its balance
is already `0`, so this also reads as a clearer error than relying on
the overpayment check alone). A successful payment transitions
`invoices.status` to `paid` once the new balance reaches `0`, else
`partially_paid` - computed arithmetically
(`balance_due - amount`), not by re-querying `invoice.payments`, and
committed together with the `Payment` insert in one transaction
(NFR-006). If the invoice was `overdue`, the next lazy overdue
refresh (FD-042) re-applies `overdue` on top of `partially_paid` if
`due_date` is still in the past - the two concerns compose without
either needing to know about the other.

**Cascade behavior (both tables):** deleting an `Invoice` **deletes**
its line items/payments (`CASCADE` - neither has identity independent
of its invoice). `Invoice.line_items`/`.payments` are ORM relationships
(`cascade="all, delete-orphan"`). No `updated_at`-free append-only
treatment here (unlike `task_histories`/`request_histories`) - both
tables use the standard `TimestampMixin`, since a line item or a
recorded payment, unlike a history entry, isn't itself an audit-trail
row describing a change to something else.

**FD-044's financial summary** (`GET .../invoices/financial-summary`,
`app.invoices.service.get_financial_summary`) is a pure read-time
aggregation over these two tables - no new column or table of its
own. It leans directly on the status reasoning above: every `Payment`
row's invoice is, by construction, in one of the statuses a payment
can ever be recorded against (`sent`/`partially_paid`/`overdue`) or
the one a full payment advances it to (`paid`) - all four are
"ever billed" statuses - so `outstanding_balance` can be computed as
a plain `total_invoiced - total_collected` subtraction of two
independently-summed totals, exactly, rather than needing to sum each
invoice's own `(total - amount_paid)` individually. See
`docs/API.md`'s Financial reports section for the full field list.
