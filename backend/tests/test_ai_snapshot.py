import json
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal

import pytest

from app.ai.snapshot import build_weekly_metrics_snapshot
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
    MembershipRole,
    MembershipStatus,
    Organization,
    Payment,
    Task,
    TaskStatus,
    User,
)

PERIOD_START = date(2026, 1, 1)
PERIOD_END = date(2026, 1, 31)


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


def _make_org(slug="org-snapshot"):
    org = Organization(name="Acme Inc", slug=slug, timezone="UTC")
    db.session.add(org)
    db.session.commit()
    return org


def _make_membership(org, email, role=MembershipRole.OWNER, status=MembershipStatus.ACTIVE, name=None):
    user = User(name=name or email.split("@")[0], email=email)
    user.set_password("correct horse battery")
    db.session.add(user)
    db.session.commit()
    membership = Membership(organization_id=org.id, user_id=user.id, role=role, status=status)
    db.session.add(membership)
    db.session.commit()
    return membership


def _make_task(org, creator, *, assignee=None, status=TaskStatus.TODO, due_date=None, department_id=None):
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
    return task


def _make_department(org, name="Support"):
    department = Department(organization_id=org.id, name=name, status=DepartmentStatus.ACTIVE)
    db.session.add(department)
    db.session.commit()
    return department


def _make_employee_profile(org, membership, *, department_id=None):
    profile = EmployeeProfile(organization_id=org.id, membership_id=membership.id, department_id=department_id)
    db.session.add(profile)
    db.session.commit()
    return profile


def _make_customer(org, name="Cust"):
    customer = Customer(organization_id=org.id, name=name, status=CustomerStatus.ACTIVE)
    db.session.add(customer)
    db.session.commit()
    return customer


def _make_invoice(org, customer, creator, *, status=InvoiceStatus.SENT, total="100.00", issue_date=None):
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


def _make_payment(org, invoice, recorder, *, amount="50.00", payment_date, reference=None):
    payment = Payment(
        organization_id=org.id,
        invoice_id=invoice.id,
        amount=Decimal(amount),
        payment_date=payment_date,
        method="bank_transfer",
        reference=reference,
        idempotency_key=uuid.uuid4().hex,
        recorded_by=recorder.id,
    )
    db.session.add(payment)
    db.session.commit()
    return payment


def test_snapshot_is_idempotent_across_two_calls(app):
    with app.app_context():
        org = _make_org("org-idempotent")
        owner = _make_membership(org, "owner-idem@example.com")
        _make_task(org, owner, assignee=owner)

        first = build_weekly_metrics_snapshot(org.id, org.timezone, period_start=PERIOD_START, period_end=PERIOD_END)
        second = build_weekly_metrics_snapshot(org.id, org.timezone, period_start=PERIOD_START, period_end=PERIOD_END)

    assert first == second


def test_snapshot_is_fully_json_serializable(app):
    with app.app_context():
        org = _make_org("org-json")
        owner = _make_membership(org, "owner-json@example.com")
        customer = _make_customer(org)
        invoice = _make_invoice(org, customer, owner, status=InvoiceStatus.PAID, issue_date=date(2026, 1, 10))
        _make_payment(org, invoice, owner, amount="100.00", payment_date=date(2026, 1, 15))
        _make_task(org, owner, assignee=owner)

        snapshot = build_weekly_metrics_snapshot(org.id, org.timezone, period_start=PERIOD_START, period_end=PERIOD_END)

    # Raises TypeError on any non-JSON-native value (Decimal/date/UUID/ORM
    # object) still lurking in the snapshot - the actual thing this test
    # is guarding against, since this dict is shipped to an external AI
    # provider as JSON (app.ai.service._build_user_prompt).
    json.dumps(snapshot)


def test_snapshot_aggregates_overview_employees_departments_and_finance(app):
    with app.app_context():
        org = _make_org("org-full")
        owner = _make_membership(org, "owner-full@example.com", name="Owner Olivia")
        employee = _make_membership(org, "employee-full@example.com", role=MembershipRole.EMPLOYEE, name="Employee Eli")
        department = _make_department(org, "Support")
        _make_employee_profile(org, employee, department_id=department.id)

        _make_task(org, owner, assignee=employee, status=TaskStatus.TODO, department_id=department.id)
        _make_task(org, owner, assignee=employee, status=TaskStatus.COMPLETED, department_id=department.id)

        customer = _make_customer(org)
        invoice = _make_invoice(org, customer, owner, status=InvoiceStatus.PAID, issue_date=date(2026, 1, 10), total="200.00")
        _make_payment(org, invoice, owner, amount="200.00", payment_date=date(2026, 1, 12), reference="REF-1")

        snapshot = build_weekly_metrics_snapshot(org.id, org.timezone, period_start=PERIOD_START, period_end=PERIOD_END)

    assert set(snapshot) == {"overview", "employees", "departments", "finance"}

    assert snapshot["overview"]["employee_count"] == 2
    assert snapshot["overview"]["period_start"] == "2026-01-01"
    assert snapshot["overview"]["monthly_invoiced"] == "200.00"

    employee_names = {row["name"] for row in snapshot["employees"]}
    assert employee_names == {"Owner Olivia", "Employee Eli"}

    department_names = {row["department_name"] for row in snapshot["departments"]}
    assert "Support" in department_names
    assert None in department_names  # the unassigned-tasks bucket (department_id: null)

    assert snapshot["finance"]["total_invoiced"] == "200.00"
    assert snapshot["finance"]["total_collected"] == "200.00"
    assert len(snapshot["finance"]["recent_payments"]) == 1
    payment_row = snapshot["finance"]["recent_payments"][0]
    assert payment_row == {
        "payment_date": "2026-01-12",
        "amount": "200.00",
        "method": "bank_transfer",
        "reference": "REF-1",
    }


def test_snapshot_never_includes_internal_payment_bookkeeping_fields(app):
    with app.app_context():
        org = _make_org("org-trim")
        owner = _make_membership(org, "owner-trim@example.com")
        customer = _make_customer(org)
        invoice = _make_invoice(org, customer, owner, status=InvoiceStatus.PAID, issue_date=date(2026, 1, 5))
        _make_payment(org, invoice, owner, amount="50.00", payment_date=date(2026, 1, 6))

        snapshot = build_weekly_metrics_snapshot(org.id, org.timezone, period_start=PERIOD_START, period_end=PERIOD_END)

    payment_row = snapshot["finance"]["recent_payments"][0]
    assert set(payment_row) == {"payment_date", "amount", "method", "reference"}
    assert "id" not in payment_row
    assert "idempotency_key" not in payment_row
    assert "recorded_by" not in payment_row
    assert "notes" not in payment_row


def test_snapshot_handles_an_organization_with_no_activity_gracefully(app):
    with app.app_context():
        org = _make_org("org-empty")
        _make_membership(org, "owner-empty@example.com")

        snapshot = build_weekly_metrics_snapshot(org.id, org.timezone, period_start=PERIOD_START, period_end=PERIOD_END)

    assert snapshot["overview"]["active_tasks"] == 0
    assert snapshot["overview"]["employee_count"] == 1
    assert snapshot["finance"]["recent_payments"] == []
    assert snapshot["finance"]["revenue_by_day"] == []
    assert snapshot["finance"]["invoice_distribution"] == {}
    # No fabricated rate/average when there's no signal to report - same
    # "None, not 0" rule app.analytics.service itself documents.
    for row in snapshot["employees"]:
        assert row["completion_rate"] is None
        assert row["avg_completion_time_hours"] is None
