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

| Decision                                     | How we got there (evidence)                                                                                                                                                                             | Rejected alternative                                         | Outcome                                                                                                      |
| -------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------ |
| D1 Merge 15 layer tables into points + areas | Live models are the same shape: `source_id, name, <type col>, catalog_id, district_id, attrs, geom`; only the type column name differs ([models.py](../backend/app/models.py)).                         | Keep one table per layer.                                    | pending                                                                                                      |
| D3 Many-to-many via tags                     | Profiled cached WFS: EV `anschluss_1..4` gives 7 connector types, 247 chargers with more than one; Kita `ang_1` gives 9 approaches, 950 of 2,905 kitas with more than one. Values like `A/B` break 1NF. | Dedicated junction per kind (needs one table pair per kind). | Phase 2: 19 tags, 10,040 links (EV 7 / 5,297, Kita 9 / 3,916, toilet 3 / 827), matching the raw-data profile |
| D4 Upsert on `(kind_code, source_id)`        | Checked source key per layer: unique and non-null except toilets (525 null) and bike parking (19 duplicate `projektnummer`). Current import deletes and reinserts everything.                           | Delete and reinsert (new ids every run).                     | Phase 2: repeat import of 980k rows changed 0 rows, ids identical (checksum)                                 |
| D6 `tree_species` lookup                     | `art_bot → art_dtsch, gattung` had 0 conflicts across street (719 species) and park (835) trees.                                                                                                        | Keep species text on every tree row.                         | Phase 2: 916 species (street ∪ park); 0 conflicts on upsert                                                  |
| D7 `operator` table                          | `t_nr → t_name, t_art` had 0 conflicts over 1,165 kita operators; EV `betreiber` has 203 names.                                                                                                         | Operator name copied onto features.                          | Phase 2: 1,404 operators (1,165 Kita by `t_nr`, rest by name)                                                |
| D8 Partition by kind                         | Trees are about 962k of about 981k point rows (counted from cache files).                                                                                                                               | Separate tree tables; one big table.                         | pending                                                                                                      |
| 0 → NULL for tree sizes                      | `baumhoehe` is 0 or missing for about 69k street and 95k park trees.                                                                                                                                    | Store 0.                                                     | pending                                                                                                      |
| D11 Read-only role                           | [sql.py](../backend/app/routers/sql.py) relies on a SELECT check plus `statement_timeout`; no database privilege limit.                                                                                 | Python check only.                                           | pending                                                                                                      |

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

### Phase 4 — API and analyses port (2026-11-06)

**Goal:** serve every endpoint from the v2 tables, port the four analyses, add the tag filter (U7), the operator report (U8) and tree statistics.
**What we did:**

- [layer_registry.py](../backend/app/layer_registry.py): `LayerDef` gets `kind_code`, `extra_src` and `taggable`; the table is `amenity_points` or `amenity_areas`, and the generated SQL filters `kind_code = '…'`. URL paths and property names are unchanged (D12), so the frontend still works. `KIND_BY_SLUG` and `AREA_KINDS` now live here.
- Ported to v2: nearest amenities (one `LATERAL` KNN per kind from a `VALUES` list), green by borough, school–green proximity.
- Density by borough reads the materialized view `borough_amenity_stats` and pivots kinds with `FILTER`; `GROUP BY ROLLUP` adds a "Berlin (total)" row.
- **U7:** `?tag=<id>` (repeatable) on EV chargers, kitas and toilets with AND semantics (`GROUP BY … HAVING count(*) = n`); other layers answer 400. `GET /tags?kind=` lists the vocabulary with usage counts (ORM). `GET /amenities/near` calls the new SQL function `amenities_near(lon, lat, radius_m, kind, tag_ids[])`.
- **U8:** `GET /analyses/operators` (CTE + `rank() OVER (PARTITION BY district …)`, kita capacity from `kita_detail`). `GET /analyses/trees-by-borough` (`COUNT(DISTINCT species)`, `percentile_cont`, `mode() WITHIN GROUP`).
- Migration [0010_v2_analytics.py](../backend/alembic/versions/0010_v2_analytics.py): the function and the view, with grants for `berlin_ro`. The importer refreshes the view after `ANALYZE`. The legacy-table drop becomes a later migration (phase 6).
- [test_api_v2.py](../backend/tests/test_api_v2.py): 10 tests on real data.
  **How we decided:**
