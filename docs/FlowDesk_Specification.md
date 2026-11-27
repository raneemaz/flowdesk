# FlowDesk
## Complete Product & System Specification + Development Backlog & Execution Plan

**Product:** FlowDesk — Business Operations Platform for Small Businesses
**Category:** Business Operations & Management Platform (multi-tenant SaaS)
**Version:** 1.0 — consolidated working baseline
**Status:** Ready for technical review and phased implementation

---

# Part I — Product Vision & Specification

## 1. Problem statement

Small businesses often run their operations across disconnected tools: spreadsheets for employee data, chat apps for internal communication, separate task trackers, manual invoicing, and paper-based customer-request tracking. This causes:

- Scattered information and poor visibility for owners.
- Missed or delayed tasks with unclear ownership.
- Inconsistent handling of customer requests.
- No clear picture of which invoices are paid, outstanding, or overdue.
- Manual, time-consuming weekly reporting.
- Weak auditability when records change.

## 2. Proposed solution

FlowDesk centralizes employees, customers, tasks, invoices, and daily operational activity into one workspace, with role-specific dashboards, workflow management, analytics, notifications, and AI-generated weekly business summaries grounded in real platform data.

FlowDesk should be generic enough for consulting agencies, marketing agencies, small retail businesses, IT companies, service providers, and small administrative teams — not designed around a single industry.

## 3. Product objectives

| Objective | Expected outcome |
|---|---|
| Centralization | All business operations in one platform |
| Productivity | Better task assignment and tracking |
| Accountability | Track who performed each action |
| Visibility | Real-time operational dashboards |
| Financial organization | Centralized invoice management |
| Automation | Automated notifications and summaries |
| Decision support | AI-powered business insights |

## 4. Product principles

1. **One source of operational truth** — key records and their histories live in one system.
2. **Clear ownership** — work has an owner, status, and, where relevant, a due date.
3. **Least privilege** — users see and change only what their role and organization membership permit.
4. **Tenant isolation by design** — organization boundaries are enforced in backend queries and authorization, never only hidden in the UI.
5. **Explainable analytics** — calculations are deterministic and traceable to stored data.
6. **AI as an interpreter, not an accountant** — AI explains validated metrics; it never invents or recalculates authoritative figures.
7. **Incremental delivery** — every feature ships as small, independently testable tasks.

## 5. Non-goals for V1

Explicitly out of scope, to prevent FlowDesk from growing into an ERP:

- Full double-entry accounting, tax filing, or bookkeeping.
- Payroll, benefits, or employee time-clock processing.
- Banking integrations or automatic bank reconciliation.
- Inventory and warehouse management.
- Complex HR, recruitment, or performance-review suites.
- Real-time chat, voice, or video meetings.
- E-commerce storefronts or marketplaces.
- Native iOS/Android apps.
- Subscription billing for FlowDesk itself.
- Complex approval chains and enterprise workflow builders.

## 6. Success measures

- A new organization can complete onboarding and invite a user.
- A manager can create and assign a task and track it to completion.
- A support user can process a customer request without accessing restricted financial data.
- An accountant can issue an invoice and record multiple payments.
- Dashboards reconcile with underlying records for the same filters.
- No automated authorization test can access another organization's records.
- Weekly summaries cite the reporting period and use only supplied metrics.
- Critical user journeys pass integration and end-to-end tests.

---

## 7. Users, roles and permissions

A user account may belong to more than one organization. Permissions are evaluated in the context of the active organization membership. Roles define *default* permissions, but every permission must also be enforced on the backend — hiding a button in the UI is never a security control.

### 7.1 Roles

| Role | Primary purpose | Typical access |
|---|---|---|
| **Owner** | Owns and configures the organization | Full administration and business-data access; manages settings, invites/removes employees, assigns roles, views everything, manages subscriptions (future) |
| **Manager** | Coordinates employees and operations | Departments, employees, tasks, customers/requests, operational analytics; cannot modify ownership or subscription settings |
| **Employee** | Performs assigned work | Own profile, assigned tasks, personal activity history, notifications; cannot access other employees' private information |
| **Accountant** | Handles invoices and payments | Customer billing, invoices, payments, financial reports; cannot manage employee permissions |
| **Customer Support** | Handles customers and requests | Customer records, request workflow, internal notes; no financial administration by default |

### 7.2 Permission baseline matrix

| Capability | Owner | Manager | Employee | Accountant | Customer Support |
|---|---:|---:|---:|---:|---:|
| Organization settings | Full | Limited | No | No | No |
| Invite/manage memberships | Full | As granted | No | No | No |
| View employee directory | Yes | Yes | Limited | Limited | Limited |
| Manage departments | Yes | Yes | No | No | No |
| Create/assign tasks | Yes | Yes | No by default | No by default | No by default |
| View/update own assigned task | Yes | Yes | Yes | If assigned | If assigned |
| Manage customers | Yes | Yes | Limited/No | Yes | Yes |
| Manage customer requests | Yes | Yes | If assigned | No by default | Yes |
| Manage invoices/payments | Yes | No by default | No | Yes | No |
| View financial reports | Yes | No by default | No | Yes | No |
| View operational analytics | Yes | Yes | Own/limited | Relevant subset | Relevant subset |
| View activity history | Yes | Yes | Relevant subset | Relevant subset | Relevant subset |

This is the default baseline; any change must update the matrix, permission tests, and docs together.

### 7.3 Permission principles

- Implement permissions centrally — never scatter role-name checks across route handlers.
- Every organization-owned object is scoped to the active organization.
- The backend verifies both role permission *and* object-level access.
- A user must never gain access by changing an ID in a URL, body, or query string.
- Unauthenticated requests → `401`; authenticated-but-unauthorized → `403`.
- Sensitive actions are logged.

---

## 8. Functional requirements by module

