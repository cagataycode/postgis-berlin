# Berlin Amenities Map

PostGIS learning app: **mapped Berlin open-data amenities** — parks, trees, daycare, hospitals, mobility, and more.

**Stack:** Docker PostGIS · FastAPI · SQLAlchemy 2 / GeoAlchemy2 · Alembic · Vite / React / MapLibre

**Data:** 100% official Berlin open data (daten.berlin.de / Geoportal Berlin WFS) — full source list with links and licenses: [docs/data-sources.md](docs/data-sources.md)

**Context:** hand-in for the university Databases module. Solo project: all parts (schema, importer, API, frontend, operations, documentation) were designed and written by the author.

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

## Use cases

| # | Use case | Status | Where |
| --- | --- | --- | --- |
| U1 | Show amenity layers on a map (bbox filter, zoom-gated trees) | implemented | `GET /<layer>` |
| U2 | Click the map → nearest amenity of each kind (KNN) | implemented | `GET /analyses/nearest-amenities` |
| U3 | Amenity counts per borough, with a city total | implemented | `GET /analyses/amenity-density-by-borough` |
| U4 | Park area share per borough | implemented | `GET /analyses/green-by-borough` |
| U5 | School → nearest park distance (median / p90) | implemented | `GET /analyses/school-green-proximity` |
| U6 | Read-only SQL playground with Explain (as database role `berlin_ro`) | implemented | `POST /sql/run` |
| U7 | Filter by tag: EV chargers by connector type, Kitas by approach, toilets by feature; radius search with tags | implemented | `?tag=` on the layer endpoints, `GET /tags`, `GET /amenities/near` |
| U8 | Operator report: largest operators per borough, Kita capacity; tree statistics per borough | implemented | `GET /analyses/operators`, `GET /analyses/trees-by-borough` |
| U9 | Provenance: source, licence, vintage and caveats per layer; one feature with operator, tags and typed detail | implemented | `GET /layers`, `GET /features/{layer}/{id}` |

Not implemented: editing data through the app (imports are offline scripts; the API only reads), user accounts, routing/walking distances (all distances are straight-line metres).

## Data

All data is **real open data, nothing is generated**: Berlin boundaries and amenity inventories from Geoportal Berlin WFS and daten.berlin.de (sources and licences: [docs/data-sources.md](docs/data-sources.md)). Counts after a full import (`python -m scripts.import_v2`, 17 layers; database size 1.4 GB):

| Table | Rows |
| --- | ---: |
| `amenity_points` | 975,765 (street trees 434,765 · park trees 527,780 · EV chargers 4,960 · Kitas 2,905 · bike parking 2,374 · sports 1,085 · schools 930 · toilets 525 · fountains 242 · hospitals 111 · P+R 49 · bathing waters 39) |
| `amenity_areas` | 4,675 (parks 2,563 · playgrounds 1,886 · cemeteries 226) |
| `districts` / `neighborhoods` | 12 / 97 |
| `tree_detail` / `tree_species` | 962,545 / 916 |
| `kita_detail` / `ev_charger_detail` | 2,905 / 4,960 |
| `operator` | 1,404 |
| `tag` / `amenity_point_tag` | 19 / 10,040 |
| **Features in total** | **980,440** (plus 17 catalog rows and an `import_run` audit row per import) |

Each import is idempotent: running it again reports 0 inserted / 0 updated / 0 deleted and leaves every id unchanged.

## Entity-relationship model

[docs/schema-v2/erd.md](docs/schema-v2/erd.md) (Mermaid, with cardinalities, keys and indexes). Normalization argument: [normalization.md](docs/schema-v2/normalization.md). Why each design choice, with alternatives and measurements: [design-decisions.md](docs/schema-v2/design-decisions.md). Measured query plans: [indexing-and-explain.md](docs/schema-v2/indexing-and-explain.md).

## Tests

```bash
cd backend && source .venv/bin/activate
pytest -q        # DB-backed tests need the database up (docker compose up -d); they skip cleanly otherwise
```

Backups, point-in-time recovery drill and roles: [docs/operations.md](docs/operations.md). Migrations: `alembic upgrade head` applies 0001–0013 in order; 0011 drops the legacy per-layer tables, so on a fresh database they are created and dropped again. Visible SQL: [backend/sql/](backend/sql/) — explore with ready Patterns, the schema Glossary, and free SQL in the Query tab. Smoke checklist: [docs/smoke-test.md](docs/smoke-test.md).
