# Indexing & EXPLAIN — schema v2

Level 1: tune with indexes and query optimization. Live predecessor: [explain-note.md](../explain-note.md).

## Indexes in v2

| Index | Type | Serves |
| --- | --- | --- |
| `ix_amenity_points_geom` | GiST | Bbox / KNN / `ST_DWithin` on points |
| `ix_amenity_areas_geom` | GiST | Bbox / intersects on areas |
| `ix_districts_geom` / `ix_neighborhoods_geom` | GiST | Boundary filters & PIP |
| `ix_amenity_points_kind` | btree | `WHERE kind_code = …` |
| `ix_amenity_*_district` | btree | Borough filter / density joins |
| `ix_amenity_*_catalog` | btree | Provenance joins |

## Hot map query (areas)

After data is loaded into v2:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT a.id
FROM amenity_areas a
WHERE a.kind_code = 'green_space'
  AND a.geom && ST_Transform(
        ST_MakeEnvelope(13.3, 52.45, 13.5, 52.55, 4326),
        25833
      );
```

Expect a **GiST index** path on `ix_amenity_areas_geom` (and a filter on `kind_code`), not a full sequential scan of all area kinds once tables are non-trivial.

## Hot map query (trees — must be scoped)

Street trees are large. Always combine kind + bbox (and/or district):

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT p.id
FROM amenity_points p
WHERE p.kind_code = 'street_tree'
  AND p.geom && ST_Transform(
        ST_MakeEnvelope(13.38, 52.50, 13.42, 52.53, 4326),
        25833
      );
```

## Scaling note (Level 1)

Relational engines scale poorly if every client asks for “all trees in Berlin” as GeoJSON. Application limits (bbox, district, feature cap, zoom gate) are part of the optimization story alongside indexes — not a substitute for them.

## Report artifact

Paste one `EXPLAIN (ANALYZE, BUFFERS)` showing Index Scan / Bitmap Index Scan on a GiST geom index, plus a one-line contrast with an unfiltered `SELECT` on the same table (seq scan risk).
