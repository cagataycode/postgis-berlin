# ACID & transactions — schema v2

Level 1 requires understanding transactions and ACID. This note ties those concepts to the amenity import pipeline.

## ACID in this project

| Property | Meaning here |
| --- | --- |
| **Atomicity** | One layer import either fully replaces that kind’s rows or leaves the previous data untouched. No half-deleted `street_tree` set. |
| **Consistency** | After commit, FKs hold (`kind_code`, `catalog_id`, `district_id`); geometries are valid SRID 25833 points/areas; `amenity_kind.geom_family` matches the target table. |
| **Isolation** | Concurrent readers (map API) should not see a mid-import empty kind. Use a single transaction around delete + insert + district assign (default READ COMMITTED is enough for L1). |
| **Durability** | Once committed, Postgres has written the change to durable storage (WAL). Local Docker is not a backup strategy — see Level 2 for continuous backups. |

## Recommended import transaction boundary

```text
BEGIN;
  -- upsert catalog row for this source
  -- DELETE FROM amenity_points WHERE kind_code = 'school';
  -- INSERT … (all school features)
  -- UPDATE … SET district_id = … WHERE kind_code = 'school' AND district_id IS NULL;
COMMIT;  -- or ROLLBACK on error
```

With SQLAlchemy: one `Session`, `commit()` on success, `rollback()` in `except`.

## What not to do

- Autocommit each INSERT (partial kind visible; failed mid-file = corrupt layer).  
- Delete all kinds in one transaction when only re-importing schools (unnecessary lock/blast radius).  
- Rely on the browser or API for writes — imports are offline scripts; API stays read-oriented.

## Demo for the report

1. Start import for one kind.  
2. Force a failure mid-batch (bad geometry / raised exception).  
3. Show row count for that `kind_code` unchanged after rollback.  
4. Re-run successfully; show count matches source feature count.
