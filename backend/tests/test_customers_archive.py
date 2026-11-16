import uuid

import pytest

from app.extensions import db
from app.models import Customer, Membership, MembershipRole, Organization, User


@pytest.fixture(autouse=True)
def _clean(app):
    yield
    with app.app_context():
        db.session.query(Customer).delete()
        db.session.query(Membership).delete()
        db.session.query(Organization).delete()
        db.session.query(User).delete()
        db.session.commit()


def _login(client, email, password="correct horse battery"):
    login_response = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    return login_response.get_json()["data"]["csrf_token"]


def _register_and_login(client, email, password="correct horse battery"):
    client.post("/api/v1/auth/register", json={"name": "Test User", "email": email, "password": password})
    return _login(client, email, password)


def _create_org(client, csrf_token, name="Org One"):
    return client.post(
        "/api/v1/organizations", json={"name": name}, headers={"X-CSRF-Token": csrf_token}
    ).get_json()["data"]


def _give_role(app, organization_id, email, role):
    with app.app_context():
        user = db.session.query(User).filter_by(email=email).one()
        membership = Membership(organization_id=organization_id, user_id=user.id, role=role)
        db.session.add(membership)
        db.session.commit()
        return str(membership.id)


def _create_customer(client, csrf_token, org_id, **body):
    body.setdefault("name", "Jane Customer")
    return client.post(
        f"/api/v1/organizations/{org_id}/customers", json=body, headers={"X-CSRF-Token": csrf_token}
    ).get_json()["data"]


def _archive(client, csrf_token, org_id, customer_id):
    return client.delete(
        f"/api/v1/organizations/{org_id}/customers/{customer_id}", headers={"X-CSRF-Token": csrf_token}
    )


def test_archive_sets_status_to_archived(client):
    csrf_token = _register_and_login(client, "owner@example.com")
    org = _create_org(client, csrf_token)
    customer = _create_customer(client, csrf_token, org["id"])

    response = _archive(client, csrf_token, org["id"], customer["id"])

    assert response.status_code == 200
    assert response.get_json()["data"]["status"] == "archived"


def test_archive_is_idempotent(client):
    csrf_token = _register_and_login(client, "owner2@example.com")
    org = _create_org(client, csrf_token)
    customer = _create_customer(client, csrf_token, org["id"])
    _archive(client, csrf_token, org["id"], customer["id"])

    response = _archive(client, csrf_token, org["id"], customer["id"])

    assert response.status_code == 200
    assert response.get_json()["data"]["status"] == "archived"


def test_archive_does_not_delete_the_customer_row(client, app):
    csrf_token = _register_and_login(client, "owner3@example.com")
    org = _create_org(client, csrf_token)
    customer = _create_customer(client, csrf_token, org["id"])

    _archive(client, csrf_token, org["id"], customer["id"])

    with app.app_context():
        survivor = db.session.get(Customer, uuid.UUID(customer["id"]))
        assert survivor is not None
        assert survivor.name == "Jane Customer"


def test_an_archived_customer_can_be_reactivated_via_patch(client):
    csrf_token = _register_and_login(client, "owner4@example.com")
    org = _create_org(client, csrf_token)
    customer = _create_customer(client, csrf_token, org["id"])
    _archive(client, csrf_token, org["id"], customer["id"])

    response = client.patch(
        f"/api/v1/organizations/{org['id']}/customers/{customer['id']}",
        json={"status": "active"},
        headers={"X-CSRF-Token": csrf_token},
    )

    assert response.status_code == 200
    assert response.get_json()["data"]["status"] == "active"


def test_archive_a_nonexistent_customer_returns_404(client):
    csrf_token = _register_and_login(client, "owner5@example.com")
    org = _create_org(client, csrf_token)

    response = _archive(client, csrf_token, org["id"], "00000000-0000-0000-0000-000000000000")

    assert response.status_code == 404


def test_archive_a_customer_from_a_different_organization_returns_404(client):
    csrf_token = _register_and_login(client, "owner6@example.com")
    org_a = _create_org(client, csrf_token, name="Org A")
    org_b = _create_org(client, csrf_token, name="Org B")
    customer_in_org_a = _create_customer(client, csrf_token, org_a["id"])

    response = _archive(client, csrf_token, org_b["id"], customer_in_org_a["id"])

    assert response.status_code == 404


def test_archive_without_csrf_token_returns_403(client):
    csrf_token = _register_and_login(client, "owner7@example.com")
    org = _create_org(client, csrf_token)
    customer = _create_customer(client, csrf_token, org["id"])

    response = client.delete(f"/api/v1/organizations/{org['id']}/customers/{customer['id']}")

    assert response.status_code == 403


def test_employee_cannot_archive_a_customer(client, app):
    csrf_token = _register_and_login(client, "owner8@example.com")
    org = _create_org(client, csrf_token)
    customer = _create_customer(client, csrf_token, org["id"])

    employee_csrf = _register_and_login(client, "employee8@example.com")
    _give_role(app, org["id"], "employee8@example.com", MembershipRole.EMPLOYEE)

    response = _archive(client, employee_csrf, org["id"], customer["id"])

    assert response.status_code == 403