### Module 1 — Authentication & Business Management
- **FR-001 Registration:** name, email, password; creates a business workspace; registering user becomes Owner; business name/info required.
- **FR-002 Login/logout:** secure sessions, expiry handling.
- **FR-003 Employee invitations:** Owner/authorized Manager invites by email with role; secure, expiring token; invited user joins or creates an account.
- **FR-004 Business workspace fields:** name, logo, email, phone, address, currency, time zone, date format, created date.
- **FR-005 Multi-tenancy:** a user may belong to multiple organizations; every business record is organization-owned; one organization never accesses another's data.

### Module 2 — Employee & Department Management
- **FR-006 Employee directory:** name, photo, email, job title, department, manager, role, status, join date.
- **FR-007 Employee profile:** personal + job info, assigned/completed/pending/overdue tasks, activity history.
- **FR-008 Departments:** create, rename, assign employees and managers, view stats.
- **FR-009 Employee status:** Active, Inactive, Invited, Suspended. Deactivation never deletes historical activity, invoices, or completed tasks.

### Module 3 — Task & Workflow Management
- **FR-010 Task fields:** title, description, assignee, creator, department, priority, status, start/due date, estimated/actual hours (optional), attachments (optional), timestamps.
- **FR-011 Assignment:** assign/reassign, set deadline/priority/instructions.
- **FR-012 Status workflow:** `To Do → In Progress → Under Review → Completed`, with `Cancelled` as a terminal state. Every change records actor + timestamp; managers can return tasks for revision; unauthorized transitions are blocked.
- **FR-013 Comments:** author, content, timestamp, optional attachment.
- **FR-014 Filters:** employee, department, priority, status, due date, creation date.
- **FR-015 Views:** list, Kanban board, calendar, "My Tasks."
- **FR-016 Overdue detection:** due date passed and not Completed/Cancelled; surfaced in dashboards and analytics.

### Module 4 — Customer & Request Management
- **FR-017 Customer fields:** name, email, phone, company (opt.), address (opt.), notes, created date.
- **FR-018 Request fields:** title, description, customer, category, priority, status, assignee, created/due date, resolution notes.
- **FR-019 Request workflow:** `New → Assigned → In Progress → Waiting for Customer → Resolved → Closed`.
- **FR-020 Assignment:** Managers/authorized Support staff assign requests.
- **FR-021 History:** status changes, assignment changes, internal comments, resolution details.
- **FR-022 Relationship:** one customer → many requests; customer profile shows request + invoice history.

### Module 5 — Invoice & Financial Management
*(Invoicing only in V1 — not full accounting.)*
- **FR-023 Invoice fields:** number, customer, issue/due date, currency, subtotal, discount, tax, total, notes, payment terms.
- **FR-024 Invoice items:** description, quantity, unit price, tax rate (opt.), line total.
- **FR-025 Statuses:** Draft, Sent, Partially Paid, Paid, Overdue, Cancelled.
- **FR-026 Payments:** amount, date, method, reference (opt.), notes; multiple partial payments supported.
- **FR-027 PDF generation:** logo, business info, customer info, items, taxes/discounts, total, payment status.
- **FR-028 Financial dashboard:** total invoiced, total collected, outstanding balance, overdue invoices, monthly revenue collected, recent payments. *Invoiced ≠ collected* — the dashboard must distinguish billed, paid, and outstanding amounts.
- **FR-029 Restrictions:** only Owner and authorized financial roles see sensitive financial data by default.

**Important invoice rule:** once issued, an invoice's financial details are never silently overwritten. Corrections are controlled and auditable; payments are separate records, never edits to the original total.

### Module 6 — Analytics & Reports
- **FR-030 Overview dashboard:** employees, active/completed/overdue tasks, open requests, monthly invoiced/collected.
- **FR-031 Employee performance:** assigned/completed/overdue tasks, completion rate, average completion time. *Raw task counts are not a complete performance measure — tasks vary in complexity.*
- **FR-032 Department analytics:** active/completed/overdue tasks, request volume, completion trends, compared across departments.
- **FR-033 Financial analytics:** revenue over time, invoice distribution, outstanding balances, payment trends.
- **FR-034 Date filters:** last 7/30/90 days, current month, previous month, custom range.
- **FR-035 Exporting:** CSV and PDF for authorized users.

### Module 7 — Activity History & Notifications
- **FR-036 Activity logging:** employee invited/role-changed, task created/assigned/completed, request created/resolved, invoice created, payment recorded, employee deactivated — each with actor, action, entity, entity ID, timestamp, organization, metadata.
- **FR-037 Audit log:** immutable through the normal application interface.
- **FR-038 Notification triggers:** task assigned, deadline approaching/overdue, comment added, request assigned/status changed, invoice paid (authorized users), invitation received.
- **FR-039 Notification center:** list, mark one/all read, navigate to related record. In-app first; email is a later extension.

### Module 8 — AI Business Assistant
The feature that gives FlowDesk its identity — but it must analyze *real* platform data, not produce generic advice.

- **FR-040 Weekly business summary**, covering:
  1. **Business overview** — active tasks, tasks completed this week, new/resolved requests.
  2. **Employee productivity** — who completed tasks, what's still overdue, workload imbalances.
  3. **Financial overview** — invoiced, collected, outstanding, newly overdue.
  4. **Operational problems** — rising overdue tasks, unresolved requests, repeated delays.
  5. **Suggested actions** — tasks needing attention, customers needing follow-up, departments needing rebalancing.
- **FR-041 Conversational assistant (V2):** e.g. "How many tasks were completed this month?", "Which department has the most overdue tasks?" — retrieves authorized, structured data before answering.
- **FR-042 AI reliability requirements:**
  - Never invent business statistics; use real database results.
  - Always show the reporting period; identify missing data.
  - Clearly separate facts from AI-generated recommendations.
  - Never expose another organization's information; always respect the requesting user's permissions.
  - Never perform financial/administrative actions without explicit authorization.

**Recommended AI pipeline:** FlowDesk DB → deterministic Analytics Service (verified metrics) → AI Service (interprets metrics, generates insights) → stored Weekly Report (summary + findings + recommendations). Use a swappable LLM-provider abstraction so the project isn't locked to one vendor.

---

## 9. System architecture

