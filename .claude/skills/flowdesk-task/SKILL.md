---
name: flowdesk-task
description: Use this skill for every FD-xxx backlog task in the FlowDesk project (docs/FlowDesk_Specification.md). It enforces the spec's mandatory 10-step execution protocol and completion-report template so every task gets the same rigor - Select, Inspect, Clarify, Plan, Implement, Test, Review, Document, Report, Complete.
---

# FlowDesk Task Runner

Follow this protocol for the single FD-xxx task you have been assigned. Treat `docs/FlowDesk_Specification.md` as the source of truth throughout - re-read the relevant section(s) for this task before starting.

## The 10 steps (Spec Section 32)

1. **Select** - Confirm the assigned task ID and that every task it depends on (see Section 21 dependency map and the task's own "Depends on" column) is already Done. If a dependency isn't Done, stop and say so instead of starting.
2. **Inspect** - Read the existing repository structure, relevant models, routes, services, and tests before writing anything. Don't assume - look.
3. **Clarify** - If the task touches one of the "Open decisions" in Section 35, or any other security/money/data-retention ambiguity not already pinned down earlier in the project, stop and ask the user. Never silently guess on these.
4. **Plan** - Before editing, state the files you intend to touch, the data/API impact, and the test plan.
5. **Implement** - Build only the assigned task's scope plus directly necessary supporting changes. No unrelated features, no work from later tasks "while you're in there."
6. **Test** - Run the unit/integration/regression tests relevant to this task. Never skip this step.
7. **Review** - Check authorization, tenant isolation, input validation, error handling, data integrity, and maintainability before calling it done. For anything touching organization-scoped data or money, invoke the tenant-security-reviewer / financial-integrity-reviewer subagents here.
8. **Document** - Update the relevant docs (API.md, DATABASE.md, ARCHITECTURE.md, migration notes) whenever an API, model, or architecture decision changes.
9. **Report** - Use the completion report template below.
10. **Complete** - Only mark the task Done once every one of its acceptance criteria is verified by an actual test run. "Code exists" is not "done."

## Mandatory rules (Spec Section 32) - never violate these

- Never implement placeholder/stub functionality and call it complete.
- Never skip an acceptance criterion.
- Never duplicate business logic between frontend and backend - backend is the source of truth.
- Never trust frontend role checks as authorization.
- Every organization-owned record must be protected by organization-level authorization.
- Use service layers for complex business logic; keep route handlers thin.
- Write tests for every critical business rule, including negative/unauthorized/cross-tenant cases.
- Never hardcode credentials or API keys.
- Preserve backward compatibility when modifying existing endpoints.
- Never mark a task complete without actually running its tests.

## Completion report template (Spec Section 32)

Report, for the task just finished:

- **What was implemented**
- **Files created/modified**
- **Database changes** (models, migrations)
- **API endpoints added/changed**
- **Tests executed and their exact results** (commands + pass/fail counts)
- **Known bugs/limitations**
- **Remaining work**
- **Whether the next task can safely begin**, and which task is next per the dependency map

Do not proceed to the next FD-xxx task until the user confirms.
