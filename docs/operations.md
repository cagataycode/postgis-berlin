# Operations: backups, recovery, roles

How the database is kept safe and how we proved it. Everything here ran on the real data (980k features, 1.4 GB database) in Docker on a laptop, on 2026-11-06.

## What is in place

| Piece | Where | What it does |
| --- | --- | --- |
| Continuous WAL archiving | [docker-compose.yml](../docker-compose.yml) | `archive_mode=on`; every finished WAL segment (and at least one per 60 s) is copied to `./backups/wal` |
| Base backup | [backup_base.sh](../backend/scripts/backup_base.sh) | `pg_basebackup` (tar, gzip, WAL streamed) into `./backups/base/<UTC timestamp>/` |
| Logical backup | [backup_logical.sh](../backend/scripts/backup_logical.sh) | `pg_dump -Fc` of one database into `./backups/logical/` (portable, restores a single database) |
| Point-in-time recovery | [restore_pitr.sh](../backend/scripts/restore_pitr.sh) | unpacks a base backup into a throwaway container and replays the WAL archive up to a target time |
| Query statistics | `pg_stat_statements` (migration 0013) | slowest queries after a demo session |

`./backups/` is git-ignored.

### Two kinds of backup, on purpose

- **Base backup + WAL archive** restores the whole cluster to *any moment* after the base backup (here: down to the second). This is the "continuous backup".
- **Logical dump** restores one database, on another Postgres version or machine, but only to the moment it was taken.

Measured: base backup 70 s, 225 MB (database 1.4 GB); logical dump 46 s, 80 MB.

## Restore drill (point-in-time recovery)

Scenario: someone deletes all public toilets by mistake. We recover them from the archive without touching the live database until the data is verified.

```bash
# 0. Start the database with archiving, take a base backup
POSTGRES_PORT=5433 docker compose up -d db
backend/scripts/backup_base.sh                  # -> backups/base/20261106T113211Z
```

```sql
-- 1. Note the time, then "the accident" (live database)
SELECT count(*) FILTER (WHERE kind_code = 'toilet') AS toilets, count(*) AS total FROM amenity_points;
--  toilets |  total
--      525 | 975765
SELECT now();                                   -- 2026-11-06 11:34:20+00   <- recovery target
DELETE FROM amenity_points WHERE kind_code = 'toilet';   -- DELETE 525 (junction rows cascade)
-- committed at 11:34:26
SELECT count(*) FILTER (WHERE kind_code = 'toilet'), count(*) FROM amenity_points;
--      0 | 975240
SELECT pg_switch_wal();                         -- make sure the segment holding the delete is archived
```

```bash
# 2. Recover into a separate container, stopping before the delete
backend/scripts/restore_pitr.sh 20261106T113211Z "2026-11-06 11:34:20+00" 5434
```

The restore container's log shows the recovery working:

```text
LOG:  starting point-in-time recovery to 2026-11-06 11:34:20+00
LOG:  starting backup recovery with redo LSN 3/C6000028, checkpoint LSN 3/C6000060, on timeline ID 1
LOG:  restored log file "0000000100000003000000C6" from archive
      ... (C7 to CA)
LOG:  consistent recovery state reached at 3/C7000050
LOG:  recovery stopping before commit of transaction 2144, time 2026-11-06 11:34:26.44512+00
```

It stops *before the commit of the DELETE transaction*. The whole recovery took 19 s.

```text
restored (port 5434):   toilets 525 | total 975765 | toilet tag links 827
live (port 5433):       toilets   0 | total 975240 | toilet tag links   0
```

```bash
# 3. Bring the rows back into the live database from the recovered copy (ids preserved)
#    COPY (SELECT * FROM amenity_points WHERE kind_code='toilet') TO STDOUT   on the restore container
#    COPY amenity_points FROM STDIN                                            on the live database (same for amenity_point_tag)
```

```text
live after copy-back:   toilets 525 | total 975765 | tag links 827
md5 of toilet (id, source_id) restored vs live:  75fbe36b31d43172c502ff79fd0c9d90  (identical)
```

```bash
# 4. Remove the throwaway instance
docker rm -f berlin-restore && docker volume rm berlin_restore_data
```

### What the drill shows

- A deleted kind comes back with **the same ids**, because recovery replays the original rows; a re-import would have created new ids for everything that references them.
- The live database stayed online and was only written to in step 3, after the recovered data was checked.
- `recovery_target_time` is a time, so the target must be chosen from knowledge of the accident (here: noted just before the DELETE). `pg_create_restore_point('name')` with `recovery_target_name` is the safer habit when a risky operation is planned.

### Limits (honest list)

- The archive lives on the same laptop as the database. A real setup copies `backups/` off the machine (object storage, another host).
- Base backups are taken by hand (`backup_base.sh`); there is no schedule or retention policy.
- The drill restores a *cluster*; recovering one table needed the copy-back in step 3.
- The restore container runs the amd64 image under emulation on Apple silicon (a warning is printed); speed is not representative of a production host.

## Roles

| Role | Used for | Privileges |
| --- | --- | --- |
| `postgis` (owner, superuser in the Docker image) | Alembic migrations, `import_v2`, and in development the API's normal reads | everything |
| `berlin_ro` | the SQL playground (`POST /sql/run`) | `SELECT` on all tables, the views and `amenities_near()`; `default_transaction_read_only = on` |

The playground cannot write even if the Python `SELECT` check were bypassed (tested in `tests/test_orm_models.py` and `tests/test_constraints.py`).

Gap to name: in this development setup the API's own read endpoints also connect as the owner (`DATABASE_URL`). A production deployment would give the API a third, non-superuser role with `SELECT` only, or point `DATABASE_URL` at `berlin_ro`, and keep the owner for migrations and imports.

## Inspecting slow queries

After a demo session:

```sql
SELECT calls, round(total_exec_time) AS total_ms, round(mean_exec_time, 1) AS mean_ms,
       left(regexp_replace(query, '\s+', ' ', 'g'), 80) AS query
FROM pg_stat_statements
WHERE dbid = (SELECT oid FROM pg_database WHERE datname = current_database())
ORDER BY total_exec_time DESC LIMIT 10;
```

Reset with `SELECT pg_stat_statements_reset();`. The health check in `docker-compose.yml` (`pg_isready`) was already in place.
