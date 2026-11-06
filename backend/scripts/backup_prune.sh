#!/usr/bin/env bash
# Retention for physical backups: keep the newest KEEP base backups (default 3), delete older ones,
# then delete archived WAL older than the oldest kept base backup (it is no longer needed for PITR).
# Usage: backend/scripts/backup_prune.sh           (KEEP=3 by default)
#        DRY_RUN=1 backend/scripts/backup_prune.sh (only print what would be removed)
set -euo pipefail
cd "$(dirname "$0")/../.."
KEEP="${KEEP:-3}"
DRY_RUN="${DRY_RUN:-0}"

ALL=()
while IFS= read -r d; do ALL+=("$d"); done < <(ls -1 backups/base 2>/dev/null | sort)
COUNT=${#ALL[@]}
if (( COUNT == 0 )); then echo "no base backups, nothing to prune"; exit 0; fi

for ((i = 0; i < COUNT - KEEP; i++)); do
  echo "remove base backup: ${ALL[i]}"
  [[ "$DRY_RUN" == 1 ]] || rm -rf "backups/base/${ALL[i]}"
done

OLDEST="${ALL[$(( COUNT > KEEP ? COUNT - KEEP : 0 ))]}"
# First WAL segment this backup needs is named in its backup_label.
WAL="$(tar -xzOf "backups/base/${OLDEST}/base.tar.gz" backup_label | sed -n 's/^START WAL LOCATION: .*(file \(.*\))$/\1/p')"
[[ -n "$WAL" ]] || { echo "cannot read START WAL from ${OLDEST}; refusing to prune WAL" >&2; exit 1; }
echo "oldest kept base backup: ${OLDEST} (needs WAL from ${WAL})"
if [[ "$DRY_RUN" == 1 ]]; then
  docker compose exec -T -u postgres db pg_archivecleanup -n /backups/wal "$WAL"
else
  docker compose exec -T -u postgres db pg_archivecleanup -d /backups/wal "$WAL"
fi
echo "kept $(( COUNT > KEEP ? KEEP : COUNT )) base backup(s); WAL archive now $(du -sh backups/wal | cut -f1)"
