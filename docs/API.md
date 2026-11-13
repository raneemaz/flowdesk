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

Not demonstrated on a real endpoint yet (no list endpoints exist until
FD-008+), but established here so every future list endpoint is
consistent from the start.

List endpoints accept `page` (default `1`) and `per_page` (default `20`,
max `100`) query params, plus endpoint-specific `sort` and filter params.
The response adds a `meta` object alongside `data`:

```json
{
  "success": true,
  "message": "Tasks retrieved",
  "data": [ { "id": "uuid", "title": "..." } ],
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

## Current endpoints

| Method | Path | Purpose | Added in |
|---|---|---|---|
| POST | `/api/v1/auth/register` | Create a `User` account (no session, no organization) | FD-009 |
| POST | `/api/v1/auth/login` | Verify credentials, start a session, return a CSRF token | FD-010 |
| POST | `/api/v1/auth/logout` | Destroy the session (requires session + CSRF token) | FD-010 |
| GET | `/api/v1/auth/me` | Current user's profile (no memberships yet — see below) | FD-011 |
| POST | `/api/v1/organizations` | Create a business workspace, creator becomes Owner | FD-013 |
| GET | `/api/v1/organizations` | List the caller's own organization memberships | FD-014 |
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
