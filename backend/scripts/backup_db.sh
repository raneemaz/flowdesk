#!/usr/bin/env bash
# FD-065. Manual backup of the production database via pg_dump, for use
# alongside (or instead of, on a plan with none) a managed provider's
# own automated backups - see backend/README.md's Deployment section
# for when this is actually needed and how often to run it.
#
# Usage: DATABASE_URL=postgresql://... ./scripts/backup_db.sh
# Produces: backups/flowdesk-YYYY-MM-DDTHH-MM-SSZ.sql.gz
set -euo pipefail

if [ -z "${DATABASE_URL:-}" ]; then
  echo "DATABASE_URL must be set (the production connection string, not .env's dev default)." >&2
  exit 1
fi

mkdir -p backups
timestamp="$(date -u +%Y-%m-%dT%H-%M-%SZ)"
output="backups/flowdesk-${timestamp}.sql.gz"

pg_dump "$DATABASE_URL" --format=plain --no-owner --no-privileges | gzip > "$output"

echo "Backup written to $output"
