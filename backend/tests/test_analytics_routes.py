import uuid
from datetime import date, datetime, timedelta, timezone

import pytest

from app.analytics.service import resolve_period_filter
from app.errors import APIError
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


# --- resolve_period_filter (FR-034 taxonomy, unit-level) --------------------


def test_resolve_period_last_7_days_is_inclusive_of_today():
    now = datetime(2026, 1, 15, 12, 0, tzinfo=timezone.utc)
    period_start, period_end = resolve_period_filter("last_7_days", "UTC", now=now)
    assert period_end == date(2026, 1, 15)
    assert period_start == date(2026, 1, 15) - timedelta(days=6)


def test_resolve_period_last_30_days():
    now = datetime(2026, 1, 15, 12, 0, tzinfo=timezone.utc)
    period_start, period_end = resolve_period_filter("last_30_days", "UTC", now=now)
    assert period_end == date(2026, 1, 15)
    assert period_start == date(2026, 1, 15) - timedelta(days=29)


def test_resolve_period_last_90_days():
    now = datetime(2026, 1, 15, 12, 0, tzinfo=timezone.utc)
    period_start, period_end = resolve_period_filter("last_90_days", "UTC", now=now)
    assert period_end == date(2026, 1, 15)
    assert period_start == date(2026, 1, 15) - timedelta(days=89)


def test_resolve_period_current_month_is_full_calendar_month():
    now = datetime(2026, 2, 10, 12, 0, tzinfo=timezone.utc)
    period_start, period_end = resolve_period_filter("current_month", "UTC", now=now)
    assert (period_start, period_end) == (date(2026, 2, 1), date(2026, 2, 28))


def test_resolve_period_previous_month():
    now = datetime(2026, 2, 10, 12, 0, tzinfo=timezone.utc)
    period_start, period_end = resolve_period_filter("previous_month", "UTC", now=now)
    assert (period_start, period_end) == (date(2026, 1, 1), date(2026, 1, 31))


def test_resolve_period_previous_month_wraps_the_year_boundary():
    now = datetime(2026, 1, 10, 12, 0, tzinfo=timezone.utc)
    period_start, period_end = resolve_period_filter("previous_month", "UTC", now=now)
    assert (period_start, period_end) == (date(2025, 12, 1), date(2025, 12, 31))


def test_resolve_period_custom_passes_the_given_bounds_through():
    period_start, period_end = resolve_period_filter(
        "custom", "UTC", period_start=date(2026, 3, 1), period_end=date(2026, 3, 10)
    )
    assert (period_start, period_end) == (date(2026, 3, 1), date(2026, 3, 10))


def test_resolve_period_custom_without_bounds_raises():
    with pytest.raises(APIError) as exc_info:
        resolve_period_filter("custom", "UTC")
    assert exc_info.value.status_code == 422


def test_resolve_period_custom_inverted_bounds_raises():
    with pytest.raises(APIError) as exc_info:
        resolve_period_filter("custom", "UTC", period_start=date(2026, 3, 10), period_end=date(2026, 3, 1))
    assert exc_info.value.status_code == 422


def test_resolve_period_unknown_period_raises():
    with pytest.raises(APIError) as exc_info:
        resolve_period_filter("not_a_real_period", "UTC")
    assert exc_info.value.status_code == 422


# --- GET .../analytics/overview ---------------------------------------------


def test_unauthenticated_overview_request_returns_401(client):
    response = client.get("/api/v1/organizations/00000000-0000-0000-0000-000000000000/analytics/overview")
    assert response.status_code == 401


def test_owner_can_view_overview_analytics(client, app):
    csrf_token = _register_and_login(client, "owner1@example.com")
    org = _create_org(client, csrf_token)

    response = client.get(
        f"/api/v1/organizations/{org['id']}/analytics/overview?period=current_month",
        headers={"X-CSRF-Token": csrf_token},
    )

    assert response.status_code == 200
    data = response.get_json()["data"]
    assert data["employee_count"] == 1
    assert set(data) == {
        "period_start",
        "period_end",
        "employee_count",
        "active_tasks",
        "completed_tasks",
        "overdue_tasks",
        "open_requests",
        "monthly_invoiced",
        "monthly_collected",
    }


