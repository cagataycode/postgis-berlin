# Project plan — Databases module

One page that ties the module requirements ([module-requirements/](module-requirements/)) to what exists. Target was **Level 1 solid, Level 2 covered, Level 3 partly**; status below is the final state of branch `feat/schema-v2`.

## 1. What we hand in

| Hand-in item | Where it lives | Status |
| --- | --- | --- |
| Repo access (read for `peterruppel`) | GitHub | **todo (author): grant access** |
| Working data layer serving the use cases | `backend/app/` (ORM models, feature loader), `backend/sql/` (analyses) | done |
| Use cases, with implemented / not marked | [README.md](../README.md#use-cases), section 3 below | done |
| README with dev + DB setup | [README.md](../README.md) | done |
| ER model (cardinality, keys, indexes) | [schema-v2/erd.md](schema-v2/erd.md) (Mermaid) | done |
| Non-trivial schema, ≥1 many-to-many | `amenity_points ⟷ tag` and `amenity_kind ⟷ tag_category` | done, migrated, loaded |
| Data volume + origin | [README.md](../README.md#data), section 4 below | done (counted from the database) |
| Team contribution | solo project: all parts | done (stated in README) |
| Oral demo (15–30 min) | section 6 | script ready; rehearse |
| Hand-in form on the Learning Platform | — | **todo (author)** |

## 2. Schema (v2, 16 tables + 3 partitions + 2 materialized views)

`dataset_catalog` · `amenity_kind` · `districts` · `neighborhoods` · `operator` · `amenity_points` (partitioned) · `amenity_areas` · `tag_category` · `tag` · `kind_tag_category` · `amenity_point_tag` · `tree_species` · `tree_detail` · `kita_detail` · `ev_charger_detail` · `import_run`

- Collapses ~15 clone layer tables into `amenity_points` / `amenity_areas` + `kind_code`.
- `operator` pulls repeated operator facts out of the features (Kita Träger: 1,165 distinct, `t_nr → name, type` has no conflicts; EV `betreiber`: 203).
- `tag` + `amenity_point_tag` is the many-to-many: EV connectors, Kita pedagogical approaches, toilet features. Replaces values like `Offene-Arbeit/Situationsansatz`.
- Two M:N relationships (points ⟷ tag, kind ⟷ tag_category); the database checks kind/geometry and tag/kind consistency with composite FKs.
- `borough_amenity_stats` and `borough_tree_stats` (materialized views) hold the per-borough counts and tree statistics, refreshed at the end of every import.
- Details: [erd.md](schema-v2/erd.md), [schema.sql](schema-v2/schema.sql), [normalization.md](schema-v2/normalization.md).

## 3. Use cases

| # | Use case | Status |
| --- | --- | --- |
| U1 | Show amenity layers on a map (bbox/zoom-gated trees) | implemented |
| U2 | Click map → nearest amenity per kind (KNN) | implemented |
| U3 | Amenity density by borough | implemented |
| U4 | Green space share by borough | implemented |
| U5 | School → nearest park distance (median / p90) | implemented |
| U6 | Read-only SQL playground with Explain | implemented |
| U7 | **Filter by tag**: EV chargers by connector type (e.g. CHAdeMO), Kitas by approach, accessible toilets | implemented (`?tag=`, `/tags`, `/amenities/near`) |
| U8 | **Operator report**: chargers/kitas per operator, largest operators per borough | implemented |
| U9 | Provenance: catalog, vintage and caveats per feature | implemented (`/layers`, `/features/{layer}/{id}`) |

All use cases are implemented on v2. U7 and U8 are what make the schema demonstrably non-trivial.

## 4. Data volume (loaded database, Berlin open data, real not generated)

| Group | Rows |
| --- | --- |
| Street trees | 434,765 |
| Park trees | 527,780 |
| EV chargers | 4,960 |
| Kitas | 2,905 |
| Green spaces | 2,563 |
| Bike parking | 2,374 |
| Playgrounds | 1,886 |
| Sports facilities | 1,085 |
| Schools | 930 |
| Toilets | 525 |
| Drinking fountains | 242 |
| Cemeteries | 226 |
| Hospitals | 111 |
| Neighborhoods / Districts | 97 / 12 |
| Park & Ride / Bathing waters | 49 / 39 |
| **Total features** | **≈ 981,000** |

Loaded: 980,440 features, 10,040 junction rows (EV 5,297 · Kita 3,916 · toilet 827), 1,404 operators, 916 tree species, 962,545 tree details; database size 1.4 GB. Source list: [data-sources.md](data-sources.md).

## 5. Implementation steps

Phases, acceptance criteria and evidence: [module-requirements/implementation-plan.md](module-requirements/implementation-plan.md); what actually happened: [implementation-log.md](implementation-log.md). All phases 0–8 are done; phase 9 (this documentation) closes the project.

| Phase | Result |
| --- | --- |
| 0 Design docs | ERD, DDL verified on PostGIS 16 |
| 1 Migration `0009_schema_v2` | 18 constraint tests: what the database refuses |
| 2 Importer `import_v2` | 980k features, idempotent, per-layer transactions, audit table |
| 3 ORM | models with association object; feature loader |
| 4 API and analyses | tag filter, operators, tree statistics, `amenities_near()`, materialized views |
| 5 Frontend | glossary and 25 patterns, tag chips, feature card, new Compare measures |
| 6 Cutover `0011` | legacy tables dropped, legacy importer retired |
| 7 Performance | seven measured plans; tree report 11 s → 0.1 ms |
| 8 Operations | WAL archiving, base and logical backups, point-in-time recovery drill |
| 9 Docs | README, design decisions, this plan |

## 6. Level mapping and demo story

| Level objective | Evidence |
| --- | --- |
| L1 schema design, normalization | [ERD](schema-v2/erd.md), [normalization.md](schema-v2/normalization.md): 1NF violations in the raw WFS (`'A/B'` lists) fixed via M:N; operator and species 3NF extraction |
| L1 SQL | analyses in `backend/sql/`: joins, aggregates, KNN |
| L1 indexing + optimization | [indexing-and-explain.md](schema-v2/indexing-and-explain.md): partition pruning 16.6 vs 79.2 ms, KNN 0.7 vs 2,029 ms, GIN 5.5 vs 390 ms |
| L1 ACID / transactions | per-layer import transactions, rollback demo ([acid-and-transactions.md](schema-v2/acid-and-transactions.md)) |
| L1 scaling | bbox + zoom gate, feature caps, materialized views; why "all trees" does not scale |
| L1 ORM / access modules | SQLAlchemy models (association object, 1:1 details) next to hand-written SQL files, with the rule for each ([design-decisions.md](schema-v2/design-decisions.md)) |
| L2 advanced schema | two M:N with composite foreign keys, lookup tables, 1:1 subtype tables, list partitioning, CHECK constraints, trigger |
| L2 advanced indexes | GiST, GIN `jsonb_path_ops`, composite GiST measured and rejected, tag-first junction index |
| L2 advanced SQL | LATERAL KNN, `ROLLUP`, `rank() OVER`, `percentile_cont`, `mode()`, SQL function `amenities_near` |
| L2 continuous backups | WAL archiving + base backup + point-in-time recovery drill ([operations.md](operations.md)) |
| L3 production-like / reasoning | roles, audit table, backup drill with stated limits; [design-decisions.md](schema-v2/design-decisions.md) |

### Demo script (≈20 min)

Prepare: `POSTGRES_PORT=5433 docker compose up -d db`, backend and frontend running against the loaded database (`DATABASE_URL`/`DATABASE_URL_RO` with port 5433), a terminal in `backend/`.

1. **ERD (2 min).** Open [erd.md](schema-v2/erd.md): the two many-to-many relations, the partitioned points table, the 1:1 detail tables.
2. **Map and nearest (3 min).** Layers on; click a spot → Nearby tab (14 KNN results). Click an EV charger → feature card: operator, connector tags, power.
3. **Tag filter and operators (4 min).** EV chargers → tag chips → "DC CHAdeMO" (4,960 → 106). Compare tab → "Top operator" and "Tree species count".
4. **What the database refuses (3 min).** `pytest tests/test_constraints.py -v`: an area kind in the points table, a Kita tag on a toilet, a duplicate key, zero tree height each fail with a named constraint.
5. **EXPLAIN (4 min).** Query tab → "Partition pruning" pattern with Explain (one partition); "Street trees in view" with Explain (GiST); then the contrast without the `kind_code` line. Show [explain/05-knn.md](schema-v2/explain/05-knn.md): `<->` 0.7 ms vs 2 s.
6. **Transaction rollback (2 min).** `python -m scripts.import_v2 --layers toilets --fail-after-rows 100`; then `SELECT status, error FROM import_run ORDER BY id DESC LIMIT 1` (failed) and the unchanged toilet count. Re-run without the flag: 0 inserted / 0 updated / 0 deleted.
7. **Recovery (optional, 2 min).** Show the [drill output](operations.md#restore-drill-point-in-time-recovery): 525 → 0 → 525 toilets with identical ids.
8. **Q&A on design decisions.** [design-decisions.md](schema-v2/design-decisions.md): each of D1–D12 has the alternatives and the numbers.

## 7. Risks and open decisions (resolved)

- **Tag extraction quality**: near-duplicate connector spellings kept as published (documented in design-decisions).
- **Big imports**: solved with `COPY` into a staging table and set-based upserts; a tree layer loads in 12–14 minutes, a repeat run in 5–6.
- **Scope creep**: tags on areas, more detail tables and production HA stay as future work.
