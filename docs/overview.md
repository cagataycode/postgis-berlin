# Overview

**Berlin Amenities Map** — PostGIS learning app that maps public amenity inventories from Berlin open data.

Click the map to see the nearest park, playground, street/park tree, bike rack, EV charger, drinking fountain, toilet, sports site, daycare, hospital, cemetery, Park & Ride, and bathing water (planar distance in EPSG:25833). Compare amenity counts and green cover by borough.

All data comes from official Berlin open-data portals — per-layer sources, links, and licenses: [data-sources.md](data-sources.md).

## Tech stack

| Layer | Choice |
| --- | --- |
| Database | PostgreSQL + PostGIS |
| Backend | FastAPI + SQLAlchemy 2 / GeoAlchemy2; SQL in `backend/sql/` |
| Migrations | Alembic |
| Import | Offline WFS / GeoJSON → PostGIS |
| Frontend | Vite + React + MapLibre |

## Goals

1. Show mapped amenity layers from open Berlin inventories.
2. Point nearest-amenity and borough density analyses in PostGIS.
3. Keep provenance and coverage caveats visible.
4. Explore Berlin inventories through the Query playground: schema glossary, ready SQL patterns, Run/Explain against the live map.

## Non-goals

Routing / walk-time; live occupancy of chargers or fountains; production multi-tenant; citywide tree GeoJSON in the browser.

## Docs

[MVP scope](mvp-scope.md) · [Data sources](data-sources.md) · [Technical requirements](technical-requirements.md) · [Schema v2 study redesign](schema-v2/README.md)
