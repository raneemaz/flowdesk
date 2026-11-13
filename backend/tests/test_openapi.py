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
