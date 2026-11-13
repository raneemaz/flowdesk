"""Centralized RBAC permission definitions (FD-015).

Resolves Section 35 open decision #9 ("exact permissions wherever the
baseline matrix says 'limited' or 'as explicitly granted'") and open
decision #8 ("whether employees may create tasks") against the baseline
matrix in spec Section 7.2. Every (role, permission) pair below is an
explicit, deliberate decision - nothing is left to an implicit default,
and nothing is scattered into route handlers (Section 7.3's mandatory
rule: "Implement permissions centrally").

These decisions were made now, ahead of the features they'll guard
(departments, tasks, customers, invoices, analytics, activity logs all
come in later tasks), at the user's explicit direction. The rationale
for each non-obvious scope is recorded next to the matrix entry it
resolves, so the task that eventually builds the concrete resource has a
precise contract to implement against.
"""

import enum

from app.models import MembershipRole


class Permission(str, enum.Enum):
    """One entry per capability row in spec Section 7.2."""

    ORGANIZATION_SETTINGS_MANAGE = "organization_settings_manage"
    MEMBERSHIP_MANAGE = "membership_manage"
    EMPLOYEE_DIRECTORY_VIEW = "employee_directory_view"
    DEPARTMENT_MANAGE = "department_manage"
    TASK_CREATE_ASSIGN = "task_create_assign"
    TASK_VIEW_UPDATE = "task_view_update"
    CUSTOMER_MANAGE = "customer_manage"
    CUSTOMER_REQUEST_MANAGE = "customer_request_manage"
    INVOICE_PAYMENT_MANAGE = "invoice_payment_manage"
    FINANCIAL_REPORTS_VIEW = "financial_reports_view"
    ANALYTICS_VIEW = "analytics_view"
    ACTIVITY_HISTORY_VIEW = "activity_history_view"


class PermissionScope(str, enum.Enum):
    """How far a granted permission reaches.

    app.authz.decorators.require_permission only checks whether a scope
    other than NONE is granted and hands the scope on via
    g.permission_scope - it has no knowledge of a resource that doesn't
    exist yet. The route/service layer for that specific resource is
    responsible for applying the scope's filtering (e.g. "only rows
    where assignee_id == caller" for ASSIGNED, or restricting which
    fields are returned/editable for LIMITED) once that resource exists.
    """

    FULL = "full"  # every record/field in the organization
    LIMITED = "limited"  # a defined subset - see the capability's own comment below
    OWN = "own"  # only the caller's own records
    ASSIGNED = "assigned"  # only records assigned to the caller
    NONE = "none"  # no access at all


