#!/usr/bin/env bash
# Runs once, on first container startup (empty data directory only).
# Creates a second database for tests, alongside POSTGRES_DB for dev,
# so test runs never touch dev data - mirrors the FD-004/FD-005 local setup.
set -euo pipefail

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
    SELECT 'CREATE DATABASE ${POSTGRES_TEST_DB} OWNER ${POSTGRES_USER}'
    WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = '${POSTGRES_TEST_DB}')\gexec
EOSQL
