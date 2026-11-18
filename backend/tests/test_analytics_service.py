import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.analytics.service import (
    get_department_analytics,
    get_employee_performance,
    get_financial_analytics,
    get_overview_metrics,
)
from app.authz.permissions import PermissionScope
from app.errors import APIError
from app.extensions import db
from app.models import (
    CustomerRequest,
    Department,
    DepartmentStatus,
    DiscountType,
    EmployeeProfile,
    Invoice,
    InvoiceStatus,
    Membership,
    MembershipRole,
    MembershipStatus,
    Organization,
    Payment,
    RequestStatus,
    Task,
    TaskHistory,
    TaskStatus,
    User,
)


@pytest.fixture(autouse=True)
def _clean(app):
    yield
    with app.app_context():
        db.session.query(Payment).delete()
        db.session.query(Invoice).delete()
        db.session.query(TaskHistory).delete()
        db.session.query(Task).delete()
        db.session.query(CustomerRequest).delete()
        db.session.query(EmployeeProfile).delete()
        db.session.query(Department).delete()
        db.session.query(Membership).delete()
        db.session.query(Organization).delete()
        db.session.query(User).delete()
        db.session.commit()


def _make_org(slug="org-analytics"):
    org = Organization(name="Org", slug=slug)
    db.session.add(org)
    db.session.commit()
    return org


def _make_membership(org, email, role=MembershipRole.OWNER, status=MembershipStatus.ACTIVE):
    user = User(name=email.split("@")[0], email=email)
    user.set_password("correct horse battery")
    db.session.add(user)
    db.session.commit()
    membership = Membership(organization_id=org.id, user_id=user.id, role=role, status=status)
    db.session.add(membership)
    db.session.commit()
    return membership


def _make_task(org, creator, *, assignee=None, status=TaskStatus.TODO, due_date=None, created_at=None, department_id=None):
    task = Task(
        organization_id=org.id,
        creator_membership_id=creator.id,
        title="Task",
        status=status,
        assignee_membership_id=assignee.id if assignee else None,
        due_date=due_date,
        department_id=department_id,
    )
    db.session.add(task)
    db.session.commit()
    if created_at is not None:
        db.session.query(Task).filter_by(id=task.id).update({"created_at": created_at})
        db.session.commit()
    return task


def _complete_task(task, *, at):
    task.status = TaskStatus.COMPLETED
    history = TaskHistory(
        organization_id=task.organization_id,
        task_id=task.id,
        actor_membership_id=task.assignee_membership_id,
        event_type="status_changed",
        previous_value="in_progress",
        new_value="completed",
    )
    db.session.add(history)
    db.session.commit()
    db.session.query(TaskHistory).filter_by(id=history.id).update({"created_at": at})
    db.session.commit()
    return history


def _make_request(org, creator, *, assignee=None, status=RequestStatus.NEW, created_at=None):
    from app.models import Customer, CustomerStatus

    customer = db.session.query(Customer).filter_by(organization_id=org.id).first()
    if customer is None:
        customer = Customer(organization_id=org.id, name="Cust", status=CustomerStatus.ACTIVE)
        db.session.add(customer)
        db.session.commit()
    request = CustomerRequest(
        organization_id=org.id,
        customer_id=customer.id,
        creator_membership_id=creator.id,
        assignee_membership_id=assignee.id if assignee else None,
        title="Request",
        status=status,
    )
    db.session.add(request)
    db.session.commit()
    if created_at is not None:
        db.session.query(CustomerRequest).filter_by(id=request.id).update({"created_at": created_at})
        db.session.commit()
    return request


def _make_invoice(org, creator, *, status=InvoiceStatus.SENT, total="100.00", issue_date=None):
    from app.models import Customer, CustomerStatus

    customer = db.session.query(Customer).filter_by(organization_id=org.id).first()
    if customer is None:
        customer = Customer(organization_id=org.id, name="Cust", status=CustomerStatus.ACTIVE)
        db.session.add(customer)
        db.session.commit()

    invoice = Invoice(
        organization_id=org.id,
        customer_id=customer.id,
        invoice_number=f"INV-{uuid.uuid4().hex[:8]}",
        status=status,
        issue_date=issue_date,
        currency="USD",
        discount_type=DiscountType.FLAT,
        discount_value=Decimal("0.00"),
        total=Decimal(total),
        created_by=creator.id,
    )
    db.session.add(invoice)
    db.session.commit()
    return invoice


