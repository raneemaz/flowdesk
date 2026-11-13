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


def test_openapi_file_has_exactly_one_components_block():
    """A second top-level `components:` key is valid YAML but silently
    clobbers the first (last key wins) - caught once already while
    writing this file. Checking the raw text, not the parsed dict (which
    can only ever show the surviving one), is what actually catches it."""
    with open(OPENAPI_FILE) as f:
        lines = f.readlines()

    top_level_components_lines = [line for line in lines if line.rstrip("\n") == "components:"]
    assert len(top_level_components_lines) == 1


def test_openapi_schemas_referenced_by_new_endpoints_are_defined():
    spec = _load_spec()
    schemas = spec["components"]["schemas"]

    assert "LoginRequest" in schemas
    assert "UserPublic" in schemas


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
