# Implementation log

Running record of what we did, why, and what came out of it. Plan: [module-requirements/implementation-plan.md](module-requirements/implementation-plan.md).

**Rule:** at the end of every phase, add one entry (template below) before moving on. Keep entries short and put real output in them: counts, plans, test results.

## Entry template

```markdown
### Phase N — title (YYYY-MM-DD)

**Goal:** one line.
**What we did:** 3–6 bullets, in order. Name files/commits.
**How we decided:** the question, the evidence (query, data profile, EXPLAIN), the alternatives rejected.
**Outcome:** what works now, with numbers or pasted output.
**Problems / changes to plan:** what broke or surprised us; what we changed.
**Report/demo material:** which output to reuse (EXPLAIN, ERD, test run, counts).
```

---

## Decision evidence (how we got to each reason)

Each decision in the plan came from a check on the real data or code, not from preference. Fill the "Outcome" column when the phase is done.

| Decision                                     | How we got there (evidence)                                                                                                                                                                             | Rejected alternative                                         | Outcome |
| -------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------ | ------- |
| D1 Merge 15 layer tables into points + areas | Live models are the same shape: `source_id, name, <type col>, catalog_id, district_id, attrs, geom`; only the type column name differs ([models.py](../backend/app/models.py)).                         | Keep one table per layer.                                    | pending |
| D3 Many-to-many via tags                     | Profiled cached WFS: EV `anschluss_1..4` gives 7 connector types, 247 chargers with more than one; Kita `ang_1` gives 9 approaches, 950 of 2,905 kitas with more than one. Values like `A/B` break 1NF. | Dedicated junction per kind (needs one table pair per kind). | Phase 2: 19 tags, 10,040 links (EV 7 / 5,297, Kita 9 / 3,916, toilet 3 / 827), matching the raw-data profile |
| D4 Upsert on `(kind_code, source_id)`        | Checked source key per layer: unique and non-null except toilets (525 null) and bike parking (19 duplicate `projektnummer`). Current import deletes and reinserts everything.                           | Delete and reinsert (new ids every run).                     | Phase 2: repeat import of 980k rows changed 0 rows, ids identical (checksum) |
| D6 `tree_species` lookup                     | `art_bot → art_dtsch, gattung` had 0 conflicts across street (719 species) and park (835) trees.                                                                                                        | Keep species text on every tree row.                         | Phase 2: 916 species (street ∪ park); 0 conflicts on upsert |
| D7 `operator` table                          | `t_nr → t_name, t_art` had 0 conflicts over 1,165 kita operators; EV `betreiber` has 203 names.                                                                                                         | Operator name copied onto features.                          | Phase 2: 1,404 operators (1,165 Kita by `t_nr`, rest by name) |
| D8 Partition by kind                         | Trees are about 962k of about 981k point rows (counted from cache files).                                                                                                                               | Separate tree tables; one big table.                         | pending |
| 0 → NULL for tree sizes                      | `baumhoehe` is 0 or missing for about 69k street and 95k park trees.                                                                                                                                    | Store 0.                                                     | pending |
| D11 Read-only role                           | [sql.py](../backend/app/routers/sql.py) relies on a SELECT check plus `statement_timeout`; no database privilege limit.                                                                                 | Python check only.                                           | pending |

---

## Entries

### Phase pre-0 — Design and planning (2026-11-05)

**Goal:** agree a schema and plan that satisfies the module hand-in.
**What we did:**

- Read the module requirements, the live code and schema v2 docs.
- Found the gap: no many-to-many relationship in the live or v2 schema.
- Profiled cached WFS data for multi-valued fields, key uniqueness and operator/species dependencies (results in the table above).
- Wrote the Mermaid ERD, updated `schema.sql`, and wrote [project-plan.md](project-plan.md) and the implementation plan.
  **How we decided:** see the evidence table.
  **Outcome:** design docs and plan committed to the working tree (not yet to git). Nothing in the database has changed.
  **Problems / changes to plan:** the database was not running (Docker down), so row counts come from cache files and `schema.sql` has not been applied yet.
  **Report/demo material:** ERD, data volume table in project-plan.

### Phase 0 — Sync design docs (2026-11-05)

