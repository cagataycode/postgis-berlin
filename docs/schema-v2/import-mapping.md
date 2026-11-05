# Import mapping — WFS → schema v2

Schema-first ETL: each Berlin open-data source maps into the v2 model. Full provenance links: [data-sources.md](../data-sources.md).

## Boundaries (unchanged targets)

| Live / source slug | v2 table | Notes |
| --- | --- | --- |
| `districts` | `districts` | + `dataset_catalog` row |
| `neighborhoods` | `neighborhoods` | set `district_id` via spatial join after load |

## Point amenities → `amenity_points`

| Source slug (live) | `kind_code` | Curated `subtype` from |
| --- | --- | --- |
| `schools` | `school` | school type field |
| `kitas` | `kita` | facility type |
| `hospitals` | `hospital` | hospital type |
| `trees` | `street_tree` | species |
| `park_trees` | `park_tree` | species |
| `bike_parking` | `bike_parking` | facility type |
| `ev_chargers` | `ev_charger` | charger type |
| `drinking_fountains` | `drinking_fountain` | fountain type |
| `bathing_waters` | `bathing_water` | quality rating |
| `toilets` | `toilet` | facility type |
| `sports_facilities` | `sports_facility` | facility type |
| `park_and_ride` | `park_and_ride` | facility type |

Every feature: `catalog_id` from upserted catalog row; full GeoJSON properties → `attrs`; `district_id` assigned after insert (`ST_Within` / point-on-surface).

## Area amenities → `amenity_areas`

| Source slug (live) | `kind_code` | Curated `subtype` from |
| --- | --- | --- |
| `green_spaces` | `green_space` | space type |
| `playgrounds` | `playground` | space type |
| `cemeteries` | `cemetery` | denomination |

## Operators and tags (extra step after insert)

| Source field | Target |
| --- | --- |
| Kita `t_name`, `t_art` (key `t_nr`) | `operator` (name, operator_type) → `amenity_points.operator_id` |
| EV `betreiber`; toilet `betreiber` | `operator` → `operator_id` |
| EV `anschluss_1..4` (split on `;`) | `tag` (`ev_connector`) + `amenity_point_tag` |
| Kita `ang_1` (split on `/`) | `tag` (`kita_approach`) + `amenity_point_tag` |
| Toilet `barrierefrei`, `wickeltisch`, `nutzungsentgelt = 0` | `tag` (`toilet_feature`) for each `ja` |

## Import algorithm (per layer)

1. Begin transaction.  
2. Upsert `dataset_catalog` by slug.  
3. `DELETE FROM amenity_points WHERE kind_code = :kind` (or areas).  
4. Insert features with `kind_code`, curated columns, `attrs`, `geom` (transform to 25833).  
5. Assign `district_id` for that kind; upsert operators; upsert tags and insert junction rows (`ON CONFLICT DO NOTHING`).  
6. Commit (or rollback on failure).

See [acid-and-transactions.md](acid-and-transactions.md).

## App impact (when implementing)

- `layer_registry`: query `amenity_points` / `amenity_areas` with `kind_code = …` (or compatibility views).  
- Analyses: `GROUP BY kind_code` instead of one subquery per old table.  
- Query glossary: document the six base tables + kinds.
