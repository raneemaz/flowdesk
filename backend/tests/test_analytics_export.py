import uuid
from datetime import date
from decimal import Decimal

import pytest

from app.analytics.export import _csv_from_sections, _sanitize_csv_cell, build_overview_export
from app.extensions import db
from app.models import (
    Customer,
    CustomerRequest,
    Department,
    EmployeeProfile,
    Invoice,
    InvoiceLineItem,
    Membership,
    MembershipRole,
    MembershipStatus,
    Organization,
    Payment,
    Task,
    TaskHistory,
    User,
)


@pytest.fixture(autouse=True)
def _clean(app):
    yield
    with app.app_context():
        db.session.query(Payment).delete()
        db.session.query(InvoiceLineItem).delete()
        db.session.query(Invoice).delete()
        db.session.query(TaskHistory).delete()
        db.session.query(Task).delete()
        db.session.query(CustomerRequest).delete()
        db.session.query(Customer).delete()
        db.session.query(EmployeeProfile).delete()
        db.session.query(Department).delete()
        db.session.query(Membership).delete()
        db.session.query(Organization).delete()
        db.session.query(User).delete()
        db.session.commit()


def _login(client, email, password="correct horse battery"):
    login_response = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    return login_response.get_json()["data"]["csrf_token"]


def _register_and_login(client, email, name="Test User", password="correct horse battery"):
    client.post("/api/v1/auth/register", json={"name": name, "email": email, "password": password})
    return _login(client, email, password)


def _create_org(client, csrf_token, name="Org One"):
    return client.post("/api/v1/organizations", json={"name": name}, headers={"X-CSRF-Token": csrf_token}).get_json()[
        "data"
    ]


def _give_role(app, organization_id, email, role, status=MembershipStatus.ACTIVE):
    with app.app_context():
        user = db.session.query(User).filter_by(email=email.lower()).one()
        membership = Membership(organization_id=organization_id, user_id=user.id, role=role, status=status)
        db.session.add(membership)
        db.session.commit()
        return str(membership.id)


def _membership_id(app, organization_id, email):
    with app.app_context():
        user = db.session.query(User).filter_by(email=email.lower()).one()
        membership = (
            db.session.query(Membership).filter_by(organization_id=uuid.UUID(organization_id), user_id=user.id).one()
        )
        return str(membership.id)


def _make_department(app, organization_id, name="Support"):
    with app.app_context():
        department = Department(organization_id=uuid.UUID(organization_id), name=name)
        db.session.add(department)
        db.session.commit()
        return str(department.id)


# --- CSV injection sanitization (unit-level) --------------------------------


@pytest.mark.parametrize("dangerous", ["=SUM(A1:A9)", "+1+1", "-1+1", "@SUM(1,2)", "\tHello", "\rHello"])
def test_sanitize_csv_cell_escapes_formula_prefixes(dangerous):
    assert _sanitize_csv_cell(dangerous) == "'" + dangerous


@pytest.mark.parametrize("safe", ["Ada Lovelace", "42", "Support", "", None])
def test_sanitize_csv_cell_leaves_safe_values_alone(safe):
    expected = "" if safe is None else str(safe)
    assert _sanitize_csv_cell(safe) == expected


def test_csv_from_sections_sanitizes_every_data_cell_not_the_header():
    csv_text = _csv_from_sections([("Title", ["Name", "Note"], [["=EVIL()", "fine"]])])
    assert "'=EVIL()" in csv_text
    assert "\nName,Note\n" in csv_text or "Name,Note\r\n" in csv_text


def test_csv_from_sections_starts_with_a_utf8_bom():
    csv_text = _csv_from_sections([("Title", ["A"], [["1"]])])
    assert csv_text.startswith("﻿")


def test_build_overview_export_csv_contains_the_metric_values():
    metrics = {
        "period_start": date(2026, 1, 1),
        "period_end": date(2026, 1, 31),
        "employee_count": 3,
        "active_tasks": 5,
        "completed_tasks": 2,
        "overdue_tasks": 1,
        "open_requests": 4,
        "monthly_invoiced": Decimal("1000.00"),
        "monthly_collected": Decimal("250.50"),
    }

    csv_text = build_overview_export(metrics, "Acme Inc", "csv")

    assert "3" in csv_text
    assert "1000.00" in csv_text
    assert "250.50" in csv_text