**Goal:** make the design docs match the agreed plan, and prove the DDL works before writing a migration.
**What we did:**

- Rewrote [schema.sql](schema-v2/schema.sql) to the target design: 16 tables, `amenity_points` list-partitioned by kind (3 partitions), composite FKs, two M:N relationships, detail tables, `import_run`, update trigger, GiST/btree/GIN indexes, seeds.
- Rewrote [erd.md](schema-v2/erd.md) (Mermaid, all 16 tables, cardinalities, index table), [normalization.md](schema-v2/normalization.md), [acid-and-transactions.md](schema-v2/acid-and-transactions.md), [indexing-and-explain.md](schema-v2/indexing-and-explain.md) and [import-mapping.md](schema-v2/import-mapping.md); updated the schema README and project plan counts.
- Started Docker, applied `schema.sql` to a scratch database (`schema_v2_check`, PostGIS 16) with `ON_ERROR_STOP`, ran 13 constraint checks, then dropped it.
  **How we decided:**
- Dropped the composite GiST `(kind_code, geom)` and the plain `kind_code` btree from the DDL: partition pruning plus the `(kind_code, source_id)` unique index already cover kind lookups. The composite stays as a phase 7 experiment.
- Identity column replaced by a shared sequence default: `GENERATED ALWAYS AS IDENTITY` on a partitioned parent is awkward, and a sequence also lets us keep one id space across partitions.
- Detail tables reference `amenity_points (id, kind_code)`, which works because Postgres accepts foreign keys that point at a partitioned table's primary key.
  **Outcome:** the DDL applies cleanly. Constraint checks (all behaved as designed):
- area kind in `amenity_points` → FK error
- duplicate `(kind_code, source_id)` → unique error
- Kita tag on a toilet → FK error on `kind_tag_category`
- tag with wrong category → FK error
- wrong kind for a point in the junction → FK error
- `tree_detail` for a kita → CHECK error
- `height_m = 0` → CHECK error
- self-intersecting polygon → CHECK error
- rows route to `amenity_points_street_tree` / `amenity_points_other`
- `UPDATE` bumps `updated_at`
- `WHERE kind_code = 'street_tree'` plans against only the street-tree partition.
  **Problems / changes to plan:**
- Check 7 first hit the junction primary key, not the FK, so it proved nothing. Re-run with a fresh tag showed the intended FK error.
- Plan said 17 tables; the real count is 16 plus 3 partitions. Docs corrected.
- Docker was stopped; started Docker Desktop. The dev `berlin` database was not touched.
  **Report/demo material:** the constraint checks are the "what the database refuses" demo; phase 1 turns them into `tests/test_constraints.py`.

### Phase 1 — Migration `0009_schema_v2` (2026-11-05)

**Goal:** create the v2 schema through Alembic, with tests proving the database enforces its rules.
**What we did:**

- Wrote [0009_schema_v2.py](../backend/alembic/versions/0009_schema_v2.py) by hand: lookups, partitioned `amenity_points`, `amenity_areas`, tag tables (both M:N), detail tables, `import_run`, indexes, seeds, `berlin_ro` role. DDL lives in the migration (self-contained); [schema.sql](schema-v2/schema.sql) stays the commented reference.
- `alembic/env.py`: `include_object` hook so autogenerate never proposes dropping tables that have no model yet (v2 tables until phase 3, partitions always).
- `app/config.py` + `.env.example`: `DATABASE_URL_RO` for the read-only role.
- [tests/test_constraints.py](../backend/tests/test_constraints.py): 18 tests, each in a rolled-back transaction with expected failures in savepoints. They assert the **name of the violated constraint**, not just "an error".
- Ran on a scratch database `schema_v2_mig`: `upgrade` → `downgrade -1` → `upgrade`.
  **How we decided:**
