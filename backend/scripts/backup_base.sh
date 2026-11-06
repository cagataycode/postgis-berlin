#!/usr/bin/env bash
# Physical base backup of the Docker database (basis for point-in-time recovery).
# Writes ./backups/base/<UTC timestamp>/{base.tar.gz,pg_wal.tar.gz}; WAL archive lives in ./backups/wal.
# Usage: backend/scripts/backup_base.sh        (run from anywhere; needs `docker compose up -d db`)
set -euo pipefail
cd "$(dirname "$0")/../.."
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
DIR="/backups/base/${STAMP}"
docker compose exec -T -u postgres db \
  pg_basebackup -U "${POSTGRES_USER:-postgis}" -D "$DIR" -Ft -z -X stream -c fast -P
# Close the current WAL segment so everything up to this moment is archived.
docker compose exec -T db psql -U "${POSTGRES_USER:-postgis}" -d postgres -Atc "SELECT pg_switch_wal()" >/dev/null
echo "base backup: backups/base/${STAMP} ($(du -sh "backups/base/${STAMP}" | cut -f1))"
