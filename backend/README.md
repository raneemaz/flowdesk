# FlowDesk Backend

Flask API for FlowDesk. Domain modules (auth, organizations, employees,
tasks, etc.) are added incrementally per the backlog in
[`docs/FlowDesk_Specification.md`](../docs/FlowDesk_Specification.md);
the application skeleton, database connection, migration pipeline, API
documentation infra, and the first domain model exist so far (FD-002,
FD-004, FD-005, FD-007, FD-008).

## Structure

```
backend/
  wsgi.py              Entry point (`app = create_app()`)
  openapi.yaml          Hand-maintained API contract (OpenAPI 3.0.3)
  app/
    __init__.py        Application factory, blueprint registration
    config.py           Per-environment config (FLASK_ENV: development/testing/production);
                          loads .env and reads env vars fresh per create_app() call
    extensions.py         SQLAlchemy + Flask-Migrate instances, naming convention
    errors.py            APIError + central error handlers (hybrid envelope)
    security.py            Password hashing (Argon2id) - see docs/DATABASE.md
    models/                SQLAlchemy models (see docs/DATABASE.md for the schema)
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
this.

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

## Running

```bash
FLASK_ENV=development ./.venv/Scripts/python.exe -m flask --app wsgi run
```

## Testing

```bash
FLASK_ENV=testing ./.venv/Scripts/python.exe -m pytest -v
```
