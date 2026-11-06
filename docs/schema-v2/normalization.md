# Normalization — schema v2

How the redesign satisfies **1NF → 2NF → 3NF**, with the source-data evidence for each step. Decision IDs (D1…) refer to [implementation-plan.md](../module-requirements/implementation-plan.md).

## 1NF — atomic values, no repeating groups

Violations found in the raw WFS data (cached files, checked 2026-11-05):

| Source field | Problem | Fix |
| --- | --- | --- |
| EV `anschluss_1..4`, values like `AC Typ 2 Steckdose; DC CHAdeMO` | repeating column group + `;`-lists. 247 of 4,960 chargers have more than one connector | `tag` + `amenity_point_tag` (D3) |
| Kita `ang_1`, values like `Offene-Arbeit/Situationsansatz` | `/`-list in one column. 950 of 2,905 kitas have more than one approach | `tag` + `amenity_point_tag` |
| Toilet `barrierefrei`, `wickeltisch`, … | one yes/no column per feature | `tag` (category `toilet_feature`) |

After the fix: one row = one fact, no lists, one geometry per row. `attrs` (jsonb) keeps the raw source record for provenance only; query predicates use real columns (`kind_code`, `district_id`, `name`, `subtype`) or tags.

## 2NF — no partial dependency on a composite key

- Single-column keys everywhere except the composite ones below.
- `amenity_points (id, kind_code)`: every non-key column depends on `id` alone, and `kind_code` is determined by the row. The composite key exists for partitioning and composite FKs, not because attributes depend on part of it.
- Detail tables `(point_id, kind_code)`: attributes (`capacity`, `height_m`, …) depend on the point. `kind_code` is carried so the database can check it.
- Junction `amenity_point_tag (point_id, tag_id)`: no non-key attribute depends on only one side. `kind_code` and `category_code` are fully determined by `point_id` and `tag_id`; they are repeated on purpose (see 3NF note).

## 3NF — no transitive dependency (non-key → non-key)

| Fact | Depends on | Lives in | Evidence |
| --- | --- | --- | --- |
| Org, license, URL, vintage | catalog row | `dataset_catalog` | |
| Kind label, geometry family | kind code | `amenity_kind` | |
| District name, polygon | district id | `districts` | |
| German name, genus | botanical name | `tree_species` (D6) | `art_bot → art_dtsch, gattung`: 0 conflicts in ~962k trees, 719 + 835 species |
| Operator name, type | operator reference | `operator` (D7) | `t_nr → t_name, t_art`: 0 conflicts, 1,165 Kita operators |
| Tag label, category | tag id | `tag` | |
| Height, circumference, planting year, capacity, power | point id | detail tables (D5) | typed, constrained columns |

Features store foreign keys only, never copied operator, species or district names.

### Deliberate exceptions

| Exception | Why it is acceptable |
| --- | --- |
| `amenity_point_tag.kind_code` / `category_code` repeat facts of the point and the tag | Composite FKs make the database verify them on every insert. They cannot drift, so no update anomaly is possible. |
| `amenity_*.geom_family` is a constant per table | Needed as the second half of the FK to `amenity_kind (code, geom_family)` (D2). |
| `district_id` on features (D9) | Derived by `ST_Within` at import: a cached spatial join for fast borough filters. Re-derived on every import. A `neighborhood_id` next to it would add a transitive dependency, so there is none. |

## vs live schema

| Live | v2 |
| --- | --- |
| ~15 nearly identical amenity tables, type column renamed per table | `amenity_points` + `amenity_areas` + `kind_code` + `subtype` (D1) |
| Species, operator, connector types as free text per row | lookup tables and tags |
| Uniqueness enforced only by the importer (delete + reinsert) | `UNIQUE (kind_code, source_id)` (D4) |
| Kind/geometry consistency by convention | composite FKs (D2) |

## Functional dependencies (summary)

```text
dataset_catalog.id        → slug, name, source_organization, source_url, license_text, …
amenity_kind.code         → label, geom_family
operator.id               → official_ref, name, operator_type
tree_species.id           → botanical_name, german_name, genus
districts.id              → official_id, name, geom, catalog_id
neighborhoods.id          → official_id, name, district_id, geom, catalog_id
amenity_points.(id, kind) → source_id, name, subtype, catalog_id, district_id, operator_id, attrs, geom
                            (kind_code, source_id) → id          (candidate key)
amenity_areas.id          → kind_code, source_id, name, subtype, catalog_id, district_id, attrs, geom
tag.id                    → category_code, label
tree_detail.point_id      → species_id, planting_year, trunk_circumference_cm, height_m, crown_diameter_m
kita_detail.point_id      → capacity
ev_charger_detail.point_id→ charge_points, max_power_kw, commissioned_on, public_space
```