- Reuse `dataset_catalog`, `districts`, `neighborhoods` as they are: the live columns already match v2 (checked against [models.py](../backend/app/models.py)). The migration creates only new objects, so it is additive and the legacy tables keep working until cutover.
- `exec_driver_sql` instead of `text()`: avoids `:name` bind parsing of SQL such as `::jsonb`.
- Read-only role password is a local-dev default (`berlin_ro`); the role is skipped with a notice if the migrating user cannot create roles.
  **Outcome:** 13 new tables + 3 partitions + 1 function + 1 sequence; downgrade removes all of them and the role. `pytest tests/test_constraints.py`: **18 passed**, including `berlin_ro` being unable to `DELETE`. Scratch database holds 0 leftover rows after the run. Existing suite: 19 passed, 23 skipped (no database reachable with the default `.env`), no failures.
  **Problems / changes to plan:**
- First upgrade failed: psycopg treats `%` as a placeholder even with no parameters, so `format('%I')` had to be written `%%I`. The failed migration rolled back completely (transactional DDL), so the retry started clean.
- First test run errored: SQLAlchemy 2 autobegins on the first `execute`, so `begin()` after the table-exists check failed. Fixture reordered.
- First `updated_at` test proved nothing (`now()` is constant inside a transaction). Replaced by a test that writes `updated_at = '2000-01-01'` and checks the trigger overwrites it.
- The default `.env` points at a local passwordless Postgres, not the Docker container; the migration has **not** been applied to the dev `berlin` database. Run `alembic upgrade head` there before phase 2.
  **Report/demo material:** the 18 constraint tests ("what the database refuses"); `alembic upgrade/downgrade` cycle.

### Phase 2 — Importer (`scripts/import_v2.py`) (2026-11-05)

**Goal:** load all 15 layers into the v2 tables with stable ids, one transaction per layer, and an audit trail.
**What we did:**
- New [import_v2.py](../backend/scripts/import_v2.py) instead of editing `import_layers.py` in place: it reuses that file's catalog metadata and fetch helpers, so the legacy importer and the running app keep working until the phase 6 cutover.
- Per layer: parse in Python (0/empty → NULL, split `;` and `/` lists) → `COPY` into a temp staging table → derive `district_id` → upsert operators → `INSERT … ON CONFLICT (kind_code, source_id) DO UPDATE … WHERE row IS DISTINCT` → delete rows missing from the source → tags (insert + remove stale) → species and detail tables.
- `apply_layer()` never commits (tests run it in a rolled-back transaction). The CLI wraps each layer: `import_run` `running` → commit/rollback → `committed`/`failed`. `--fail-after-rows N` stages N rows, applies them, then raises, to demo rollback.
- Fixed source keys: toilets `fid` (legacy found a key for 0 of 525), bike parking `gml_id`.
- [test_import_v2.py](../backend/tests/test_import_v2.py): 18 tests (parsing, operator/tag/detail creation, repeat run, in-place update, delete + cascade, stale tag removal, rollback, duplicate key, empty source, district derivation, species). All pass together with the 18 constraint tests (36).
**How we decided:**
- Counts for inserted/updated come from `rowcount` of the upsert and a join count of existing keys, not from `xmax`, which is unreliable on partitioned tables.
- A source with 0 usable features raises instead of wiping the kind.
- District derivation, three attempts: (1) correlated `ST_Within … ORDER BY id LIMIT 1` per row: still running after 8+ min on street trees, killed; (2) polygons split with `ST_Subdivide(geom, 128)` plus GiST in a temp table; (3) the real cost was a post-insert `UPDATE` rewriting 434k rows and every index, so `district_id` is now computed in the unindexed staging table and written once. Boundary ties go to the lowest district id.
**Outcome (database `schema_v2_real`, PostGIS 16, Docker on macOS):**
- 980,440 features: 975,765 points + 4,675 areas; plus 12 districts and 97 neighborhoods. Every layer's row count equals its source file; 0 skipped.
- 1,404 operators, 916 tree species, 962,545 tree details, 2,905 Kita details, 4,960 EV details, 19 tags, 10,040 tag links.
- District coverage 99.8–100% (the rest lie outside the 12 borough polygons, e.g. 5 cemeteries, 842 park trees).
- First load (s): street trees 736.6, park trees 872.1, EV chargers 52.2, Kitas 24.9, green spaces 23.3, others ≤ 7.
- **Repeat run:** every layer 0 inserted / 0 updated / 0 deleted; md5 of all (id, kind, source_id) and of all tag links identical before and after. Street trees 302 s, park trees 361 s (reading and comparing, no writes).
- Rollback demo on the sample set: toilets with `--fail-after-rows 1` deleted 1 row inside the transaction, count stayed 2 afterwards, `import_run` shows `failed` with the error.
**Problems / changes to plan:**
- The `CHECK (crown_diameter_m > 0)` rejected `0.04`, which rounds to `0.0` in `numeric(5,1)`; the street-tree layer rolled back after ~15 min. Cleaning now rounds first, then tests; verified all 962k values against the constraint ranges before the rerun. The database caught a bug our code missed.
- Two processes were stopped by hand (slow district update; port clash), leaving `import_run` rows stuck at `running`; closed manually. Follow-up: mark stale `running` rows as failed at the start of a run.
- Starting Homebrew Postgres took `localhost:5432` away from the Docker database mid-run (the import lost its connection). Docker now publishes on **5433** (`POSTGRES_PORT=5433`).
- Re-importing districts re-derived `district_id` for all 975k features (306 s) even when nothing changed; now only when a boundary row changed (1.0 s).
- Plan said ~1.1k species; measured 916.
**Open / measured later:** a tree layer takes 12–14.5 min to load; the CPU-bound insert maintains ~6 indexes incl. a GIN on `attrs` (123 MB on street trees). Phase 7 compares 50k-row loads with and without that GIN index; likely outcome is keeping it only on `amenity_points_other`. `--fail-after-rows` was exercised on samples only.
**Report/demo material:** idempotency checksums, rollback demo, per-layer timing table, district-derivation story (three attempts, numbers).

