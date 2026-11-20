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
becomes Owner), FD-014 (`GET /organizations` — list the caller's own
memberships), FD-015 (centralized RBAC — permission definitions,
`require_permission` decorator, object-level membership checks; see
`docs/API.md`'s Authorization section), FD-016 (employee
invitations — secure expiring tokens, real SMTP email delivery,
acceptance, cancellation; RBAC's first real consumer), FD-017
(authentication frontend — login/register, protected routes, auth
state), FD-018 (organization onboarding — creation flow, org switcher;
see `frontend/README.md`), FD-019 (Department model — org-scoped,
manager reference), FD-020 (Employee profile model — linked to
membership, department, manager), FD-021 (department CRUD —
list/create/update/deactivate, safe-deletion policy), FD-022
(employee directory API — search, filters, pagination, safe fields
only; see `docs/API.md`'s Employee directory section), FD-023
(employee profile & status management — single-employee view/edit,
deactivation doesn't break history; see `docs/API.md`'s Employee
profile & status management section), FD-024 (employee frontend —
directory, profile, department management; see
`frontend/README.md`'s own section), FD-025 (Task/TaskComment/
TaskHistory models, with indexes; see `docs/DATABASE.md`'s own
sections), FD-026 (task creation/retrieval — pagination, filters), and
FD-027 (task assignment/reassignment — validated assignee, history),
FD-028 (task status workflow — To Do → In Progress → Under Review →
Completed, Cancelled terminal), FD-029 (task editing & deadlines —
date validation, history on change), FD-030 (task comments —
access-restricted, author + timestamp), FD-031 (task history —
chronological, append-only, read-only; see `docs/API.md`'s Tasks
section), FD-032 (task frontend — list/board/calendar/My Tasks,
assignment, comments, history; see `frontend/README.md`'s own section),
and FD-033 (overdue detection — timezone-aware, excludes terminal
statuses; see `docs/API.md`'s Tasks section) are Done, completing Epic
E04 (Task Management and Workflows). FD-034 (Customer model —
org-scoped, search indexes; see `docs/DATABASE.md`'s own section) and
FD-035 (customer CRUD — search, pagination, archive; see
`docs/API.md`'s Customers section), FD-036 (CustomerRequest/
RequestComment/RequestHistory models; see `docs/DATABASE.md`'s own
sections), and FD-037 (request workflow — create/retrieve, assignment,
New → Assigned → In Progress → Waiting for Customer → Resolved →
Closed; see `docs/API.md`'s Customer requests section), and FD-038
(request comments & history — internal comments never
customer-exposed by construction; see `docs/API.md`'s own section), and
FD-039 (customer & request frontend — directory, profile, queue,
assignment, status controls; see `frontend/README.md`'s own section)
are Done, completing Epic E05 (Customer and Request Management).
FD-040 (Invoice/InvoiceLineItem/Payment models — decimal money types,
invoice number unique per org; see `docs/DATABASE.md`'s own sections),
FD-041 (invoice calculations — server-authoritative line totals,
subtotal, tax summed at full precision and rounded once, flat/percentage
discount; see `docs/DATABASE.md`'s own section), FD-042 (invoice
lifecycle — create/list/get/edit, issue (draft → sent, locks financial
details), cancel (blocked once a payment is recorded), lazy overdue
auto-transition; see `docs/API.md`'s Invoices section), FD-043
(payment recording — client-supplied idempotency key, overpayment
rejected, row-locked balance check, transactional status update to
partially_paid/paid; see `docs/API.md`'s Payments section), and
FD-044 (financial API & reports — invoiced/collected/outstanding
totals, overdue count, monthly revenue, recent payments, gated by
FINANCIAL_REPORTS_VIEW; see `docs/API.md`'s Financial reports
section), FD-045 (invoice PDF generation via WeasyPrint — logo,
line items, totals, payment status, with SSRF defenses on the
org-supplied logo URL; see `docs/API.md`'s Invoice PDF section), and
FD-046 (invoice frontend — editor, payment form, balance/status
refresh, PDF access; see `frontend/README.md`'s own section) are
Done, completing Epic E06 (Invoice and Payment Management). FD-047
(centralized activity logging — a shared `log_activity()` service
wired into employee invites, task/request/invoice/payment
create-and-lifecycle events, and employee deactivation, with a
role/scope-filtered `GET .../activity` read endpoint; one named event,
"role-changed", is a documented gap since no "change a member's role"
feature exists yet to log; see `docs/DATABASE.md`'s `activity_logs`
section and `docs/API.md`'s Activity log section) is Done, the first
task of Epic E07. FD-048 (notification infrastructure — `Notification`
model, recipient-scoped with no RBAC permission at all since the spec
defines none for this entity, read/mark-one/mark-all-read endpoints)
and FD-049 (event-based notifications — wires the shared
`create_notification()`/`create_notifications_for_roles()` service
into task/request assignment, task/request comments, request status
changes, and invoice-paid events fanned out to Owner/Accountant;
"invitation received" and "deadline approaching/overdue" are
documented gaps — no pre-membership recipient and no scheduler
infrastructure exists yet, respectively; see `docs/DATABASE.md`'s
`notifications` section and `docs/API.md`'s Notifications section) are
both Done. FD-050 (notification frontend — a `NotificationsPage` with
list/unread-filter/mark-one/mark-all-read, an unread-count badge and
nav entry on `HomePage` following FD-024 through FD-046's own
precedent of no shell/top-bar yet, and navigation to a notification's
related task/request/invoice; see `frontend/README.md`'s own section)
is Done. FD-051 (analytics service — `app/analytics/service.py`,
service layer only, no routes yet; four deterministic, explicit-period,
org-scoped functions matching FR-030 through FR-033: overview metrics,
per-employee performance, per-department breakdown, financial
analytics; reuses the already-reviewed `get_financial_summary` rather
than recomputing money figures; no fabricated "trend" field — a caller
wanting one calls this twice and compares two real results; department
request-volume is derived via each request's assignee's own
department, since `CustomerRequest` has no department column of its
own) is Done. FD-052 (analytics API — four `GET
.../analytics/{overview,employees,departments,finance}` endpoints over
FD-051's service functions, each gated by `ANALYTICS_VIEW` with the
scope restrictions FR-030 through FR-033 actually specify; adds the
FR-034 named date-filter taxonomy — last 7/30/90 days, current/previous
calendar month, custom range — resolved into the explicit
`period_start`/`period_end` dates the service layer requires; routes do
their own 404 existence/ownership check for a cross-organization
`target_membership_id`/`department_id` before calling into the
service, per FD-051's own documented warning) is Done. FD-053
(dashboards & analytics frontend — the real persistent shell
(sidebar + top bar, spec Section 12.2) every prior frontend module's
own "no sidebar yet" comment deferred to this task; a role-specific
Overview dashboard per spec Section 12.3 (Owner/Manager/Employee/
Accountant/CustomerSupport each see different real data, sourced from
FD-052's own endpoints wherever an aggregate fits, plain list-endpoint
reads where a widget is a row list rather than a total); a new
`/analytics` page with Recharts charts gated per sub-endpoint exactly
like the backend gates it, plus the FR-034 period selector; AI Reports/
Activity/Settings sidebar entries and the top bar's search/theme
selector are documented gaps, not oversights — no FD task ever builds
those three pages, and dark theme is explicitly optional and
unimplemented) is Done. FD-054 (CSV/PDF report export — a
`.../export` sibling for each of FD-052's four analytics endpoints,
same `ANALYTICS_VIEW` permission, scope rules, period taxonomy, and
cross-org 404s; CSV cells are sanitized against formula injection
with the standard leading-`'` defusing prefix; the financial export
has four sections — summary, revenue by day, invoice distribution,
recent payments — mirroring the JSON response's own shape; backend
only, same precedent as FD-045/FD-046's PDF-generation/PDF-access
split, so there's no frontend download button yet) is Done, completing
Epic E07 (Analytics, Activity History and Notifications). FD-055
(design the AI reporting service — `backend/app/ai/`: a swappable
`AIProvider` abstraction, one real implementation (`AnthropicProvider`,
plain stdlib `urllib`, no vendor SDK), its own timeout/retry rules,
and the FR-040/FR-042 weekly-report input/output contract; resolves
Section 35 open decision #12 — Anthropic Claude API, no hard budget
cap beyond a bounded token limit + request timeout, and the provider
only ever receives an already-computed metrics snapshot, never a DB
session or another organization's data; design only, no HTTP endpoint
— FD-056 through FD-060 build the real pipeline on top of this) is
Done, starting Epic E08 (AI Business Assistant). FD-056 (weekly
metrics aggregation — `app/ai/snapshot.py`'s `build_weekly_metrics_snapshot`
combines FD-051's four analytics functions into one JSON-serializable
`metrics_snapshot` dict per organization/period, always at full scope
since there's no HTTP caller to scope to; pure and side-effect-free,
so retrying it is always safe — its own "idempotent"; trims
`recent_payments` to the same externally-safe fields FD-054's export
already chose) is Done. FD-057 (AI weekly summary generation —
`app/ai/service.py`'s `generate_report_for_organization` ties FD-056's
snapshot to FD-055's `generate_weekly_report`/`build_default_provider`
for one real organization and period, resolving provider/token/
timeout/retry defaults from config only when not given explicitly;
takes an already-loaded `Organization` instance and issues no
database query of its own; still unreachable from any HTTP route —
FD-058/059 wire the real persisted/scheduled pipeline on top of this)
is Done. FD-058 (AI report persistence — a new `AIReport` model
(`summary`/`recommendations` as two separate JSONB columns per
FR-042's facts-vs-recommendations split, plus a `UniqueConstraint` on
organization/type/period defined now for FD-059's own future "no
duplicates" need) and a new `app/ai_reports/` module exposing `POST
.../ai-reports/generate`, `GET .../ai-reports[/{id}]`, gated by
`ANALYTICS_VIEW` at full scope only; widened FD-057's own
`generate_report_for_organization` to also return the snapshot it
used, since persisting a freshly-recomputed one risked a mismatch
with what the AI actually saw) is Done.

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
