# Import mapping — WFS → schema v2

Schema-first ETL: each Berlin open-data source maps into the v2 model. Provenance links: [data-sources.md](../data-sources.md). Algorithm and transaction boundary: [acid-and-transactions.md](acid-and-transactions.md).

## Boundaries

| Source slug | v2 table | Key | Notes |
| --- | --- | --- | --- |
| `districts` | `districts` | `official_id` | upsert; ids stay stable so dependents are not cleared |
| `neighborhoods` | `neighborhoods` | `official_id` | `district_id` via spatial join after load |

## Point amenities → `amenity_points`

`source_id` is the natural key (D4): `UNIQUE (kind_code, source_id)`. Checked against the cached WFS files: unique and non-null except where noted.

| Source slug | `kind_code` | `source_id` from | `subtype` from | Note |
| --- | --- | --- | --- | --- |
| `schools` | `school` | `bsn` | `schulart` | |
| `kitas` | `kita` | `e_nr` | `e_art` | + operator, tags, `kita_detail` |
| `hospitals` | `hospital` | `plan:<gisid>` / `other:<gisid>` | `hospital_type` | two WFS sources merged |
| `trees` | `street_tree` | `gisid` | — | + `tree_detail`, species |
| `park_trees` | `park_tree` | `gisid` | — | + `tree_detail`, species |
| `bike_parking` | `bike_parking` | **`gml_id`** | `faa_typ1` | `projektnummer` has 19 duplicates (one project, several sites) |
| `ev_chargers` | `ev_charger` | `importid` | `art_ladeeinrichtung` | + operator, tags, `ev_charger_detail` |
| `drinking_fountains` | `drinking_fountain` | `nummer` | `trinkbrunnenart` | |
| `bathing_waters` | `bathing_water` | `bathingwat` | quality rating | |
| `toilets` | `toilet` | **`fid`** | `modelltyp` | live importer looks for `nummer`/`id`: all 525 rows end up without a key |
| `sports_facilities` | `sports_facility` | `id` | — | |
| `park_and_ride` | `park_and_ride` | `id` | facility type | |

Every feature: `catalog_id` from the upserted catalog row; full source properties → `attrs`; `district_id` derived after insert (`ST_Within`, D9); geometry transformed to 25833.

## Area amenities → `amenity_areas`

| Source slug | `kind_code` | `source_id` from | `subtype` from |
| --- | --- | --- | --- |
| `green_spaces` | `green_space` | `pitid` | `objartname` |
| `playgrounds` | `playground` | `pitid` | space type |
| `cemeteries` | `cemetery` | `pitid` | `konfess` |

Polygons go through `ST_MakeValid` before insert; the table also has `CHECK (ST_IsValid(geom))`.

## Operators, tags, details

| Source field | Target |
| --- | --- |
| Kita `t_nr`, `t_name`, `t_art` | `operator` (`official_ref`, name, operator_type) → `operator_id` |
| EV / toilet `betreiber` | `operator` (name only, partial unique index) → `operator_id` |
| EV `anschluss_1..4` (split on `;`) | `tag` (`ev_connector`) + `amenity_point_tag`. Spellings kept as published |
| Kita `ang_1` (split on `/`) | `tag` (`kita_approach`) + `amenity_point_tag` |
| Toilet `barrierefrei`, `wickeltisch`, fee = 0 | `tag` (`toilet_feature`) for each yes |
| Tree `art_bot`, `art_dtsch`, `gattung` | `tree_species` (upsert by botanical name) → `tree_detail.species_id` |
| Tree `pflanzjahr`, `stammumfg`, `baumhoehe`, `kronedurch` | `tree_detail`; **0 or empty → NULL** (source uses 0 for unknown) |
| Kita `e_platz` | `kita_detail.capacity` |
| EV `anzahl_ladepunkte`, `ladeleistung_*`, `inbetriebnahme`, `oeffentlicher_raum` | `ev_charger_detail` |

## Import algorithm (per layer)

1. `import_run` row `running` (own transaction).
2. Transaction: upsert catalog → `COPY` into a temp staging table → `INSERT … ON CONFLICT (kind_code, source_id) DO UPDATE` (changed rows only) → delete rows of this kind missing from staging → derive `district_id` → operators → tags → detail tables.
3. Commit; `import_run` set to `committed` with counts, or `failed` with the error after rollback.

## App impact

- `layer_registry`: `LayerDef.table` becomes `kind_code` + family; same URL paths (D12).
- Analyses: `GROUP BY kind_code` instead of one subquery per old table.
- Query glossary: document the 16 tables and kinds.
