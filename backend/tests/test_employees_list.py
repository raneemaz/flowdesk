import pytest

from app.extensions import db
from app.models import (
    Department,
    EmployeeProfile,
    EmployeeStatus,
    Membership,
    MembershipRole,
    MembershipStatus,
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


def _give_role(app, organization_id, email, role, status=MembershipStatus.ACTIVE):
    with app.app_context():
        user = db.session.query(User).filter_by(email=email).one()
        membership = Membership(organization_id=organization_id, user_id=user.id, role=role, status=status)
        db.session.add(membership)
        db.session.commit()
        return str(membership.id)


def _make_profile(app, organization_id, membership_id, **kwargs):
    import uuid as uuid_mod

    with app.app_context():
        profile = EmployeeProfile(
            organization_id=uuid_mod.UUID(organization_id),
            membership_id=uuid_mod.UUID(membership_id),
            **kwargs,
        )
        db.session.add(profile)
        db.session.commit()
        return str(profile.id)


def _make_department(app, organization_id, name="Sales"):
    import uuid as uuid_mod

    with app.app_context():
        department = Department(organization_id=uuid_mod.UUID(organization_id), name=name)
        db.session.add(department)
        db.session.commit()
        return str(department.id)


def _list_employees(client, org_id, **params):
    return client.get(f"/api/v1/organizations/{org_id}/employees", query_string=params)


def test_unauthenticated_request_returns_401(client):
    response = client.get("/api/v1/organizations/00000000-0000-0000-0000-000000000000/employees")
    assert response.status_code == 401


def test_non_member_gets_404(client):
    csrf_token = _register_and_login(client, "owner@example.com")
    org = _create_org(client, csrf_token)

    outsider_csrf = _register_and_login(client, "outsider@example.com")

    response = _list_employees(client, org["id"])

    assert response.status_code == 404


def test_owner_sees_full_fields(client, app):
    csrf_token = _register_and_login(client, "owner2@example.com", name="Owner Two")
    org = _create_org(client, csrf_token)

    response = _list_employees(client, org["id"])

    assert response.status_code == 200
    body = response.get_json()["data"]
    assert len(body) == 1
    record = body[0]
    assert record["name"] == "Owner Two"
    assert record["role"] == "owner"
    assert "email" in record
    assert record["email"] == "owner2@example.com"
    assert "job_title" in record
    assert "department" in record
    assert "manager" in record
    assert "joined_at" in record


def test_employee_sees_limited_fields_only(client, app):
    csrf_token = _register_and_login(client, "owner3@example.com")
    org = _create_org(client, csrf_token)
    employee_csrf = _register_and_login(client, "employee3@example.com", name="Employee Three")
    _give_role(app, org["id"], "employee3@example.com", MembershipRole.EMPLOYEE)

    response = _list_employees(client, org["id"])

    assert response.status_code == 200
    records = {r["name"]: r for r in response.get_json()["data"]}
    employee_record = records["Employee Three"]
    assert set(employee_record.keys()) == {"membership_id", "name", "role", "status"}
    assert employee_record["role"] == "employee"


@pytest.mark.parametrize("role", [MembershipRole.ACCOUNTANT, MembershipRole.CUSTOMER_SUPPORT])
def test_accountant_and_customer_support_see_limited_fields(client, app, role):
    csrf_token = _register_and_login(client, f"owner-{role.value}@example.com")
    org = _create_org(client, csrf_token)
    other_email = f"{role.value}@example.com"
    _register_and_login(client, other_email, name="Other Role")
    _give_role(app, org["id"], other_email, role)

    response = _list_employees(client, org["id"])

    records = {r["name"]: r for r in response.get_json()["data"]}
    record = records["Other Role"]
    assert set(record.keys()) == {"membership_id", "name", "role", "status"}


def test_manager_sees_full_fields(client, app):
    csrf_token = _register_and_login(client, "owner4@example.com")
    org = _create_org(client, csrf_token)
    manager_csrf = _register_and_login(client, "manager4@example.com", name="Manager Four")
    _give_role(app, org["id"], "manager4@example.com", MembershipRole.MANAGER)

    response = _list_employees(client, org["id"])

    records = {r["name"]: r for r in response.get_json()["data"]}
    assert "email" in records["Manager Four"]


def test_directory_includes_members_without_an_employee_profile(client, app):
    csrf_token = _register_and_login(client, "owner5@example.com", name="Owner Five")
    org = _create_org(client, csrf_token)

    response = _list_employees(client, org["id"])

    body = response.get_json()["data"]
    assert len(body) == 1
    record = body[0]
    assert record["status"] is None
    assert record["job_title"] is None
    assert record["department"] is None
    assert record["manager"] is None


def test_directory_shows_profile_fields_when_present(client, app):
    csrf_token = _register_and_login(client, "owner6@example.com")
    org = _create_org(client, csrf_token)

    employee_csrf = _register_and_login(client, "employee6@example.com", name="Employee Six")
    employee_membership_id = _give_role(app, org["id"], "employee6@example.com", MembershipRole.EMPLOYEE)
    department_id = _make_department(app, org["id"], name="Engineering")
    _make_profile(
        app,
        org["id"],
        employee_membership_id,
        job_title="Software Engineer",
        department_id=department_id,
        status=EmployeeStatus.ACTIVE,
    )
    csrf_token = _login(client, "owner6@example.com")

    response = _list_employees(client, org["id"])

    records = {r["name"]: r for r in response.get_json()["data"]}
    record = records["Employee Six"]
    assert record["job_title"] == "Software Engineer"
    assert record["department"] == {"id": department_id, "name": "Engineering"}
    assert record["status"] == "active"


def test_directory_resolves_manager_name(client, app):
    csrf_token = _register_and_login(client, "owner7@example.com")
    org = _create_org(client, csrf_token)

    manager_csrf = _register_and_login(client, "manager7@example.com", name="Manager Seven")
    manager_membership_id = _give_role(app, org["id"], "manager7@example.com", MembershipRole.MANAGER)

    employee_csrf = _register_and_login(client, "employee7@example.com", name="Employee Seven")
    employee_membership_id = _give_role(app, org["id"], "employee7@example.com", MembershipRole.EMPLOYEE)
    _make_profile(app, org["id"], employee_membership_id, manager_membership_id=manager_membership_id)

    csrf_token = _login(client, "owner7@example.com")

    response = _list_employees(client, org["id"])

    records = {r["name"]: r for r in response.get_json()["data"]}
    assert records["Employee Seven"]["manager"] == {"membership_id": manager_membership_id, "name": "Manager Seven"}


def test_directory_never_leaks_a_cross_org_manager(client, app):
    """Defensive: EmployeeProfile.manager_membership_id has no write-
    time cross-org validation yet (FD-023), so the read side must not
    assume one was already enforced."""
    csrf_token = _register_and_login(client, "owner8@example.com")
    org_a = _create_org(client, csrf_token, name="Org A")
    org_b = _create_org(client, csrf_token, name="Org B")

    _register_and_login(client, "outsider-manager@example.com", name="Outsider Manager")
    outsider_manager_membership_id = _give_role(
        app, org_b["id"], "outsider-manager@example.com", MembershipRole.MANAGER
    )

    employee_csrf = _register_and_login(client, "employee8@example.com", name="Employee Eight")
    employee_membership_id = _give_role(app, org_a["id"], "employee8@example.com", MembershipRole.EMPLOYEE)
    _make_profile(app, org_a["id"], employee_membership_id, manager_membership_id=outsider_manager_membership_id)

    csrf_token = _login(client, "owner8@example.com")

    response = _list_employees(client, org_a["id"])

    records = {r["name"]: r for r in response.get_json()["data"]}
    assert records["Employee Eight"]["manager"] is None


def test_directory_never_leaks_a_cross_org_department(client, app):
    """Same defense as test_directory_never_leaks_a_cross_org_manager,
    for the sibling field: EmployeeProfile.department_id also has no
    write-time cross-org validation yet."""
    csrf_token = _register_and_login(client, "owner8b@example.com")
    org_a = _create_org(client, csrf_token, name="Org A2")
    org_b = _create_org(client, csrf_token, name="Org B2")
    outsider_department_id = _make_department(app, org_b["id"], name="Outsider Department")

    employee_csrf = _register_and_login(client, "employee8b@example.com", name="Employee Eight B")
    employee_membership_id = _give_role(app, org_a["id"], "employee8b@example.com", MembershipRole.EMPLOYEE)
    _make_profile(app, org_a["id"], employee_membership_id, department_id=outsider_department_id)

    csrf_token = _login(client, "owner8b@example.com")

    response = _list_employees(client, org_a["id"])

    records = {r["name"]: r for r in response.get_json()["data"]}
    assert records["Employee Eight B"]["department"] is None


def test_deactivated_memberships_are_excluded(client, app):
    csrf_token = _register_and_login(client, "owner9@example.com")
    org = _create_org(client, csrf_token)
    _register_and_login(client, "inactive9@example.com", name="Inactive Nine")
    _give_role(app, org["id"], "inactive9@example.com", MembershipRole.EMPLOYEE, status=MembershipStatus.INACTIVE)
    csrf_token = _login(client, "owner9@example.com")

    response = _list_employees(client, org["id"])

    names = {r["name"] for r in response.get_json()["data"]}
    assert "Inactive Nine" not in names


def test_cross_tenant_isolation(client, app):
    csrf_token = _register_and_login(client, "owner10@example.com", name="Owner Ten")
    org_a = _create_org(client, csrf_token, name="Org A")
    org_b = _create_org(client, csrf_token, name="Org B")

    _register_and_login(client, "member-b@example.com", name="Member B")
    _give_role(app, org_b["id"], "member-b@example.com", MembershipRole.EMPLOYEE)
    csrf_token = _login(client, "owner10@example.com")

    response = _list_employees(client, org_a["id"])

    names = {r["name"] for r in response.get_json()["data"]}
    assert names == {"Owner Ten"}


def test_search_matches_name_case_insensitively(client, app):
    csrf_token = _register_and_login(client, "owner11@example.com", name="Alpha Owner")
    org = _create_org(client, csrf_token)
    _register_and_login(client, "bravo11@example.com", name="Bravo Employee")
    _give_role(app, org["id"], "bravo11@example.com", MembershipRole.EMPLOYEE)
    csrf_token = _login(client, "owner11@example.com")

    response = _list_employees(client, org["id"], search="bravo")

    names = {r["name"] for r in response.get_json()["data"]}
    assert names == {"Bravo Employee"}


def test_search_never_matches_email(client, app):
    csrf_token = _register_and_login(client, "unique-address-12@example.com", name="Owner Twelve")
    org = _create_org(client, csrf_token)

    response = _list_employees(client, org["id"], search="unique-address-12")

    assert response.get_json()["data"] == []


def test_filter_by_department_id(client, app):
    csrf_token = _register_and_login(client, "owner13@example.com")
    org = _create_org(client, csrf_token)
    department_id = _make_department(app, org["id"], name="Sales")

    _register_and_login(client, "insales13@example.com", name="In Sales")
    in_sales_membership = _give_role(app, org["id"], "insales13@example.com", MembershipRole.EMPLOYEE)
    _make_profile(app, org["id"], in_sales_membership, department_id=department_id)

    _register_and_login(client, "outsales13@example.com", name="Out Of Sales")
    _give_role(app, org["id"], "outsales13@example.com", MembershipRole.EMPLOYEE)

    csrf_token = _login(client, "owner13@example.com")

    response = _list_employees(client, org["id"], department_id=department_id)

    names = {r["name"] for r in response.get_json()["data"]}
    assert names == {"In Sales"}


def test_filter_by_role(client, app):
    csrf_token = _register_and_login(client, "owner14@example.com", name="Owner Fourteen")
    org = _create_org(client, csrf_token)
    _register_and_login(client, "manager14@example.com", name="Manager Fourteen")
    _give_role(app, org["id"], "manager14@example.com", MembershipRole.MANAGER)
    csrf_token = _login(client, "owner14@example.com")

    response = _list_employees(client, org["id"], role="manager")

    names = {r["name"] for r in response.get_json()["data"]}
    assert names == {"Manager Fourteen"}


def test_filter_by_status_only_matches_members_with_that_profile_status(client, app):
    csrf_token = _register_and_login(client, "owner15@example.com")
    org = _create_org(client, csrf_token)

    _register_and_login(client, "active15@example.com", name="Active Fifteen")
    active_membership = _give_role(app, org["id"], "active15@example.com", MembershipRole.EMPLOYEE)
    _make_profile(app, org["id"], active_membership, status=EmployeeStatus.ACTIVE)

    _register_and_login(client, "noprofile15@example.com", name="No Profile Fifteen")
    _give_role(app, org["id"], "noprofile15@example.com", MembershipRole.EMPLOYEE)

    csrf_token = _login(client, "owner15@example.com")

    response = _list_employees(client, org["id"], status="active")

    names = {r["name"] for r in response.get_json()["data"]}
    assert names == {"Active Fifteen"}


def test_results_are_sorted_by_name(client, app):
    csrf_token = _register_and_login(client, "owner16@example.com", name="Zeta Owner")
    org = _create_org(client, csrf_token)
    _register_and_login(client, "alpha16@example.com", name="Alpha Employee")
    _give_role(app, org["id"], "alpha16@example.com", MembershipRole.EMPLOYEE)
    csrf_token = _login(client, "owner16@example.com")

    response = _list_employees(client, org["id"])

    names = [r["name"] for r in response.get_json()["data"]]
    assert names == ["Alpha Employee", "Zeta Owner"]


def test_pagination_meta_and_page_size(client, app):
    csrf_token = _register_and_login(client, "owner17@example.com", name="Owner Seventeen")
    org = _create_org(client, csrf_token)
    for i in range(3):
        email = f"emp17-{i}@example.com"
        _register_and_login(client, email, name=f"Employee {i}")
        _give_role(app, org["id"], email, MembershipRole.EMPLOYEE)
    csrf_token = _login(client, "owner17@example.com")

    response = _list_employees(client, org["id"], per_page=2, page=1)

    body = response.get_json()
    assert len(body["data"]) == 2
    assert body["meta"] == {"page": 1, "per_page": 2, "total": 4, "total_pages": 2}

    second_page = _list_employees(client, org["id"], per_page=2, page=2).get_json()
    assert len(second_page["data"]) == 2
    assert second_page["meta"]["page"] == 2


def test_invalid_per_page_returns_422(client):
    csrf_token = _register_and_login(client, "owner18@example.com")
    org = _create_org(client, csrf_token)

    response = _list_employees(client, org["id"], per_page="101")

    assert response.status_code == 422


def test_invalid_page_returns_422(client):
    csrf_token = _register_and_login(client, "owner19@example.com")
    org = _create_org(client, csrf_token)

    response = _list_employees(client, org["id"], page="0")

    assert response.status_code == 422


def test_invalid_department_id_returns_422(client):
    csrf_token = _register_and_login(client, "owner20@example.com")
    org = _create_org(client, csrf_token)

    response = _list_employees(client, org["id"], department_id="not-a-uuid")

    assert response.status_code == 422


def test_unknown_query_param_returns_422(client):
    csrf_token = _register_and_login(client, "owner21@example.com")
    org = _create_org(client, csrf_token)

    response = _list_employees(client, org["id"], sort_by="name")

    assert response.status_code == 422
