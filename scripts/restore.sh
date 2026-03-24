#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════
#  Evidion — restore from backup
#  Usage:  ./scripts/restore.sh backups/evidion_20250101_030000.sql.gz
# ═══════════════════════════════════════════════════════════════

set -euo pipefail

FILE="${1:-}"
if [ -z "$FILE" ] || [ ! -f "$FILE" ]; then
  echo "Usage: $0 <backup_file.sql.gz>"
  echo "Available backups:"
  ls -lh "$(dirname "$0")/../backups/"*.sql.gz 2>/dev/null || echo "  (none)"
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
[ -f "$PROJECT_DIR/.env" ] && export $(grep -v '^#' "$PROJECT_DIR/.env" | grep -v '^\s*$' | xargs)

DB_USER="${POSTGRES_USER:-evidion}"
DB_NAME="${POSTGRES_DB:-evidion}"
CONTAINER="evidion_postgres"

echo "[$(date '+%Y-%m-%d %H:%M:%S')] Restoring from $FILE"
read -p "This will OVERWRITE all data in '$DB_NAME'. Continue? [y/N] " CONFIRM
[ "$CONFIRM" != "y" ] && { echo "Aborted."; exit 0; }

# Drop & recreate DB, then restore
docker exec -i "$CONTAINER" psql -U "$DB_USER" -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname='$DB_NAME' AND pid <> pg_backend_pid();" postgres
docker exec -i "$CONTAINER" psql -U "$DB_USER" -c "DROP DATABASE IF EXISTS $DB_NAME;" postgres
docker exec -i "$CONTAINER" psql -U "$DB_USER" -c "CREATE DATABASE $DB_NAME;" postgres
gunzip -c "$FILE" | docker exec -i "$CONTAINER" psql -U "$DB_USER" "$DB_NAME"

echo "[$(date '+%Y-%m-%d %H:%M:%S')] Restore complete."
