import uuid
from datetime import date

import pytest

from app.ai_assistant.tools import TOOL_DEFINITIONS, execute_tool
from app.authz.permissions import MembershipRole, PermissionScope
from app.extensions import db
from app.models import (
    Customer,
    CustomerStatus,
    Department,
    DepartmentStatus,
    DiscountType,
    EmployeeProfile,
    Invoice,
    InvoiceStatus,
    Membership,
    MembershipStatus,
    Organization,
    Payment,
    Task,
    TaskStatus,
    User,
)

from decimal import Decimal


@pytest.fixture(autouse=True)
def _clean(app):
    yield
    with app.app_context():
        db.session.query(Payment).delete()
        db.session.query(Invoice).delete()
        db.session.query(Task).delete()
        db.session.query(Customer).delete()
        db.session.query(EmployeeProfile).delete()
        db.session.query(Department).delete()
        db.session.query(Membership).delete()
        db.session.query(Organization).delete()
        db.session.query(User).delete()
        db.session.commit()


def _make_org(slug="org-assistant-tools"):
    org = Organization(name="Acme Inc", slug=slug, timezone="UTC")
    db.session.add(org)
    db.session.commit()
    return org


def _make_membership(org, email, role=MembershipRole.OWNER, name=None):
    user = User(name=name or email.split("@")[0], email=email)
    user.set_password("correct horse battery")
    db.session.add(user)
    db.session.commit()
    membership = Membership(organization_id=org.id, user_id=user.id, role=role, status=MembershipStatus.ACTIVE)
    db.session.add(membership)
    db.session.commit()
    return membership


def test_tool_definitions_cover_the_four_analytics_categories():
    names = {tool.name for tool in TOOL_DEFINITIONS}
    assert names == {
        "get_overview_metrics",
        "get_employee_performance",
        "get_department_analytics",
        "get_financial_analytics",
    }


def test_tool_definitions_expose_no_write_capability():
    """No tool name/description implies any create/edit/delete
    capability - this task's own "no unapproved writes" is satisfied
    by there simply being no such tool, which this test pins down."""
    for tool in TOOL_DEFINITIONS:
        for verb in ("create", "update", "delete", "edit", "cancel", "issue", "record"):
            assert verb not in tool.name.lower()
            assert verb not in tool.description.lower()


# --- execute_tool: permission-aware behavior --------------------------------


def test_execute_tool_returns_real_data_for_full_scope(app):
    with app.app_context():
        org = _make_org("org-tools-full")
        owner = _make_membership(org, "owner-tools-full@example.com")
        db.session.add(Task(organization_id=org.id, creator_membership_id=owner.id, title="t", status=TaskStatus.TODO))
        db.session.commit()

        result = execute_tool(
            "get_overview_metrics",
            {"period": "current_month"},
            organization=org,
            scope=PermissionScope.FULL,
            role=MembershipRole.OWNER,
            caller_membership_id=owner.id,
        )

        assert "error" not in result
        assert result["active_tasks"] == 1
        assert result["employee_count"] == 1


def test_execute_tool_returns_an_error_for_a_disallowed_scope(app):
    with app.app_context():
        org = _make_org("org-tools-denied")
        owner = _make_membership(org, "owner-tools-denied@example.com")

        # get_overview_metrics requires FULL scope - OWN (Employee) must
        # not see real data, and must not raise either.
        result = execute_tool(
            "get_overview_metrics",
            {"period": "current_month"},
            organization=org,
            scope=PermissionScope.OWN,
            role=MembershipRole.EMPLOYEE,
            caller_membership_id=owner.id,
        )

        assert "error" in result
        assert "active_tasks" not in result


def test_execute_tool_employee_performance_forces_own_scope_to_the_caller(app):
    with app.app_context():
        org = _make_org("org-tools-own")
        owner = _make_membership(org, "owner-tools-own@example.com", name="Owner")
        employee = _make_membership(org, "employee-tools-own@example.com", role=MembershipRole.EMPLOYEE, name="Employee")

        result = execute_tool(
            "get_employee_performance",
            {"period": "current_month"},
            organization=org,
            scope=PermissionScope.OWN,
            role=MembershipRole.EMPLOYEE,
            caller_membership_id=employee.id,
        )

        assert "error" not in result
        assert len(result["employees"]) == 1
        assert result["employees"][0]["membership_id"] == str(employee.id)
        assert result["employees"][0]["name"] == "Employee"


