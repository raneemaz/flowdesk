import uuid

import pytest

from app.extensions import db
from app.models import (
    Department,
    DepartmentStatus,
    EmployeeProfile,
    Membership,
    MembershipRole,
    Organization,
    User,
)


@pytest.fixture(autouse=True)
def _clean(app):
    yield
    with app.app_context():
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


def _membership_id(app, organization_id, email):
    with app.app_context():
        user = db.session.query(User).filter_by(email=email).one()
        membership = (
            db.session.query(Membership)
            .filter_by(organization_id=uuid.UUID(organization_id), user_id=user.id)
            .one()
        )
        return str(membership.id)


def _make_department(app, organization_id, name="Sales", status=None):
    with app.app_context():
        department = Department(organization_id=uuid.UUID(organization_id), name=name)
        if status is not None:
            department.status = status
        db.session.add(department)
        db.session.commit()
        return str(department.id)


def _get_employee(client, org_id, membership_id):
    return client.get(f"/api/v1/organizations/{org_id}/employees/{membership_id}")


def _patch_employee(client, csrf_token, org_id, membership_id, **body):
    return client.patch(
        f"/api/v1/organizations/{org_id}/employees/{membership_id}",
        json=body,
        headers={"X-CSRF-Token": csrf_token},
    )


# --- GET single profile ---------------------------------------------


def test_unauthenticated_get_returns_401(client):
    response = client.get(
        "/api/v1/organizations/00000000-0000-0000-0000-000000000000/employees/"
        "00000000-0000-0000-0000-000000000000"
    )
    assert response.status_code == 401


def test_non_member_get_returns_404(client):
    csrf_token = _register_and_login(client, "owner@example.com")
    org = _create_org(client, csrf_token)

    _register_and_login(client, "outsider@example.com")

    response = _get_employee(client, org["id"], "00000000-0000-0000-0000-000000000000")
    assert response.status_code == 404


def test_get_nonexistent_target_membership_returns_404(client):
    csrf_token = _register_and_login(client, "owner2@example.com")
    org = _create_org(client, csrf_token)

    response = _get_employee(client, org["id"], str(uuid.uuid4()))
    assert response.status_code == 404


def test_get_a_real_but_cross_org_target_membership_returns_404(client, app):
    owner_a_csrf = _register_and_login(client, "owner2a@example.com")
    org_a = _create_org(client, owner_a_csrf, name="Org A")
    owner_b_csrf = _register_and_login(client, "owner2b@example.com")
    org_b = _create_org(client, owner_b_csrf, name="Org B")
    _register_and_login(client, "employee2b@example.com", name="Employee B")
    org_b_membership_id = _give_role(app, org_b["id"], "employee2b@example.com", MembershipRole.EMPLOYEE)

    # Org A's owner is the actor-under-test, so they log in last.
    _login(client, "owner2a@example.com")

    response = _get_employee(client, org_a["id"], org_b_membership_id)

    assert response.status_code == 404


def test_owner_sees_full_fields_for_any_employee(client, app):
    csrf_token = _register_and_login(client, "owner3@example.com")
    org = _create_org(client, csrf_token)
    _register_and_login(client, "employee3@example.com", name="Employee Three")
    employee_membership_id = _give_role(app, org["id"], "employee3@example.com", MembershipRole.EMPLOYEE)
    # The owner is the actor-under-test for this GET, so their session
    # must be active last (employee3's register+login above switched
    # the client's active session away from the owner).
    _login(client, "owner3@example.com")

    response = _get_employee(client, org["id"], employee_membership_id)

    assert response.status_code == 200
    record = response.get_json()["data"]
    assert record["name"] == "Employee Three"
    assert "email" in record
    assert "job_title" in record
    assert "department" in record
    assert "manager" in record


def test_employee_sees_limited_fields_for_another_employee(client, app):
    csrf_token = _register_and_login(client, "owner4@example.com")
    org = _create_org(client, csrf_token)
    _register_and_login(client, "employee4a@example.com", name="Employee A")
    target_id = _give_role(app, org["id"], "employee4a@example.com", MembershipRole.EMPLOYEE)
    _register_and_login(client, "employee4b@example.com", name="Employee B")
    _give_role(app, org["id"], "employee4b@example.com", MembershipRole.EMPLOYEE)

    # Viewer (Employee B) is the actor-under-test, so they log in last.
    _login(client, "employee4b@example.com")

    response = _get_employee(client, org["id"], target_id)

    assert response.status_code == 200
    record = response.get_json()["data"]
    assert set(record.keys()) == {"membership_id", "name", "role", "status"}