def test_build_overview_export_pdf_is_a_real_pdf():
    metrics = {
        "period_start": date(2026, 1, 1),
        "period_end": date(2026, 1, 31),
        "employee_count": 3,
        "active_tasks": 5,
        "completed_tasks": 2,
        "overdue_tasks": 1,
        "open_requests": 4,
        "monthly_invoiced": Decimal("1000.00"),
        "monthly_collected": Decimal("250.50"),
    }

    pdf_bytes = build_overview_export(metrics, "Acme Inc", "pdf")

    assert pdf_bytes.startswith(b"%PDF")


# ---------------------------------------------------------------------------
# Route-level - mirrors test_analytics_routes.py's own permission matrix for
# each of the four JSON endpoints, since every export route reuses the exact
# same service call and scope/role gating.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("fmt", ["csv", "pdf"])
def test_owner_can_export_overview(client, app, fmt):
    csrf_token = _register_and_login(client, f"owner-ov-{fmt}@example.com")
    org = _create_org(client, csrf_token)

    response = client.get(
        f"/api/v1/organizations/{org['id']}/analytics/overview/export?period=current_month&format={fmt}",
        headers={"X-CSRF-Token": csrf_token},
    )

    assert response.status_code == 200
    if fmt == "csv":
        assert response.content_type.startswith("text/csv")
        assert response.data.decode("utf-8-sig").startswith("Overview")
    else:
        assert response.content_type == "application/pdf"
        assert response.data.startswith(b"%PDF")
    assert "attachment" in response.headers["Content-Disposition"]


def test_employee_cannot_export_overview(client, app):
    csrf_token = _register_and_login(client, "owner-ov-emp@example.com")
    org = _create_org(client, csrf_token)
    _register_and_login(client, "employee-ov-emp@example.com", name="Employee")
    _give_role(app, org["id"], "employee-ov-emp@example.com", MembershipRole.EMPLOYEE)
    employee_csrf = _login(client, "employee-ov-emp@example.com")

    response = client.get(
        f"/api/v1/organizations/{org['id']}/analytics/overview/export?period=current_month&format=csv",
        headers={"X-CSRF-Token": employee_csrf},
    )

    assert response.status_code == 403


def test_export_rejects_an_invalid_format_value(client, app):
    csrf_token = _register_and_login(client, "owner-badfmt@example.com")
    org = _create_org(client, csrf_token)

    response = client.get(
        f"/api/v1/organizations/{org['id']}/analytics/overview/export?period=current_month&format=xlsx",
        headers={"X-CSRF-Token": csrf_token},
    )

    assert response.status_code == 422


def test_export_rejects_a_custom_period_missing_bounds(client, app):
    csrf_token = _register_and_login(client, "owner-badperiod@example.com")
    org = _create_org(client, csrf_token)

    response = client.get(
        f"/api/v1/organizations/{org['id']}/analytics/overview/export?period=custom&format=csv",
        headers={"X-CSRF-Token": csrf_token},
    )

    assert response.status_code == 422


def test_owner_can_export_every_employees_performance_csv(client, app):
    csrf_token = _register_and_login(client, "owner-emp-export@example.com")
    org = _create_org(client, csrf_token)
    _register_and_login(client, "employee-emp-export@example.com", name="Employee Export")
    csrf_token = _login(client, "owner-emp-export@example.com")

    response = client.get(
        f"/api/v1/organizations/{org['id']}/analytics/employees/export?period=current_month&format=csv",
        headers={"X-CSRF-Token": csrf_token},
    )

    assert response.status_code == 200
    body = response.data.decode("utf-8-sig")
    assert "Employee performance" in body
    assert "Test User" in body  # the owner's own registered display name


