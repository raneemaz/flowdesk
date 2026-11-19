# FlowDesk Backend

Flask API for FlowDesk. Domain modules (auth, organizations, employees,
tasks, etc.) are added incrementally per the backlog in
[`docs/FlowDesk_Specification.md`](../docs/FlowDesk_Specification.md);
the application skeleton, database connection, migration pipeline, API
documentation infra, auth (model, registration, login/logout,
current-user), organizations (model, creation, listing caller's own
memberships), centralized RBAC (permission definitions, decorator,
object-level membership checks), and employee invitations (secure
expiring tokens, real SMTP email delivery, acceptance, cancellation)
exist so far (FD-002, FD-004, FD-005, FD-007, FD-008, FD-009, FD-010,
FD-011, FD-012, FD-013, FD-014, FD-015, FD-016). No GET/PATCH for a
single organization, and no "list members of an org" endpoint - neither
is part of any assigned task yet (see docs/API.md). FD-016 is RBAC's
first real consumer; see docs/API.md's Invitations section.

## Structure

```
backend/
  wsgi.py              Entry point (`app = create_app()`)
  openapi.yaml          Hand-maintained API contract (OpenAPI 3.0.3)
  app/
    __init__.py        Application factory, blueprint registration
    config.py           Per-environment config (FLASK_ENV: development/testing/production);
                          loads .env and reads env vars fresh per create_app() call
    extensions.py         SQLAlchemy + Flask-Migrate + Flask-Session instances, naming convention
    errors.py            APIError + central error handlers (hybrid envelope) + WSGI safety net +
                            validation_error_details() shared by every pydantic-validated route
    security.py            Password hashing (Argon2id) - see docs/DATABASE.md
    models/                SQLAlchemy models (see docs/DATABASE.md for the schema)
    auth/                   schemas.py, service.py, decorators.py (login_required, csrf_protect), routes.py:
                              POST /api/v1/auth/register, /login, /logout; GET /me
    organizations/           schemas.py, service.py (create_organization - slug generation, transactional
                              Owner Membership; list_user_memberships), routes.py:
                              POST /api/v1/organizations, GET /organizations
    authz/                   permissions.py (Permission, PermissionScope, ROLE_PERMISSIONS matrix),
                              service.py (get_active_membership_or_404, check_scope_allows, can_assign_role,
                              can_invite_with_role), decorators.py (require_permission) - see docs/API.md's
                              Authorization section
    invitations/             schemas.py, service.py (create_invitation, list_invitations, cancel_invitation,
                              accept_invitation), routes.py: POST/GET /organizations/{id}/invitations,
                              DELETE .../invitations/{id}, POST /invitations/accept
    email/                   client.py (send_email - real SMTP, dev-logs when SMTP_HOST is unset)
    health/              GET /api/v1/health (liveness + DB connectivity status)
    docs/                 GET /api/v1/openapi.json, GET /api/v1/docs (Swagger UI)
  migrations/            Alembic migration environment (flask db <cmd>)
  tests/                 Pytest suite
```

## Database

Requires a running PostgreSQL instance. `DATABASE_URL` (dev) and
`TEST_DATABASE_URL` (test) in `.env` point to separate databases so test
runs never touch dev data. Connection pooling (`pool_pre_ping`, `pool_size`,
`max_overflow`, `pool_recycle`) is configured via `SQLALCHEMY_ENGINE_OPTIONS`
in `app/config.py`, tunable via the `DB_POOL_SIZE` / `DB_MAX_OVERFLOW` env
vars.

Local dev database setup (once, on a local PostgreSQL install — or use
`docker compose up` from the project root instead, see the root README):

```sql
CREATE ROLE flowdesk LOGIN PASSWORD '...';
CREATE DATABASE flowdesk_dev OWNER flowdesk;
CREATE DATABASE flowdesk_test OWNER flowdesk;
```

Then set `DATABASE_URL` / `TEST_DATABASE_URL` in `.env` (scheme
`postgresql+psycopg://`, matching the `psycopg` v3 driver in
`requirements.txt`) accordingly.

## Migrations

Alembic via Flask-Migrate, rooted at `migrations/`. Constraints and
indexes get deterministic names from the naming convention in
`app/extensions.py` (`ix_`/`uq_`/`ck_`/`fk_`/`pk_` prefixes) so
autogenerate never produces an unnamed-constraint diff.

