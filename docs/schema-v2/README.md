# Schema v2 — study redesign

**Status:** design finalized and DDL verified on PostGIS 16 (phase 0). Alembic migration is phase 1.  
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

16 tables + 3 partitions. No compatibility views: the legacy tables are dropped at cutover (phase 6).

## Doc map

0. [Project plan](../project-plan.md) — overview, use cases; [implementation plan](../module-requirements/implementation-plan.md); [log](../implementation-log.md)
1. [ERD](erd.md) — Mermaid diagram, cardinalities, indexes  
2. [Normalization](normalization.md) — 1NF / 2NF / 3NF  
3. [schema.sql](schema.sql) — target DDL + indexes (verified)  
4. [Import mapping](import-mapping.md) — WFS → v2 tables  
5. [ACID & transactions](acid-and-transactions.md)  
6. [Indexing & EXPLAIN](indexing-and-explain.md)  

Live app docs stay under [docs/](../). Data sources: [data-sources.md](../data-sources.md).

## Level 1 checklist (this redesign)

- [x] Tables, PKs, FKs, relationships (see ERD)  
- [x] Normalized schema rationale (see normalization)  
- [ ] Implement migration + ETL against this DDL (phases 1–2)  
- [x] Indexing / EXPLAIN story (questions defined; plans after import, phase 7)  
- [x] Transactions / ACID narrative (see ACID doc)  
- [x] Scaling notes (bbox + kind filters; tree volume)  
- [ ] Retarget SQLAlchemy models, analyses, Query glossary  

## Out of scope for Level 1

Continuous backups, production HA — Level 2+. Partitioning and GIN indexes are used anyway, as Level 2 material (see implementation plan).
