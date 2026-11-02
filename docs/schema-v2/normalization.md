# Normalization — schema v2

How the redesign satisfies **1NF → 2NF → 3NF** for Level 1.

## 1NF — atomic values, no repeating groups

- One row = one feature (or one district / neighborhood / catalog entry / kind).
- No comma-separated district lists; no array-of-amenities columns.
- Geometry is a single PostGIS value per row.
- Source leftovers live in `attrs` (jsonb). That is fine for provenance blobs; **query predicates** use real columns (`kind_code`, `district_id`, `name`, `subtype`).

## 2NF — no partial dependency on a composite key

Primary keys are single-column (`id` or `amenity_kind.code`). With a single-attribute PK, partial-key dependencies do not arise.

Avoid: `PRIMARY KEY (kind_code, source_id)` while also storing attributes that depend only on `kind_code` (e.g. kind label). Kind metadata belongs on `amenity_kind`.

## 3NF — no transitive dependency (non-key → non-key)

| Fact | Depends on | Lives in |
| --- | --- | --- |
| Organization, license, source URL, vintage | catalog row | `dataset_catalog` |
| Kind label, geom family | kind code | `amenity_kind` |
| District name, borough polygon | district id | `districts` |
| Feature name, subtype, geom | feature id | `amenity_points` / `amenity_areas` |

Features store **foreign keys only** (`catalog_id`, `kind_code`, `district_id`) — not copied org names or district names.

### vs live schema

| Live | v2 |
| --- | --- |
| Provenance in `dataset_catalog` (already 3NF-friendly) | Keep |
| `district_id` FK (already 3NF-friendly) | Keep |
| ~15 nearly identical amenity tables | Collapse to `amenity_points` + `amenity_areas` + `kind_code` |
| Type column renamed per table (`school_type`, `facility_type`, …) | Single `subtype` |

Collapsing clones is **entity consolidation** guided by the same mindset as 3NF: one fact shape, one place.

## Functional dependencies (summary)

```text
dataset_catalog.id → slug, name, source_organization, source_url, license_text, …
amenity_kind.code  → label, geom_family
districts.id       → official_id, name, geom, catalog_id
neighborhoods.id   → official_id, name, district_id, geom, catalog_id
amenity_points.id  → kind_code, catalog_id, district_id, source_id, name, subtype, attrs, geom
amenity_areas.id   → kind_code, catalog_id, district_id, source_id, name, subtype, attrs, geom
```

## Deliberate denormalization (none required for L1)

No cached `district_name` on features. Join `districts` when needed. If a future report needs heavy read denormalization, document it as an explicit tradeoff — not accidental duplication.
