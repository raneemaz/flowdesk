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

## AI reporting service, persistence, scheduling, and assistant (FD-055/FD-056/FD-057/FD-058/FD-059/FD-061)

`app/ai/` stays the stateless generation pipeline (no DB model, no
HTTP routes): `providers.py` defines the swappable `AIProvider`
abstraction plus the one real implementation, `AnthropicProvider`
(plain stdlib `urllib`, not the vendor SDK - same reasoning as the
SMTP-over-vendor-SDK choice above) and its own timeout/retry rules
(`complete_with_retries`); `schemas.py` defines the weekly-report
input/output contract (`WeeklyReportInput`/`WeeklyReportOutput`);
`service.py`'s `generate_weekly_report` ties them together, and
FD-057's `generate_report_for_organization` ties that to FD-056's own
`snapshot.py`'s `build_weekly_metrics_snapshot` for one real
organization + period, returning a `GeneratedWeeklyReport` (the
output **and** the snapshot it was built from - widened once FD-058
needed to persist the exact snapshot a report was generated from).
Resolves Section 35 open decision #12: Anthropic Claude API, no hard
budget cap beyond a bounded `AI_MAX_TOKENS` + `AI_REQUEST_TIMEOUT_SECONDS`,
and the provider only ever sees an already-computed metrics snapshot
- never a DB session or another organization's data.

`app/ai_reports/` (FD-058, new) owns the one genuinely persisted
entity this epic needs: the `AIReport` model (`app/models/ai_report.py`
- `summary`/`recommendations` as two separate JSONB columns, per
FR-042's "clearly separate facts from AI-generated recommendations";
a `UniqueConstraint` on `(organization_id, report_type, period_start,
period_end)` defined now rather than retrofitted once FD-059 needs
it) and its own three endpoints (`POST .../ai-reports/generate`,
`GET .../ai-reports[/{id}]`), gated by `ANALYTICS_VIEW` at full scope
only (Owner/Manager) - reusing the existing permission rather than
inventing a new one, since a report's content includes data a
limited/own-scope caller can't otherwise see. See `docs/API.md`'s own
AI Reporting Service section for the full design rationale. Env vars
(`.env.example`): `ANTHROPIC_API_KEY` (empty until something actually
calls this), `ANTHROPIC_MODEL`, `AI_REQUEST_TIMEOUT_SECONDS`,
`AI_MAX_RETRIES`, `AI_MAX_TOKENS`.

`app/celery_app.py` + `app/ai_reports/tasks.py` (FD-059, new) are the
scheduled half - see "Scheduled AI reports (FD-059)" under Running,
below, for how to start the worker/beat processes and the Section 35
open decision #11 resolution (Monday 06:00, each organization's own
local timezone; an organization with no activity yet still gets a
report, per FR-042's own "identify missing data" rather than this job
inventing a skip condition).