def test_owner_gets_404_exporting_a_cross_org_target_membership(client, app):
    owner_a_csrf = _register_and_login(client, "owner-exp-a@example.com")
    org_a = _create_org(client, owner_a_csrf, name="Org A")
    owner_b_csrf = _register_and_login(client, "owner-exp-b@example.com")
    org_b = _create_org(client, owner_b_csrf, name="Org B")
    other_org_membership_id = _membership_id(app, org_b["id"], "owner-exp-b@example.com")
    owner_a_csrf = _login(client, "owner-exp-a@example.com")

    response = client.get(
        f"/api/v1/organizations/{org_a['id']}/analytics/employees/export"
        f"?period=current_month&format=csv&target_membership_id={other_org_membership_id}",
        headers={"X-CSRF-Token": owner_a_csrf},
    )

    assert response.status_code == 404


def test_employee_is_forced_to_their_own_performance_when_exporting(client, app):
    csrf_token = _register_and_login(client, "owner-emp-force@example.com")
    org = _create_org(client, csrf_token)
    _register_and_login(client, "employeea-force@example.com", name="Employee A")
    employee_a_id = _give_role(app, org["id"], "employeea-force@example.com", MembershipRole.EMPLOYEE)
    _register_and_login(client, "employeeb-force@example.com", name="Employee B")
    employee_b_id = _give_role(app, org["id"], "employeeb-force@example.com", MembershipRole.EMPLOYEE)
    employee_a_csrf = _login(client, "employeea-force@example.com")

    response = client.get(
        f"/api/v1/organizations/{org['id']}/analytics/employees/export"
        f"?period=current_month&format=csv&target_membership_id={employee_b_id}",
        headers={"X-CSRF-Token": employee_a_csrf},
    )

    assert response.status_code == 200
    body = response.data.decode("utf-8-sig")
    assert "Employee A" in body
    assert "Employee B" not in body
    assert employee_a_id  # sanity: fixture actually created a distinct membership


def test_customer_support_cannot_export_employee_performance(client, app):
    csrf_token = _register_and_login(client, "owner-support-exp@example.com")
    org = _create_org(client, csrf_token)
    _register_and_login(client, "support-exp@example.com", name="Support")
    _give_role(app, org["id"], "support-exp@example.com", MembershipRole.CUSTOMER_SUPPORT)
    support_csrf = _login(client, "support-exp@example.com")

    response = client.get(
        f"/api/v1/organizations/{org['id']}/analytics/employees/export?period=current_month&format=csv",
        headers={"X-CSRF-Token": support_csrf},
    )

    assert response.status_code == 403


def test_owner_can_export_department_analytics_including_unassigned_bucket(client, app):
    csrf_token = _register_and_login(client, "owner-dept-exp@example.com")
    org = _create_org(client, csrf_token)
    _make_department(app, org["id"], "Support")

    response = client.get(
        f"/api/v1/organizations/{org['id']}/analytics/departments/export?period=current_month&format=csv",
        headers={"X-CSRF-Token": csrf_token},
    )

    assert response.status_code == 200
    body = response.data.decode("utf-8-sig")
    assert "Support" in body
    assert "No department" in body


def test_owner_gets_404_exporting_a_cross_org_department(client, app):
    owner_a_csrf = _register_and_login(client, "owner-dept-a@example.com")
    org_a = _create_org(client, owner_a_csrf, name="Org A")
    owner_b_csrf = _register_and_login(client, "owner-dept-b@example.com")
    org_b = _create_org(client, owner_b_csrf, name="Org B")
    other_org_department_id = _make_department(app, org_b["id"], "Finance")
    owner_a_csrf = _login(client, "owner-dept-a@example.com")

    response = client.get(
        f"/api/v1/organizations/{org_a['id']}/analytics/departments/export"
        f"?period=current_month&format=csv&department_id={other_org_department_id}",
        headers={"X-CSRF-Token": owner_a_csrf},
    )

    assert response.status_code == 404


def test_employee_cannot_export_department_analytics(client, app):
    csrf_token = _register_and_login(client, "owner-dept-emp@example.com")
    org = _create_org(client, csrf_token)
    _register_and_login(client, "employee-dept-emp@example.com", name="Employee")
    _give_role(app, org["id"], "employee-dept-emp@example.com", MembershipRole.EMPLOYEE)
    employee_csrf = _login(client, "employee-dept-emp@example.com")

    response = client.get(
        f"/api/v1/organizations/{org['id']}/analytics/departments/export?period=current_month&format=csv",
        headers={"X-CSRF-Token": employee_csrf},
    )

    assert response.status_code == 403


