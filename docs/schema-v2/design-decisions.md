# Design decisions — schema v2

Why the database looks the way it does, what else we could have done, and what the data and the measurements said. IDs D1–D12 match the [implementation plan](../module-requirements/implementation-plan.md); the working record is the [implementation log](../implementation-log.md); plans are in [explain/](explain/).

How to read each entry: **Decision** · **Alternatives we rejected** and why · **Evidence** (measured on the real data, 980k features) · **Cost we accept**.

---

## D1 — One table per geometry family, classified by kind

**Decision.** The 15 open-data layers collapse into `amenity_points` (Point) and `amenity_areas` (MultiPolygon). `amenity_kind` says what a row is.

**Alternatives.**
- *Keep one table per layer* (the old schema). Rejected: the 15 tables had the same columns (`source_id, name, <type>, catalog_id, district_id, attrs, geom`); only the type column's name differed. Every analysis had to list 14 tables by hand (the old density query was 14 subqueries).
- *One table for everything, geometry type unconstrained.* Rejected: points and polygons need different index behaviour and different functions (`ST_Distance` to a point vs. to an edge). `geometry(Point)` / `geometry(MultiPolygon)` keep the geometry type honest.

**Evidence.** The density analysis went from 14 hand-written subqueries to one `GROUP BY`; the layer SQL is generated from one template filtered by `kind_code`.

**Cost.** A kind-specific column (e.g. the school type) becomes the generic `subtype`; the API maps it back to the old property names so the frontend did not change (D12).

## D2 — The database, not the application, checks kind against geometry

**Decision.** `amenity_kind` has `UNIQUE (code, geom_family)`. Each feature table has a constant `geom_family` column (`CHECK (geom_family = 'point')`) and a composite foreign key `(kind_code, geom_family)` to it.

**Alternatives.** A trigger that looks up the kind on insert; a check in the importer only. Rejected: a trigger is code that must be remembered on every write path and runs per row; an importer check does not protect against a manual `INSERT`. A foreign key is declarative and free.

**Evidence.** `tests/test_constraints.py` inserts an area kind into `amenity_points` and gets the foreign-key error, naming the constraint.

**Cost.** One extra column per feature table, and a slightly unusual composite key.

## D3 — Many-to-many for tags, and a second many-to-many for what a kind may carry

**Decision.** `amenity_points ⟷ tag` through `amenity_point_tag`. Which tag *categories* a kind may carry is the second M:N, `amenity_kind ⟷ tag_category` (`kind_tag_category`). The junction carries `kind_code` and `category_code` so three composite foreign keys can check every row: the point exists with that kind; the tag exists in that category; that kind may carry that category.

**Alternatives.**
- *Keep the lists in a text column* (`'Offene-Arbeit/Situationsansatz'`, `'AC Typ 2; DC CCS'`). Rejected: violates 1NF; cannot be indexed or counted.
- *Generic EAV key/value table.* Rejected: no vocabulary, no foreign keys; any typo becomes a new "attribute".
- *A junction table per kind* (`ev_charger_connector`, `kita_approach`, …). Rejected: one table pair per kind, and the tag filter and the tag-listing endpoint would need one query per kind.
- *Array column (`text[]`) with GIN.* Rejected: fast to build, but no referential integrity and no vocabulary table to list.

**Evidence.** The raw WFS data: EV `anschluss_1..4` gives 7 connector types, 247 chargers carry several; Kita `ang_1` gives 9 approaches, 950 of 2,905 Kitas carry several. Loaded result: 19 tags, 10,040 links. `tests/test_constraints.py`: a Kita tag on a toilet is rejected by the database. The AND filter (`?tag=1&tag=2`) returned 2,376 → 752 → 18 chargers for none, one, two tags.

**Cost.** Near-duplicate connector spellings (`AC Steckdose Typ 2` / `AC Typ 2 Steckdose`) are stored as published, not merged; this is documented rather than hidden.

## D4 — Natural keys and upsert, not delete-and-reinsert

