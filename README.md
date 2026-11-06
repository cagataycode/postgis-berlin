# Berlin Amenities Map

PostGIS learning app: **mapped Berlin open-data amenities** — parks, trees, daycare, hospitals, mobility, and more.

**Stack:** Docker PostGIS · FastAPI · SQLAlchemy 2 / GeoAlchemy2 · Alembic · Vite / React / MapLibre

**Data:** 100% official Berlin open data (daten.berlin.de / Geoportal Berlin WFS) — full source list with links and licenses: [docs/data-sources.md](docs/data-sources.md)

Product docs: [docs/overview.md](docs/overview.md) · [mvp-scope](docs/mvp-scope.md) · [data-sources](docs/data-sources.md) · [technical-requirements](docs/technical-requirements.md)

## Quick start

```bash
# 1. Env
cp .env.example .env

# 2. Database (pick one)
docker compose up -d
# OR local Homebrew Postgres + PostGIS:
#   createdb berlin && psql -d berlin -c "CREATE EXTENSION postgis;"
#   then set DATABASE_URL=postgresql+psycopg://YOUR_USER@localhost:5432/berlin in .env

# 3. Backend
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
alembic upgrade head                            # creates the v2 schema (migrations 0001–0011)
python -m scripts.import_v2                     # Berlin open data → PostGIS (default, ~40 min incl. trees)
# python -m scripts.import_v2 --source samples  # tiny offline fixtures only (seconds)
# Skip the two tree inventories (about 960k rows) for a quick first run:
# python -m scripts.import_v2 --layers districts,neighborhoods,green_spaces,schools,bike_parking,ev_chargers,drinking_fountains,bathing_waters,toilets,playgrounds,sports_facilities,kitas,hospitals,cemeteries,park_and_ride

uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# 4. Frontend (new terminal)
cd frontend
npm install
npm run dev
```

- API: http://localhost:8000/docs  
- App: http://localhost:5173  

No external API keys. Only local `DATABASE_URL` and `DATABASE_URL_RO` in `.env` (gitignored). `DATABASE_URL_RO` is the read-only role `berlin_ro` (created by migration 0009) that the SQL playground uses. If port 5432 is taken (e.g. Homebrew Postgres), start Docker with `POSTGRES_PORT=5433 docker compose up -d db` and use port 5433 in both URLs.

## Schema (v2)

Design docs: [docs/schema-v2/](docs/schema-v2/README.md) (ERD, normalization, indexing, ACID). Decisions D1–D12: [implementation plan](docs/module-requirements/implementation-plan.md).

| Table | Role |
| --- | --- |
| `dataset_catalog` | Provenance, vintage, caveats |
| `districts`, `neighborhoods` | Borough and Ortsteil polygons (EPSG:25833) |
| `amenity_kind` | The 15 kinds; `geom_family` says point or area |
| `amenity_points` | All point amenities, **list-partitioned by `kind_code`** (street trees, park trees, other) |
| `amenity_areas` | Parks, playgrounds, cemeteries (validity-checked polygons) |
| `tag_category`, `tag` | Vocabulary: EV connector types, Kita approaches, toilet features |
| `amenity_point_tag` | **Many-to-many** point ⟷ tag, with composite foreign keys |
| `kind_tag_category` | **Many-to-many** kind ⟷ tag category (which kind may carry which tags) |
| `operator` | Who runs a facility (Kita number or name) |
| `tree_species` | Botanical name → German name, genus (3NF lookup) |
| `tree_detail`, `kita_detail`, `ev_charger_detail` | 1:1 typed facts for the kinds we analyse |
| `import_run` | Audit row per layer import |
| `borough_amenity_stats` | Materialized view: counts per borough and kind |

The database refuses inconsistent data (an area kind in the points table, a Kita tag on a toilet, a duplicate source key, a zero tree height): see `backend/tests/test_constraints.py`. All geometries EPSG:25833; sources per layer: [docs/data-sources.md](docs/data-sources.md). Each feature keeps its raw source properties in `attrs` (jsonb) for provenance.

## Analyses

1. **Nearest amenities** — `GET /analyses/nearest-amenities?lon=&lat=` (one KNN per kind)
2. **Amenity density by borough** — counts per district, with a city total (`ROLLUP`)
3. **Green by borough** — mapped park area share
4. **School–green proximity** — median / p90 distance per borough
5. **Tag filter** — `GET /ev-chargers?tag=<id>&tag=<id>` (AND), `GET /tags?kind=`, `GET /amenities/near`
6. **Operators** — `GET /analyses/operators` (top operators per borough, Kita capacity)
7. **Tree statistics** — `GET /analyses/trees-by-borough` (species diversity, median year, top genus)

## Tests

```bash
cd backend && source .venv/bin/activate
pytest -q        # DB-backed tests need the database up (docker compose up -d); they skip cleanly otherwise
```

Backups, point-in-time recovery drill and roles: [docs/operations.md](docs/operations.md). Migrations: `alembic upgrade head` applies 0001–0013 in order; 0011 drops the legacy per-layer tables, so on a fresh database they are created and dropped again. Visible SQL: [backend/sql/](backend/sql/) — explore with ready Patterns, the schema Glossary, and free SQL in the Query tab. Smoke checklist: [docs/smoke-test.md](docs/smoke-test.md).
