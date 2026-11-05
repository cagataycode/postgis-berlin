# Implementation plan — Schema v2

How we take the Berlin Amenities Map from the live per-layer schema to the v2 design, and what evidence each step produces for the module hand-in.

- Requirements: [assessment-instructions.md](assessment-instructions.md), [level-expectations.md](level-expectations.md)
- Overview and use cases: [../project-plan.md](../project-plan.md)
- Design docs: [../schema-v2/](../schema-v2/README.md)

**Target:** Level 1 complete, Level 2 covered (advanced schema, indexes, SQL, continuous backups), Level 3 partly (production-like operation, written design rationale).

**Documentation rule:** every phase ends with an entry in [../implementation-log.md](../implementation-log.md) (what we did, how we decided, outcome, problems). A phase is not done until its entry exists.

**Branch:** all work on `feat/schema-v2`, merged to `main` when phases 1–6 pass. The app is cut over in one go, so the two schemas never run side by side in `main`.

---

## 1. Design decisions (fixed)

| # | Decision | Reason |
| --- | --- | --- |
| D1 | Collapse 15 layer tables into `amenity_points` (Point) and `amenity_areas` (MultiPolygon), classified by `amenity_kind`. | One fact shape, one table. Geometry types stay honest. |
| D2 | **The database enforces kind/geometry consistency.** `amenity_kind UNIQUE (code, geom_family)`; each feature table has a constant `geom_family` column with a `CHECK` and a composite FK `(kind_code, geom_family)`. | A point row with an area kind cannot exist. No trigger needed. |
| D3 | **Many-to-many relationship `amenity_points ⟷ tag`** through `amenity_point_tag`. Allowed combinations are a second M:N relationship, `amenity_kind ⟷ tag_category` (`kind_tag_category`). The junction carries `kind_code` and `category_code` so three composite FKs can check every row. | Fixes the 1NF violations in the source data (`'A/B'` and `'X; Y'` lists). A kita tag on a toilet is rejected by the database. |
| D4 | **Stable natural keys:** `source_id NOT NULL`, `UNIQUE (kind_code, source_id)`. Imports **upsert** instead of delete-and-reinsert. | Ids survive re-imports, junction rows aren't churned, and there are no huge DELETEs bloating the trees table. |
| D5 | **Supertype/subtype tables (1:1)** for kinds with typed facts we query: `tree_detail`, `kita_detail`, `ev_charger_detail`. Each is keyed by `(point_id, kind_code)` with a composite FK and a `CHECK` on the kind. | Typed, constrained and analyzable columns instead of jsonb. `attrs` keeps the raw source data for provenance only. |
| D6 | **`tree_species` lookup table.** Botanical name → German name and genus. | Transitive dependency in the source data (`art_bot → art_dtsch, gattung`, 0 conflicts in about 962k rows). 3NF extraction. |
| D7 | **`operator` table.** `official_ref` is unique; a partial unique index on `name WHERE official_ref IS NULL`. | Kita operators have an official number (`t_nr`); EV and toilet operators only have names. |
| D8 | **List-partition `amenity_points` by `kind_code`.** Partitions: `street_tree`, `park_tree`, `DEFAULT` (everything else). PK `(id, kind_code)`, id from a shared sequence. | Trees are about 98% of point rows. Gives partition pruning, smaller per-partition indexes and per-partition VACUUM. The PK already matches the composite FKs from D3/D5. |
| D9 | **`district_id` is a deliberate, derived denormalization.** It's maintained by the import with a spatial join. No `neighborhood_id` on features. | Cached `ST_Within` result for fast borough filters. A `neighborhood_id` next to it would add a transitive dependency. |
| D10 | **`import_run` audit table.** Written in its own transactions, outside the import transaction. | It must record failed runs too, and a single transaction would roll that record back. Useful when explaining ACID. |
| D11 | **Read-only database role for the SQL playground.** Plus `SET TRANSACTION READ ONLY`. | Today the playground relies on a SELECT check in Python and a timeout. Privileges are the right layer for this. |
| D12 | **Keep API URL paths** (`/ev-chargers`, `/trees`, …). Only the registry changes from table to `kind_code`. | The frontend map code stays mostly the same. |

## 2. Data profile (cached WFS, checked 2026-11-05)

These findings shape the import and the constraints:

| Finding | Consequence |
| --- | --- |
| Toilets: all 525 rows have no `source_id` (importer looks for `nummer` / `id`; the real key is `fid`) | Fix key mapping. Otherwise `source_id NOT NULL` fails. |
| Bike parking: 19 duplicate `projektnummer` (one project, several sites) | Use `gml_id` as `source_id`; keep `projektnummer` in attrs. |
| Trees: `gisid` unique, 0 nulls (street and park) | Natural key for trees. |
| Trees: `baumhoehe`, `kronedurch` = 0 means unknown (about 69k street, 95k park) | Import maps 0 to NULL; `CHECK (height_m > 0)`. |
| Trees: park trees missing `pflanzjahr` 192k, `art_bot` 11k | Nullable detail columns; `species_id` nullable. |
| Species: 719 street + 835 park botanical names, consistent | `tree_species` about 1.1k rows (sets overlap). |
| EV connectors: 7 distinct after splitting on `;` (near-duplicate spellings, e.g. `AC Steckdose Typ 2` / `AC Typ 2 Steckdose`) | Store as published (decided). Note in docs. About 5,300 junction rows. |
| Kita approaches: 9 distinct after splitting on `/`, 950 kitas with more than one | About 3,900 junction rows. |
| Kita operators: 1,165 distinct `t_nr`, `t_nr → name, type` consistent | Safe 3NF extraction. |
| All other layers: source keys unique, no nulls | `UNIQUE (kind_code, source_id)` holds. |

## 3. Target schema

```text
dataset_catalog      id PK, slug UK, … (unchanged)
amenity_kind         code PK, label, geom_family CHECK(point|area), UNIQUE(code, geom_family)
districts            id PK, official_id UK, name, catalog_id FK, attrs, geom GiST   (unchanged shape)
neighborhoods        id PK, official_id UK, name, district_id FK, catalog_id FK, attrs, geom GiST
operator             id PK, official_ref UK NULL, name, operator_type
                     + UNIQUE (name) WHERE official_ref IS NULL
amenity_points       PARTITION BY LIST (kind_code)
                     id bigint DEFAULT nextval(seq), kind_code, geom_family='point',
                     source_id NOT NULL, name, subtype, catalog_id FK, district_id FK NULL,
                     operator_id FK NULL, attrs jsonb, geom Point GiST, updated_at
                     PK (id, kind_code), UNIQUE (kind_code, source_id),
                     FK (kind_code, geom_family) → amenity_kind
  ├ amenity_points_street_tree  FOR VALUES IN ('street_tree')
  ├ amenity_points_park_tree    FOR VALUES IN ('park_tree')
  └ amenity_points_other        DEFAULT
amenity_areas        id PK, kind_code, geom_family='area', source_id NOT NULL, …,
                     UNIQUE (kind_code, source_id), UNIQUE (id, kind_code),
                     CHECK (ST_IsValid(geom)), FK (kind_code, geom_family) → amenity_kind
tag_category         code PK, label
tag                  id PK, category_code FK, label, UNIQUE (category_code, label),
                     UNIQUE (id, category_code)
kind_tag_category    (kind_code, category_code) PK, both FK            -- M:N #2
amenity_point_tag    (point_id, kind_code, tag_id, category_code)      -- M:N #1
                     PK (point_id, tag_id)
                     FK (point_id, kind_code)      → amenity_points (id, kind_code) ON DELETE CASCADE
                     FK (tag_id, category_code)    → tag (id, category_code)
                     FK (kind_code, category_code) → kind_tag_category
                     + index (tag_id, point_id)
tree_species         id PK, botanical_name UK, german_name, genus
tree_detail          (point_id, kind_code) PK/FK, CHECK kind IN (street_tree, park_tree),
                     species_id FK NULL, planting_year smallint CHECK, trunk_circumference_cm,
                     height_m CHECK > 0, crown_diameter_m CHECK > 0
kita_detail          (point_id, kind_code) PK/FK, CHECK kind = 'kita', capacity int CHECK >= 0
ev_charger_detail    (point_id, kind_code) PK/FK, CHECK kind = 'ev_charger',
                     charge_points smallint, max_power_kw numeric, commissioned_on date,
                     public_space boolean
import_run           id PK, catalog_id FK, started_at, finished_at,
                     status CHECK(running|committed|failed), rows_inserted, rows_updated,
                     rows_deleted, error text
```