**Decision.** `source_id NOT NULL`, `UNIQUE (kind_code, source_id)`. The importer upserts (`INSERT … ON CONFLICT … DO UPDATE … WHERE row IS DISTINCT`), and deletes only rows missing from the source.

**Alternatives.** Delete the kind, reinsert everything (the old importer). Rejected: new ids on every run, so everything that references a feature is rewritten, and 435k-row deletes bloat the trees.

**Evidence.** A repeat import of all 980k rows reports 0 inserted / 0 updated / 0 deleted, and md5 checksums of all ids and all tag links are identical before and after (phase 2). The data profile also forced two key fixes: toilets use `fid` (the old importer found a key for 0 of 525), bike parking uses `gml_id` (`projektnummer` has 19 duplicates).

**Cost.** Comparing rows costs reads: a repeat import of a tree layer takes 5–6 minutes instead of writing nothing instantly. We accept it because imports are offline and rare.

## D5 — Supertype/subtype (1:1) tables for kinds with typed facts, `attrs` only for provenance

**Decision.** `tree_detail`, `kita_detail`, `ev_charger_detail`, each keyed by `(point_id, kind_code)` with a composite foreign key and a `CHECK` on the kind. `attrs jsonb` keeps the raw source row.

**Alternatives.**
- *Everything in `attrs`.* Rejected: no types, no constraints, no useful statistics (we compute medians and sums over these columns).
- *Wide nullable columns on `amenity_points`.* Rejected: ~20 columns that are NULL for 98% of rows.

**Evidence.** The database rejected a `crown_diameter_m` of `0.04` (it rounds to 0.0 in `numeric(5,1)` and violates `CHECK (> 0)`): the import rolled back after 15 minutes and exposed a bug our cleaning code missed. The Kita capacity sum and the tree medians run on typed columns.

**Cost.** One join per detail query; the join key is the same composite key as the foreign key.

## D6 — `tree_species` lookup (3NF)

**Decision.** Botanical name → German name and genus in its own table.

**Alternatives.** Keep species text on every tree row. Rejected: `art_bot → art_dtsch, gattung` is a transitive dependency, repeated 962k times.

**Evidence.** 0 conflicts for the dependency across the whole data; 916 species for 962,545 trees.

## D7 — `operator` table with two identification strategies

**Decision.** `official_ref` is unique; a partial unique index covers `name WHERE official_ref IS NULL`.

**Alternatives.** Copy the operator name onto features; a single unique `name`. Rejected: Kita operators have an official number (`t_nr`) and the number → name/type dependency has 0 conflicts over 1,165 operators; EV and toilet operators have only names, and two different operators could share a name once a number exists.

**Evidence.** 1,404 operators (1,165 by number, the rest by name). The operator report ranks them per borough.

## D8 — List partitioning of `amenity_points` by kind

**Decision.** Partitions `street_tree`, `park_tree`, and a `DEFAULT` partition for everything else. Primary key `(id, kind_code)`, ids from one shared sequence.

**Alternatives.**
- *One big table.* Rejected after measuring.
- *Separate tree tables.* Rejected: brings back the clone tables D1 removed and splits every query that spans kinds.
- *Range or hash partitioning.* Rejected: no natural range key; hash would not prune on `kind_code`.

**Evidence** ([explain/01](explain/01-partition-pruning.md)). Street trees in a bounding box: **16.6 ms** partitioned with the kind filter, 36.0 ms without the filter (all partitions probed), 79.2 ms on one flat table (a `BitmapAnd` with a `kind_code` btree that returns 435k ids). The plan for a kind query contains one partition only; `tests/test_query_plans.py` asserts it.

**Cost.** Partition pruning only helps queries that name the kind; the primary key must include the partition key, which is why the composite foreign keys point at `(id, kind_code)`.

## D9 — `district_id` is a deliberate, derived denormalization

**Decision.** Each feature stores the borough it lies in, computed at import with a spatial join. No `neighborhood_id`.