### Phase 3 — ORM models and data layer (2026-11-06)

**Goal:** map all v2 tables in the ORM and serve one feature with its tags, operator and detail through it.
**What we did:**
- [models.py](../backend/app/models.py): removed the 15 legacy layer models; added `AmenityKind`, `Operator`, `TreeSpecies`, `TagCategory`, `Tag`, `KindTagCategory`, `AmenityPoint` (partitioned parent, composite PK `(id, kind_code)`), `AmenityArea`, `AmenityPointTag`, `TreeDetail`, `KitaDetail`, `EvChargerDetail`, `ImportRun`. Composite FKs are declared as `ForeignKeyConstraint` pairs.
- `AmenityPointTag` is an **association object**, because the junction carries `kind_code` and `category_code`. `AmenityPoint.tags` is a read-only convenience relationship through it. Detail tables are 1:1 (`uselist=False`).
- New [features.py](../backend/app/features.py): `get_feature(db, kind_code, id)` loads the point, operator, tags and detail with `joinedload`/`selectinload` and filters on `kind_code` so the planner prunes to one partition. `GET /features/{layer}/{id}` uses it for the 15 amenity layers; districts and neighborhoods keep the plain SQL path.
- [db.py](../backend/app/db.py): second engine `engine_ro` (role `berlin_ro`); `POST /sql/run` now uses it, so the playground is read-only by privilege, not only by the Python SELECT check.
- [test_orm_models.py](../backend/tests/test_orm_models.py): 7 tests (mappers configure, tags via association object, 1:1 detail, endpoint payload, wrong kind → 404, `berlin_ro` cannot write).
**How we decided:**
- **ORM for entity reads and relationships; SQL files for spatial and analytical queries** (KNN, aggregates, windows). Geometry output stays `ST_AsGeoJSON` in the query.
- Layer slug → `kind_code` lives in `features.py` for now; phase 4 moves it into the registry.
**Outcome (on `schema_v2_real`):** kita returns operator + capacity; EV charger returns operator, connector tag and power/date detail; street tree returns species (botanical, German, genus) and sizes. Full suite: 67 tests, all pass.
**Problems / changes to plan:**
- The suite had one test from phase 1 that counted every row in `amenity_point_tag`, so it failed on a loaded database (10,040 rows). It now counts only its own point.
- The first full run took ~2 min on the loaded database (constraint and import tests).
- `/features/...` for the 15 amenity layers now needs the v2 data; a database that holds only legacy tables returns 404 until the phase 4 cutover of the layer endpoints.
**Report/demo material:** the "ORM vs. SQL" rule; association object because the junction has extra key columns.