def _make_payment(org, invoice, recorder, *, amount="50.00", payment_date):
    payment = Payment(
        organization_id=org.id,
        invoice_id=invoice.id,
        amount=Decimal(amount),
        payment_date=payment_date,
        method="bank_transfer",
        idempotency_key=uuid.uuid4().hex,
        recorded_by=recorder.id,
    )
    db.session.add(payment)
    db.session.commit()
    return payment


def _make_department(org, name="Sales"):
    department = Department(organization_id=org.id, name=name, status=DepartmentStatus.ACTIVE)
    db.session.add(department)
    db.session.commit()
    return department


def _make_employee_profile(org, membership, *, department_id=None):
    profile = EmployeeProfile(organization_id=org.id, membership_id=membership.id, department_id=department_id)
    db.session.add(profile)
    db.session.commit()
    return profile


PERIOD_START = date(2026, 1, 1)
PERIOD_END = date(2026, 1, 31)


def _in_period(day_offset=5):
    return datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(days=day_offset)


# --- get_overview_metrics ------------------------------------------------


def test_overview_requires_full_scope(app):
    with app.app_context():
        org = _make_org("org-ov-scope")
        with pytest.raises(APIError) as exc_info:
            get_overview_metrics(
                org.id, "UTC", PermissionScope.OWN, period_start=PERIOD_START, period_end=PERIOD_END
            )
        assert exc_info.value.status_code == 403


def test_overview_rejects_inverted_period(app):
    with app.app_context():
        org = _make_org("org-ov-period")
        with pytest.raises(APIError) as exc_info:
            get_overview_metrics(
                org.id, "UTC", PermissionScope.FULL, period_start=PERIOD_END, period_end=PERIOD_START
            )
        assert exc_info.value.status_code == 422


def test_overview_metrics_reconcile_with_fixtures(app):
    with app.app_context():
        org = _make_org("org-ov-fixtures")
        owner = _make_membership(org, "ov-owner@example.com", MembershipRole.OWNER)
        employee = _make_membership(org, "ov-emp@example.com", MembershipRole.EMPLOYEE)
        _make_membership(org, "ov-inactive@example.com", MembershipRole.EMPLOYEE, status=MembershipStatus.INACTIVE)

        _make_task(org, owner, assignee=employee, status=TaskStatus.IN_PROGRESS)  # active
        overdue_task = _make_task(org, owner, assignee=employee, status=TaskStatus.IN_PROGRESS, due_date=date(2020, 1, 1))
        completed_task = _make_task(org, owner, assignee=employee, status=TaskStatus.TODO)
        _complete_task(completed_task, at=_in_period(10))

        _make_request(org, owner, status=RequestStatus.NEW)
        _make_request(org, owner, status=RequestStatus.CLOSED)

        invoice = _make_invoice(org, owner, status=InvoiceStatus.SENT, total="200.00", issue_date=date(2026, 1, 15))
        _make_payment(org, invoice, owner, amount="75.00", payment_date=date(2026, 1, 20))

        result = get_overview_metrics(org.id, "UTC", PermissionScope.FULL, period_start=PERIOD_START, period_end=PERIOD_END)

        assert result["employee_count"] == 2  # owner + active employee, not the inactive one
        assert result["active_tasks"] == 2  # the two in_progress tasks; the completed one no longer counts
        assert result["overdue_tasks"] == 1
        assert result["completed_tasks"] == 1
        assert result["open_requests"] == 1  # NEW only, CLOSED excluded
        assert result["monthly_invoiced"] == Decimal("200.00")
        assert result["monthly_collected"] == Decimal("75.00")


def test_overview_active_tasks_excludes_completed_and_cancelled(app):
    with app.app_context():
        org = _make_org("org-ov-active")
        owner = _make_membership(org, "ov-active-owner@example.com", MembershipRole.OWNER)
        _make_task(org, owner, status=TaskStatus.CANCELLED)
        completed = _make_task(org, owner, status=TaskStatus.TODO)
        _complete_task(completed, at=_in_period(1))
        _make_task(org, owner, status=TaskStatus.TODO)

        result = get_overview_metrics(org.id, "UTC", PermissionScope.FULL, period_start=PERIOD_START, period_end=PERIOD_END)

        assert result["active_tasks"] == 1