**Alternatives.** Compute `ST_Within` at query time. Rejected: a borough filter on the map would run a spatial join per request. A `neighborhood_id` next to `district_id` would add a transitive dependency (neighborhood → district).

**Evidence.** Three attempts at the assignment (phase 2): a correlated subquery per row was still running after 8 minutes; subdividing the polygons helped; the real cost was a post-insert `UPDATE` rewriting 434k rows and all their indexes, so the value is now computed in an unindexed staging table and written once. Coverage is 99.8–100% per kind; the rest lie outside the 12 borough polygons.

**Cost.** The column is a cache: it must be recomputed when borough boundaries change (the importer does this only when a boundary row changed: 306 s → 1 s).

## D10 — `import_run` audit table written outside the import transaction

**Decision.** One row per layer import, committed in its own transactions (`running` before, `committed`/`failed` after).

**Alternatives.** Write the audit row inside the import transaction. Rejected: a failed import rolls back, and the record of the failure would roll back with it.

**Evidence.** A rollback demo (`--fail-after-rows`) leaves the row counts unchanged and an `import_run` row with `failed` and the error text. 38 rows exist after the full project load: 35 committed, 3 failed.

**Cost.** Interrupted processes can leave a row stuck at `running`; closing stale rows at the start of a run is open work.

## D11 — A read-only database role for the SQL playground

**Decision.** `berlin_ro` with `SELECT` only and `default_transaction_read_only = on`; `POST /sql/run` uses its own engine.

**Alternatives.** The previous Python regex check plus a statement timeout. Kept as defence in depth but rejected as the only layer: a parser is the wrong place to enforce privileges.

**Evidence.** Tests assert that `berlin_ro` cannot `DELETE`, even when the Python check is bypassed.

**Cost / gap.** The API's other read endpoints still use the owner role in development ([operations.md](../operations.md#roles)).

## D12 — Keep the API paths

**Decision.** `/ev-chargers`, `/trees`, … stay; only the registry changes from table name to `kind_code`.

**Why.** The frontend map code did not change. Property names are mapped back (`subtype` → `charger_type`, …), so the cutover was a backend change.

---

## Further choices made along the way

| Choice | Alternatives | Why |
| --- | --- | --- |
| GiST on `geom`, GIN `jsonb_path_ops` on `attrs`, btree on `district_id`, `operator_id`, `catalog_id`, `(tag_id, point_id)` | composite `(kind_code, geom)` GiST via `btree_gist` | Measured: the composite index is 2x larger and not faster on 13k rows ([explain/02](explain/02-composite-gist.md)) |
| Keep GIN on `attrs` for all partitions | GIN only on the small partition | 390 ms → 5.5 ms for a genus lookup; costs 1.7x on bulk load and 138 MB ([explain/04](explain/04-gin-attrs.md), [06](explain/06-gin-load-cost.md)) |
| Materialized views for borough counts and tree statistics | compute per request | The tree report took 11 s live, 0.1 ms from the view ([explain/07](explain/07-trees-by-borough.md)) |
| ORM for entity reads and relationships; hand-written SQL files for spatial and analytical queries | ORM for everything; raw SQL for everything | The ORM expresses "one feature with its tags, operator and detail" well; KNN, `ROLLUP`, `rank()`, `percentile_cont` are clearer as visible SQL, and the Query tab shows those files |
| Per-layer transactions in the importer | one transaction for all layers; autocommit | A failure in the last layer must not discard the 30 minutes spent on trees; a half-loaded layer must not be visible |
| Recover by time into a throwaway container | restore in place | The live database is never at risk during a drill ([operations.md](../operations.md)) |

## What we did not do (future work)

- Tags on areas, bike-rack types as a child table, and more detail tables: scope creep; the schema leaves room for them.
- Merging near-duplicate EV connector spellings into one tag.
- A dedicated non-superuser role for the API's read endpoints.
- Scheduled base backups, retention, and an off-machine copy of the WAL archive.
- Dropping GIN from the two tree partitions if bulk-load time matters more than `attrs` searches on trees.