def test_employee_sees_full_fields_for_their_own_profile(client, app):
    csrf_token = _register_and_login(client, "owner5@example.com")
    org = _create_org(client, csrf_token)
    _register_and_login(client, "employee5@example.com", name="Employee Five")
    employee_membership_id = _give_role(app, org["id"], "employee5@example.com", MembershipRole.EMPLOYEE)

    _login(client, "employee5@example.com")

    response = _get_employee(client, org["id"], employee_membership_id)

    assert response.status_code == 200
    record = response.get_json()["data"]
    assert record["name"] == "Employee Five"
    assert "email" in record
    assert "job_title" in record
    assert "department" in record
    assert "manager" in record


# --- PATCH profile/status ---------------------------------------------


def test_unauthenticated_patch_returns_401(client):
    response = client.patch(
        "/api/v1/organizations/00000000-0000-0000-0000-000000000000/employees/"
        "00000000-0000-0000-0000-000000000000",
        json={},
    )
    assert response.status_code == 401


def test_patch_without_csrf_token_returns_403(client, app):
    _register_and_login(client, "owner6@example.com")
    org = _create_org(client, _login(client, "owner6@example.com"))
    _register_and_login(client, "employee6@example.com", name="Employee Six")
    target_id = _give_role(app, org["id"], "employee6@example.com", MembershipRole.EMPLOYEE)
    _login(client, "owner6@example.com")

    response = client.patch(
        f"/api/v1/organizations/{org['id']}/employees/{target_id}", json={"job_title": "Analyst"}
    )

    assert response.status_code == 403


def test_owner_can_create_a_profile_that_did_not_exist_yet(client, app):
    csrf_token = _register_and_login(client, "owner7@example.com")
    org = _create_org(client, csrf_token)
    _register_and_login(client, "employee7@example.com", name="Employee Seven")
    target_id = _give_role(app, org["id"], "employee7@example.com", MembershipRole.EMPLOYEE)
    owner_csrf = _login(client, "owner7@example.com")

    response = _patch_employee(client, owner_csrf, org["id"], target_id, job_title="Analyst")

    assert response.status_code == 200
    body = response.get_json()["data"]
    assert body["job_title"] == "Analyst"
    assert body["status"] == "active"
    assert body["membership_id"] == target_id


def test_partial_update_only_changes_given_fields(client, app):
    csrf_token = _register_and_login(client, "owner8@example.com")
    org = _create_org(client, csrf_token)
    _register_and_login(client, "employee8@example.com", name="Employee Eight")
    target_id = _give_role(app, org["id"], "employee8@example.com", MembershipRole.EMPLOYEE)
    owner_csrf = _login(client, "owner8@example.com")
    _patch_employee(client, owner_csrf, org["id"], target_id, job_title="Analyst")

    response = _patch_employee(client, owner_csrf, org["id"], target_id, status="suspended")

    assert response.status_code == 200
    body = response.get_json()["data"]
    assert body["job_title"] == "Analyst"
    assert body["status"] == "suspended"


def test_job_title_can_be_cleared_with_explicit_null(client, app):
    csrf_token = _register_and_login(client, "owner9@example.com")
    org = _create_org(client, csrf_token)
    _register_and_login(client, "employee9@example.com", name="Employee Nine")
    target_id = _give_role(app, org["id"], "employee9@example.com", MembershipRole.EMPLOYEE)
    owner_csrf = _login(client, "owner9@example.com")
    _patch_employee(client, owner_csrf, org["id"], target_id, job_title="Analyst")

    response = _patch_employee(client, owner_csrf, org["id"], target_id, job_title=None)

    assert response.status_code == 200
    assert response.get_json()["data"]["job_title"] is None


def test_manager_can_patch_an_employees_profile(client, app):
    csrf_token = _register_and_login(client, "owner10@example.com")
    org = _create_org(client, csrf_token)
    _register_and_login(client, "manager10@example.com", name="Manager Ten")
    _give_role(app, org["id"], "manager10@example.com", MembershipRole.MANAGER)
    _register_and_login(client, "employee10@example.com", name="Employee Ten")
    target_id = _give_role(app, org["id"], "employee10@example.com", MembershipRole.EMPLOYEE)

    manager_csrf = _login(client, "manager10@example.com")

    response = _patch_employee(client, manager_csrf, org["id"], target_id, job_title="Support Rep")

    assert response.status_code == 200
    assert response.get_json()["data"]["job_title"] == "Support Rep"