# fmt: off
ROLE_PERMISSIONS: dict[MembershipRole, dict[Permission, PermissionScope]] = {
    MembershipRole.OWNER: {
        Permission.ORGANIZATION_SETTINGS_MANAGE: PermissionScope.FULL,
        Permission.MEMBERSHIP_MANAGE: PermissionScope.FULL,
        Permission.EMPLOYEE_DIRECTORY_VIEW: PermissionScope.FULL,
        Permission.DEPARTMENT_MANAGE: PermissionScope.FULL,
        Permission.TASK_CREATE_ASSIGN: PermissionScope.FULL,
        Permission.TASK_VIEW_UPDATE: PermissionScope.FULL,
        Permission.CUSTOMER_MANAGE: PermissionScope.FULL,
        Permission.CUSTOMER_REQUEST_MANAGE: PermissionScope.FULL,
        Permission.INVOICE_PAYMENT_MANAGE: PermissionScope.FULL,
        Permission.FINANCIAL_REPORTS_VIEW: PermissionScope.FULL,
        Permission.ANALYTICS_VIEW: PermissionScope.FULL,
        Permission.ACTIVITY_HISTORY_VIEW: PermissionScope.FULL,
    },
    MembershipRole.MANAGER: {
        # LIMITED: may edit logo/email/phone/address/date_format but not
        # name/slug/currency/timezone, and may never delete the org or
        # transfer ownership - those are identity/financial-impacting
        # fields reserved for the Owner.
        Permission.ORGANIZATION_SETTINGS_MANAGE: PermissionScope.LIMITED,
        # LIMITED ("as granted" in the spec): may invite members and
        # assign/change roles only among Employee/Accountant/
        # CustomerSupport, and only for a target whose *current* role is
        # also one of those three - can never touch an Owner or another
        # Manager, and can never promote anyone to Owner or Manager.
        # Self-role-change is forbidden for every role regardless of
        # scope (see app.authz.service.can_assign_role) per spec
        # Section 13's mandatory scenario ("Employee tries to change
        # their own role -> 403"), generalized here to every role.
        Permission.MEMBERSHIP_MANAGE: PermissionScope.LIMITED,
        Permission.EMPLOYEE_DIRECTORY_VIEW: PermissionScope.FULL,
        Permission.DEPARTMENT_MANAGE: PermissionScope.FULL,
        Permission.TASK_CREATE_ASSIGN: PermissionScope.FULL,
        Permission.TASK_VIEW_UPDATE: PermissionScope.FULL,
        Permission.CUSTOMER_MANAGE: PermissionScope.FULL,
        Permission.CUSTOMER_REQUEST_MANAGE: PermissionScope.FULL,
        Permission.INVOICE_PAYMENT_MANAGE: PermissionScope.NONE,
        Permission.FINANCIAL_REPORTS_VIEW: PermissionScope.NONE,
        Permission.ANALYTICS_VIEW: PermissionScope.FULL,
        Permission.ACTIVITY_HISTORY_VIEW: PermissionScope.FULL,
    },
    MembershipRole.EMPLOYEE: {
        Permission.ORGANIZATION_SETTINGS_MANAGE: PermissionScope.NONE,
        Permission.MEMBERSHIP_MANAGE: PermissionScope.NONE,
        # LIMITED: name/role/status of other active members only - never
        # another employee's email/phone/other contact details (that's
        # HR-adjacent data reserved for Owner/Manager).
        Permission.EMPLOYEE_DIRECTORY_VIEW: PermissionScope.LIMITED,
        Permission.DEPARTMENT_MANAGE: PermissionScope.NONE,
        # Resolves Section 35 open decision #8: employees may NOT create
        # or assign tasks in V1, only act on tasks already assigned to
        # them (TASK_VIEW_UPDATE below).
        Permission.TASK_CREATE_ASSIGN: PermissionScope.NONE,
        Permission.TASK_VIEW_UPDATE: PermissionScope.ASSIGNED,
        # Resolved toward the stricter reading of "Limited/No" (least
        # privilege, no stated business need): employees are not
        # customer-facing by default. Accountant/CustomerSupport already
        # cover the customer-facing and financial roles.
        Permission.CUSTOMER_MANAGE: PermissionScope.NONE,
        Permission.CUSTOMER_REQUEST_MANAGE: PermissionScope.ASSIGNED,
        Permission.INVOICE_PAYMENT_MANAGE: PermissionScope.NONE,
        Permission.FINANCIAL_REPORTS_VIEW: PermissionScope.NONE,
        # OWN: personal productivity analytics only (e.g. "my tasks this
        # week"), never an org-wide dashboard.
        Permission.ANALYTICS_VIEW: PermissionScope.OWN,
        # OWN: activity entries about the employee's own actions/records
        # only.
        Permission.ACTIVITY_HISTORY_VIEW: PermissionScope.OWN,
    },
    MembershipRole.ACCOUNTANT: {
        Permission.ORGANIZATION_SETTINGS_MANAGE: PermissionScope.NONE,
        Permission.MEMBERSHIP_MANAGE: PermissionScope.NONE,
        Permission.EMPLOYEE_DIRECTORY_VIEW: PermissionScope.LIMITED,
        Permission.DEPARTMENT_MANAGE: PermissionScope.NONE,
        Permission.TASK_CREATE_ASSIGN: PermissionScope.NONE,
        Permission.TASK_VIEW_UPDATE: PermissionScope.ASSIGNED,
        Permission.CUSTOMER_MANAGE: PermissionScope.FULL,
        Permission.CUSTOMER_REQUEST_MANAGE: PermissionScope.NONE,
        Permission.INVOICE_PAYMENT_MANAGE: PermissionScope.FULL,
        Permission.FINANCIAL_REPORTS_VIEW: PermissionScope.FULL,
        # LIMITED: the financial analytics subset (revenue, invoices,
        # payments trends) - not operational/task/employee analytics.
        Permission.ANALYTICS_VIEW: PermissionScope.LIMITED,
        # LIMITED: activity entries tied to invoices/payments/financial
        # records only.
        Permission.ACTIVITY_HISTORY_VIEW: PermissionScope.LIMITED,
    },
    MembershipRole.CUSTOMER_SUPPORT: {
        Permission.ORGANIZATION_SETTINGS_MANAGE: PermissionScope.NONE,
        Permission.MEMBERSHIP_MANAGE: PermissionScope.NONE,
        Permission.EMPLOYEE_DIRECTORY_VIEW: PermissionScope.LIMITED,
        Permission.DEPARTMENT_MANAGE: PermissionScope.NONE,
        Permission.TASK_CREATE_ASSIGN: PermissionScope.NONE,
        Permission.TASK_VIEW_UPDATE: PermissionScope.ASSIGNED,
        Permission.CUSTOMER_MANAGE: PermissionScope.FULL,
        Permission.CUSTOMER_REQUEST_MANAGE: PermissionScope.FULL,
        Permission.INVOICE_PAYMENT_MANAGE: PermissionScope.NONE,
        Permission.FINANCIAL_REPORTS_VIEW: PermissionScope.NONE,
        # LIMITED: the customer/request analytics subset (volume,
        # resolution time) - not financial or task-management analytics.
        Permission.ANALYTICS_VIEW: PermissionScope.LIMITED,
        # LIMITED: activity entries tied to customers/requests only.
        Permission.ACTIVITY_HISTORY_VIEW: PermissionScope.LIMITED,
    },
}
# fmt: on
