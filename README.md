# FlowDesk

Business Operations Platform for Small Businesses — a multi-tenant SaaS that
centralizes employees, customers, tasks, invoices, and daily operational
activity into one workspace, with role-specific dashboards, workflow
management, analytics, notifications, and AI-generated weekly business
summaries grounded in real platform data.

FlowDesk is built to be generic enough for consulting agencies, marketing
agencies, small retail businesses, IT companies, service providers, and
small administrative teams — it is not designed around a single industry.

The full product specification and development backlog is the single
source of truth for this project: [`docs/FlowDesk_Specification.md`](docs/FlowDesk_Specification.md).

## Architecture

Modular monolith: one deployable Flask backend organized into domain
blueprints, paired with a React + TypeScript SPA frontend.

| Layer | Technology |
|---|---|
| Frontend | React + TypeScript + Vite, Tailwind CSS + shadcn/ui, TanStack Query |
| Backend | Python Flask (Blueprints), SQLAlchemy, Alembic/Flask-Migrate |
| Database | PostgreSQL |
| Background jobs | Celery + Redis |
| PDF generation | WeasyPrint |
| Testing | Pytest (backend), Vitest + React Testing Library + Playwright (frontend) |

See Section 9 of the specification for the complete architecture, domain
boundaries, and repository layout.

## Repository layout

```text
flowdesk/
  README.md
  .gitignore
  .env.example
  docker-compose.yml   # Postgres + Redis for local dev (FD-006)
  docker/
    postgres-initdb/    # creates the second (test) database on first boot
  docs/
    FlowDesk_Specification.md
    API.md               # API conventions (versioning, envelopes, pagination, status codes)
    DATABASE.md           # Schema conventions + table-by-table reference
  backend/            # Flask API (set up in FD-002+)
  frontend/           # React + TypeScript SPA (set up in FD-003+)
```

`backend/` has a working Flask application skeleton with a live PostgreSQL
connection and migration pipeline (FD-002, FD-004, FD-005); `frontend/`
has a working Vite + React + TypeScript skeleton (FD-003).

## Status

This project is being built incrementally against a 65-task backlog
(FD-001 through FD-065), strictly respecting the dependency map and
priorities defined in the specification. FD-001 (repository structure),
FD-002 (Flask app factory, config, central error handling, health check),
FD-003 (React/Vite/TS/Router/TanStack Query/Tailwind/shadcn scaffold),
FD-004 (PostgreSQL + SQLAlchemy connection, sessions, pooling),
FD-005 (Alembic/Flask-Migrate, naming convention, baseline migration),
FD-006 (Docker Compose dev infrastructure for Postgres + Redis),
FD-007 (API conventions documented in `docs/API.md` + a live OpenAPI
contract), FD-008 (User model — the first domain model), FD-009
(registration), FD-010 (login/logout, Redis-backed sessions, CSRF),
FD-011 (`GET /auth/me`), FD-012 (Organization + Membership models —
first organization-scoped data), FD-013 (organization creation, creator
becomes Owner), and FD-014 (`GET /organizations` — list the caller's own
memberships) are Done; no other feature pages exist yet.

## Local development infrastructure

`docker-compose.yml` runs Postgres and Redis as containers so you don't
need either installed natively:

```bash
cp .env.example .env   # fill in POSTGRES_PASSWORD etc.
docker compose up -d
```

This creates two databases on first boot — `POSTGRES_DB` (dev) and
`POSTGRES_TEST_DB` (test), via `docker/postgres-initdb/` — matching the
dev/test split the backend already expects (FD-004/FD-005). Point
`DATABASE_URL` / `TEST_DATABASE_URL` in `.env` at the container using the
same credentials and `DB_HOST_PORT`.

If port 5432 or 6379 is already taken by a native Postgres/Redis install
on your machine, override `DB_HOST_PORT` / `REDIS_HOST_PORT` in `.env`
before starting the containers, or stop the native services first — both
would otherwise try to bind the same host port.

**Not yet verified against a live Docker daemon.** This repository's
development environment doesn't have Docker Desktop installed, so
`docker-compose.yml` has only been validated against the official Compose
Specification JSON schema and had its init script's SQL logic exercised
directly against a real Postgres instance — not run end-to-end with
`docker compose up`. If something doesn't start cleanly on a machine that
does have Docker, that's the first place to look.

## Development workflow

**Branching:** create a branch per backlog task, named `fd-<id>-<short-description>`
(e.g. `fd-002-flask-app-factory`). Merge into `main` once the task's
acceptance criteria are verified.

**Commits:** write commit messages that describe *why* a change was made,
referencing the backlog task ID (e.g. `FD-002: add Flask application
factory and per-env config`). Keep commits scoped to a single task where
possible.

**Task tracking:** backlog task status follows
`Backlog → Ready → In Progress → In Review → Blocked → Done`. A task is
only marked Done once every acceptance criterion in the specification has
been verified by running its tests — see Section 31 of the specification.

## Getting started

Backend setup, running, and testing instructions are in
[`backend/README.md`](backend/README.md); frontend instructions are in
[`frontend/README.md`](frontend/README.md).