def test_manager_cannot_patch_the_owners_profile(client, app):
    csrf_token = _register_and_login(client, "owner11@example.com")
    org = _create_org(client, csrf_token)
    owner_id = _membership_id(app, org["id"], "owner11@example.com")
    _register_and_login(client, "manager11@example.com", name="Manager Eleven")
    _give_role(app, org["id"], "manager11@example.com", MembershipRole.MANAGER)

    manager_csrf = _login(client, "manager11@example.com")

    response = _patch_employee(client, manager_csrf, org["id"], owner_id, job_title="CEO")

    assert response.status_code == 403


def test_manager_cannot_patch_another_managers_profile(client, app):
    csrf_token = _register_and_login(client, "owner12@example.com")
    org = _create_org(client, csrf_token)
    _register_and_login(client, "manager12a@example.com", name="Manager A")
    target_manager_id = _give_role(app, org["id"], "manager12a@example.com", MembershipRole.MANAGER)
    _register_and_login(client, "manager12b@example.com", name="Manager B")
    _give_role(app, org["id"], "manager12b@example.com", MembershipRole.MANAGER)

    acting_manager_csrf = _login(client, "manager12b@example.com")

    response = _patch_employee(client, acting_manager_csrf, org["id"], target_manager_id, job_title="VP")

    assert response.status_code == 403


def test_employee_cannot_patch_any_profile_including_their_own(client, app):
    csrf_token = _register_and_login(client, "owner13@example.com")
    org = _create_org(client, csrf_token)
    _register_and_login(client, "employee13@example.com", name="Employee Thirteen")
    target_id = _give_role(app, org["id"], "employee13@example.com", MembershipRole.EMPLOYEE)

    employee_csrf = _login(client, "employee13@example.com")

    response = _patch_employee(client, employee_csrf, org["id"], target_id, job_title="Self Promotion")

    assert response.status_code == 403


def test_patch_nonexistent_target_membership_returns_404(client):
    csrf_token = _register_and_login(client, "owner14@example.com")
    org = _create_org(client, csrf_token)

    response = _patch_employee(client, csrf_token, org["id"], str(uuid.uuid4()), job_title="Analyst")

    assert response.status_code == 404


def test_patch_a_real_but_cross_org_target_membership_returns_404(client, app):
    owner_a_csrf = _register_and_login(client, "owner14a@example.com")
    org_a = _create_org(client, owner_a_csrf, name="Org A")
    owner_b_csrf = _register_and_login(client, "owner14b@example.com")
    org_b = _create_org(client, owner_b_csrf, name="Org B")
    _register_and_login(client, "employee14b@example.com", name="Employee B")
    org_b_membership_id = _give_role(app, org_b["id"], "employee14b@example.com", MembershipRole.EMPLOYEE)

    owner_a_csrf = _login(client, "owner14a@example.com")

    response = _patch_employee(client, owner_a_csrf, org_a["id"], org_b_membership_id, job_title="Analyst")

    assert response.status_code == 404


def test_patch_with_unknown_department_id_returns_422(client, app):
    csrf_token = _register_and_login(client, "owner15@example.com")
    org = _create_org(client, csrf_token)
    _register_and_login(client, "employee15@example.com", name="Employee Fifteen")
    target_id = _give_role(app, org["id"], "employee15@example.com", MembershipRole.EMPLOYEE)
    owner_csrf = _login(client, "owner15@example.com")

    response = _patch_employee(client, owner_csrf, org["id"], target_id, department_id=str(uuid.uuid4()))

    assert response.status_code == 422
    assert response.get_json()["error"]["code"] == "INVALID_DEPARTMENT"


def test_patch_with_a_cross_org_department_id_returns_422(client, app):
    owner_a_csrf = _register_and_login(client, "owner16a@example.com")
    org_a = _create_org(client, owner_a_csrf, name="Org A")
    owner_b_csrf = _register_and_login(client, "owner16b@example.com")
    org_b = _create_org(client, owner_b_csrf, name="Org B")
    foreign_department_id = _make_department(app, org_b["id"])

    _register_and_login(client, "employee16@example.com", name="Employee Sixteen")
    target_id = _give_role(app, org_a["id"], "employee16@example.com", MembershipRole.EMPLOYEE)
    owner_a_csrf = _login(client, "owner16a@example.com")

    response = _patch_employee(client, owner_a_csrf, org_a["id"], target_id, department_id=foreign_department_id)

    assert response.status_code == 422
    assert response.get_json()["error"]["code"] == "INVALID_DEPARTMENT"


