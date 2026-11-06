#!/usr/bin/env bash
# Logical backup (pg_dump custom format): portable across Postgres versions, restores one database.
# Writes ./backups/logical/<db>_<UTC timestamp>.dump
# Usage: backend/scripts/backup_logical.sh [database]   (default: $POSTGRES_DB or berlin)
set -euo pipefail
cd "$(dirname "$0")/../.."
DB="${1:-${POSTGRES_DB:-berlin}}"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
FILE="/backups/logical/${DB}_${STAMP}.dump"
docker compose exec -T -u postgres db \
  pg_dump -U "${POSTGRES_USER:-postgis}" -d "$DB" -Fc -f "$FILE"
echo "logical backup: backups/logical/${DB}_${STAMP}.dump ($(du -sh "backups/logical/${DB}_${STAMP}.dump" | cut -f1))"
echo "restore with: pg_restore -d <empty db with postgis> --no-owner backups/logical/${DB}_${STAMP}.dump"
