# Project plan — Databases module

One page that ties the module requirements ([module-requirements/](module-requirements/)) to what exists and what is left. Target: **Level 1 solid, Level 2 where cheap.**

## 1. What we hand in

| Hand-in item | Where it lives | Status |
| --- | --- | --- |
| Repo access (read for `peterruppel`) | GitHub | todo: grant access |
| Working data layer serving the use cases | `backend/app/`, `backend/sql/` | exists on live schema; **port to v2** |
| Use cases, with implemented / not marked | section 3 below | draft |
| README with dev + DB setup | [README.md](../README.md) | exists; update for v2 |
| ER model (cardinality, keys, indexes) | [schema-v2/erd.md](schema-v2/erd.md) (Mermaid) | **done (design)** |
| Non-trivial schema, ≥1 many-to-many | `amenity_points ⟷ tag` | **designed**, not migrated |
| Data volume + origin | section 4 below | counted from cached WFS |
| Team contribution | solo project: all parts | n/a |
| Oral demo (15–30 min) | section 6 | prepare after implementation |

## 2. Target schema (v2, 10 tables)

`dataset_catalog` · `amenity_kind` · `districts` · `neighborhoods` · `operator` · `amenity_points` · `amenity_areas` · `tag_category` · `tag` · `amenity_point_tag` (junction)

- Collapses ~15 clone layer tables into `amenity_points` / `amenity_areas` + `kind_code`.
- `operator` pulls repeated operator facts out of the features (Kita Träger: 1,165 distinct, `t_nr → name, type` has no conflicts; EV `betreiber`: 203).
- `tag` + `amenity_point_tag` is the many-to-many: EV connectors, Kita pedagogical approaches, toilet features. Replaces values like `Offene-Arbeit/Situationsansatz`.
- Details: [erd.md](schema-v2/erd.md), [schema.sql](schema-v2/schema.sql), [normalization.md](schema-v2/normalization.md).

## 3. Use cases

| # | Use case | Status |
| --- | --- | --- |
| U1 | Show amenity layers on a map (bbox/zoom-gated trees) | implemented (live schema) |
| U2 | Click map → nearest amenity per kind (KNN) | implemented (live schema) |
| U3 | Amenity density by borough | implemented (live schema) |
| U4 | Green space share by borough | implemented (live schema) |
| U5 | School → nearest park distance (median / p90) | implemented (live schema) |
| U6 | Read-only SQL playground with Explain | implemented (live schema) |
| U7 | **Filter by tag**: EV chargers by connector type (e.g. CHAdeMO), Kitas by approach, accessible toilets | new, needs v2 |
| U8 | **Operator report**: chargers/kitas per operator, largest operators per borough | new, needs v2 |
| U9 | Provenance: catalog, vintage and caveats per feature | implemented, port to v2 |

U1–U6 and U9 must keep working after the port. U7 and U8 are what make the schema demonstrably non-trivial.

## 4. Data volume (cached WFS, Berlin open data, real not generated)

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

Expected junction rows: ~5,300 EV connector links, ~3,900 Kita approach links, plus toilet features. Source list: [data-sources.md](data-sources.md). Re-count with the database up before the final hand-in.

## 5. Implementation steps

Full plan with phases, acceptance criteria and evidence: [module-requirements/implementation-plan.md](module-requirements/implementation-plan.md). Short version:


1. **Migration `0009_schema_v2`**: create the 10 tables and indexes (Alembic, from `schema.sql`).
2. **Import rewrite** (`scripts/import_layers.py`): per layer, one transaction: upsert catalog → delete the kind's rows → insert → assign `district_id` → upsert operators → split multi-valued fields into `tag` / `amenity_point_tag` → commit/rollback.
3. **Models**: SQLAlchemy models for the new tables, with `relationship()` for the M:N (`secondary=amenity_point_tag`).
4. **Layer registry + analyses**: query by `kind_code`; density becomes a single `GROUP BY kind_code, district_id`.
5. **New endpoints for U7/U8**: `GET /layers/ev_charger?connector=…`, `GET /analyses/operators`.
6. **Playground glossary** and tests updated for v2. Add tests: rollback leaves counts unchanged; M:N filter returns the right chargers.
7. **Drop the old per-layer tables** in the same migration or a follow-up, once the import verifies.
8. **Docs**: README, EXPLAIN screenshots from the real data, this plan updated to final state.

## 6. Level mapping and demo story

| Level objective | Evidence we will show |
| --- | --- |
| L1 schema design, normalization | ERD, [normalization.md](schema-v2/normalization.md): 1NF violations in raw WFS (`'A/B'` lists) fixed via M:N; operator 3NF extraction |
| L1 SQL | analyses in `backend/sql/`: joins, aggregates, KNN |
| L1 indexing + optimization | EXPLAIN before/after on 430k street trees: seq scan vs GiST, `(kind_code, geom)` composite |
| L1 ACID / transactions | import rollback demo ([acid-and-transactions.md](schema-v2/acid-and-transactions.md)) |
| L1 scaling | bbox + zoom gate, feature caps; why "all trees" does not scale |
| L1 ORM / access modules | SQLAlchemy models + raw SQL files, side by side, with a reason for each |
| L2 advanced schema | M:N with junction, lookup tables, composite and partial constraints |
| L2 advanced indexes | GiST composite via `btree_gist`, GIN on `attrs` (`jsonb_path_ops`) |
| L2 advanced SQL | add CTE + window-function analysis (rank operators per borough; `percentile_cont` already used) |
| L2 continuous backups | `pg_dump` script now; WAL archiving / `pg_basebackup` with restore test if time allows |
| L3 production-like | not targeted unless time remains |

Oral order (≈20 min): ERD (2) → live map and nearest (3) → tag filter and operator report (4) → EXPLAIN on trees (4) → transaction rollback demo (3) → Q&A on design decisions.

## 7. Risks and open decisions

- **Tag extraction quality**: connector strings have near-duplicates (`AC Steckdose Typ 2` vs `AC Typ 2 Steckdose`). Decide: normalize into one tag or keep as published. Default: keep as published, document it.
- **Big imports**: ~960k tree rows; use `COPY` or batched inserts, otherwise import is slow.
- **Scope creep**: tags on areas, a second M:N (`catalog ⟷ kind`), and L3 work are optional. Do not start them before steps 1–6 are done.