def test_overview_completed_tasks_excludes_outside_period(app):
    with app.app_context():
        org = _make_org("org-ov-boundary")
        owner = _make_membership(org, "ov-boundary-owner@example.com", MembershipRole.OWNER)
        inside = _make_task(org, owner, status=TaskStatus.TODO)
        _complete_task(inside, at=datetime(2026, 1, 31, 23, 0, tzinfo=timezone.utc))
        outside = _make_task(org, owner, status=TaskStatus.TODO)
        _complete_task(outside, at=datetime(2026, 2, 1, 0, 0, tzinfo=timezone.utc))

        result = get_overview_metrics(org.id, "UTC", PermissionScope.FULL, period_start=PERIOD_START, period_end=PERIOD_END)

        assert result["completed_tasks"] == 1


# --- get_employee_performance ---------------------------------------------


def test_employee_performance_own_scope_forces_self(app):
    with app.app_context():
        org = _make_org("org-emp-own")
        owner = _make_membership(org, "emp-own-owner@example.com", MembershipRole.OWNER)
        caller = _make_membership(org, "emp-own-caller@example.com", MembershipRole.EMPLOYEE)
        other = _make_membership(org, "emp-own-other@example.com", MembershipRole.EMPLOYEE)
        _make_task(org, owner, assignee=other, created_at=_in_period(1))

        results = get_employee_performance(
            org.id, "UTC", PermissionScope.OWN, caller.id, period_start=PERIOD_START, period_end=PERIOD_END, target_membership_id=other.id
        )

        assert len(results) == 1
        assert results[0]["membership_id"] == caller.id
        assert results[0]["assigned_tasks"] == 0  # the task was assigned to `other`, not the caller


def test_employee_performance_rejects_limited_scope(app):
    with app.app_context():
        org = _make_org("org-emp-limited")
        caller = _make_membership(org, "emp-limited-caller@example.com", MembershipRole.ACCOUNTANT)
        with pytest.raises(APIError) as exc_info:
            get_employee_performance(
                org.id, "UTC", PermissionScope.LIMITED, caller.id, period_start=PERIOD_START, period_end=PERIOD_END
            )
        assert exc_info.value.status_code == 403


def test_employee_performance_full_scope_computes_rate_and_avg_time(app):
    with app.app_context():
        org = _make_org("org-emp-full")
        owner = _make_membership(org, "emp-full-owner@example.com", MembershipRole.OWNER)
        employee = _make_membership(org, "emp-full-employee@example.com", MembershipRole.EMPLOYEE)

        task_a = _make_task(org, owner, assignee=employee, created_at=_in_period(1))
        _complete_task(task_a, at=_in_period(1) + timedelta(hours=10))
        task_b = _make_task(org, owner, assignee=employee, created_at=_in_period(2))
        _complete_task(task_b, at=_in_period(2) + timedelta(hours=20))
        _make_task(org, owner, assignee=employee, created_at=_in_period(3))  # never completed

        results = get_employee_performance(
            org.id, "UTC", PermissionScope.FULL, owner.id, period_start=PERIOD_START, period_end=PERIOD_END, target_membership_id=employee.id
        )

        assert len(results) == 1
        entry = results[0]
        assert entry["assigned_tasks"] == 3
        assert entry["completed_tasks"] == 2
        assert entry["completion_rate"] == pytest.approx(2 / 3)
        assert entry["avg_completion_time_hours"] == pytest.approx(15.0)


def test_employee_performance_full_scope_without_target_returns_every_active_employee(app):
    with app.app_context():
        org = _make_org("org-emp-all")
        owner = _make_membership(org, "emp-all-owner@example.com", MembershipRole.OWNER)
        _make_membership(org, "emp-all-e1@example.com", MembershipRole.EMPLOYEE)
        _make_membership(org, "emp-all-e2@example.com", MembershipRole.EMPLOYEE)
        _make_membership(org, "emp-all-inactive@example.com", MembershipRole.EMPLOYEE, status=MembershipStatus.INACTIVE)

        results = get_employee_performance(org.id, "UTC", PermissionScope.FULL, owner.id, period_start=PERIOD_START, period_end=PERIOD_END)

        assert len(results) == 3  # owner + 2 active employees, not the inactive one


def test_employee_performance_null_when_no_data(app):
    with app.app_context():
        org = _make_org("org-emp-null")
        owner = _make_membership(org, "emp-null-owner@example.com", MembershipRole.OWNER)

        results = get_employee_performance(
            org.id, "UTC", PermissionScope.FULL, owner.id, period_start=PERIOD_START, period_end=PERIOD_END, target_membership_id=owner.id
        )

        assert results[0]["completion_rate"] is None
        assert results[0]["avg_completion_time_hours"] is None


