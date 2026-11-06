# 4. `attrs @>` : GIN (jsonb_path_ops) vs sequential scan

Containment lookups on the raw source properties. Real indexes vs copies of the same rows without GIN.

## A. EV chargers by operator, GIN (amenity_points_other)

```sql
SELECT id FROM amenity_points_other WHERE attrs @> '{"betreiber": "Wall GmbH"}'
```

```text
Bitmap Heap Scan on amenity_points_other  (cost=19.19..785.40 rows=401 width=8) (actual time=0.228..0.988 rows=341 loops=1)
  Recheck Cond: (attrs @> '{"betreiber": "Wall GmbH"}'::jsonb)
  Heap Blocks: exact=30
  Buffers: shared hit=34
  ->  Bitmap Index Scan on amenity_points_other_attrs_idx  (cost=0.00..19.09 rows=401 width=0) (actual time=0.205..0.206 rows=341 loops=1)
        Index Cond: (attrs @> '{"betreiber": "Wall GmbH"}'::jsonb)
        Buffers: shared hit=4
Planning:
  Buffers: shared hit=1
Planning Time: 0.515 ms
Execution Time: 1.138 ms
```

## B. same, no GIN

```sql
SELECT id FROM perf.other_nogin WHERE attrs @> '{"betreiber": "Wall GmbH"}'
```

```text
Seq Scan on other_nogin  (cost=0.00..1189.25 rows=401 width=8) (actual time=14.236..22.001 rows=341 loops=1)
  Filter: (attrs @> '{"betreiber": "Wall GmbH"}'::jsonb)
  Rows Removed by Filter: 12879
  Buffers: shared hit=1024
Planning Time: 0.440 ms
Execution Time: 22.139 ms
```

## C. street trees, genus Ginkgo, GIN (435k rows)

```sql
SELECT id FROM amenity_points_street_tree WHERE attrs @> '{"gattung": "Ginkgo"}'
```

```text
Bitmap Heap Scan on amenity_points_street_tree  (cost=25.84..194.12 rows=43 width=8) (actual time=0.959..5.045 rows=1315 loops=1)
  Recheck Cond: (attrs @> '{"gattung": "Ginkgo"}'::jsonb)
  Heap Blocks: exact=492
  Buffers: shared hit=498
  ->  Bitmap Index Scan on amenity_points_street_tree_attrs_idx  (cost=0.00..25.82 rows=43 width=0) (actual time=0.736..0.737 rows=1315 loops=1)
        Index Cond: (attrs @> '{"gattung": "Ginkgo"}'::jsonb)
        Buffers: shared hit=6
Planning:
  Buffers: shared hit=1
Planning Time: 0.666 ms
Execution Time: 5.496 ms
```

## D. same, no GIN

```sql
SELECT id FROM perf.street_nogin WHERE attrs @> '{"gattung": "Ginkgo"}'
```

```text
Gather  (cost=1000.00..43191.08 rows=4391 width=8) (actual time=30.501..389.104 rows=1315 loops=1)
  Workers Planned: 2
  Workers Launched: 2
  Buffers: shared hit=2176 read=37312
  ->  Parallel Seq Scan on street_nogin  (cost=0.00..41751.98 rows=1830 width=8) (actual time=16.329..320.593 rows=438 loops=3)
        Filter: (attrs @> '{"gattung": "Ginkgo"}'::jsonb)
        Rows Removed by Filter: 144483
        Buffers: shared hit=2176 read=37312
Planning Time: 0.582 ms
Execution Time: 389.621 ms
```

GIN index on street trees: 138 MB for a 323 MB table.

## Summary (warm execution time)

| Case | ms |
| --- | ---: |
| A. EV chargers by operator, GIN (amenity_points_other) | 1.1 |
| B. same, no GIN | 22.1 |
| C. street trees, genus Ginkgo, GIN (435k rows) | 5.5 |
| D. same, no GIN | 389.6 |
