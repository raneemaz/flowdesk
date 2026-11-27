#!/usr/bin/env bash
# FD-065. Restores a backup produced by backup_db.sh. Destructive -
# this replaces data in whatever database DATABASE_URL points at, so
# double-check that value before running this against production.
#
# Usage: DATABASE_URL=postgresql://... ./scripts/restore_db.sh backups/flowdesk-....sql.gz
set -euo pipefail

if [ -z "${DATABASE_URL:-}" ]; then
  echo "DATABASE_URL must be set (the TARGET database to restore into)." >&2
  exit 1
fi

if [ -z "${1:-}" ]; then
  echo "Usage: DATABASE_URL=... $0 <backup-file.sql.gz>" >&2
  exit 1
fi

backup_file="$1"
# Redacts user:password@ before printing - this confirmation exists so
# an operator can double check the TARGET host/database, never to
# re-display the password back to a terminal, shell history, or (if
# this script is ever run non-interactively) a log.
redacted_target="$(echo "$DATABASE_URL" | sed -E 's#(://)[^/@]*@#\1[redacted]@#')"
echo "About to restore $backup_file into:"
echo "  $redacted_target"
read -r -p "Type 'yes' to continue: " confirmation
if [ "$confirmation" != "yes" ]; then
  echo "Aborted."
  exit 1
fi

gunzip -c "$backup_file" | psql "$DATABASE_URL"

echo "Restore complete."