# --- get_department_analytics ----------------------------------------------


def test_department_analytics_requires_full_scope(app):
    with app.app_context():
        org = _make_org("org-dept-scope")
        with pytest.raises(APIError) as exc_info:
            get_department_analytics(org.id, "UTC", PermissionScope.LIMITED, period_start=PERIOD_START, period_end=PERIOD_END)
        assert exc_info.value.status_code == 403


def test_department_analytics_breaks_down_by_department_including_unassigned(app):
    with app.app_context():
        org = _make_org("org-dept-breakdown")
        owner = _make_membership(org, "dept-owner@example.com", MembershipRole.OWNER)
        sales = _make_department(org, "Sales")
        support = _make_department(org, "Support")

        _make_task(org, owner, status=TaskStatus.IN_PROGRESS, department_id=sales.id)
        overdue = _make_task(org, owner, status=TaskStatus.IN_PROGRESS, department_id=sales.id, due_date=date(2020, 1, 1))
        completed = _make_task(org, owner, status=TaskStatus.TODO, department_id=support.id)
        _complete_task(completed, at=_in_period(5))
        _make_task(org, owner, status=TaskStatus.IN_PROGRESS, department_id=None)  # unassigned

        results = get_department_analytics(org.id, "UTC", PermissionScope.FULL, period_start=PERIOD_START, period_end=PERIOD_END)

        by_id = {r["department_id"]: r for r in results}
        assert by_id[sales.id]["active_tasks"] == 2
        assert by_id[sales.id]["overdue_tasks"] == 1
        assert by_id[support.id]["completed_tasks"] == 1
        assert by_id[None]["active_tasks"] == 1
        assert by_id[None]["department_name"] is None


def test_department_analytics_filtered_to_one_department_has_no_unassigned_bucket(app):
    with app.app_context():
        org = _make_org("org-dept-filtered")
        owner = _make_membership(org, "dept-filtered-owner@example.com", MembershipRole.OWNER)
        sales = _make_department(org, "Sales")
        _make_task(org, owner, status=TaskStatus.IN_PROGRESS, department_id=sales.id)
        _make_task(org, owner, status=TaskStatus.IN_PROGRESS, department_id=None)

        results = get_department_analytics(
            org.id, "UTC", PermissionScope.FULL, period_start=PERIOD_START, period_end=PERIOD_END, department_id=sales.id
        )

        assert len(results) == 1
        assert results[0]["department_id"] == sales.id


def test_department_analytics_request_volume_derived_via_assignee_department(app):
    with app.app_context():
        org = _make_org("org-dept-requests")
        owner = _make_membership(org, "dept-req-owner@example.com", MembershipRole.OWNER)
        support_employee = _make_membership(org, "dept-req-emp@example.com", MembershipRole.EMPLOYEE)
        unassigned_employee = _make_membership(org, "dept-req-emp2@example.com", MembershipRole.EMPLOYEE)
        support = _make_department(org, "Support")
        _make_employee_profile(org, support_employee, department_id=support.id)
        # unassigned_employee deliberately has no EmployeeProfile row

        _make_request(org, owner, assignee=support_employee, created_at=_in_period(1))
        _make_request(org, owner, assignee=unassigned_employee, created_at=_in_period(1))  # no profile -> uncounted
        _make_request(org, owner, assignee=None, created_at=_in_period(1))  # no assignee -> uncounted

        results = get_department_analytics(org.id, "UTC", PermissionScope.FULL, period_start=PERIOD_START, period_end=PERIOD_END)

        by_id = {r["department_id"]: r for r in results}
        assert by_id[support.id]["request_volume"] == 1
        assert by_id[None]["request_volume"] == 0


# --- get_financial_analytics ------------------------------------------------


def test_financial_analytics_requires_full_or_accountant_limited(app):
    with app.app_context():
        org = _make_org("org-fin-scope")
        with pytest.raises(APIError) as exc_info:
            get_financial_analytics(
                org.id, "UTC", PermissionScope.LIMITED, MembershipRole.CUSTOMER_SUPPORT, period_start=PERIOD_START, period_end=PERIOD_END
            )
        assert exc_info.value.status_code == 403


