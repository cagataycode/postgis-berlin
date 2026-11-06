# Smoke test

1. `alembic upgrade head`
2. `python -m scripts.import_v2 --source samples` (schema v2 importer; also refreshes `borough_amenity_stats`)
3. `GET /health` → ok + PostGIS
4. `GET /layers` lists amenity catalog slugs; `GET /layers/bike_parking/sql` returns that layer's rendered GeoJSON SQL (reads `amenity_points` with `kind_code = 'bike_parking'`)
5. `GET /bike-parking` / `/ev-chargers` / `/drinking-fountains` / `/bathing-waters` / `/toilets` / `/playgrounds` / `/sports-facilities` / `/kitas` / `/hospitals` / `/cemeteries` / `/park-and-ride` return FeatureCollections
6. `GET /trees` and `/park-trees` without bbox/district → 400; with bbox → features
7. `GET /analyses/nearest-amenities?lon=13.405&lat=52.52` → `nearest` array with distances (incl. kitas / hospitals / cemeteries / P+R / park trees)
8. `GET /analyses/amenity-density-by-borough` → 12 (or sample) borough rows plus a "Berlin (total)" row; `GET /analyses/operators` and `/analyses/trees-by-borough` return rows; `GET /tags?kind=ev_charger` lists connector tags; `GET /ev-chargers?tag=<id>` returns fewer features than without the tag; `GET /schools?tag=1` → 400; `GET /features/ev_chargers/<id>` returns tags, operator and detail
9. UI: click map → Nearby tab fills (clicking on a feature also shows its card with operator, tags and detail); EV charger / Kita / toilet tag chips filter the layer and change its count; Compare has Top operator, Tree species count and Median planting year (tree measures read the materialized view `borough_tree_stats`); layer toggles for new amenities; Compare measure rows populate; clicking a borough filters and focuses the map
10. Street/park trees stay off until zoom ≥ 15 when enabled (chip shows “z15”); oversized bbox → 400; Query: open a ready **pattern**, **Run** draws GeoJSON and syncs layer filters; **Glossary** lists tables/fields; EXPLAIN on a bbox pattern can show a GiST index when zoomed in; layer **Query** / **Show query** load into the same editor; binds stay as `:name` and fill only at run time; `POST /sql/run` accepts SELECT / rejects writes
11. Toggle Neighborhoods → lighter Ortsteil borders + names (zoom ≥ 11); `GET /neighborhoods` returns FeatureCollection