**Style:** modular monolith. One deployable Flask backend organized into domain modules/blueprints — avoids microservices complexity at this scale.

### 9.1 Technology stack

| Layer | Technology | Purpose |
|---|---|---|
| Frontend | React + TypeScript + Vite | SPA UI |
| Styling | Tailwind CSS + shadcn/ui | Consistent, accessible components |
| Routing | React Router | Navigation |
| Server state | TanStack Query | Fetching, caching, mutations |
| Forms | React Hook Form + Zod | Form state & validation |
| Charts | Recharts | Dashboard visualizations |
| Backend | Python Flask | REST API & business logic |
| API structure | Flask Blueprints | Modular domain boundaries |
| ORM | SQLAlchemy | Database access |
| Migrations | Alembic / Flask-Migrate | Versioned schema changes |
| Database | PostgreSQL | Primary production database |
| Auth | Secure HTTP-only cookie sessions (preferred) | Avoid long-lived tokens in localStorage |
| Background jobs | Celery + Redis | Scheduled/async work |
| PDF | WeasyPrint | Invoice/report rendering |
| Backend tests | Pytest | Unit/integration |
| Frontend tests | Vitest + React Testing Library | Component/logic |
| E2E | Playwright | Critical browser workflows |
| API docs | OpenAPI/Swagger | Contract documentation |
| Frontend hosting | Vercel | — |
| Backend hosting | Render (or equivalent) | — |
| File storage | S3-compatible object storage | Attachments, logos |

**Database choice:** PostgreSQL from day one — multi-user concurrency, reliable transactions, strong relational features, production scalability, advanced indexing, and a good fit for multi-tenant apps. SQLite is fine for quick local experiments/isolated tests only; don't rely on cross-database portability.

### 9.2 Backend domain boundaries

`auth · organizations · memberships · employees · departments · tasks · customers · requests · invoices · payments · analytics · activity · notifications · ai_reports`

Each domain separates routes/controllers, schemas/validation, services/business rules, and models/repositories.

### 9.3 Suggested repository layout

```text
flowdesk/
  README.md
  .gitignore
  .env.example
  docker-compose.yml
  docs/
    PRD.md
    SRS.md
    ARCHITECTURE.md
    DATABASE.md
    API.md
    TESTING.md
  backend/
    app/
      __init__.py
      config.py
      extensions.py
      models/
      auth/
      organizations/
      employees/
      departments/
      tasks/
      customers/
      requests/
      invoices/
      payments/
      analytics/
      activity/
      notifications/
      ai/
      services/
      permissions/
      utils/
      jobs/
    migrations/
    tests/
    requirements.txt
    wsgi.py
  frontend/
    src/
      api/
      components/
      layouts/
      pages/
      features/
      hooks/
      contexts/
      routes/
      types/
      utils/
    public/
    package.json
```

---

## 10. Data model

Use UUID primary keys for all externally exposed records. Add `created_at`/`updated_at` where useful. Index organization-scoping columns, foreign keys, common filters, and uniqueness constraints. Store all timestamps in UTC.

### 10.1 Core entities

| Entity | Purpose / key fields |
|---|---|
| User | Global identity: id, name, email (unique), password hash, status, timestamps |
| Organization | id, name, slug, logo, currency, timezone, address, contact info |
| Membership | id, organization_id, user_id, role, status, joined_at — unique org/user pair |
| Invitation | id, organization_id, email, role, token hash, expiry, accepted_at, inviter_id |
| Department | id, organization_id, name, description, manager, status |
| EmployeeProfile | id, organization_id, membership_id, department_id, job_title, employment status |
| Task | id, organization_id, title, description, status, priority, creator, assignee, department, start/due date, est./actual hours |
| TaskComment | id, task_id, author_id, body, created_at |
| TaskHistory | id, task_id, actor_id, event_type, previous_value, new_value, created_at |
| Customer | id, organization_id, name, email, phone, company, address, notes, status |
| CustomerRequest | id, organization_id, customer_id, title, description, category, status, priority, assignee, creator, due date, resolution notes |
| RequestComment / RequestHistory | linked to request; actor, event_type, timestamps |
| Invoice | id, organization_id, customer_id, invoice_number, status, issue/due date, currency, subtotal, tax_total, discount_total, total, created_by |
| InvoiceLineItem | id, invoice_id, description, quantity, unit_price, line_total |
| Payment | id, invoice_id, amount, payment_date, method, reference, notes, recorded_by |
| ActivityLog | id, organization_id, actor_id, action, entity_type, entity_id, metadata, created_at |
| Notification | id, organization_id, recipient_id, type, title, body, entity_type, entity_id, read_at, created_at |
| AIReport | id, organization_id, report_type, period_start, period_end, metrics_snapshot, summary, recommendations, model/provider metadata |
| Attachment | metadata for uploaded files, linked to its entity |

### 10.2 Key relationships

- User **1:N** Membership; Organization **1:N** Membership.
- Organization **1:N** Departments, Customers, Tasks, Requests, Invoices, ActivityLogs, Notifications, AIReports.
- Department **1:N** EmployeeProfiles.
- Task **1:N** TaskComments, TaskHistory.
- Customer **1:N** CustomerRequests, Invoices.
- Invoice **1:N** InvoiceLineItems, Payments.

### 10.3 Data integrity rules

1. Every organization-owned child record carries its organization ID.
2. Related records (customer, employee, department, invoice, task...) must belong to the *same* organization — validated in application logic and enforced with foreign keys/constraints.
3. Use database transactions for multi-record operations, especially financial ones.
4. Use decimal/numeric types for money — never floating point.
5. Use soft deletion/archiving where business history must survive (customers, employees); never cascade-delete financial or audit history without an approved retention policy.

---

## 11. API design

Base path `/api/v1`. JSON everywhere, consistent response envelope, pagination on all list endpoints.

**Success:**
```json
{
  "success": true,
  "message": "Task created successfully",
  "data": { "id": "uuid", "title": "Prepare monthly report" }
}
```