def test_execute_tool_financial_analytics_allows_accountant(app):
    with app.app_context():
        org = _make_org("org-tools-accountant")
        owner = _make_membership(org, "owner-tools-accountant@example.com")

        result = execute_tool(
            "get_financial_analytics",
            {"period": "current_month"},
            organization=org,
            scope=PermissionScope.LIMITED,
            role=MembershipRole.ACCOUNTANT,
            caller_membership_id=owner.id,
        )

        assert "error" not in result
        assert "total_invoiced" in result


def test_execute_tool_financial_analytics_denies_limited_scope_for_a_non_accountant_role(app):
    with app.app_context():
        org = _make_org("org-tools-support")
        owner = _make_membership(org, "owner-tools-support@example.com")

        result = execute_tool(
            "get_financial_analytics",
            {"period": "current_month"},
            organization=org,
            scope=PermissionScope.LIMITED,
            role=MembershipRole.CUSTOMER_SUPPORT,
            caller_membership_id=owner.id,
        )

        assert "error" in result


def test_execute_tool_department_analytics_requires_full_scope(app):
    with app.app_context():
        org = _make_org("org-tools-dept")
        owner = _make_membership(org, "owner-tools-dept@example.com")
        db.session.add(Department(organization_id=org.id, name="Support", status=DepartmentStatus.ACTIVE))
        db.session.commit()

        full_result = execute_tool(
            "get_department_analytics",
            {"period": "current_month"},
            organization=org,
            scope=PermissionScope.FULL,
            role=MembershipRole.OWNER,
            caller_membership_id=owner.id,
        )
        denied_result = execute_tool(
            "get_department_analytics",
            {"period": "current_month"},
            organization=org,
            scope=PermissionScope.LIMITED,
            role=MembershipRole.ACCOUNTANT,
            caller_membership_id=owner.id,
        )

        assert "error" not in full_result
        assert any(row["department_name"] == "Support" for row in full_result["departments"])
        assert "error" in denied_result


def test_execute_tool_returns_an_error_for_an_unknown_tool_name(app):
    with app.app_context():
        org = _make_org("org-tools-unknown")
        owner = _make_membership(org, "owner-tools-unknown@example.com")

        result = execute_tool(
            "delete_everything",
            {"period": "current_month"},
            organization=org,
            scope=PermissionScope.FULL,
            role=MembershipRole.OWNER,
            caller_membership_id=owner.id,
        )

        assert "error" in result


def test_execute_tool_returns_an_error_for_an_invalid_custom_period_instead_of_raising(app):
    with app.app_context():
        org = _make_org("org-tools-badperiod")
        owner = _make_membership(org, "owner-tools-badperiod@example.com")

        result = execute_tool(
            "get_overview_metrics",
            {"period": "custom"},  # missing period_start/period_end
            organization=org,
            scope=PermissionScope.FULL,
            role=MembershipRole.OWNER,
            caller_membership_id=owner.id,
        )

        assert "error" in result


def test_execute_tool_financial_analytics_never_includes_recent_payments(app):
    """recent_payments is deliberately omitted (module docstring) -
    the assistant answers aggregate questions, not "list my payments"."""
    with app.app_context():
        org = _make_org("org-tools-nopayments")
        owner = _make_membership(org, "owner-tools-nopayments@example.com")
        customer = Customer(organization_id=org.id, name="Cust", status=CustomerStatus.ACTIVE)
        db.session.add(customer)
        db.session.commit()
        invoice = Invoice(
            organization_id=org.id,
            customer_id=customer.id,
            invoice_number="INV-0001",
            status=InvoiceStatus.PAID,
            currency="USD",
            discount_type=DiscountType.FLAT,
            discount_value=Decimal("0.00"),
            total=Decimal("100.00"),
            created_by=owner.id,
        )
        db.session.add(invoice)
        db.session.commit()
        db.session.add(
            Payment(
                organization_id=org.id,
                invoice_id=invoice.id,
                amount=Decimal("100.00"),
                payment_date=date(2026, 1, 15),
                method="cash",
                idempotency_key=uuid.uuid4().hex,
                recorded_by=owner.id,
            )
        )
        db.session.commit()

        result = execute_tool(
            "get_financial_analytics",
            {"period": "custom", "period_start": "2026-01-01", "period_end": "2026-01-31"},
            organization=org,
            scope=PermissionScope.FULL,
            role=MembershipRole.OWNER,
            caller_membership_id=owner.id,
        )

        assert "recent_payments" not in result
        assert result["total_collected"] == "100.00"