**Indexes** (beyond PKs and uniques):
- GiST on every `geom`.
- On partitioned `amenity_points`: GiST `geom` (pruning removes most of the need for a `(kind_code, geom)` composite; compare both in phase 7).
- btree on `district_id`, `operator_id`, `catalog_id`, and `tree_detail(species_id)`.
- GIN `jsonb_path_ops` on `attrs`.

**Seeds:** 15 kinds, 3 tag categories, 3 `kind_tag_category` rows (`ev_charger↔ev_connector`, `kita↔kita_approach`, `toilet↔toilet_feature`).

---

## 4. Phases

Each phase lists tasks, then **Done when** (acceptance), then **Evidence** (what goes into the report or demo).

### Phase 0 — Sync design docs

- Update [erd.md](../schema-v2/erd.md) (Mermaid) and [schema.sql](../schema-v2/schema.sql) to section 3.
- Update [normalization.md](../schema-v2/normalization.md): 1NF (tag lists), 3NF (species, operator), D9 denormalization note.
- Update [indexing-and-explain.md](../schema-v2/indexing-and-explain.md) for partitions.
- Update [acid-and-transactions.md](../schema-v2/acid-and-transactions.md) for per-kind transactions and `import_run`.

**Done when:** `schema.sql` runs cleanly on an empty PostGIS 16 database (`psql -v ON_ERROR_STOP=1 -f`).
**Evidence:** ERD and normalization docs.

### Phase 1 — Migration `0009_schema_v2`

- Hand-written Alembic migration (`op.execute` DDL). Autogenerate doesn't understand partitions or composite FKs, so exclude these tables from autogenerate compare in `alembic/env.py` (`include_object`).
- Order: extension `btree_gist` → lookups (`amenity_kind`, `tag_category`, `tree_species`, `operator`) → `amenity_points` + partitions + sequence → `amenity_areas` → `tag`, `kind_tag_category`, `amenity_point_tag` → detail tables → `import_run` → indexes → seeds.
- Shared tables (`dataset_catalog`, `districts`, `neighborhoods`) stay as they are. Legacy layer tables remain until phase 6.
- `updated_at` trigger function `set_updated_at()` on `amenity_points` / `amenity_areas` (BEFORE UPDATE). This is our trigger example.
- Roles (in migration, idempotent): `berlin_ro` with `GRANT SELECT` on all tables, `ALTER ROLE … SET default_transaction_read_only = on`.
- `downgrade()` drops everything 0009 created.

**Done when:** `alembic upgrade head` then `alembic downgrade -1` then `upgrade` again works on an empty database.
**Tests (new `tests/test_constraints.py`):**
- Inserting an area kind into `amenity_points` fails.
- A `kita_approach` tag on a toilet fails.
- A duplicate `(kind_code, source_id)` fails.
- `tree_detail` for a school fails.
- Height 0 fails.
- An invalid polygon in `amenity_areas` fails.

**Evidence:** constraint test output; "what the database refuses" slide for the oral.

### Phase 2 — Import rewrite (`scripts/import_layers.py`)

Today all layers run in **one** transaction, and each layer does delete-then-insert row by row. New flow **per layer**:

1. Separate transaction: `INSERT import_run (status='running')`, commit.
2. Main transaction:
   1. Upsert `dataset_catalog`.
   2. `COPY` features into a `TEMP` staging table (psycopg3 `cursor.copy()`). Geometry is passed as WKB/GeoJSON and transformed to 25833 in SQL; polygons get `ST_MakeValid`.
   3. Set-based SQL from staging:
      - `INSERT … ON CONFLICT (kind_code, source_id) DO UPDATE … WHERE (row) IS DISTINCT FROM (excluded)`.
      - `DELETE` rows of this kind that are missing from staging.
      - Count inserted, updated and deleted rows.
   4. Assign `district_id` with one spatial `UPDATE … FROM districts` for this kind (point-on-surface for areas).
   5. Upsert `operator` (by `official_ref`, else by name), then set `operator_id`.
   6. Tags: split source fields, upsert `tag`, replace this kind's `amenity_point_tag` rows (`ON CONFLICT DO NOTHING` + delete stale ones).
   7. Detail tables: upsert `tree_species` first, then `tree_detail` / `kita_detail` / `ev_charger_detail` (0 → NULL, text years → smallint).
   8. Commit.