**Error:**
```json
{
  "success": false,
  "message": "Validation failed",
  "errors": { "due_date": "Due date cannot be earlier than start date" }
}
```

### 11.1 Endpoint outline

| Module | Method | Endpoint |
|---|---|---|
| Auth | POST | `/auth/register` |
| Auth | POST | `/auth/login` |
| Auth | POST | `/auth/logout` |
| Auth | GET | `/auth/me` |
| Organizations | GET/POST/PATCH | `/organizations`, `/organizations/{id}` |
| Memberships | GET/POST/PATCH | `/organizations/{id}/members`, `/organizations/{id}/invitations` |
| Departments | GET/POST/PATCH/DELETE | `/organizations/{id}/departments[/{dept_id}]` |
| Employees | GET/POST/PATCH | `/organizations/{id}/employees[/{emp_id}]` |
| Tasks | GET/POST/PATCH | `/organizations/{id}/tasks[/{task_id}]`, `/assign`, `/status`, `/comments`, `/history` |
| Customers | GET/POST/PATCH | `/organizations/{id}/customers[/{customer_id}]` |
| Requests | GET/POST/PATCH | `/organizations/{id}/requests[/{request_id}]`, `/assign`, `/status`, `/comments`, `/history` |
| Invoices | GET/POST/PATCH | `/organizations/{id}/invoices[/{invoice_id}]`, `/issue`, `/cancel`, `/payments`, `/pdf` |
| Analytics | GET | `/organizations/{id}/analytics/overview|tasks|requests|finance` |
| Activity | GET | `/organizations/{id}/activity` |
| Notifications | GET/POST | `/organizations/{id}/notifications[/{id}/read]`, `/read-all` |
| AI Reports | GET/POST | `/organizations/{id}/ai-reports[/{id}]`, `/generate` |

### 11.2 Conventions

- `200` read/update success · `201` created · `204` success, no body.
- `400` malformed input · `401` unauthenticated · `403` unauthorized · `404` missing/inaccessible · `409` conflict · `422` semantic validation (if adopted).
- Standard error shape: `{"error":{"code":"VALIDATION_ERROR","message":"...","details":{}}}`.
- List endpoints support `page`, `per_page`, sort, and filter params.
- All input is validated server-side; never trust client-submitted totals or calculations.
- Never expose stack traces or secrets in responses.

---

## 12. Frontend experience

### 12.1 Design direction
Clean, modern, professional — closer to a polished commercial SaaS product than a generic admin template. Light theme primary, dark theme optional.

The visual language is a business ledger: a deep-green desk blotter (the sidebar) beside sheets of paper (the page and its cards), ink-green for actions, and tabular numerals so figures line up in columns. The active sidebar item is drawn as a paper filing tab that opens into the page. Typeface: Schibsted Grotesk (400–700). Tokens live in `frontend/src/index.css` (OKLCH, built in tweakcn); the hex values below are their equivalents.

| Element | Color |
|---|---|
| Primary (ink green) | `#1E6A4E` |
| Secondary | `#E2EAE4` |
| Background (paper) | `#F1F3EE` |
| Sidebar (blotter) | `#163A2D` |
| Sidebar hover | `#21503F` |
| Cards | `#FBFCF9` |
| Muted text | `#5A6570` |
| Borders / inputs | `#D7DDD4` / `#CBD3C8` |
| Success | `#2E7A52` |
| Warning | `#D6A43A` |
| Danger | `#B3362C` |
| Chart in-progress (ink blue) | `#3F6E8C` |
| Main text | `#1C2631` |

### 12.2 Layout
- **Sidebar:** Overview, Employees, Departments, Tasks, Customers, Requests, Invoices, Analytics, AI Reports, Activity, Settings.
- **Top bar:** search, notifications, current organization switcher, user profile, theme selector.
- **Main content:** page title, contextual actions, stat cards, tables/charts, filters.
- Navigation is permission-aware; hidden actions are a UX nicety, never the security boundary.

### 12.3 Role-specific dashboards
- **Owner:** business stats, financial overview, employee performance, overdue tasks, AI weekly summary.
- **Manager:** team workload, task progress, pending reviews, request queue, department-level activity.
- **Employee:** my tasks, upcoming deadlines, overdue tasks, recent activity, notifications.
- **Accountant:** invoices, outstanding balances, payments, monthly collections.
- **Customer Support:** open/waiting requests, assignments, response workload.

Dashboard totals always come from the analytics API — never reimplemented client-side.

### 12.4 UX requirements
Responsive (desktop/tablet/mobile) · loading skeletons · empty states · error states · confirmation dialogs for destructive actions · inline form validation · search/filtering · consistent status indicators (never color alone) · toast notifications · reusable components · consistent date/currency formatting · keyboard-operable forms and visible focus states.

---

## 13. Non-functional requirements

| ID | Requirement |
|---|---|
| NFR-001 | Passwords hashed with a modern, maintained algorithm. |
| NFR-002 | All production traffic uses HTTPS/TLS. |
| NFR-003 | Organization data remains fully isolated. |
| NFR-004 | Every backend endpoint validates role + organization membership. |
| NFR-005 | All input validated server-side. |
| NFR-006 | Financial operations use database transactions. |
| NFR-007 | API errors never leak internal details. |
| NFR-008 | Important operations are logged (never secrets). |
| NFR-009 | Database backups are supported and documented. |
| NFR-010 | Large collections are paginated. |
| NFR-011 | The application is responsive across viewport sizes. |
| NFR-012 | AI requests respect user permissions and org boundaries. |
| NFR-013 | Secrets live in environment variables / secret management only. |
| NFR-014 | Tests cover critical business rules and permissions. |
| NFR-015 | Migrations are version-controlled. |

**Security checklist:** RBAC · organization-level authorization · secure token/cookie handling with CSRF protection · auth rate limiting · input validation · SQL-injection protection via parameterized ORM calls · secure file-upload validation · audit logging · environment-based secrets.

**Critical security test scenarios (mandatory):**

