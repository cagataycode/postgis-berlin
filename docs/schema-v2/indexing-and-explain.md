# Indexing & EXPLAIN — schema v2

Index list: [erd.md](erd.md#indexes). Live predecessor: [explain-note.md](../explain-note.md). Measured in phase 7 on the real data (980k features, PostGIS 16, Docker on macOS, 128 MB `shared_buffers`); full plans in [explain/](explain/). Reproduce with `python -m scripts.perf_evidence`.

## Verified already (empty tables, phase 0)

Partition pruning works on the DDL:

```text
EXPLAIN SELECT id FROM amenity_points WHERE kind_code = 'street_tree';
 Index Scan using amenity_points_street_tree_kind_code_source_id_key
   on amenity_points_street_tree amenity_points
```

Only the `street_tree` partition appears in the plan; the park-tree and other partitions are pruned. (The index choice on an empty table is not meaningful; real plans come in phase 7.)

## Phase 7 results

Warm execution time (second run) from `EXPLAIN (ANALYZE, BUFFERS)`. Each experiment's full plans are in [explain/](explain/).

| # | Question | Result | Decision |
| --- | --- | --- | --- |
| 1 | Street trees in a bbox: [partitioned vs flat](explain/01-partition-pruning.md) | partitioned + kind filter **16.6 ms**; partitioned without the filter 36.0 ms; one flat table 79.2 ms | Keep the partitions. |
| 2 | [Composite GiST `(kind_code, geom)` vs plain GiST](explain/02-composite-gist.md) on `amenity_points_other` | 1.1–2.5 ms either way; composite index is 2x larger (1,048 vs 536 kB) | Keep the plain GiST. |
| 3 | [Tag lookup: `(tag_id, point_id)` index](explain/03-tag-junction-index.md) | rare tag 0.1 ms vs 5.7 ms without; common tag (2,074 Kitas) 16.2 vs 21.7 ms | Keep the extra index. |
| 4 | [`attrs @>`: GIN vs sequential scan](explain/04-gin-attrs.md) | operator lookup 1.1 vs 22.1 ms; genus lookup on 435k street trees **5.5 vs 389.6 ms** | Keep GIN, see cost in 6. |
| 5 | [Nearest neighbours](explain/05-knn.md) | `<->`: **0.7 ms**; `ORDER BY ST_Distance`: 2,029 ms; production query (14 kinds) 120 ms | Always use `<->` with `LIMIT`. |
| 6 | [GIN cost on bulk load](explain/06-gin-load-cost.md) | 50k rows: 14.6 s with GIN, 8.4 s without (1.7x) | Keep, but see the note below. |
| 7 | [`/analyses/trees-by-borough`](explain/07-trees-by-borough.md) | live query 10.7–11.2 s | Moved to a materialized view (migration 0012): 0.1 ms. |
| 8 | District assignment for ~434k trees | correlated `ST_Within … LIMIT 1` per row: killed after 8+ min; subdivided polygons in an unindexed staging table, written once: part of a 12 min load | See [implementation log, phase 2](../implementation-log.md). |

### What each result says

1. **Partition pruning.** With `kind_code = 'street_tree'` the plan has one node, a bitmap scan of `amenity_points_street_tree_geom_idx` (1,263 buffer hits). Without the filter the planner probes all three partitions (2,464 hits, 2x the time). The flat table needs a `BitmapAnd` of the GiST and a `kind_code` btree that returns 435k row ids just to discard most of them: 79 ms, 5x slower. Pruning only helps when the query names the kind, so the API always does.
2. **Composite GiST.** Both variants finish in 1–3 ms on 13k rows, and the differences are within noise. The composite index doubles the index size and slows writes, so there is nothing to gain. It would matter for a much larger mixed partition; that is not this data.
3. **Junction index.** The primary key is `(point_id, tag_id)`, so a lookup by tag cannot use it. The extra `(tag_id, point_id)` index turns a scan of 10k junction rows into an index probe (0.1 ms vs 5.7 ms for a rare tag). For a tag on 2,074 Kitas the planner still joins in bulk and the saving is small, which is expected.
4. **GIN on `attrs`.** The big win is on the large partition: 5.5 ms vs 390 ms for a genus lookup. It is the only index that answers "any source field" questions without knowing the column in advance.
5. **KNN.** The `<->` plan is an `Index Scan … Order By: (geom <-> …)` with no sort node and 8 buffer hits. The same question written as `ORDER BY ST_Distance(...)` seq-scans the partition, sorts, and takes 2 s (a third of it JIT compilation).
6. **Cost of GIN.** The GIN index makes bulk inserts 1.7x slower (about +6 s per 50k rows) and takes 138 MB for 323 MB of street-tree table. Imports are rare and offline, and the GIN lookups above are interactive, so we keep it. Option for later: GIN only on `amenity_points_other` (where it serves the operator lookups) and drop it from the two tree partitions, which would save about 130 MB per tree partition and ~40% of tree load time at the price of slow `attrs` searches on trees.
7. **Tree report.** The live query reads 88k pages and sorts about 960k rows twice (the sorts spill to disk, `work_mem` 4 MB) for `COUNT(DISTINCT …)`, `percentile_cont` and `mode()`. No index helps ordered-set aggregates, so the report is precomputed in `borough_tree_stats` (migration 0012) and refreshed at the end of every import, like `borough_amenity_stats`.

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