- Keep the wide per-borough response shape and layer slugs instead of the long ROLLUP shape, so the frontend needs no change in this phase.
- Trees use `name` (German species) for the old `species` property, because `subtype` is empty for trees.
- Counts for density come from a materialized view so the page does not scan 980k rows; the cost is that it is stale until the next import.
  **Outcome (on `schema_v2_real`):** every layer endpoint returns data from v2; nearest amenities 0.7 s; density 0.04 s; green 0.1 s; school proximity 0.9 s; operators 0.1 s; `amenities_near` 0.06 s. EV chargers in a Berlin-centre bbox: 2,376 → 752 with one tag → 18 with two tags.
  **Problems / changes to plan:**
- `trees-by-borough` takes ~10 s: it sorts 962k rows for two ordered-set aggregates. Left as is; phase 7 measures it (candidates: a materialized view, or computing medians on a sample).
- The old `/layers/{slug}/sql` tests assumed per-layer tables; they now assert `amenity_points` and the `kind_code` filter.
- `feature_by_id.sql` is only used for districts and neighborhoods now.
  **Report/demo material:** the SQL files (LATERAL KNN, ROLLUP, `rank()`, `percentile_cont`, `mode()`), the tag AND-filter numbers, `amenities_near`.

### Phase 5 — Frontend (2026-11-06)

**Goal:** make the UI use the v2 schema: glossary and patterns, tag filter, new Compare measures, feature card.
**What we did:**
- [exercises.ts](../frontend/src/exercises.ts): glossary rewritten for the v2 tables (16 entries incl. junctions, detail tables, the materialized view and `import_run`). Patterns rewritten for `amenity_points` / `amenity_areas` with `kind_code` filters; 25 patterns, including a many-to-many connector count, a Kita AND-filter, the operator ranking, partition pruning (use Explain), the `amenities_near()` function and the import history.
- Tag filter: chips under the layer grid for EV chargers, Kitas and toilets (vocabulary from `GET /tags`); selection is sent as repeated `?tag=` and reloads the layer.
- Compare tab: three new measures, "Top operator (facilities)", "Tree species count", "Median planting year". The density table skips the ROLLUP total row.
- Feature card: clicking a feature calls `GET /features/{layer}/{id}` (ORM) and shows operator, species, typed detail and tags in the Nearby tab.
- Query editor: layers are now detected from `kind_code` literals instead of table names; new binds (`:tag_ids`, `:n_tags`, `:top_n`, `:kind`, `:radius_m`, `:limit`) get default values.
**How we decided:**
- One tag-chip row per taggable layer instead of a dropdown: tags are few (7 and 9) and AND filtering needs several selected at once.
- Tree measures load lazily, only when chosen, because `trees-by-borough` takes about 10 s.
**Outcome (browser check on `schema_v2_real`):** map, layer counts, tag filter, feature card, Nearby and the three new Compare measures work. Selecting the DC CHAdeMO tag cut the EV chargers from 4,960 to 106. All 25 patterns, the 6 analysis SQL files and 3 layer SQL files ran through `POST /sql/run` as the read-only role; the pruning pattern's plan scans only `amenity_points_street_tree`. `tsc` and `vite build` pass. [smoke-test.md](smoke-test.md) is updated.
**Problems / changes to plan:**
- React re-applied the `open` attribute on the tag `<details>` after each toggle and closed it; it is now uncontrolled.
- Not done: the UI has no tag filter for tags on other layers (none exist) and no operator column in the layer popup beyond the feature card.
**Report/demo material:** the tag chips (M:N in the UI), the feature card (1:1 detail + operator FK), the Compare operator ranking.

### Phase 6 — Cutover (2026-11-06)

