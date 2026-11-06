# ACID & transactions — schema v2

How ACID maps to the amenity import pipeline and to the constraints in [schema.sql](schema.sql).

## ACID in this project

| Property | Meaning here |
| --- | --- |
| **Atomicity** | One layer import either fully applies (rows, operators, tags, details, district ids) or leaves the previous data untouched. No half-updated `street_tree` set. |
| **Consistency** | Constraints guard every commit: composite FKs (kind ↔ geometry family, tag category ↔ kind), `UNIQUE (kind_code, source_id)`, `CHECK`s on detail columns, `ST_IsValid` on areas. A bad row aborts the transaction instead of being stored. |
| **Isolation** | Map readers must not see a half-imported kind. Imports use upsert inside one transaction, so readers (READ COMMITTED) see either the old or the new state of each row, never an empty kind. |
| **Durability** | After commit the change is in the WAL on disk. Docker volume ≠ backup: continuous archiving is phase 8. |

## Transaction boundary: one transaction per layer (D4, D10)

```text
-- tx A (own transaction)
INSERT INTO import_run (catalog_id, status) VALUES (…, 'running');   COMMIT;

-- tx B (the import)
BEGIN;
  upsert dataset_catalog
  COPY features → TEMP staging
  INSERT … ON CONFLICT (kind_code, source_id) DO UPDATE …            -- changed rows only
  DELETE rows of this kind missing from staging
  UPDATE district_id (spatial join), upsert operator, tags, detail tables
COMMIT;   -- or ROLLBACK on any error

-- tx C (own transaction)
UPDATE import_run SET status = 'committed' | 'failed', counts / error;   COMMIT;
```

`import_run` is written outside tx B on purpose: if it were inside, a rollback would erase the record of the failure.

With SQLAlchemy: one `Session` per layer, `commit()` on success, `rollback()` in `except`, then the status update in a fresh session.

## Why upsert instead of delete + reinsert

- Row ids stay stable, so tag and detail rows are not churned.
- Re-running an unchanged import writes nothing (0 inserted / 0 updated / 0 deleted).
- No mass `DELETE` on ~960k tree rows (dead tuples, table bloat).

## Other transaction uses

- **Playground:** `POST /sql/run` uses a read-only role plus `statement_timeout` (D11). Writes fail at the database, not only in Python.
- **Trigger:** `set_updated_at()` runs inside the same transaction as the update, so `updated_at` is atomic with the change.

## What not to do

- Autocommit each INSERT (partial kind visible; failed mid-file = corrupt layer).
- One transaction around all layers (a failure in the last layer discards hours of tree import).
- Writes from the browser or API: imports are offline scripts; the API stays read-only.

## Demo for the report

1. Run `python -m scripts.import_v2 --layers toilets --fail-after-rows 100`.
2. Show `SELECT count(*) … WHERE kind_code = 'toilet'` unchanged, and `import_run.status = 'failed'` with the error.
3. Re-run without the flag: status `committed`, counts match the source.
4. Re-run again: 0 inserted / 0 updated / 0 deleted, ids unchanged.