3. Separate transaction: update `import_run` to `committed` with counts, or to `failed` with the error after rollback.

Other changes:
- Fix source key mapping: toilets → `fid`, bike parking → `gml_id`.
- Districts/neighborhoods upsert by `official_id`, so ids stay stable and dependents are no longer cleared. Re-importing districts re-runs district assignment for all kinds.
- Flag `--fail-after-rows N` raises mid-load, for the rollback demo.
- `ANALYZE` the touched tables after commit.

**Done when:**
- A full open-data import completes.
- Re-running it gives 0 inserted / 0 updated / 0 deleted and the same ids.
- A `--fail-after-rows` run leaves counts unchanged and `import_run.status = 'failed'`.

**Tests:**
- Idempotency (import samples twice, compare ids).
- Rollback (failure injection).
- Tag splitting unit tests.
- 0 → NULL mapping.

**Evidence:** row counts per table (feeds the README data-volume section), `import_run` history, rollback demo.

### Phase 3 — ORM models and data layer

- `app/models.py`: models for all v2 tables.
  - `AmenityPoint` maps the partitioned parent (composite PK).
  - `AmenityPointTag` is an **association object** (not plain `secondary`), because the junction carries `kind_code` / `category_code`.
  - `AmenityPoint.tags` is a convenience `relationship` through it.
  - Detail tables are 1:1 `relationship(uselist=False)`.
- Remove legacy models.
- Write down the rule: **ORM for entity reads and relationships** (feature detail, tags, operator); **hand-written SQL files in `backend/sql/`** for spatial and analytical queries (KNN, aggregates, windows). This is an "ORM vs. SQL" answer for the oral.
- Second engine for the playground using `DATABASE_URL_RO` (`berlin_ro`). Add the variable to `.env.example` and `config.py`.

**Done when:** `GET /features/{layer}/{id}` returns feature + tags + operator + detail through the ORM.

### Phase 4 — API and analyses port

- `layer_registry.py`: `LayerDef.table` becomes `kind_code` + `family` (point/area). `layer_geojson.sql` filters `kind_code = :kind`. Same URL paths (D12).
- Port the existing analyses:
  - Nearest amenities: one `LATERAL` KNN per kind over `amenity_points` / `amenity_areas`.
  - Density by borough: one `GROUP BY ROLLUP (district, kind_code)` with totals.
  - Green by borough.
  - School–green proximity (`percentile_cont`).
- New use cases:
  - **U7 tag filter:** layer endpoints take `?tag=<id>` (repeatable, AND semantics via `GROUP BY … HAVING count(*) = n`). `GET /tags?kind=ev_charger` lists the vocabulary.
  - **U8 operator report:** `GET /analyses/operators`. A CTE + `rank() OVER (PARTITION BY district ORDER BY count DESC)` gives the top operators per borough, with kita capacity totals from `kita_detail`.
  - **Tree statistics:** `GET /analyses/trees-by-borough` returns species diversity, median planting year and top genus per borough (window functions + `mode() WITHIN GROUP`).
- Database objects:
  - SQL function `amenities_near(lon, lat, radius_m, kind, tag_ids[])`, used by U7.
  - Materialized view `borough_amenity_stats`, refreshed at the end of the import.
- `POST /sql/run` uses the read-only engine.

**Done when:** all existing endpoint tests pass on v2, and new tests cover U7/U8.
**Evidence:** the SQL files themselves (advanced SQL for Level 2).

### Phase 5 — Frontend

- `exercises.ts`: rewrite the glossary for the v2 tables; rewrite the patterns (bbox by kind, KNN, tag join through the junction, operator ranking, partition-pruning EXPLAIN pattern).
- Layer chips: tag filter dropdown for EV chargers, kitas and toilets.
- Compare tab: new "Operators" and "Trees" measures.
- Feature popup: show tags, operator and detail fields.

**Done when:** the [smoke test](../smoke-test.md) is updated and passes manually.

### Phase 6 — Cutover (`0010_drop_legacy`)

- Drop the 15 legacy layer tables. No compatibility views; the glossary documents v2 only.
- `downgrade()` recreates them empty (data can be re-imported).
- Merge `feat/schema-v2` to `main`.

**Done when:** a fresh clone gets a working app by following the README from scratch.

### Phase 7 — Performance evidence