```bash
FLASK_APP=wsgi.py ./.venv/Scripts/python.exe -m flask db upgrade        # apply migrations
FLASK_APP=wsgi.py ./.venv/Scripts/python.exe -m flask db migrate -m "..."  # generate one from model changes
FLASK_APP=wsgi.py ./.venv/Scripts/python.exe -m flask db downgrade base    # roll back to empty
```

The baseline migration is intentionally empty; `users` (FD-008) is the
first real one. Each model-adding task produces its own migration via
`flask db migrate`, reviewed before committing — autogenerate doesn't
catch everything (e.g. column renames), and in FD-008 it generated a
`downgrade()` that doesn't clean up the Postgres native enum type it
created, which breaks a later re-upgrade (`type "..." already exists`).
Always check a generated enum-dropping migration's `downgrade()` for
this. The reverse gotcha showed up in FD-016: a *second* table (`invitations`)
reusing an already-existing native enum type (`membership_role`, owned
by `memberships`) makes autogenerate emit a plain `sa.Enum(...)` that
tries to `CREATE TYPE` it again on upgrade - fails with `type "..."
already exists`. Fixed by hand with `postgresql.ENUM(..., create_type=False)`
on that column; verified with a full downgrade/upgrade round-trip (this
also means its `downgrade()` correctly leaves the shared type alone).

## Sessions (FD-010)

Server-side, Redis-backed (Flask-Session) — decided over client-side
signed cookies per Section 35 open decision #3, so logout and account
suspension can actually revoke a session immediately rather than waiting
for a cookie to expire client-side. Full rationale and the CSRF/session-
fixation details are in [`docs/API.md`](../docs/API.md)'s Authentication
section and the docstrings in `app/auth/service.py`.

Relevant env vars (`.env.example`): `REDIS_URL`, `SESSION_LIFETIME_DAYS`
(default 7), `SESSION_COOKIE_SAMESITE` (default `Lax`),
`SESSION_COOKIE_SECURE` (default `false` in dev, `true` in production).
**`SESSION_COOKIE_SAMESITE`/`SECURE` will need to change at actual
deployment time** if the frontend (Vercel) and backend (Render) end up on
different registrable domains — true cross-site cookies need
`SameSite=None; Secure` plus CORS configured with credentials and an
explicit allowed origin, not the wildcard default. Not yet relevant since
hosting domains aren't chosen (Section 35 open decision #13).

**No Redis in this dev environment** (same gap as Docker in FD-006 — no
service, no binary installed here). Tests use `fakeredis` as a stand-in
so they still exercise the real Flask-Session Redis code path;
`development`/`production` always point at genuine Redis and are
**unverified here**. Confirmed this concretely: hit `/auth/login` against
the dev server without Redis running and got a clean `500
INTERNAL_SERVER_ERROR` envelope (not a leak, not a hang) - see the WSGI
safety net below. Once `docker compose up` is actually run (FD-006),
this becomes fully verifiable.

## Invitation email delivery (FD-016)

Real SMTP (`app/email/client.py`), resolving Section 35 open decision
#4 - chosen over a vendor SDK so development and production share the
exact same code path; only the `SMTP_*` env vars differ. Relevant env
vars (`.env.example`): `SMTP_HOST`/`SMTP_PORT`/`SMTP_USERNAME`/`SMTP_PASSWORD`/`SMTP_USE_TLS`,
`EMAIL_FROM_ADDRESS`, `INVITATION_EXPIRY_DAYS` (default 7). The invite
link's base URL reuses `FRONTEND_ORIGIN` rather than adding a second,
near-duplicate "where's the frontend" variable.

**No real SMTP server in this dev environment** (same gap as
Docker/Redis elsewhere in this project). `SMTP_HOST` empty means
`send_email` logs the message instead of opening a socket - this is
also what `TestingConfig` forces regardless of a real value in `.env`,
so the test suite never attempts a network send. `ProductionConfig`
refuses to start without `SMTP_HOST` set (`app/__init__.py`). A failed
send never rolls back the invitation row - see `docs/API.md`'s
Invitations section.

## AI reporting service (FD-055/FD-056)