def test_employee_cannot_view_overview_analytics(client, app):
    csrf_token = _register_and_login(client, "owner2@example.com")
    org = _create_org(client, csrf_token)
    _register_and_login(client, "employee2@example.com", name="Employee Two")
    _give_role(app, org["id"], "employee2@example.com", MembershipRole.EMPLOYEE)
    employee_csrf = _login(client, "employee2@example.com")

    response = client.get(
        f"/api/v1/organizations/{org['id']}/analytics/overview?period=last_30_days",
        headers={"X-CSRF-Token": employee_csrf},
    )

    assert response.status_code == 403


def test_accountant_cannot_view_overview_analytics(client, app):
    csrf_token = _register_and_login(client, "owner3@example.com")
    org = _create_org(client, csrf_token)
    _register_and_login(client, "accountant3@example.com", name="Accountant Three")
    _give_role(app, org["id"], "accountant3@example.com", MembershipRole.ACCOUNTANT)
    accountant_csrf = _login(client, "accountant3@example.com")

    response = client.get(
        f"/api/v1/organizations/{org['id']}/analytics/overview?period=last_7_days",
        headers={"X-CSRF-Token": accountant_csrf},
    )

    assert response.status_code == 403


def test_overview_rejects_a_custom_period_missing_bounds(client, app):
    csrf_token = _register_and_login(client, "owner4@example.com")
    org = _create_org(client, csrf_token)

    response = client.get(
        f"/api/v1/organizations/{org['id']}/analytics/overview?period=custom",
        headers={"X-CSRF-Token": csrf_token},
    )

    assert response.status_code == 422


def test_overview_rejects_explicit_bounds_on_a_named_period(client, app):
    csrf_token = _register_and_login(client, "owner5@example.com")
    org = _create_org(client, csrf_token)

    response = client.get(
        f"/api/v1/organizations/{org['id']}/analytics/overview?period=last_7_days&period_start=2026-01-01&period_end=2026-01-07",
        headers={"X-CSRF-Token": csrf_token},
    )

    assert response.status_code == 422


def test_overview_rejects_an_unrecognized_period_value(client, app):
    csrf_token = _register_and_login(client, "owner6@example.com")
    org = _create_org(client, csrf_token)

    response = client.get(
        f"/api/v1/organizations/{org['id']}/analytics/overview?period=last_week",
        headers={"X-CSRF-Token": csrf_token},
    )

    assert response.status_code == 422


def test_overview_custom_period_returns_the_given_bounds(client, app):
    csrf_token = _register_and_login(client, "owner7@example.com")
    org = _create_org(client, csrf_token)

    response = client.get(
        f"/api/v1/organizations/{org['id']}/analytics/overview?period=custom&period_start=2026-01-01&period_end=2026-01-31",
        headers={"X-CSRF-Token": csrf_token},
    )

    assert response.status_code == 200
    data = response.get_json()["data"]
    assert data["period_start"] == "2026-01-01"
    assert data["period_end"] == "2026-01-31"


# --- GET .../analytics/employees ---------------------------------------------


def test_owner_can_view_every_employees_performance(client, app):
    csrf_token = _register_and_login(client, "owner8@example.com")
    org = _create_org(client, csrf_token)
    _register_and_login(client, "employee8@example.com", name="Employee Eight")
    _give_role(app, org["id"], "employee8@example.com", MembershipRole.EMPLOYEE)
    csrf_token = _login(client, "owner8@example.com")

    response = client.get(
        f"/api/v1/organizations/{org['id']}/analytics/employees?period=current_month",
        headers={"X-CSRF-Token": csrf_token},
    )

    assert response.status_code == 200
    data = response.get_json()["data"]
    assert len(data) == 2  # owner + employee, both active


