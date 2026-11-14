from app.authz.permissions import Permission, PermissionScope, ROLE_PERMISSIONS
from app.models import MembershipRole


def test_every_role_has_an_explicit_scope_for_every_permission():
    """No implicit defaults - Section 7.3's "implement permissions
    centrally" means every (role, permission) pair is a deliberate,
    recorded decision, not an accidental KeyError waiting to happen."""
    for role in MembershipRole:
        assert role in ROLE_PERMISSIONS
        for permission in Permission:
            assert permission in ROLE_PERMISSIONS[role], f"{role} is missing a scope for {permission}"


def test_owner_has_full_scope_for_every_permission():
    for permission in Permission:
        assert ROLE_PERMISSIONS[MembershipRole.OWNER][permission] == PermissionScope.FULL


def test_manager_cannot_manage_invoices_or_view_financial_reports():
    assert ROLE_PERMISSIONS[MembershipRole.MANAGER][Permission.INVOICE_PAYMENT_MANAGE] == PermissionScope.NONE
    assert ROLE_PERMISSIONS[MembershipRole.MANAGER][Permission.FINANCIAL_REPORTS_VIEW] == PermissionScope.NONE


def test_manager_organization_settings_and_membership_management_are_limited():
    assert (
        ROLE_PERMISSIONS[MembershipRole.MANAGER][Permission.ORGANIZATION_SETTINGS_MANAGE] == PermissionScope.LIMITED
    )
    assert ROLE_PERMISSIONS[MembershipRole.MANAGER][Permission.MEMBERSHIP_MANAGE] == PermissionScope.LIMITED


def test_employee_cannot_create_or_assign_tasks_but_can_act_on_assigned_ones():
    """Resolves Section 35 open decision #8."""
    assert ROLE_PERMISSIONS[MembershipRole.EMPLOYEE][Permission.TASK_CREATE_ASSIGN] == PermissionScope.NONE
    assert ROLE_PERMISSIONS[MembershipRole.EMPLOYEE][Permission.TASK_VIEW_UPDATE] == PermissionScope.ASSIGNED


def test_employee_has_no_access_to_organization_or_membership_management():
    assert (
        ROLE_PERMISSIONS[MembershipRole.EMPLOYEE][Permission.ORGANIZATION_SETTINGS_MANAGE] == PermissionScope.NONE
    )
    assert ROLE_PERMISSIONS[MembershipRole.EMPLOYEE][Permission.MEMBERSHIP_MANAGE] == PermissionScope.NONE


def test_employee_has_no_customer_management_access():
    assert ROLE_PERMISSIONS[MembershipRole.EMPLOYEE][Permission.CUSTOMER_MANAGE] == PermissionScope.NONE


def test_employee_analytics_and_activity_history_are_scoped_to_own():
    assert ROLE_PERMISSIONS[MembershipRole.EMPLOYEE][Permission.ANALYTICS_VIEW] == PermissionScope.OWN
    assert ROLE_PERMISSIONS[MembershipRole.EMPLOYEE][Permission.ACTIVITY_HISTORY_VIEW] == PermissionScope.OWN


def test_accountant_has_full_financial_access_but_no_membership_or_department_management():
    assert ROLE_PERMISSIONS[MembershipRole.ACCOUNTANT][Permission.INVOICE_PAYMENT_MANAGE] == PermissionScope.FULL
    assert ROLE_PERMISSIONS[MembershipRole.ACCOUNTANT][Permission.FINANCIAL_REPORTS_VIEW] == PermissionScope.FULL
    assert ROLE_PERMISSIONS[MembershipRole.ACCOUNTANT][Permission.MEMBERSHIP_MANAGE] == PermissionScope.NONE
    assert ROLE_PERMISSIONS[MembershipRole.ACCOUNTANT][Permission.DEPARTMENT_MANAGE] == PermissionScope.NONE


def test_accountant_cannot_manage_customer_requests():
    assert ROLE_PERMISSIONS[MembershipRole.ACCOUNTANT][Permission.CUSTOMER_REQUEST_MANAGE] == PermissionScope.NONE


def test_customer_support_has_full_customer_and_request_access_but_no_financial_access():
    assert ROLE_PERMISSIONS[MembershipRole.CUSTOMER_SUPPORT][Permission.CUSTOMER_MANAGE] == PermissionScope.FULL
    assert (
        ROLE_PERMISSIONS[MembershipRole.CUSTOMER_SUPPORT][Permission.CUSTOMER_REQUEST_MANAGE]
        == PermissionScope.FULL
    )
    assert (
        ROLE_PERMISSIONS[MembershipRole.CUSTOMER_SUPPORT][Permission.INVOICE_PAYMENT_MANAGE]
        == PermissionScope.NONE
    )


def test_employee_directory_view_is_full_for_owner_and_manager_limited_for_everyone_else():
    assert ROLE_PERMISSIONS[MembershipRole.OWNER][Permission.EMPLOYEE_DIRECTORY_VIEW] == PermissionScope.FULL
    assert ROLE_PERMISSIONS[MembershipRole.MANAGER][Permission.EMPLOYEE_DIRECTORY_VIEW] == PermissionScope.FULL
    for role in (MembershipRole.EMPLOYEE, MembershipRole.ACCOUNTANT, MembershipRole.CUSTOMER_SUPPORT):
        assert ROLE_PERMISSIONS[role][Permission.EMPLOYEE_DIRECTORY_VIEW] == PermissionScope.LIMITED


def test_employee_manage_is_full_for_owner_limited_for_manager_none_for_everyone_else():
    """FD-023 addition - editing a profile/status is Owner/Manager
    only, with Manager's reach further restricted (see
    can_manage_employee_profile), unlike DEPARTMENT_MANAGE's
    unrestricted full/full/none/none/none shape."""
    assert ROLE_PERMISSIONS[MembershipRole.OWNER][Permission.EMPLOYEE_MANAGE] == PermissionScope.FULL
    assert ROLE_PERMISSIONS[MembershipRole.MANAGER][Permission.EMPLOYEE_MANAGE] == PermissionScope.LIMITED
    for role in (MembershipRole.EMPLOYEE, MembershipRole.ACCOUNTANT, MembershipRole.CUSTOMER_SUPPORT):
        assert ROLE_PERMISSIONS[role][Permission.EMPLOYEE_MANAGE] == PermissionScope.NONE