| Scenario | Expected result |
|---|---|
| Employee opens another employee's restricted data | `403` |
| Business A accesses Business B's task | `404` |
| Employee tries to change their own role | `403` |
| Unauthorized user accesses invoices | `403` |
| User accesses an expired invitation | Rejected |
| User submits an invalid payment | `400` |
| User submits a duplicate payment request | No duplicate transaction created |
| AI attempts to access another organization's data | Denied |

---

## 14. Background jobs

Use Celery + Redis, introduced only once background processing is actually needed.

| Job | Trigger |
|---|---|
| Upcoming task-deadline reminders | Scheduled daily |
| Overdue task detection | Scheduled daily |
| Overdue invoice detection/notification | Scheduled daily |
| Invitation expiry handling | Scheduled |
| Weekly business/AI summary | Once per week, per organization, in the org's own timezone |
| Report export generation | On demand |

Jobs must be idempotent, organization-scoped, retry-safe, and observable via logs. A failed AI provider call must never corrupt business data or produce a false "successful" report.

---

## 15. Testing strategy

**Backend (Pytest):** auth, authorization, organization isolation, employee management, task lifecycle, customer requests, invoice calculations, partial payments, notifications, analytics accuracy, AI report generation, scheduled-job retries.

**Frontend (Vitest + React Testing Library + Playwright):** login/registration, role-based navigation, form validation, dashboard rendering, task/invoice workflows, mobile layouts, accessibility checks for core screens.

**Quality gates:** tests run from documented commands · no task is "done" just because code exists · migrations tested from a clean database · critical regressions block release · tenant isolation and financial calculations are never covered by mocks alone.

---

## 16. Seed data & demo credentials

Generate fictional data for one organization:

- 1 Owner · 2 Managers · 1 Accountant · 1 Customer Support user · 8 Employees · 4 Departments
- 30 tasks (varied statuses/priorities/due dates) · 12 customers · 20 customer requests (varied statuses)
- 15 invoices (varied lifecycle states) with multiple full/partial payments
- ~50 activity-log records and notifications across different users/dates

Use clearly fictional names/emails only. Document demo credentials per role for development — never expose demo passwords in production.

---

## 17. Deployment

| Component | Hosting |
|---|---|
| React frontend | Vercel |
| Flask API | Render (or equivalent) |
| PostgreSQL | Managed provider |
| Redis | Managed provider (once Celery is enabled) |
| Uploaded files | S3-compatible storage |
| AI API | External provider, swappable |
| Version control / CI | GitHub + GitHub Actions |

Also required: Dockerfile(s) + Docker Compose for local dev, `.env.example`, separate dev/staging/prod environment variables, a controlled migration step, HTTPS + CORS/CSRF config, health checks, logging, and documented backup/restore/rollback procedures. The whole app must be reproducible from a clean checkout using only documented commands.

---

## 18. Scope management

**V1 — must build:** Authentication, Organizations, RBAC, Employees, Departments, Tasks, Customers, Customer Requests, Invoices, Payments, Analytics, Notifications, Activity Logs, AI weekly summaries.

**V2 — later:** AI conversational assistant, email notifications, calendar integration, advanced task automation, custom workflow configuration, recurring tasks, document management, advanced report builder, multiple business locations, subscription management.

**Explicitly out of scope:** full accounting software, payroll, banking integrations, inventory management, complex HR, video conferencing, internal chat, e-commerce, native mobile apps.

---

## 19. Definition of Done

A module/task is Done only when:

- Its stated scope is implemented — no placeholder pages or stubbed functionality marked complete.
- Database models + migrations exist and apply cleanly.
- Backend endpoints work with permissions and input validation enforced.
- Frontend pages exist with loading/empty/error states.
- Relevant automated tests pass; no critical regression introduced.
- API/schema/architecture documentation is updated.
- The feature works against realistic seed data and alongside existing modules.
- Code is reviewed and committed; task status is updated with evidence.

The product as a whole is complete only when all V1 modules work together as one integrated system — not as independent demo pages.

---

# Part II — Development Backlog & Execution Plan

## 20. Backlog structure

**9 epics · 65 development tasks · dependency-driven, test-driven delivery.**

| Level | Meaning | Example |
|---|---|---|
| Epic | Major product area | Task Management |
| Story | User-facing capability | Assign a task |
| Task | Independently implementable work | Create assignment endpoint |
| Acceptance criteria | Conditions for completion | Assignment persists and permissions are enforced |

Every task has: a unique ID, description, priority, dependencies, implementation requirements, acceptance criteria, testing requirements, and a definition of done.

**Priority definitions**
- **P0** — Essential infrastructure/security, release-blocking.
- **P1** — Required for the first usable (V1) release.
- **P2** — Important enhancement, not a V1 blocker.
- **P3** — Optional / future.

**Task status definitions:** Backlog → Ready → In Progress → In Review → Blocked → Done.

**Execution rules for the AI agent**
1. Never start a task while its dependencies are incomplete.
2. Complete and test backend functionality before wiring the frontend.
3. Never implement placeholder functionality and call it complete.
4. Never skip acceptance criteria.
5. Run regression tests after modifying shared functionality.
6. Update documentation whenever an API, model, or architecture decision changes.
7. Keep a record of completed tasks and their test results.
8. Don't start the next epic while the current one has unresolved critical failures.

## 21. Dependency map

```
E01 Foundation
  └─ E02 Authentication & Organizations
       ├─ E03 Employees & Departments
       │    ├─ E04 Task Management
       │    └─ E05 Customers & Requests ── E06 Invoices & Payments
       │                                         │
       └─────────────────── E07 Analytics & Notifications (consumes E03–E06)
                                   │
                              E08 AI Business Assistant (uses verified analytics)
                                   │
                          E09 Integration, QA & Deployment
```
E05 and E06 can be developed in parallel after E02 (with E03 available for employee-assignment relationships). E07 requires the modules it reports on.

---

## 22. Epic E01 — Project Foundation
*Goal: architecture, dev environment, database infrastructure, coding standards. Depends on: nothing.*