**Goal:** remove the legacy per-layer schema and code so only v2 remains, and make a fresh setup work from the README.
**What we did:**
- Migration [0011_drop_legacy.py](../backend/alembic/versions/0011_drop_legacy.py) drops the 15 legacy layer tables. No compatibility views. `downgrade()` recreates them empty in their old shape (id, source_id, name, type column, catalog_id, district_id, attrs, geom, GiST and district indexes).
- Retired the legacy importer: `scripts/import_layers.py` became [sources.py](../backend/scripts/sources.py) (dataset catalog metadata, per-layer key mapping, file/WFS fetch helpers); its delete-and-reinsert import code is gone. `import_v2.py` is the only importer.
- README rewritten for v2: quick start (`alembic upgrade head`, `import_v2`), schema table, the seven analyses, the read-only role URL, the Docker port note.
**How we decided:**
- Renamed instead of deleting `import_layers.py`: `import_v2.py` and its tests still need its catalog and fetch code, so only the legacy import functions were removed.
- No views over the new tables: the glossary documents v2 only, as planned.
**Outcome:** on a fresh PostGIS database `alembic upgrade head` → `downgrade -1` (legacy tables back, empty) → `upgrade head` works; `import_v2 --source samples` loads all 17 layers in seconds; `/health`, layer endpoints, analyses, tags and operators answer. Suite on the fresh sample database: 72 passed, 5 skipped (tests that need real data volume now skip on samples); on the full real-data database earlier: 77 passed.
**Problems / changes to plan:**
- Four Phase 4 tests asserted non-empty results and failed on the tiny sample data; they now skip when the data is too sparse.
- A fresh database creates the legacy tables in migrations 0002–0008 and drops them in 0011; accepted so the migration history stays replayable.
- The merge of `feat/schema-v2` into `main` is left to the pull request (not done here).
**Report/demo material:** the migration chain from empty database to v2, and the retired importer.

### Phase 7 — Performance evidence (2026-11-06)

**Goal:** back each indexing and partitioning decision with a measured plan, and fix what the measurements show.
**What we did:**
- [perf_evidence.py](../backend/scripts/perf_evidence.py) runs the experiments against the loaded database (980k features) and writes `EXPLAIN (ANALYZE, BUFFERS)` plans and timings to [docs/schema-v2/explain/](schema-v2/explain/) (7 files). Comparison copies live in a scratch schema `perf`, dropped at the end; real tables are only read.
- [test_query_plans.py](../backend/tests/test_query_plans.py): 5 plan assertions (pruning to one partition, small kinds in the default partition, KNN without a sort, tag index, GIN usable).
- Results and decisions are summarized in [indexing-and-explain.md](schema-v2/indexing-and-explain.md).
**How we decided (warm timings):**
- Partition pruning: 16.6 ms with the kind filter vs 36.0 ms without and 79.2 ms on one flat table → keep partitions.
- Composite GiST `(kind_code, geom)` on the `other` partition: no gain, index twice as large → keep the plain GiST.
- Tag junction `(tag_id, point_id)`: 0.1 vs 5.7 ms for a rare tag → keep.
- GIN on `attrs`: 5.5 vs 389.6 ms on street trees, 1.1 vs 22.1 ms on EV chargers → keep.
- KNN: `<->` 0.7 ms vs `ORDER BY ST_Distance` 2,029 ms.
- GIN costs 1.7x on bulk load (14.6 s vs 8.4 s per 50k street-tree rows) and 138 MB. Kept; dropping it from the two tree partitions is the option if load time matters more than `attrs` searches on trees.
**Outcome / change made:** the live `trees-by-borough` query took 10.7–11.2 s (88k pages, two sorts spilling to disk for the ordered-set aggregates; no index helps). It is now the materialized view `borough_tree_stats` (migration [0012](../backend/alembic/versions/0012_tree_stats_view.py)), refreshed at the end of every import: 0.1 ms per read. Compare tab tree measures now answer instantly.
**Problems / changes to plan:**
- Plan item 2 assumed `btree_gist`; it is not installed by the migration (the experiment creates it on the scratch database only). Not needed in production since the plain GiST wins.
- On a 10k-row junction the saving for a common tag is small (16 vs 22 ms); the index matters for rare tags. Reported as measured.
- Timings are from one laptop with 128 MB `shared_buffers`; absolute numbers will differ, ratios are what the report uses.
**Report/demo material:** the seven plan files; the pruning plan (one node vs three), the KNN plan (no Sort node), the tree-report before/after.
Full suite on the real-data database after phase 7: 83 passed.