def test_financial_analytics_allows_accountant_limited_scope(app):
    with app.app_context():
        org = _make_org("org-fin-accountant")
        owner = _make_membership(org, "fin-acct-owner@example.com", MembershipRole.OWNER)
        invoice = _make_invoice(org, owner, status=InvoiceStatus.SENT, total="100.00", issue_date=date(2026, 1, 5))
        _make_payment(org, invoice, owner, amount="40.00", payment_date=date(2026, 1, 10))

        result = get_financial_analytics(
            org.id, "UTC", PermissionScope.LIMITED, MembershipRole.ACCOUNTANT, period_start=PERIOD_START, period_end=PERIOD_END
        )

        assert result["monthly_revenue_collected"] == Decimal("40.00")


def test_financial_analytics_revenue_by_day_and_invoice_distribution(app):
    with app.app_context():
        org = _make_org("org-fin-breakdown")
        owner = _make_membership(org, "fin-breakdown-owner@example.com", MembershipRole.OWNER)
        invoice_a = _make_invoice(org, owner, status=InvoiceStatus.SENT, total="100.00", issue_date=date(2026, 1, 5))
        invoice_b = _make_invoice(org, owner, status=InvoiceStatus.PAID, total="200.00", issue_date=date(2026, 1, 6))
        _make_invoice(org, owner, status=InvoiceStatus.DRAFT, total="0.00", issue_date=None)

        _make_payment(org, invoice_a, owner, amount="30.00", payment_date=date(2026, 1, 10))
        _make_payment(org, invoice_a, owner, amount="20.00", payment_date=date(2026, 1, 10))
        _make_payment(org, invoice_b, owner, amount="200.00", payment_date=date(2026, 1, 12))

        result = get_financial_analytics(org.id, "UTC", PermissionScope.FULL, MembershipRole.OWNER, period_start=PERIOD_START, period_end=PERIOD_END)

        by_date = {row["date"]: row["amount"] for row in result["revenue_by_day"]}
        assert by_date[date(2026, 1, 10)] == Decimal("50.00")  # two payments on the same day, summed
        assert by_date[date(2026, 1, 12)] == Decimal("200.00")
        assert date(2026, 1, 11) not in by_date  # no payment that day - never zero-filled

        assert result["invoice_distribution"] == {"sent": 1, "paid": 1}  # draft (no issue_date) excluded


# --- Cross-tenant isolation ------------------------------------------------
# Every function below is exercised with two real, fully-populated
# organizations sharing the same period, to prove org A's result never
# reflects org B's data - not just that a single org's own numbers add
# up (covered above).


def test_overview_metrics_never_reflect_a_different_organization(app):
    with app.app_context():
        org_a = _make_org("org-tenant-ov-a")
        org_b = _make_org("org-tenant-ov-b")
        owner_a = _make_membership(org_a, "tenant-ov-owner-a@example.com", MembershipRole.OWNER)
        owner_b = _make_membership(org_b, "tenant-ov-owner-b@example.com", MembershipRole.OWNER)
        _make_membership(org_b, "tenant-ov-emp-b@example.com", MembershipRole.EMPLOYEE)

        _make_task(org_b, owner_b, status=TaskStatus.IN_PROGRESS)
        _make_task(org_b, owner_b, status=TaskStatus.IN_PROGRESS, due_date=date(2020, 1, 1))
        _make_request(org_b, owner_b, status=RequestStatus.NEW)
        invoice_b = _make_invoice(org_b, owner_b, status=InvoiceStatus.SENT, total="500.00", issue_date=date(2026, 1, 10))
        _make_payment(org_b, invoice_b, owner_b, amount="500.00", payment_date=date(2026, 1, 15))

        result = get_overview_metrics(org_a.id, "UTC", PermissionScope.FULL, period_start=PERIOD_START, period_end=PERIOD_END)

        assert result["employee_count"] == 1  # only org_a's owner, not org_b's owner+employee
        assert result["active_tasks"] == 0
        assert result["overdue_tasks"] == 0
        assert result["open_requests"] == 0
        assert result["monthly_invoiced"] == Decimal("0.00")
        assert result["monthly_collected"] == Decimal("0.00")


