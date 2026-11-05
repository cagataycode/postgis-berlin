# Schema v2 — study redesign

**Status:** design / study guide (not yet the live Alembic schema).  
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
| `amenity_points` | All POINT amenities |
| `amenity_areas` | All MULTIPOLYGON amenities (parks, playgrounds, cemeteries, …) |
| `tag_category`, `tag` | Controlled vocabulary (EV connector, Kita approach, toilet feature) |
| `amenity_point_tag` | **Many-to-many** junction: points ⟷ tags |

Optional compatibility views (`schools`, `toilets`, …) can sit on top for teaching / gradual migration.

## Doc map

0. [Project plan](../project-plan.md) — overview, use cases, steps
1. [ERD](erd.md) — Mermaid diagram, cardinalities, indexes  
2. [Normalization](normalization.md) — 1NF / 2NF / 3NF  
3. [schema.sql](schema.sql) — proposed DDL + indexes  
4. [Import mapping](import-mapping.md) — WFS → v2 tables  
5. [ACID & transactions](acid-and-transactions.md)  
6. [Indexing & EXPLAIN](indexing-and-explain.md)  

Live app docs stay under [docs/](../). Data sources: [data-sources.md](../data-sources.md).

## Level 1 checklist (this redesign)

- [x] Tables, PKs, FKs, relationships (see ERD)  
- [x] Normalized schema rationale (see normalization)  
- [ ] Implement migration + ETL against this DDL  
- [x] Indexing / EXPLAIN story (see indexing doc; update after import)  
- [x] Transactions / ACID narrative (see ACID doc)  
- [x] Scaling notes (bbox + kind filters; tree volume)  
- [ ] Retarget SQLAlchemy models, analyses, Query glossary  

## Out of scope for Level 1

Continuous backups, production HA, partitioning, exotic index types beyond GiST + btree — those are Level 2+.
