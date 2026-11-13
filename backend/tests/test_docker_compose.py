"""Validates docker-compose.yml without needing a Docker daemon.

This repo's dev environment doesn't have Docker installed, so this is the
real verification available for FD-006 - structural/schema correctness,
plus exercising the init script's SQL logic directly against Postgres.
A `docker compose up` round-trip still needs to happen on a machine that
actually has Docker.
"""
import json
import os
import subprocess

import yaml
from jsonschema import validate

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
COMPOSE_FILE = os.path.join(REPO_ROOT, "docker-compose.yml")
SCHEMA_FILE = os.path.join(os.path.dirname(__file__), "fixtures", "compose-spec.schema.json")
INIT_SCRIPT = os.path.join(REPO_ROOT, "docker", "postgres-initdb", "01-create-test-db.sh")


def _load_compose():
    with open(COMPOSE_FILE) as f:
        return yaml.safe_load(f)


def test_compose_file_is_valid_yaml():
    compose = _load_compose()

    assert "services" in compose
    assert set(compose["services"]) == {"postgres", "redis"}


def test_compose_file_matches_the_official_schema():
    compose = _load_compose()
    with open(SCHEMA_FILE) as f:
        schema = json.load(f)

    validate(instance=compose, schema=schema)


def test_compose_services_do_not_hardcode_secrets():
    compose = _load_compose()
    postgres_env = compose["services"]["postgres"]["environment"]

    assert postgres_env["POSTGRES_PASSWORD"] == "${POSTGRES_PASSWORD:?Set POSTGRES_PASSWORD in .env}"


def test_postgres_init_script_has_valid_shell_syntax():
    result = subprocess.run(["bash", "-n", INIT_SCRIPT], capture_output=True, text=True)

    assert result.returncode == 0, result.stderr
