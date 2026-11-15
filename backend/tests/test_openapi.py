import os

import yaml
from openapi_spec_validator import validate

OPENAPI_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "openapi.yaml")


def _load_spec():
    with open(OPENAPI_FILE) as f:
        return yaml.safe_load(f)


def test_openapi_file_conforms_to_the_openapi_3_specification():
    validate(_load_spec())


def test_openapi_documents_the_real_health_endpoint():
    spec = _load_spec()

    assert "/health" in spec["paths"]
    assert "get" in spec["paths"]["/health"]


def test_openapi_documents_the_real_register_endpoint():
    spec = _load_spec()

    assert "/auth/register" in spec["paths"]
    assert "post" in spec["paths"]["/auth/register"]


def test_openapi_documents_the_real_login_and_logout_endpoints():
    spec = _load_spec()

    assert "post" in spec["paths"]["/auth/login"]
    assert "post" in spec["paths"]["/auth/logout"]


def test_openapi_documents_the_real_me_endpoint():
    spec = _load_spec()

    assert "get" in spec["paths"]["/auth/me"]


def test_openapi_documents_the_real_organizations_endpoint():
    spec = _load_spec()

    assert "post" in spec["paths"]["/organizations"]
    assert "get" in spec["paths"]["/organizations"]


def test_openapi_documents_the_real_invitations_endpoints():
    spec = _load_spec()

    assert "post" in spec["paths"]["/organizations/{organization_id}/invitations"]
    assert "get" in spec["paths"]["/organizations/{organization_id}/invitations"]
    assert "delete" in spec["paths"]["/organizations/{organization_id}/invitations/{invitation_id}"]
    assert "post" in spec["paths"]["/invitations/accept"]


def test_openapi_documents_the_real_departments_endpoints():
    spec = _load_spec()

    assert "post" in spec["paths"]["/organizations/{organization_id}/departments"]
    assert "get" in spec["paths"]["/organizations/{organization_id}/departments"]
    assert "patch" in spec["paths"]["/organizations/{organization_id}/departments/{department_id}"]
    assert "delete" in spec["paths"]["/organizations/{organization_id}/departments/{department_id}"]


def test_openapi_documents_the_real_employees_endpoint():
    spec = _load_spec()

    assert "get" in spec["paths"]["/organizations/{organization_id}/employees"]


def test_openapi_documents_the_real_employee_profile_endpoints():
    spec = _load_spec()

    assert "get" in spec["paths"]["/organizations/{organization_id}/employees/{membership_id}"]
    assert "patch" in spec["paths"]["/organizations/{organization_id}/employees/{membership_id}"]


def test_openapi_documents_the_real_tasks_endpoints():
    spec = _load_spec()

    assert "post" in spec["paths"]["/organizations/{organization_id}/tasks"]
    assert "get" in spec["paths"]["/organizations/{organization_id}/tasks"]
    assert "get" in spec["paths"]["/organizations/{organization_id}/tasks/{task_id}"]
    assert "patch" in spec["paths"]["/organizations/{organization_id}/tasks/{task_id}"]
    assert "patch" in spec["paths"]["/organizations/{organization_id}/tasks/{task_id}/assign"]
    assert "patch" in spec["paths"]["/organizations/{organization_id}/tasks/{task_id}/status"]


def test_openapi_file_has_exactly_one_components_block():
    """A second top-level `components:` key is valid YAML but silently
    clobbers the first (last key wins) - caught once already while
    writing this file. Checking the raw text, not the parsed dict (which
    can only ever show the surviving one), is what actually catches it."""
    with open(OPENAPI_FILE) as f:
        lines = f.readlines()

    top_level_components_lines = [line for line in lines if line.rstrip("\n") == "components:"]
    assert len(top_level_components_lines) == 1


def test_openapi_schemas_block_has_no_duplicate_schema_names():
    """Same failure mode as the components-block test above, one level
    deeper: a duplicate schema name within components.schemas is also
    valid YAML that silently clobbers the first definition (last key
    wins) - a real instance of this (a duplicate PaginationMeta) existed
    in this file until FD-023 found and removed it. Checking the raw
    text catches it the same way; the parsed dict can only ever show
    the surviving definition."""
    import re

    with open(OPENAPI_FILE) as f:
        lines = f.readlines()

    # components.schemas is the last top-level section in this file, and
    # its entries sit one level deeper (4 spaces) than every other
    # 4-space-indented key in the document (paths' get/post/patch/
    # delete/parameters) - scanning only from "  schemas:" onward avoids
    # matching those unrelated keys too.
    schemas_start = next(i for i, line in enumerate(lines) if line.rstrip("\n") == "  schemas:")
    schema_name_pattern = re.compile(r"^    ([A-Za-z0-9_]+):$")
    schema_names = [
        match.group(1) for line in lines[schemas_start + 1 :] if (match := schema_name_pattern.match(line))
    ]

    duplicates = {name for name in schema_names if schema_names.count(name) > 1}
    assert not duplicates, f"Duplicate schema name(s) in components.schemas: {duplicates}"


def test_openapi_schemas_referenced_by_new_endpoints_are_defined():
    spec = _load_spec()
    schemas = spec["components"]["schemas"]

    assert "LoginRequest" in schemas
    assert "UserPublic" in schemas
    assert "CreateOrganizationRequest" in schemas
    assert "OrganizationPublic" in schemas
    assert "MembershipPublic" in schemas
    assert "CreateInvitationRequest" in schemas
    assert "InvitationPublic" in schemas
    assert "CreateDepartmentRequest" in schemas
    assert "UpdateDepartmentRequest" in schemas
    assert "DepartmentPublic" in schemas
    assert "EmployeePublic" in schemas
    assert "EmployeeProfilePublic" in schemas
    assert "UpdateEmployeeProfileRequest" in schemas
    assert "CreateTaskRequest" in schemas
    assert "TaskPublic" in schemas
    assert "AssignTaskRequest" in schemas
    assert "UpdateTaskStatusRequest" in schemas
    assert "UpdateTaskRequest" in schemas
    assert "PaginationMeta" in schemas


def test_openapi_json_endpoint_serves_the_same_spec(client):
    response = client.get("/api/v1/openapi.json")

    assert response.status_code == 200
    body = response.get_json()
    assert body["info"]["title"] == "FlowDesk API"
    assert "/health" in body["paths"]


def test_swagger_ui_page_is_served(client):
    response = client.get("/api/v1/docs/")

    assert response.status_code == 200
    assert b"swagger" in response.data.lower()
