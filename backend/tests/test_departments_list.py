import pytest

from app.extensions import db
from app.models import Department, Membership, MembershipRole, MembershipStatus, Organization, User


@pytest.fixture(autouse=True)
def _clean(app):
    yield
    with app.app_context():
        db.session.query(Department).delete()
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


def _give_role(app, organization_id, email, role, status=MembershipStatus.ACTIVE):
    with app.app_context():
        user = db.session.query(User).filter_by(email=email).one()
        db.session.add(Membership(organization_id=organization_id, user_id=user.id, role=role, status=status))
        db.session.commit()


def _create_department(client, csrf_token, org_id, name="Sales"):
    return client.post(
        f"/api/v1/organizations/{org_id}/departments",
        json={"name": name},
        headers={"X-CSRF-Token": csrf_token},
    )


def test_list_is_empty_for_a_new_organization(client):
    csrf_token = _register_and_login(client, "owner@example.com")
    org = _create_org(client, csrf_token)

    response = client.get(f"/api/v1/organizations/{org['id']}/departments")

    assert response.status_code == 200
    assert response.get_json()["data"] == []


def test_list_returns_departments_sorted_by_name(client):
    csrf_token = _register_and_login(client, "owner2@example.com")
    org = _create_org(client, csrf_token)
    _create_department(client, csrf_token, org["id"], name="Support")
    _create_department(client, csrf_token, org["id"], name="Engineering")

    response = client.get(f"/api/v1/organizations/{org['id']}/departments")

    names = [d["name"] for d in response.get_json()["data"]]
    assert names == ["Engineering", "Support"]


def test_list_includes_inactive_departments(client):
    csrf_token = _register_and_login(client, "owner3@example.com")
    org = _create_org(client, csrf_token)
    created = _create_department(client, csrf_token, org["id"]).get_json()["data"]
    client.delete(
        f"/api/v1/organizations/{org['id']}/departments/{created['id']}", headers={"X-CSRF-Token": csrf_token}
    )

    response = client.get(f"/api/v1/organizations/{org['id']}/departments")

    body = response.get_json()["data"]
    assert len(body) == 1
    assert body[0]["status"] == "inactive"


def test_list_only_returns_the_requested_organizations_departments(client):
    csrf_token = _register_and_login(client, "owner4@example.com")
    org_a = _create_org(client, csrf_token, name="Org A")
    org_b = _create_org(client, csrf_token, name="Org B")
    _create_department(client, csrf_token, org_a["id"], name="A Dept")
    _create_department(client, csrf_token, org_b["id"], name="B Dept")

    response = client.get(f"/api/v1/organizations/{org_a['id']}/departments")

    names = [d["name"] for d in response.get_json()["data"]]
    assert names == ["A Dept"]


def test_employee_cannot_list_departments(client, app):
    csrf_token = _register_and_login(client, "owner5@example.com")
    org = _create_org(client, csrf_token)
    _register_and_login(client, "employee5@example.com")
    _give_role(app, org["id"], "employee5@example.com", MembershipRole.EMPLOYEE)

    response = client.get(f"/api/v1/organizations/{org['id']}/departments")

    assert response.status_code == 403