def test_patch_with_an_inactive_department_id_returns_422(client, app):
    csrf_token = _register_and_login(client, "owner17@example.com")
    org = _create_org(client, csrf_token)
    inactive_department_id = _make_department(app, org["id"], status=DepartmentStatus.INACTIVE)
    _register_and_login(client, "employee17@example.com", name="Employee Seventeen")
    target_id = _give_role(app, org["id"], "employee17@example.com", MembershipRole.EMPLOYEE)
    owner_csrf = _login(client, "owner17@example.com")

    response = _patch_employee(client, owner_csrf, org["id"], target_id, department_id=inactive_department_id)

    assert response.status_code == 422
    assert response.get_json()["error"]["code"] == "INVALID_DEPARTMENT"


def test_patch_with_an_unknown_manager_membership_id_returns_422(client, app):
    csrf_token = _register_and_login(client, "owner18@example.com")
    org = _create_org(client, csrf_token)
    _register_and_login(client, "employee18@example.com", name="Employee Eighteen")
    target_id = _give_role(app, org["id"], "employee18@example.com", MembershipRole.EMPLOYEE)
    owner_csrf = _login(client, "owner18@example.com")

    response = _patch_employee(client, owner_csrf, org["id"], target_id, manager_membership_id=str(uuid.uuid4()))

    assert response.status_code == 422
    assert response.get_json()["error"]["code"] == "INVALID_MANAGER_MEMBERSHIP"


def test_patch_an_employee_cannot_be_their_own_manager(client, app):
    csrf_token = _register_and_login(client, "owner19@example.com")
    org = _create_org(client, csrf_token)
    _register_and_login(client, "employee19@example.com", name="Employee Nineteen")
    target_id = _give_role(app, org["id"], "employee19@example.com", MembershipRole.EMPLOYEE)
    owner_csrf = _login(client, "owner19@example.com")

    response = _patch_employee(client, owner_csrf, org["id"], target_id, manager_membership_id=target_id)

    assert response.status_code == 422
    assert response.get_json()["error"]["code"] == "INVALID_MANAGER_MEMBERSHIP"


def test_patch_with_explicit_null_status_returns_422(client, app):
    csrf_token = _register_and_login(client, "owner20@example.com")
    org = _create_org(client, csrf_token)
    _register_and_login(client, "employee20@example.com", name="Employee Twenty")
    target_id = _give_role(app, org["id"], "employee20@example.com", MembershipRole.EMPLOYEE)
    owner_csrf = _login(client, "owner20@example.com")

    response = _patch_employee(client, owner_csrf, org["id"], target_id, status=None)

    assert response.status_code == 422


def test_patch_with_unknown_field_returns_422(client, app):
    csrf_token = _register_and_login(client, "owner21@example.com")
    org = _create_org(client, csrf_token)
    _register_and_login(client, "employee21@example.com", name="Employee Twenty One")
    target_id = _give_role(app, org["id"], "employee21@example.com", MembershipRole.EMPLOYEE)
    owner_csrf = _login(client, "owner21@example.com")

    response = _patch_employee(client, owner_csrf, org["id"], target_id, organization_id=str(uuid.uuid4()))

    assert response.status_code == 422


def test_patch_valid_manager_membership_id_is_accepted(client, app):
    csrf_token = _register_and_login(client, "owner22@example.com")
    org = _create_org(client, csrf_token)
    _register_and_login(client, "manager22@example.com", name="Manager TwentyTwo")
    manager_id = _give_role(app, org["id"], "manager22@example.com", MembershipRole.MANAGER)
    _register_and_login(client, "employee22@example.com", name="Employee TwentyTwo")
    target_id = _give_role(app, org["id"], "employee22@example.com", MembershipRole.EMPLOYEE)
    owner_csrf = _login(client, "owner22@example.com")

    response = _patch_employee(client, owner_csrf, org["id"], target_id, manager_membership_id=manager_id)

    assert response.status_code == 200
    assert response.get_json()["data"]["manager_membership_id"] == manager_id
