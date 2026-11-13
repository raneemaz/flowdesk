---
name: tenant-isolation-check
description: Use this skill whenever a new or changed API endpoint, model, or service in FlowDesk touches organization-scoped data. It runs the spec's mandatory security test scenarios (Section 13) to catch cross-tenant data leaks and privilege escalation before a task is marked Done.
---

# Tenant Isolation Check

FlowDesk's core promise (Spec Section 36) is that two organizations on the platform can provably never see each other's data. Run this checklist against any endpoint or service that reads or writes an organization-scoped record (tasks, customers, requests, invoices, payments, employees, departments, activity, notifications, AI reports).

## Mandatory security test scenarios (Spec Section 13)

For the endpoint(s) under review, verify each applicable scenario and record the actual result:

| Scenario | Expected result |
|---|---|
| Employee opens another employee's restricted data | `403` |
| Organization A's authenticated user requests Organization B's record by ID | `404` (never `403` - don't confirm the record exists) |
| Employee tries to change their own role | `403` |
| Unauthorized role accesses invoices/financial data | `403` |
| User accesses an expired or already-used invitation token | Rejected |
| User submits an invalid payment (wrong currency, negative amount, exceeds outstanding balance) | `400` |
| User submits a duplicate/retried payment request | No duplicate transaction created |
| AI report generation attempts to access another organization's data | Denied - AI service never queries the DB directly and never receives cross-org data |

## How to check it, concretely

1. **Find every query** in the changed code that fetches an organization-scoped model by ID. Confirm each one filters by the active organization membership - not just by primary key.
2. **Find every write** (create/update/delete) on an organization-scoped model. Confirm the organization_id is set from the authenticated session/membership, never trusted from client input.
3. **Check the permission layer** (Spec Section 7.3, 15) is the thing doing the authorization - not a route-local `if role == "owner"` check.
4. **Write or extend automated tests** for the scenarios above that apply to this endpoint, including the cross-tenant 404 case and the role-escalation 403 case. Mocks alone are not acceptable for tenant isolation per Section 15 - hit a real test database with two organizations' fixtures.
5. **Run the tests** and record pass/fail. A task touching organization-scoped data is not Done (Section 31, criterion 4) until this checklist is verified.

## Report

State plainly which scenarios from the table applied, which were tested, and the actual result of each - not just "looks fine."