`app/ai/` - design only, no HTTP endpoint yet (FD-057/058/059 build
the real pipeline on top of this). `providers.py` defines the
swappable `AIProvider` abstraction plus the one real implementation,
`AnthropicProvider` (plain stdlib `urllib`, not the vendor SDK - same
reasoning as the SMTP-over-vendor-SDK choice above) and its own
timeout/retry rules (`complete_with_retries`); `schemas.py` defines
the weekly-report input/output contract (`WeeklyReportInput`/
`WeeklyReportOutput`); `service.py`'s `generate_weekly_report` ties
them together; `snapshot.py`'s `build_weekly_metrics_snapshot`
(FD-056) combines FD-051's four analytics functions into one
JSON-serializable `metrics_snapshot` dict for one organization/period
- a pure, side-effect-free function (retrying it is always safe;
there's nothing of its own to deduplicate). Resolves Section 35 open
decision #12: Anthropic Claude API, no hard budget cap beyond a
bounded `AI_MAX_TOKENS` + `AI_REQUEST_TIMEOUT_SECONDS`, and the
provider only ever sees an already-computed metrics snapshot - never
a DB session or another organization's data. See `docs/API.md`'s own
AI Reporting Service section for the full design rationale. Env vars
(`.env.example`): `ANTHROPIC_API_KEY` (empty until something actually
calls this), `ANTHROPIC_MODEL`, `AI_REQUEST_TIMEOUT_SECONDS`,
`AI_MAX_RETRIES`, `AI_MAX_TOKENS`.

## Error handling note (found during FD-010)

`@app.errorhandler` only covers Flask's view-dispatch phase. An
exception raised *after* a view successfully returns — during response
finalization, e.g. Flask-Session failing to save to Redis — bypasses it
entirely and would otherwise leak Werkzeug's raw default error page
(violating NFR-007). `app/errors.py` now also wraps `app.wsgi_app` as a
last-resort catch-all so this class of failure still returns the hybrid
envelope. Regression-tested in `tests/test_errors.py` via a deliberately
failing `after_request` hook (general mechanism, not Redis-specific).

## API conventions & docs

Full conventions (versioning, response/error/pagination envelopes, status
codes) are in [`docs/API.md`](../docs/API.md). The machine-readable
contract is `openapi.yaml`, served live:

- `GET /api/v1/openapi.json` — the spec as JSON
- `GET /api/v1/docs` — interactive Swagger UI

Update `openapi.yaml` (and `docs/API.md` if the convention itself
changes) whenever an endpoint is added or changed.

## Setup

```bash
cd backend
py -3.12 -m venv .venv
./.venv/Scripts/python.exe -m pip install -r requirements-dev.txt
```

Copy the root `.env.example` to `.env` (at the project root) and adjust as
needed; `python-dotenv` loads it automatically.

### PDF generation (FD-045) on Windows

Invoice PDF generation uses WeasyPrint, which needs a system-level
GTK3 runtime (Pango/Cairo/GDK-Pixbuf) that `pip install` cannot
provide on its own - `import weasyprint` raises `OSError: cannot load
library 'libgobject-2.0-0'` without it. On Linux (production), these
typically come from system packages (e.g. a `libpango-1.0-0` apt
package) and need no extra step. On Windows, install via
[MSYS2](https://www.msys2.org/) (if not already installed):

```bash
pacman -S mingw-w64-x86_64-pango mingw-w64-x86_64-gdk-pixbuf2
```

then make sure `<msys2 install dir>\mingw64\bin` (e.g.
`C:\msys64\mingw64\bin`) is on `PATH` whenever you run the app or its
tests - **append** it, don't prepend it, since MSYS2's own `mingw64`
directory also has a `python.exe` that would otherwise shadow this
project's venv. Every other route/test in this app works fine without
this - only generating a PDF (`app.invoices.pdf.generate_invoice_pdf`,
imported lazily) actually needs it, by design.

## Running

```bash
FLASK_ENV=development ./.venv/Scripts/python.exe -m flask --app wsgi run
```

## Testing

```bash
FLASK_ENV=testing ./.venv/Scripts/python.exe -m pytest -v
```

`tests/test_invoices_pdf.py`'s few tests that render a real PDF need
WeasyPrint's native GTK3 runtime actually importable (see "PDF
generation (FD-045) on Windows" above) - everything else in the suite
runs fine without it.

`tests/conftest.py`'s `app` fixture disposes its SQLAlchemy engine
(`db.session.remove()` + `db.engine.dispose()`) after every test. Each
test gets its own fresh Flask app - and therefore its own engine/
connection pool, bound via `db.init_app(app)` inside `create_app()` -
for the simplest possible test isolation; without explicit disposal,
connections from 270+ short-lived engines accumulated faster than
Postgres's `max_connections` could absorb across a full suite run
(confirmed via `pg_stat_activity`: ~43 open connections after one run
that started from zero), producing nondeterministic deadlocks/FK
violations/"row not found" errors in otherwise-correct, unrelated
tests - not a bug in the code under test. Running a handful of test
files together is fine; it only showed up once the suite grew large
enough to approach the connection limit.
