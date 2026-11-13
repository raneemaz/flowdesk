# FlowDesk Backend

Flask API for FlowDesk. Domain modules (auth, organizations, employees,
tasks, etc.) are added incrementally per the backlog in
[`docs/FlowDesk_Specification.md`](../docs/FlowDesk_Specification.md);
only the application skeleton, database connection, and migration
pipeline exist so far (FD-002, FD-004, FD-005). No domain models yet
(FD-008+).

## Structure

```
backend/
  wsgi.py              Entry point (`app = create_app()`)
  app/
    __init__.py        Application factory, blueprint registration
    config.py           Per-environment config (FLASK_ENV: development/testing/production);
                          loads .env and reads env vars fresh per create_app() call
    extensions.py         SQLAlchemy + Flask-Migrate instances, naming convention
    errors.py            APIError + central error handlers (hybrid envelope)
    health/              GET /api/v1/health (liveness + DB connectivity status)
  migrations/            Alembic migration environment (flask db <cmd>)
  tests/                 Pytest suite
```

## Database

Requires a running PostgreSQL instance. `DATABASE_URL` (dev) and
`TEST_DATABASE_URL` (test) in `.env` point to separate databases so test
runs never touch dev data. Connection pooling (`pool_pre_ping`, `pool_size`,
`max_overflow`, `pool_recycle`) is configured via `SQLALCHEMY_ENGINE_OPTIONS`
in `app/config.py`, tunable via the `DB_POOL_SIZE` / `DB_MAX_OVERFLOW` env
vars. No models or migrations exist yet (FD-005 adds Alembic/Flask-Migrate).

Local dev database setup (once, on a local PostgreSQL install):

```sql
CREATE ROLE flowdesk LOGIN PASSWORD '...';
CREATE DATABASE flowdesk_dev OWNER flowdesk;
CREATE DATABASE flowdesk_test OWNER flowdesk;
```

Then set `DATABASE_URL` / `TEST_DATABASE_URL` in `.env` (scheme
`postgresql+psycopg://`, matching the `psycopg` v3 driver in
`requirements.txt`) accordingly. FD-006 will replace manual local setup
with Docker Compose.

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

The current baseline migration is intentionally empty — no domain models
exist yet. Each future model-adding task should produce its own migration
via `flask db migrate`, reviewed before committing (autogenerate doesn't
catch everything, e.g. column renames).

## Response envelope

Success: `{"success": true, "message": "...", "data": {...}}`

Error: `{"success": false, "error": {"code": "...", "message": "...", "details": {...}}}`

Route/service code should raise `app.errors.APIError(message, status_code, code, details)`
for expected, user-facing failures rather than building a JSON response by hand.
Unhandled exceptions and standard HTTP errors (404, 405, etc.) are converted
to the same envelope automatically.

## Setup

```bash
cd backend
py -3.12 -m venv .venv
./.venv/Scripts/python.exe -m pip install -r requirements-dev.txt
```

Copy the root `.env.example` to `.env` (at the project root) and adjust as
needed; `python-dotenv` loads it automatically.

## Running

```bash
FLASK_ENV=development ./.venv/Scripts/python.exe -m flask --app wsgi run
```

## Testing

```bash
FLASK_ENV=testing ./.venv/Scripts/python.exe -m pytest -v
```
