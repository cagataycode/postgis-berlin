#!/usr/bin/env bash
# Point-in-time recovery into a THROWAWAY container (never touches the live database).
# Usage: backend/scripts/restore_pitr.sh <base-dir-name> "<target time, UTC>" [port]
#   e.g. backend/scripts/restore_pitr.sh 20261106T123500Z "2026-11-06 12:40:00+00" 5434
# Starts container `berlin-restore` on <port> (default 5434) with volume `berlin_restore_data`.
# Remove afterwards:  docker rm -f berlin-restore && docker volume rm berlin_restore_data
set -euo pipefail
cd "$(dirname "$0")/../.."
BASE="${1:?base backup directory name under backups/base}"
TARGET="${2:?recovery target time, e.g. \"2026-11-06 12:40:00+00\"}"
PORT="${3:-5434}"
IMAGE="postgis/postgis:16-3.4"
SRC="$PWD/backups"
[ -f "$SRC/base/$BASE/base.tar.gz" ] || { echo "no such base backup: $SRC/base/$BASE" >&2; exit 1; }

docker rm -f berlin-restore >/dev/null 2>&1 || true
docker volume rm berlin_restore_data >/dev/null 2>&1 || true
docker volume create berlin_restore_data >/dev/null

# Unpack (new volumes are root-owned), hand the data directory to postgres, add recovery settings.
docker run --rm -v berlin_restore_data:/data -v "$SRC":/backups:ro "$IMAGE" bash -c "
  set -e
  tar -xzf /backups/base/$BASE/base.tar.gz -C /data
  mkdir -p /data/pg_wal && tar -xzf /backups/base/$BASE/pg_wal.tar.gz -C /data/pg_wal
  chown -R postgres:postgres /data
  chmod 700 /data
  touch /data/recovery.signal
  {
    echo \"restore_command = 'cp /backups/wal/%f %p'\"
    echo \"recovery_target_time = '$TARGET'\"
    echo \"recovery_target_action = 'promote'\"
  } >> /data/postgresql.auto.conf
"
docker run -d --name berlin-restore -p "$PORT":5432 \
  -v berlin_restore_data:/var/lib/postgresql/data -v "$SRC":/backups:ro "$IMAGE" >/dev/null

echo "recovering to $TARGET ..."
for _ in $(seq 1 120); do
  if docker exec berlin-restore psql -U "${POSTGRES_USER:-postgis}" -d postgres -Atc "SELECT NOT pg_is_in_recovery()" 2>/dev/null | grep -q t; then
    echo "recovered; connect on localhost:$PORT"; exit 0
  fi
  sleep 2
done
echo "recovery did not finish; see: docker logs berlin-restore" >&2; exit 1
