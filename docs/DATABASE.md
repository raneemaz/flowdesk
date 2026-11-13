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
  (`app.models.base.TimestampMixin`).
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
are the common case everywhere from here on.

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
