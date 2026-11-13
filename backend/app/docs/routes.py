"""Serves the hand-maintained OpenAPI contract (backend/openapi.yaml) as
JSON, plus an interactive Swagger UI page for browsing it."""
import os

import yaml
from flask import Blueprint, jsonify
from flask_swagger_ui import get_swaggerui_blueprint

from app.config import API_PREFIX

OPENAPI_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "openapi.yaml")

docs_bp = Blueprint("docs", __name__)


@docs_bp.route("/openapi.json", methods=["GET"])
def get_openapi_spec():
    with open(OPENAPI_FILE) as f:
        spec = yaml.safe_load(f)
    return jsonify(spec), 200


def build_swagger_ui_blueprint():
    return get_swaggerui_blueprint(
        base_url=f"{API_PREFIX}/docs",
        api_url=f"{API_PREFIX}/openapi.json",
        config={"app_name": "FlowDesk API"},
    )