| ID | Task | Priority | Depends on |
|---|---|---|---|
| FD-001 | Initialize repository (backend/frontend/docs dirs, `.gitignore`, README, branch/commit conventions) | P0 | — |
| FD-002 | Configure Flask application (factory, per-env config, blueprints, central error handling, `/api/v1/health`) | P0 | FD-001 |
| FD-003 | Configure React frontend (TS strict, Vite, Router, TanStack Query, Tailwind + shadcn/ui) | P0 | FD-001 |
| FD-004 | Configure PostgreSQL + SQLAlchemy (connection, sessions, pooling, health check) | P0 | FD-002 |
| FD-005 | Configure database migrations (Flask-Migrate/Alembic, naming convention, initial migration) | P0 | FD-004 |
| FD-006 | Configure development infrastructure (Docker Compose: Postgres + Redis, env files) | P1 | FD-003, FD-004 |
| FD-007 | Establish API conventions & docs (versioning, response/error/pagination format, OpenAPI) | P1 | FD-002 |

**Key acceptance criteria:** backend/frontend in separate dirs; no secrets committed; `GET /api/v1/health` returns 200; TS build succeeds; Postgres connects via env vars; a clean DB can be built from migrations alone; API conventions documented and demonstrated on a real endpoint.

---

## 23. Epic E02 — Authentication & Organizations
*Goal: secure accounts, workspaces, memberships, permissions. Depends on: E01.*

| ID | Task | Priority | Depends on |
|---|---|---|---|
| FD-008 | Create User model (UUID, name, email unique, password hash, status, timestamps) | P0 | FD-005 |
| FD-009 | Implement registration (validation, hashing, duplicate-email handling) | P0 | FD-008 |
| FD-010 | Implement login/logout (secure session/cookie auth, auth middleware, failure handling) | P0 | FD-009 |
| FD-011 | Implement `GET /auth/me` (profile + memberships, 401 if unauthenticated) | P0 | FD-010 |
| FD-012 | Create Organization model + Membership model (role, status, unique org/user pair) | P0 | FD-005, FD-008 |
| FD-013 | Implement organization creation (creator becomes Owner, transactional) | P0 | FD-012, FD-010 |
| FD-014 | Implement organization membership (multi-org support, active/inactive status) | P0 | FD-013 |
| FD-015 | Implement RBAC (centralized permission definitions/decorators, object-level checks) | P0 | FD-014 |
| FD-016 | Implement employee invitations (secure expiring tokens, acceptance, cancellation) | P1 | FD-015 |
| FD-017 | Build authentication frontend (login/register, protected routes, auth state) | P0 | FD-003, FD-009, FD-010, FD-011 |
| FD-018 | Build organization onboarding (creation flow, org switcher) | P1 | FD-013, FD-017 |

**Key acceptance criteria:** duplicate email → `409`; invalid credentials → `401`; cross-tenant membership listing rejected; every protected endpoint checks membership + capability (unauthorized → `403`); invitation tokens unpredictable, expiring, single-use; frontend never treats route visibility as a security boundary.

---

## 24. Epic E03 — Employee and Department Management
*Depends on: E02.*