`app/ai_assistant/` (FD-061, new) is the conversational assistant
(FR-041) - `tools.py`'s four tools are thin, permission-aware wrappers
around FD-051's own analytics functions (no new authorization logic);
`service.py`'s `ask_assistant` runs a bounded tool-use loop against
`app/ai/providers.py`'s new `complete_with_tools` (additive alongside
the original `complete`); `routes.py` exposes the one endpoint, `POST
.../ai-assistant/ask`. Read-only - no tool creates, edits, or deletes
anything ("no unapproved writes", this task's own title). Backend
only, no frontend chat widget. See `docs/API.md`'s own "Conversational
AI assistant" section for the full design rationale.

## Error handling note (found during FD-010)

`@app.errorhandler` only covers Flask's view-dispatch phase. An
exception raised *after* a view successfully returns — during response
finalization, e.g. Flask-Session failing to save to Redis — bypasses it
entirely and would otherwise leak Werkzeug's raw default error page
(violating NFR-007). `app/errors.py` now also wraps `app.wsgi_app` as a
last-resort catch-all so this class of failure still returns the hybrid
envelope. Regression-tested in `tests/test_errors.py` via a deliberately
failing `after_request` hook (general mechanism, not Redis-specific).

## Security & performance review (FD-064)

A whole-codebase pass against Section 13's NFR-001–015 and security
checklist, after all backend/frontend functionality and integration
testing (FD-062/FD-063) were in place - every review before this one
was scoped to a single task's own diff.

**Found and fixed: auth rate limiting was entirely missing.**
`/auth/login` and `/auth/register` could be hit an unbounded number of
times per second from a single IP - a real, unthrottled credential-
stuffing/signup-spam vector, and the one item Section 13's security
checklist explicitly names ("auth rate limiting") that nothing in the
codebase actually implemented before this task. Fixed with
Flask-Limiter (`app/extensions.py`'s `limiter`, Redis-backed in dev/
production via `RATELIMIT_STORAGE_URI`, sharing the same Redis
instance sessions already use): `10 per minute` on login, `5 per hour`
on register, both per-IP. Disabled by default in tests
(`RATELIMIT_ENABLED` read from the environment in `TestingConfig`,
defaulting to `"false"`) so the existing suite's many repeated login/
register calls never see a 429 they aren't testing for;
`tests/test_auth_rate_limiting.py` enables it on its own, freshly
created app to verify the 429 itself, the per-IP scoping, and that a
different IP isn't throttled by another's attempts.

**Found and fixed: `REDIS_URL` wasn't required at startup in
production.** Unlike `ANTHROPIC_API_KEY` (an optional feature that
fails gracefully per-request when unset), sessions and the rate
limiter above are both required for the app to function at all -
leaving `REDIS_URL` unset would silently default to
`redis://localhost:6379/0` and fail confusingly at first login in
production, rather than at startup like the existing
`SECRET_KEY`/`DATABASE_URL`/`SMTP_HOST` checks. `app/__init__.py` now
raises the same way for a missing `REDIS_URL` in production; see
`tests/test_config.py::test_production_requires_redis_url`.

**Also removed:** unused `S3_*` object-storage variables from
`.env.example` - nothing in `app/` ever reads them (PDF generation,
FD-045, renders on demand via WeasyPrint rather than persisting to
storage); leaving them in the example file risked implying S3 setup
is required when it never was.

**Reviewed and confirmed clean** (`tenant-security-reviewer` and
`financial-integrity-reviewer` subagents, full `app/` tree, not a
diff): tenant isolation (every cross-tenant access scenario in
Section 13's table, both as unit tests and the FD-062 integration
suite), CSRF coverage on every state-changing route, 100% parameterized
ORM calls (zero raw SQL with interpolated values anywhere), money
handling (Decimal end-to-end, server-recomputed totals, idempotent/
race-safe payments, a single rounding helper), and that every financial
aggregate query (not just its route) filters by `organization_id`.

**Known, non-blocking findings** (informational, not fixed - no live
code path exercises any of these today):
- No invoice correction/credit-note mechanism exists yet (spec Module 5
  implies one); an issued invoice is permanently locked with no
  in-product remedy for a mistake. A product decision for a future
  task, not a defect in what FD-040–046 built.
- No currency-conversion/single-currency-per-org enforcement in
  financial aggregates - already the documented, deliberately
  unresolved Section 35 open decision #5, not a new gap.
- `app/analytics/service.py`'s `get_employee_performance`/
  `get_department_analytics` issue several queries per employee/
  department in a loop rather than one `GROUP BY` aggregate (classic
  N+1 shape) - fine at the small-business employee counts this product
  targets, worth revisiting if an org's headcount ever grows large.
- No test exercises genuine concurrency on `record_payment`'s
  `SELECT ... FOR UPDATE` overpayment guard (only sequential logic is
  currently verified) - recommended before/after FD-065, not blocking it.
- `can_assign_role` (`app/authz/service.py`) is unit-tested but has no
  live route yet - no endpoint changes a member's role post-acceptance,
  so the scenario it protects against can't currently be exploited by
  anyone. Wire it in when that endpoint is eventually built, rather
  than re-deriving the self-escalation check.

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

### Scheduled AI reports (FD-059)

Two more long-running processes, started separately from the Flask
dev server above - `app/celery_app.py` is the Celery equivalent of
`wsgi.py`, never imported by the Flask app itself:

```bash
FLASK_ENV=development ./.venv/Scripts/python.exe -m celery -A app.celery_app.celery_app worker --loglevel=info
FLASK_ENV=development ./.venv/Scripts/python.exe -m celery -A app.celery_app.celery_app beat --loglevel=info
```

Beat fires the one scheduled job (`generate_weekly_reports_task`)
every hour, on the hour (UTC); the job itself
(`app.ai_reports.tasks.run_due_weekly_reports`) checks each
organization's own local time against Monday 06:00 and generates
that organization's weekly AI report only when it's actually due
there - see `docs/API.md`'s AI Reporting Service section for the full
design (Section 35 open decision #11's resolution).

**No real Redis in this dev environment** (same gap as Docker
elsewhere in this project) - `CELERY_BROKER_URL`/`CELERY_RESULT_BACKEND`
point at `redis://localhost:6379/0` in `.env.example`, but nothing in
the test suite ever starts a worker/beat process or connects to a
broker; `app.ai_reports.tasks.run_due_weekly_reports` is plain,
Celery-free Python, directly unit-tested with no broker involved at
all.

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

This per-test isolation is all within a single pytest process, though -
every test still talks to the same physical Postgres database
(`FLASK_ENV=testing`'s own `DATABASE_URL`), just via a fresh
connection each time. Running two separate `pytest` invocations
*concurrently* against that same database (e.g. one in the foreground,
one backgrounded) is not supported: one process's test data can be
deleted or overwritten mid-flight by another's, producing the exact
same symptoms (`NoResultFound`, stale-row 404s) for reasons that have
nothing to do with the code under test. Run one `pytest` process at a
time against the test database.

### Integration tests (FD-062)

`tests/integration/` holds cross-module, end-to-end tests driven
entirely through real HTTP routes (never a direct ORM insert, except
reading an invitation token out of a monkeypatched "sent" email) -
every other test file in this suite is deliberately scoped to one
module at a time, so this is the one place that would catch a bug only
visible when several modules interact with the same real data:

- `test_full_workflow.py` - the canonical customer -> request -> task
  -> invoice -> payment -> AI-report workflow (spec Section 36),
  exercised start to finish by five different roles.
- `test_tenant_isolation.py` - two full organizations' workflows run
  side by side with deliberately overlapping data, checking every
  list/aggregate endpoint (not just single-resource 404s, which every
  module's own tests already cover) for cross-tenant leakage.
- `test_financial_transactions.py` - several invoices in different
  terminal states (paid, partially paid, cancelled, overdue) at once,
  reconciled exactly against both `GET .../invoices/financial-summary`
  and `GET .../analytics/overview` - two independent queries over the
  same money that could otherwise silently drift apart.
- `test_analytics_reconciliation.py` - the org-wide overview,
  per-department, and per-employee analytics views, each its own
  independent query, cross-checked to add up to each other over the
  same real tasks/requests.
