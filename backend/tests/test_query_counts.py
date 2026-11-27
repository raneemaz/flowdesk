"""Performance regression guard: every list endpoint's SQL query count
must stay flat as the number of rows on the page grows (no N+1).

Each endpoint is hit once with a small dataset and again after ten more
rows exist; the number of statements Postgres receives must not change.
A fixed overhead (auth, session, membership lookup, COUNT for
pagination) is fine - only per-row queries are a defect.
"""

import uuid

import pytest
from sqlalchemy import event

from app.extensions import db
from app.models import (
    ActivityLog,
    Customer,
    CustomerRequest,
    Invoice,
    InvoiceLineItem,
    Membership,
    MembershipRole,
    MembershipStatus,
    Notification,
    Organization,
    Payment,
    Task,
    TaskHistory,
    User,
)

OWNER = "owner@query-counts.example.com"
PASSWORD = "correct horse battery"


@pytest.fixture(autouse=True)
def _clean(app):
    yield
    with app.app_context():
        db.session.query(Notification).delete()
        db.session.query(ActivityLog).delete()
        db.session.query(Payment).delete()
        db.session.query(InvoiceLineItem).delete()
        db.session.query(Invoice).delete()
        db.session.query(TaskHistory).delete()
        db.session.query(Task).delete()
        db.session.query(CustomerRequest).delete()
        db.session.query(Customer).delete()
        db.session.query(Membership).delete()
        db.session.query(Organization).delete()
        db.session.query(User).delete()
        db.session.commit()


def _count_queries(app, client, url):
    statements = []

    def _record(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    with app.app_context():
        engine = db.engine
    event.listen(engine, "before_cursor_execute", _record)
    try:
        response = client.get(url)
    finally:
        event.remove(engine, "before_cursor_execute", _record)
    assert response.status_code == 200, (url, response.get_json())
    return len(statements), len(response.get_json()["data"])


def _add_rows(app, client, csrf, org_id, owner_membership_id, start, count):
    headers = {"X-CSRF-Token": csrf}
    base = f"/api/v1/organizations/{org_id}"
    for i in range(start, start + count):
        customer = client.post(
            f"{base}/customers", json={"name": f"Customer {i}", "email": f"c{i}@query-counts.example.com"}, headers=headers
        ).get_json()["data"]
        client.post(
            f"{base}/customer-requests", json={"customer_id": customer["id"], "title": f"Request {i}", "priority": "high"}, headers=headers
        )
        task = client.post(f"{base}/tasks", json={"title": f"Task {i}", "due_date": "2026-12-31"}, headers=headers).get_json()[
            "data"
        ]
        client.patch(
            f"{base}/tasks/{task['id']}/assign", json={"assignee_membership_id": owner_membership_id}, headers=headers
        )
        client.post(
            f"{base}/invoices",
            json={
                "customer_id": customer["id"],
                "currency": "USD",
                "line_items": [{"description": "Work", "quantity": "1", "unit_price": "10.00"}],
            },
            headers=headers,
        )
    # Members with their own users, for the employee directory.
    with app.app_context():
        for i in range(start, start + count):
            user = User(email=f"m{i}@query-counts.example.com", name=f"Member {i}", password_hash="x")
            db.session.add(user)
            db.session.flush()
            db.session.add(
                Membership(
                    organization_id=uuid.UUID(org_id), user_id=user.id, role=MembershipRole.EMPLOYEE, status=MembershipStatus.ACTIVE
                )
            )
        db.session.commit()


LIST_ENDPOINTS = [
    "customers",
    "customer-requests",
    "tasks",
    "invoices",
    "employees",
    "notifications",
    "activity",
]


def test_list_endpoints_do_not_issue_per_row_queries(app, client):
    client.post("/api/v1/auth/register", json={"name": "Owner", "email": OWNER, "password": PASSWORD})
    csrf = client.post("/api/v1/auth/login", json={"email": OWNER, "password": PASSWORD}).get_json()["data"]["csrf_token"]
    org = client.post("/api/v1/organizations", json={"name": "Query Counts"}, headers={"X-CSRF-Token": csrf}).get_json()[
        "data"
    ]
    org_id = org["id"]
    with app.app_context():
        owner_membership_id = str(db.session.query(Membership).filter_by(organization_id=uuid.UUID(org_id)).one().id)

    _add_rows(app, client, csrf, org_id, owner_membership_id, start=0, count=2)
    small = {name: _count_queries(app, client, f"/api/v1/organizations/{org_id}/{name}") for name in LIST_ENDPOINTS}

    _add_rows(app, client, csrf, org_id, owner_membership_id, start=2, count=10)
    large = {name: _count_queries(app, client, f"/api/v1/organizations/{org_id}/{name}") for name in LIST_ENDPOINTS}

    print("\nqueries (rows returned), small -> large dataset:")
    for name in LIST_ENDPOINTS:
        print(f"  {name}: {small[name][0]} ({small[name][1]}) -> {large[name][0]} ({large[name][1]})")

    # The probe only proves something where the second page really has
    # more rows. Notifications are excluded: assigning a task to
    # yourself sends no notification, so that list stays empty here.
    for name in LIST_ENDPOINTS:
        if name != "notifications":
            assert large[name][1] > small[name][1], (name, small[name], large[name])
    grown = {name: (small[name][0], large[name][0]) for name in LIST_ENDPOINTS if large[name][0] > small[name][0]}
    assert not grown, f"per-row queries detected: {grown}"