def test_owner_can_export_financial_report_csv(client, app):
    csrf_token = _register_and_login(client, "owner-fin-exp@example.com")
    org = _create_org(client, csrf_token)

    response = client.get(
        f"/api/v1/organizations/{org['id']}/analytics/finance/export?period=current_month&format=csv",
        headers={"X-CSRF-Token": csrf_token},
    )

    assert response.status_code == 200
    body = response.data.decode("utf-8-sig")
    assert "Financial summary" in body
    assert "Revenue by day" in body
    assert "Invoice distribution" in body
    assert "Recent payments" in body


def test_owner_can_export_financial_report_pdf(client, app):
    csrf_token = _register_and_login(client, "owner-fin-pdf@example.com")
    org = _create_org(client, csrf_token)

    response = client.get(
        f"/api/v1/organizations/{org['id']}/analytics/finance/export?period=current_month&format=pdf",
        headers={"X-CSRF-Token": csrf_token},
    )

    assert response.status_code == 200
    assert response.content_type == "application/pdf"
    assert response.data.startswith(b"%PDF")


def test_accountant_can_export_financial_report(client, app):
    csrf_token = _register_and_login(client, "owner-fin-acct@example.com")
    org = _create_org(client, csrf_token)
    _register_and_login(client, "accountant-fin-acct@example.com", name="Accountant")
    _give_role(app, org["id"], "accountant-fin-acct@example.com", MembershipRole.ACCOUNTANT)
    accountant_csrf = _login(client, "accountant-fin-acct@example.com")

    response = client.get(
        f"/api/v1/organizations/{org['id']}/analytics/finance/export?period=current_month&format=csv",
        headers={"X-CSRF-Token": accountant_csrf},
    )

    assert response.status_code == 200


def test_customer_support_cannot_export_financial_report(client, app):
    csrf_token = _register_and_login(client, "owner-fin-support@example.com")
    org = _create_org(client, csrf_token)
    _register_and_login(client, "support-fin-support@example.com", name="Support")
    _give_role(app, org["id"], "support-fin-support@example.com", MembershipRole.CUSTOMER_SUPPORT)
    support_csrf = _login(client, "support-fin-support@example.com")

    response = client.get(
        f"/api/v1/organizations/{org['id']}/analytics/finance/export?period=current_month&format=csv",
        headers={"X-CSRF-Token": support_csrf},
    )

    assert response.status_code == 403


def test_a_non_member_cannot_export_a_foreign_organizations_analytics(client, app):
    owner_a_csrf = _register_and_login(client, "owner-nonmember-a@example.com")
    org_a = _create_org(client, owner_a_csrf, name="Org A")
    owner_b_csrf = _register_and_login(client, "owner-nonmember-b@example.com")
    _create_org(client, owner_b_csrf, name="Org B")

    response = client.get(
        f"/api/v1/organizations/{org_a['id']}/analytics/overview/export?period=current_month&format=csv",
        headers={"X-CSRF-Token": owner_b_csrf},
    )

    assert response.status_code == 404


def test_unauthenticated_export_request_returns_401(client):
    response = client.get(
        "/api/v1/organizations/00000000-0000-0000-0000-000000000000/analytics/overview/export?period=current_month&format=csv"
    )
    assert response.status_code == 401


def test_a_name_starting_with_a_formula_character_is_sanitized_in_the_actual_csv_response(client, app):
    """End-to-end version of the unit-level CSV injection tests above -
    a department whose own display name starts with `=` must still be
    defused (prefixed with `'`) in the real HTTP response body, not
    just in the unit-tested builder function."""
    csrf_token = _register_and_login(client, "owner-csvinjection@example.com")
    org = _create_org(client, csrf_token)
    _make_department(app, org["id"], "=cmd|'/c calc'!A1")

    response = client.get(
        f"/api/v1/organizations/{org['id']}/analytics/departments/export?period=current_month&format=csv",
        headers={"X-CSRF-Token": csrf_token},
    )

    assert response.status_code == 200
    body = response.data.decode("utf-8-sig")
    assert "'=cmd|'/c calc'!A1" in body
