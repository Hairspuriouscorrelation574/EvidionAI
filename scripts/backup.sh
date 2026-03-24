#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════
#  Evidion — PostgreSQL backup script
#  Usage:  ./scripts/backup.sh
#  Cron:   0 3 * * * /path/to/evidion/scripts/backup.sh >> /var/log/evidion-backup.log 2>&1
# ═══════════════════════════════════════════════════════════════

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

# Load .env if present
[ -f "$PROJECT_DIR/.env" ] && export $(grep -v '^#' "$PROJECT_DIR/.env" | grep -v '^\s*$' | xargs)

BACKUP_DIR="${BACKUP_DIR:-$PROJECT_DIR/backups}"
KEEP_DAYS="${BACKUP_KEEP_DAYS:-7}"
DB_USER="${POSTGRES_USER:-evidion}"
DB_NAME="${POSTGRES_DB:-evidion}"
CONTAINER="evidion_postgres"

mkdir -p "$BACKUP_DIR"

TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
FILE="$BACKUP_DIR/evidion_${TIMESTAMP}.sql.gz"

echo "[$(date '+%Y-%m-%d %H:%M:%S')] Starting backup → $FILE"

docker exec "$CONTAINER" pg_dump -U "$DB_USER" "$DB_NAME" | gzip > "$FILE"

SIZE=$(du -sh "$FILE" | cut -f1)
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Done. Size: $SIZE"

# Rotate: delete backups older than KEEP_DAYS
DELETED=$(find "$BACKUP_DIR" -name "evidion_*.sql.gz" -mtime +$KEEP_DAYS -print -delete | wc -l)
[ "$DELETED" -gt 0 ] && echo "[$(date '+%Y-%m-%d %H:%M:%S')] Rotated $DELETED old backup(s)"

echo "[$(date '+%Y-%m-%d %H:%M:%S')] Backup complete."