def test_owner_can_scope_employee_performance_to_one_target(client, app):
    csrf_token = _register_and_login(client, "owner9@example.com")
    org = _create_org(client, csrf_token)
    _register_and_login(client, "employee9@example.com", name="Employee Nine")
    employee_id = _give_role(app, org["id"], "employee9@example.com", MembershipRole.EMPLOYEE)
    csrf_token = _login(client, "owner9@example.com")

    response = client.get(
        f"/api/v1/organizations/{org['id']}/analytics/employees?period=current_month&target_membership_id={employee_id}",
        headers={"X-CSRF-Token": csrf_token},
    )

    assert response.status_code == 200
    data = response.get_json()["data"]
    assert len(data) == 1
    assert data[0]["membership_id"] == employee_id


def test_owner_gets_404_for_a_target_membership_from_another_organization(client, app):
    owner_a_csrf = _register_and_login(client, "owner10a@example.com")
    org_a = _create_org(client, owner_a_csrf, name="Org A")
    owner_b_csrf = _register_and_login(client, "owner10b@example.com")
    org_b = _create_org(client, owner_b_csrf, name="Org B")
    other_org_membership_id = _membership_id(app, org_b["id"], "owner10b@example.com")
    owner_a_csrf = _login(client, "owner10a@example.com")

    response = client.get(
        f"/api/v1/organizations/{org_a['id']}/analytics/employees?period=current_month&target_membership_id={other_org_membership_id}",
        headers={"X-CSRF-Token": owner_a_csrf},
    )

    assert response.status_code == 404


def test_employee_is_forced_to_their_own_performance_even_if_another_target_is_requested(client, app):
    csrf_token = _register_and_login(client, "owner11@example.com")
    org = _create_org(client, csrf_token)
    _register_and_login(client, "employee11a@example.com", name="Employee A")
    employee_a_id = _give_role(app, org["id"], "employee11a@example.com", MembershipRole.EMPLOYEE)
    _register_and_login(client, "employee11b@example.com", name="Employee B")
    _give_role(app, org["id"], "employee11b@example.com", MembershipRole.EMPLOYEE)
    employee_a_csrf = _login(client, "employee11a@example.com")

    response = client.get(
        f"/api/v1/organizations/{org['id']}/analytics/employees?period=current_month&target_membership_id={employee_a_id}",
        headers={"X-CSRF-Token": employee_a_csrf},
    )

    assert response.status_code == 200
    data = response.get_json()["data"]
    assert len(data) == 1
    assert data[0]["membership_id"] == employee_a_id


def test_customer_support_cannot_view_employee_performance(client, app):
    csrf_token = _register_and_login(client, "owner12@example.com")
    org = _create_org(client, csrf_token)
    _register_and_login(client, "support12@example.com", name="Support Twelve")
    _give_role(app, org["id"], "support12@example.com", MembershipRole.CUSTOMER_SUPPORT)
    support_csrf = _login(client, "support12@example.com")

    response = client.get(
        f"/api/v1/organizations/{org['id']}/analytics/employees?period=current_month",
        headers={"X-CSRF-Token": support_csrf},
    )

    assert response.status_code == 403


# --- GET .../analytics/departments -------------------------------------------


def test_owner_can_view_department_analytics_including_unassigned_bucket(client, app):
    csrf_token = _register_and_login(client, "owner13@example.com")
    org = _create_org(client, csrf_token)
    _make_department(app, org["id"], "Support")

    response = client.get(
        f"/api/v1/organizations/{org['id']}/analytics/departments?period=current_month",
        headers={"X-CSRF-Token": csrf_token},
    )

    assert response.status_code == 200
    data = response.get_json()["data"]
    assert len(data) == 2  # the one real department + the unassigned bucket
    assert any(row["department_id"] is None for row in data)


