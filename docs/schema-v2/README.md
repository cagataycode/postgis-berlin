# Schema v2 — study redesign

**Status:** implemented and running (migrations 0009–0013, importer, API, frontend); measured on the real data in phase 7.  
**Goal:** schema-first relational model that aligns this project with module **Level 1**, while keeping the Berlin Amenities Map product.

## Why v2

The live schema mostly mirrors each open-data layer as its own table (`schools`, `toilets`, `ev_chargers`, …). Those tables share the same shape. Schema v2 designs the domain first, then maps each WFS into that model — fewer clone tables, clearer 1NF/2NF/3NF story, same map app.

## Target relations

| Table | Role |
| --- | --- |
| `dataset_catalog` | Provenance once (org, license, URL, vintage) |
| `amenity_kind` | Lookup for feature kinds (`school`, `toilet`, …) |
| `districts` | Borough polygons |
| `neighborhoods` | Ortsteile → districts |
| `operator` | Who runs a feature (Kita Träger, charger operator) |
| `amenity_points` | All POINT amenities, list-partitioned by kind |
| `amenity_areas` | All MULTIPOLYGON amenities (parks, playgrounds, cemeteries, …) |
| `tag_category`, `tag` | Controlled vocabulary (EV connector, Kita approach, toilet feature) |
| `amenity_point_tag` | **Many-to-many** junction: points ⟷ tags |
| `kind_tag_category` | **Many-to-many**: which tag categories a kind may use |
| `tree_species` | Botanical name → German name, genus |
| `tree_detail`, `kita_detail`, `ev_charger_detail` | 1:1 typed details per point |
| `import_run` | Audit of each layer import |

16 tables + 3 partitions + 2 materialized views (`borough_amenity_stats`, `borough_tree_stats`). No compatibility views: the legacy tables were dropped at cutover (migration 0011).

## Doc map

0. [Project plan](../project-plan.md) — overview, use cases; [implementation plan](../module-requirements/implementation-plan.md); [log](../implementation-log.md)
1. [ERD](erd.md) — Mermaid diagram, cardinalities, indexes  
2. [Normalization](normalization.md) — 1NF / 2NF / 3NF  
3. [schema.sql](schema.sql) — target DDL + indexes (verified)  
4. [Import mapping](import-mapping.md) — WFS → v2 tables  
5. [ACID & transactions](acid-and-transactions.md)  
6. [Indexing & EXPLAIN](indexing-and-explain.md) — measured plans in [explain/](explain/)  
7. [Design decisions](design-decisions.md) — D1–D12 with alternatives and evidence  
8. [Operations](../operations.md) — backups, point-in-time recovery drill, roles  

Live app docs stay under [docs/](../). Data sources: [data-sources.md](../data-sources.md).

## Level 1 checklist (this redesign)

- [x] Tables, PKs, FKs, relationships (see ERD)  
- [x] Normalized schema rationale (see normalization)  
- [x] Implement migration + ETL against this DDL (migration 0009, `import_v2`)  
- [x] Indexing / EXPLAIN story (measured plans on the real data)  
- [x] Transactions / ACID narrative (see ACID doc)  
- [x] Scaling notes (bbox + kind filters; tree volume)  
- [x] Retarget SQLAlchemy models, analyses, Query glossary  

## Out of scope for Level 1

Production HA — Level 3. Partitioning, GIN indexes and continuous backups (WAL archiving with a point-in-time recovery drill) are done as Level 2 material.
