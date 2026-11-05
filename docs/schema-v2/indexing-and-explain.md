# Indexing & EXPLAIN — schema v2

Index list: [erd.md](erd.md#indexes). Live predecessor: [explain-note.md](../explain-note.md). Real plans are collected in phase 7; this page holds the questions and expectations, and gets plans pasted in.

## Verified already (empty tables, phase 0)

Partition pruning works on the DDL:

```text
EXPLAIN SELECT id FROM amenity_points WHERE kind_code = 'street_tree';
 Index Scan using amenity_points_street_tree_kind_code_source_id_key
   on amenity_points_street_tree amenity_points
```

Only the `street_tree` partition appears in the plan; the park-tree and other partitions are pruned. (The index choice on an empty table is not meaningful; real plans come in phase 7.)

## Phase 7 experiments

| # | Question | Compare | Expect |
| --- | --- | --- | --- |
| 1 | Street trees in a bbox | partitioned + GiST vs a non-partitioned copy | only `amenity_points_street_tree` scanned; GiST bitmap/index scan |
| 2 | Is a composite GiST `(kind_code, geom)` worth it? | composite via `btree_gist` vs plain GiST, on the `other` partition | keep whichever wins, record why |
| 3 | Points with a tag | junction `(tag_id, point_id)` index vs none | index scan instead of seq scan on the junction |
| 4 | `attrs @> '{"betreiber": "Wall GmbH"}'` | GIN `jsonb_path_ops` vs seq scan | GIN bitmap scan |
| 5 | Nearest amenities (KNN) | `ORDER BY geom <-> point LIMIT n` | index-ordered scan, no sort |
| 6 | District assignment `UPDATE … ST_Within` for ~434k trees | with vs without districts GiST | index probe per tree |

Template:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT p.id
FROM amenity_points p
WHERE p.kind_code = 'street_tree'
  AND p.geom && ST_Transform(ST_MakeEnvelope(13.38, 52.50, 13.42, 52.53, 4326), 25833);
```

Always scope tree queries by kind **and** bbox or district. Contrast each with the unfiltered version to show the seq-scan risk.

## Scaling note

Relational engines scale poorly if every client asks for "all trees in Berlin" as GeoJSON. Application limits (bbox, district, feature cap, zoom gate) are part of the optimization story alongside indexes and partitioning, not a substitute for them.

## Report artifact

For each experiment: the plan (Index/Bitmap scan on the intended index), timing before and after, and a one-paragraph explanation. Saved under `docs/schema-v2/explain/`.