def test_owner_gets_404_for_a_department_from_another_organization(client, app):
    owner_a_csrf = _register_and_login(client, "owner14a@example.com")
    org_a = _create_org(client, owner_a_csrf, name="Org A")
    owner_b_csrf = _register_and_login(client, "owner14b@example.com")
    org_b = _create_org(client, owner_b_csrf, name="Org B")
    other_org_department_id = _make_department(app, org_b["id"], "Finance")
    owner_a_csrf = _login(client, "owner14a@example.com")

    response = client.get(
        f"/api/v1/organizations/{org_a['id']}/analytics/departments?period=current_month&department_id={other_org_department_id}",
        headers={"X-CSRF-Token": owner_a_csrf},
    )

    assert response.status_code == 404


def test_employee_cannot_view_department_analytics(client, app):
    csrf_token = _register_and_login(client, "owner15@example.com")
    org = _create_org(client, csrf_token)
    _register_and_login(client, "employee15@example.com", name="Employee Fifteen")
    _give_role(app, org["id"], "employee15@example.com", MembershipRole.EMPLOYEE)
    employee_csrf = _login(client, "employee15@example.com")

    response = client.get(
        f"/api/v1/organizations/{org['id']}/analytics/departments?period=current_month",
        headers={"X-CSRF-Token": employee_csrf},
    )

    assert response.status_code == 403


# --- GET .../analytics/finance ------------------------------------------------


def test_owner_can_view_financial_analytics(client, app):
    csrf_token = _register_and_login(client, "owner16@example.com")
    org = _create_org(client, csrf_token)

    response = client.get(
        f"/api/v1/organizations/{org['id']}/analytics/finance?period=current_month",
        headers={"X-CSRF-Token": csrf_token},
    )

    assert response.status_code == 200
    data = response.get_json()["data"]
    assert "revenue_by_day" in data
    assert "invoice_distribution" in data
    assert "total_invoiced" in data


def test_accountant_can_view_financial_analytics(client, app):
    csrf_token = _register_and_login(client, "owner17@example.com")
    org = _create_org(client, csrf_token)
    _register_and_login(client, "accountant17@example.com", name="Accountant Seventeen")
    _give_role(app, org["id"], "accountant17@example.com", MembershipRole.ACCOUNTANT)
    accountant_csrf = _login(client, "accountant17@example.com")

    response = client.get(
        f"/api/v1/organizations/{org['id']}/analytics/finance?period=current_month",
        headers={"X-CSRF-Token": accountant_csrf},
    )

    assert response.status_code == 200


def test_customer_support_cannot_view_financial_analytics(client, app):
    csrf_token = _register_and_login(client, "owner18@example.com")
    org = _create_org(client, csrf_token)
    _register_and_login(client, "support18@example.com", name="Support Eighteen")
    _give_role(app, org["id"], "support18@example.com", MembershipRole.CUSTOMER_SUPPORT)
    support_csrf = _login(client, "support18@example.com")

    response = client.get(
        f"/api/v1/organizations/{org['id']}/analytics/finance?period=current_month",
        headers={"X-CSRF-Token": support_csrf},
    )

    assert response.status_code == 403


def test_employee_cannot_view_financial_analytics(client, app):
    csrf_token = _register_and_login(client, "owner19@example.com")
    org = _create_org(client, csrf_token)
    _register_and_login(client, "employee19@example.com", name="Employee Nineteen")
    _give_role(app, org["id"], "employee19@example.com", MembershipRole.EMPLOYEE)
    employee_csrf = _login(client, "employee19@example.com")

    response = client.get(
        f"/api/v1/organizations/{org['id']}/analytics/finance?period=current_month",
        headers={"X-CSRF-Token": employee_csrf},
    )

    assert response.status_code == 403


def test_a_non_member_cannot_view_a_foreign_organizations_analytics(client, app):
    owner_a_csrf = _register_and_login(client, "owner20a@example.com")
    org_a = _create_org(client, owner_a_csrf, name="Org A")
    owner_b_csrf = _register_and_login(client, "owner20b@example.com")
    _create_org(client, owner_b_csrf, name="Org B")

    response = client.get(
        f"/api/v1/organizations/{org_a['id']}/analytics/overview?period=current_month",
        headers={"X-CSRF-Token": owner_b_csrf},
    )

    assert response.status_code == 404