| ID | Task | Priority | Depends on |
|---|---|---|---|
| FD-019 | Create Department model (org-scoped, manager reference) | P1 | FD-012 |
| FD-020 | Create Employee profile model (linked to membership, department, manager) | P1 | FD-014, FD-019 |
| FD-021 | Implement department CRUD (list/create/update/deactivate, safe-deletion policy) | P1 | FD-019, FD-015 |
| FD-022 | Implement employee directory API (search, filters, pagination, safe fields only) | P1 | FD-020 |
| FD-023 | Implement employee profile & status management (deactivation doesn't break history) | P1 | FD-022 |
| FD-024 | Build employee frontend (directory, profile, department management) | P1 | FD-017, FD-021, FD-022, FD-023 |

**Key acceptance criteria:** department/employee references always validated against the same organization; inactive employees can't be newly assigned work but keep historical task ownership; cross-tenant IDs are inaccessible.

---

## 25. Epic E04 — Task Management and Workflows
*Depends on: E02, E03.*

| ID | Task | Priority | Depends on |
|---|---|---|---|
| FD-025 | Create Task, TaskComment, TaskHistory models (with indexes) | P1 | FD-020 |
| FD-026 | Implement task creation/retrieval (pagination, filters) | P1 | FD-025, FD-015 |
| FD-027 | Implement task assignment/reassignment (validated assignee, history) | P1 | FD-026 |
| FD-028 | Implement task status workflow (To Do → In Progress → Under Review → Completed; Cancelled terminal) | P1 | FD-026 |
| FD-029 | Implement task editing & deadlines (date validation, history on change) | P1 | FD-026 |
| FD-030 | Implement task comments (access-restricted, author + timestamp) | P1 | FD-026 |
| FD-031 | Implement task history (chronological, append-only) | P1 | FD-027, FD-028, FD-029 |
| FD-032 | Build task frontend (list/board/calendar/"My Tasks", assignment, comments, history) | P1 | FD-026–FD-031 |
| FD-033 | Implement overdue detection (timezone-aware, excludes terminal statuses) | P1 | FD-028, FD-029 |

**Key acceptance criteria:** invalid status transitions rejected with a clear error; assignee/creator always validated same-organization; reassignment keeps prior assignments in history; overdue calc is timezone-documented and tested at the rollover boundary.

---

## 26. Epic E05 — Customer and Request Management
*Depends on: E02, E03.*

| ID | Task | Priority | Depends on |
|---|---|---|---|
| FD-034 | Create Customer model (org-scoped, search indexes) | P1 | FD-012 |
| FD-035 | Implement customer CRUD (search, pagination, archive) | P1 | FD-034, FD-015 |
| FD-036 | Create CustomerRequest, RequestComment, RequestHistory models | P1 | FD-034, FD-020 |
| FD-037 | Implement request workflow (New → Assigned → In Progress → Waiting for Customer → Resolved → Closed) | P1 | FD-036 |
| FD-038 | Implement request comments & history (internal comments never customer-exposed) | P1 | FD-036, FD-037 |
| FD-039 | Build customer & request frontend (directory, profile, queue, assignment, status controls) | P1 | FD-035, FD-037, FD-038 |

**Key acceptance criteria:** archived customers stay linked to historical requests/invoices; only permitted status transitions succeed; unauthorized users can't close requests.

---

## 27. Epic E06 — Invoice and Payment Management
*Depends on: E02, E05.*

| ID | Task | Priority | Depends on |
|---|---|---|---|
| FD-040 | Create Invoice, InvoiceLineItem, Payment models (decimal money types, unique invoice number per org) | P1 | FD-034, FD-005 |
| FD-041 | Implement invoice calculations (line totals, subtotal, tax/discount, grand total — server-authoritative) | P1 | FD-040 |
| FD-042 | Implement invoice lifecycle (Draft/Sent/Partially Paid/Paid/Overdue/Cancelled; controlled editing) | P1 | FD-041, FD-015 |
| FD-043 | Implement payment recording (partial payments, transactional balance update, idempotent) | P1 | FD-042 |
| FD-044 | Implement financial API & reports (invoiced/collected/outstanding, scoped by permission) | P1 | FD-043 |
| FD-045 | Implement invoice PDF generation (logo, line items, totals, payment status) | P1 | FD-042 |
| FD-046 | Build invoice frontend (editor, payment form, balance/status refresh, PDF access) | P1 | FD-042, FD-043, FD-044, FD-045 |

**Key acceptance criteria:** all money arithmetic is decimal, never floating point; client-submitted totals are never authoritative; total payments can never exceed the outstanding balance absent an approved overpayment policy; issuing an invoice locks or controls financial edits per policy.

---

## 28. Epic E07 — Analytics, Activity History and Notifications
*Depends on: E03, E04, E05, E06.*

| ID | Task | Priority | Depends on |
|---|---|---|---|
| FD-047 | Implement centralized activity logging (shared service, safe metadata only) | P1 | FD-015 |
| FD-048 | Implement notification infrastructure (model, recipient-scoped, read/unread) | P1 | FD-015, FD-047 |
| FD-049 | Implement event-based notifications (assignment, workflow, payment events; no duplicate delivery) | P1 | FD-027, FD-028, FD-037, FD-043, FD-048 |
| FD-050 | Build notification frontend (center, unread count, mark read, navigate to record) | P1 | FD-048 |
| FD-051 | Implement analytics service (deterministic metrics, explicit periods, org-scoped) | P1 | FD-033, FD-035, FD-037, FD-044 |
| FD-052 | Implement analytics API (overview/employee/department/finance endpoints, date filters) | P1 | FD-051 |
| FD-053 | Build dashboards & analytics frontend (role-specific layouts, charts from real API data) | P1 | FD-052 |
| FD-054 | Implement CSV/PDF report export (same filters/permissions as analytics API; sanitized CSV) | P2 | FD-052 |

**Key acceptance criteria:** metrics reconcile with independently verified database fixtures; no fabricated trends when comparison data is missing; financial metrics never shown to unauthorized roles; retried operations never create duplicate notifications.

---

## 29. Epic E08 — AI Business Assistant
*Depends on: FD-051, FD-052.*

| ID | Task | Priority | Depends on |
|---|---|---|---|
| FD-055 | Design AI reporting service (provider abstraction, input/output contract, timeout/retry rules) | P1 | FD-051 |
| FD-056 | Implement weekly metrics aggregation (idempotent snapshot per organization) | P1 | FD-051 |
| FD-057 | Implement AI weekly summary generation (narrative + recommendations from the snapshot only) | P1 | FD-055, FD-056 |
| FD-058 | Implement AI report persistence (store report + snapshot + generation metadata) | P1 | FD-057 |
| FD-059 | Implement scheduled AI reports (Celery Beat, per-org timezone, retry-safe, no duplicates) | P1 | FD-006, FD-058 |
| FD-060 | Build AI reports frontend (list, detail, period, findings, recommendations clearly labeled advisory) | P1 | FD-058 |
| FD-061 | Implement conversational AI assistant (permission-aware tools, no unapproved writes) | P2 | FD-057, FD-060 |

**Key acceptance criteria:** AI never queries the database directly and never receives another organization's data; output schema is validated; a failed generation never produces a misleading "successful" report; one organization's failure never blocks another's report.

---

## 30. Epic E09 — Integration, QA and Deployment
*Depends on: all required V1 epics.*

| ID | Task | Priority | Depends on |
|---|---|---|---|
| FD-062 | Backend integration testing (full workflows, tenant isolation, financial transactions, analytics) | P0 | E02–E08 core backend tasks |
| FD-063 | Frontend integration & E2E testing (critical journeys, role restrictions, responsiveness) | P0 | FD-062 |
| FD-064 | Security & performance review (auth, authz, isolation, input handling, query efficiency, secrets) | P0 | FD-062, FD-063 |
| FD-065 | Production deployment & documentation (deploy, HTTPS, migrations, backups, README) | P0 | FD-064 |

**Key acceptance criteria:** no unresolved critical cross-tenant access issue; critical user journeys pass end-to-end; production has no dev secrets; README covers setup, testing, and deployment end to end.

---

## 31. Global completion requirements

Every task must satisfy, before being marked Done:

1. Implementation matches scope — no unrelated features added.
2. All acceptance criteria verified.
3. Relevant automated tests pass; no critical regression introduced.
4. Authorization and tenant isolation tested where applicable.
5. Documentation updated (API, schema, architecture, config).
6. Changes committed to version control.
7. Task status updated with implementation evidence (exact test commands + results).

**Release acceptance criteria for V1:**
- All P0/P1 V1 tasks are Done.
- All nine epics pass their release acceptance checks.
- A user can complete the full customer → request → task → invoice → payment workflow.
- Role permissions work correctly; organization data stays isolated.
- Analytics reflect actual database records; weekly AI reports use verified metrics.
- Automated tests pass; deployment and setup docs are complete.

P2/P3 work is never a blocker for V1.

---

## 32. AI coding-agent execution protocol

For every task:

1. **Select** — choose the highest-priority Ready task whose dependencies are Done.
2. **Inspect** — review existing repository structure, models, routes, services, tests.
3. **Clarify** — surface ambiguity or conflicts before making consequential assumptions; don't silently guess on security, money, or retention behavior.
4. **Plan** — list intended changes: files, data/API impact, test plan.
5. **Implement** — only the selected task plus necessary supporting changes.
6. **Test** — run unit, integration, and regression tests relevant to the task.
7. **Review** — check authorization, tenant isolation, validation, error handling, data integrity, maintainability.
8. **Document** — update relevant docs and migration notes.
9. **Report** — summarize changes, exact test commands/results, limitations, and the next unblocked task.
10. **Complete** — mark Done only once every acceptance criterion is verified.

### Mandatory development rules
1. Follow the approved PRD and architecture; document any deviation before making it.
2. Never skip database migrations.
3. Never duplicate business logic between frontend and backend — the backend is the source of truth.
4. Never trust frontend role checks as authorization.
5. Every organization-owned record is protected by organization-level authorization.
6. Use service layers for complex business operations; keep route handlers thin.
7. Write tests for every critical business rule, including negative/unauthorized/cross-tenant cases.
8. Never hardcode credentials or API keys — environment variables only.
9. Preserve backward compatibility when modifying existing endpoints.
10. Never mark a task complete without actually running its tests.

### Completion report template
For each task/phase, report: what was implemented; files created/modified; database changes; API endpoints added; tests executed and their exact results; known bugs/limitations; remaining work; whether the next task can safely begin.

---

## 33. First task to hand the agent

Do not start with authentication or the dashboard — start with **FD-001** and move through the foundation sequentially.

> You are working on FlowDesk, a multi-tenant business-operations SaaS application. This specification and backlog are the source of truth.
>
> **Your assigned task is FD-001 — Initialize repository. Implement FD-001 only.**
>
> First inspect the existing workspace and determine whether a repository or project files already exist. Preserve all existing work — do not overwrite, delete, rename, or reorganize files without explaining why and getting approval.
>
> Establish the initial structure for the approved Flask backend and React + TypeScript frontend. Add a `.gitignore`, a root README describing the product and architecture, and an `.env.example` with placeholder variable names only — no real secrets. If Git is already initialized, don't reinitialize it.
>
> Do not implement Flask behavior, database models, authentication, API endpoints, or frontend features — those belong to later tasks.
>
> Before editing, present the repository structure you intend to create and flag any existing files that must be preserved. Then implement the approved FD-001 scope.
>
> **Verify:** structure is clear; `.gitignore` excludes envs/dependencies/build output/caches/local DBs/secrets; `.env.example` has no real secrets; README explains the project; existing files are preserved.
>
> Report: files created/changed, files preserved, validation commands run and their exact results, any unresolved issue, and whether every FD-001 acceptance criterion passed.
>
> Do not mark FD-001 Done unless every acceptance criterion is verified. Do not begin FD-002 or any later task.

---

# Part III — Governance

## 34. Change-control rules

- This document is the baseline specification. Changes are explicit, reviewed, and reflected in the relevant requirement IDs and backlog tasks.
- A permission/role change requires updating the permission matrix and authorization tests.
- A workflow change requires updating transition rules, API behavior, UI controls, and tests.
- A financial-calculation change requires documented formulas, decimal/rounding rules, and regression tests.
- A tenant-scoping change requires cross-tenant security tests.
- A new feature is classified V1 or later and gets its own independently testable backlog task(s).

## 35. Open decisions to resolve before the affected implementation

The agent must not invent these — they're deliberate decision points for the product owner:

1. Exact required business-profile fields for an organization.
2. Whether registration requires email verification in V1.
3. Final authentication mechanism and deployment-specific CSRF/session configuration.
4. Invitation delivery provider and email templates.
5. Currency policy — single default currency per organization, or multi-currency invoices.
6. Tax/discount rules and rounding precision for invoices.
7. Whether issued invoices can only be voided, or also corrected via credit-note-like records.
8. Whether employees may create tasks, or only update ones assigned to them.
9. Exact permissions wherever the baseline matrix says "limited" or "as explicitly granted."
10. Data retention/deletion policy for organizations, customers, invoices, and audit logs.
11. Weekly-report day/time and behavior when an organization has insufficient data.
12. AI provider, budget limits, privacy terms, and model selection.
13. Production hosting choices, domains, backup retention, and recovery objectives.

## 36. Why this project is a strong portfolio piece

| Area | Complexity |
|---|---|
| React frontend | Medium–High |
| Flask backend | High |
| Database architecture | High |
| Authentication & security | High |
| Business workflows | High |
| Analytics | Medium |
| AI integration | Medium–High |
| Deployment | Medium |

**Skills it demonstrates:** full-stack development, REST API architecture, relational database design, authentication & RBAC, multi-tenancy, financial data handling, background processing, AI integration grounded in real data, automated testing, deployment/DevOps.

**What makes it stand out:**
1. **Multi-tenancy from day one** — two businesses on one platform, provably unable to see each other's data.
2. **Real audit history** — exactly who changed what, when.
3. **AI grounded in actual data** — an analytical assistant, not a generic chatbot.
4. **Genuinely distinct role experiences** — Owner/Manager/Accountant/Employee should feel like different apps sharing one platform.
5. **One realistic end-to-end workflow**, e.g.: customer submits a request → support logs it → manager assigns it → employee completes it → manager resolves it → accountant invoices it → payment is recorded → analytics reflect it → the AI weekly summary mentions it. One flow, six modules, real integration.

## 37. Final implementation principle

Build FlowDesk as a secure, tenant-isolated, modular business application in small, verifiable increments. Prioritize correctness of permissions, workflows, and financial records over visual polish or extra AI features — the AI assistant is only valuable once the underlying operational data is trustworthy. Make the AI weekly summary the final major V1 feature, built once the data beneath it is reliable.
