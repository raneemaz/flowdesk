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
  docs/
    FlowDesk_Specification.md
  backend/            # Flask API (set up in FD-002+)
  frontend/           # React + TypeScript SPA (set up in FD-003+)
```

`backend/` and `frontend/` are placeholders at this stage — the application
code, dependencies, and tooling for each are introduced in later backlog
tasks (FD-002 and FD-003), not in this initial commit.

## Status

This project is being built incrementally against a 65-task backlog
(FD-001 through FD-065), strictly respecting the dependency map and
priorities defined in the specification. No application functionality
exists yet; this commit establishes the repository structure only.

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

Setup, running, and testing instructions will be added as the backend
(FD-002) and frontend (FD-003) are initialized.