def test_employee_performance_ignores_a_target_membership_from_another_org(app):
    with app.app_context():
        org_a = _make_org("org-tenant-emp-a")
        org_b = _make_org("org-tenant-emp-b")
        owner_a = _make_membership(org_a, "tenant-emp-owner-a@example.com", MembershipRole.OWNER)
        owner_b = _make_membership(org_b, "tenant-emp-owner-b@example.com", MembershipRole.OWNER)
        employee_b = _make_membership(org_b, "tenant-emp-employee-b@example.com", MembershipRole.EMPLOYEE)
        _make_task(org_b, owner_b, assignee=employee_b, created_at=_in_period(1))

        results = get_employee_performance(
            org_a.id, "UTC", PermissionScope.FULL, owner_a.id,
            period_start=PERIOD_START, period_end=PERIOD_END, target_membership_id=employee_b.id,
        )

        assert results == []  # employee_b belongs to org_b - never resolved against org_a


def test_employee_performance_full_scope_without_target_excludes_other_orgs(app):
    with app.app_context():
        org_a = _make_org("org-tenant-emp-all-a")
        org_b = _make_org("org-tenant-emp-all-b")
        owner_a = _make_membership(org_a, "tenant-emp-all-owner-a@example.com", MembershipRole.OWNER)
        _make_membership(org_b, "tenant-emp-all-owner-b@example.com", MembershipRole.OWNER)
        _make_membership(org_b, "tenant-emp-all-emp-b@example.com", MembershipRole.EMPLOYEE)

        results = get_employee_performance(org_a.id, "UTC", PermissionScope.FULL, owner_a.id, period_start=PERIOD_START, period_end=PERIOD_END)

        assert len(results) == 1
        assert results[0]["membership_id"] == owner_a.id


def test_department_analytics_never_reflects_a_different_organizations_departments(app):
    with app.app_context():
        org_a = _make_org("org-tenant-dept-a")
        org_b = _make_org("org-tenant-dept-b")
        owner_a = _make_membership(org_a, "tenant-dept-owner-a@example.com", MembershipRole.OWNER)
        owner_b = _make_membership(org_b, "tenant-dept-owner-b@example.com", MembershipRole.OWNER)
        dept_b = _make_department(org_b, "Org B Sales")
        _make_task(org_b, owner_b, status=TaskStatus.IN_PROGRESS, department_id=dept_b.id)

        results = get_department_analytics(org_a.id, "UTC", PermissionScope.FULL, period_start=PERIOD_START, period_end=PERIOD_END)

        assert all(r["department_id"] != dept_b.id for r in results)
        unassigned = next(r for r in results if r["department_id"] is None)
        assert unassigned["active_tasks"] == 0  # org_b's task never counted against org_a's "no department" bucket


def test_department_analytics_rejects_a_department_id_from_another_org(app):
    with app.app_context():
        org_a = _make_org("org-tenant-dept-filter-a")
        org_b = _make_org("org-tenant-dept-filter-b")
        _make_membership(org_a, "tenant-dept-filter-owner-a@example.com", MembershipRole.OWNER)
        owner_b = _make_membership(org_b, "tenant-dept-filter-owner-b@example.com", MembershipRole.OWNER)
        dept_b = _make_department(org_b, "Org B Support")
        _make_task(org_b, owner_b, status=TaskStatus.IN_PROGRESS, department_id=dept_b.id)

        results = get_department_analytics(
            org_a.id, "UTC", PermissionScope.FULL, period_start=PERIOD_START, period_end=PERIOD_END, department_id=dept_b.id
        )

        assert results == []  # dept_b belongs to org_b - never resolved against org_a


def test_financial_analytics_never_reflects_a_different_organizations_money(app):
    with app.app_context():
        org_a = _make_org("org-tenant-fin-a")
        org_b = _make_org("org-tenant-fin-b")
        _make_membership(org_a, "tenant-fin-owner-a@example.com", MembershipRole.OWNER)
        owner_b = _make_membership(org_b, "tenant-fin-owner-b@example.com", MembershipRole.OWNER)
        invoice_b = _make_invoice(org_b, owner_b, status=InvoiceStatus.SENT, total="900.00", issue_date=date(2026, 1, 8))
        _make_payment(org_b, invoice_b, owner_b, amount="900.00", payment_date=date(2026, 1, 9))

        result = get_financial_analytics(org_a.id, "UTC", PermissionScope.FULL, MembershipRole.OWNER, period_start=PERIOD_START, period_end=PERIOD_END)

        assert result["monthly_revenue_collected"] == Decimal("0.00")
        assert result["revenue_by_day"] == []
        assert result["invoice_distribution"] == {}