For each query, `EXPLAIN (ANALYZE, BUFFERS)` before and after, saved to `docs/schema-v2/explain/`:
1. Street trees in a bbox: partition pruning (only `amenity_points_street_tree` scanned) + GiST. Contrast: the same query on a non-partitioned copy.
2. Composite `(kind_code, geom)` GiST vs plain GiST on the `other` partition. Keep the one that wins and record why.
3. Tag filter: junction `(tag_id, point_id)` index used vs seq scan without it.
4. `attrs @> '{"betreiber": "Wall GmbH"}'`: GIN vs seq scan.
5. Nearest amenities: KNN index-ordered scan (`<->`).

**Done when:** each item has a plan, timings and a one-paragraph explanation in [indexing-and-explain.md](../schema-v2/indexing-and-explain.md).

### Phase 8 — Operations: backups and production-like setup

- **Continuous backups (Level 2):**
  - `docker-compose.yml`: `wal_level=replica`, `archive_mode=on`, `archive_command` copying WAL to a mounted `./backups/wal` volume (gitignored).
  - `scripts/backup_base.sh`: `pg_basebackup` into `./backups/base/<timestamp>`.
  - `scripts/backup_logical.sh`: `pg_dump -Fc` for portability.
- **Restore drill, written up in `docs/operations.md`:** note the time → delete rows of one kind → point-in-time recovery to before the delete (`recovery_target_time`) → verify counts. This is a demo option.
- Healthcheck already exists. Add `pg_stat_statements` to inspect the slowest queries after a demo session.
- Roles summary: owner (migrations/import), `berlin_ro` (playground). The app never connects as a superuser.

**Done when:** the restore drill has been run once end to end and its output is pasted into `docs/operations.md`.

### Phase 9 — Docs and hand-in

- README:
  - Setup including role and URL variables.
  - Use cases with implemented status (copy the final table from project-plan).
  - Data volume from `import_run` / `pg_class` counts.
  - Data origin (all real open data, nothing generated).
  - Solo ownership statement.
- `docs/schema-v2/design-decisions.md` (Level 3): D1–D12 with alternatives considered (generic tags vs dedicated junctions, partitioning vs separate tree table, upsert vs partition swap, jsonb vs subtype tables) and why each was rejected.
- Demo script in [../project-plan.md](../project-plan.md).
- Grant `peterruppel` read access to the repo; submit the hand-in form.

---

## 5. Order and size

| Phase | Depends on | Size |
| --- | --- | --- |
| 0 Docs sync | — | S |
| 1 Migration | 0 | M |
| 2 Import | 1 | L (largest risk) |
| 3 ORM | 1 | S |
| 4 API/analyses | 2, 3 | M |
| 5 Frontend | 4 | M |
| 6 Cutover | 5 | S |
| 7 Performance | 2 (real data) | M |
| 8 Backups/ops | 1 | M |
| 9 Docs/hand-in | all | S |

Phases 3 and 8 can run in parallel with phase 2. Phase 7 can start as soon as phase 2 has loaded real data.

## 6. Testing strategy

- **Constraint tests:** the database rejects invalid data (phase 1).
- **Import tests:** idempotency, rollback, parsing (phase 2), run on `--source samples` in CI-like local runs.
- **API tests:** the existing suite ported plus U7/U8 (phase 4).
- **Plan tests:** a light assertion that the street-tree bbox plan mentions only the street-tree partition (phase 7).
- **Security test:** `berlin_ro` cannot `INSERT`, even when the Python SELECT check is bypassed (phase 4).
- Database-backed tests keep skipping cleanly when the database is down (current `conftest.py` behavior).

## 7. Risks

| Risk | Mitigation |
| --- | --- |
| Composite FKs and partitions are unfamiliar to Alembic and ORM tooling | Hand-written DDL; association object in the ORM; exclude from autogenerate. |
| Import of about 962k trees is slow | `COPY` into staging + set-based upsert; drop/rebuild nothing, rely on upsert touching only changed rows. |
| Spatial `UPDATE` for district assignment on about 962k trees | One set-based statement per kind using the districts GiST index; measure in phase 7. |
| Upstream WFS changes keys or fields | `source_id` mapping per layer is tested on samples; `import_run.failed` makes it visible. |
| Scope creep (bike rack types as a child table, tags on areas, more detail tables) | Not before phase 9 is done. Listed as future work in design-decisions. |
