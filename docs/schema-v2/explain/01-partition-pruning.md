# 1. Street trees in a bbox: partition pruning

Is partitioning `amenity_points` by `kind_code` worth it? Same bbox query on the partitioned table, without the kind filter, and on a non-partitioned copy of all point rows (one table, GiST on geom, btree on kind_code).

## A. partitioned, kind filter

```sql
SELECT p.id FROM amenity_points p WHERE p.kind_code = 'street_tree' AND p.geom && ST_Transform(ST_MakeEnvelope(13.38, 52.50, 13.42, 52.53, 4326), 25833)
```

```text
Bitmap Heap Scan on amenity_points_street_tree p  (cost=497.48..16266.58 rows=5832 width=8) (actual time=5.028..14.883 rows=5856 loops=1)
  Recheck Cond: (geom && '0103000020E96400000100000005000000ECC44BD544CE1741FC47C56087315641DCAB4A5B70CF174190144C89C934564198C11928D5F917417271B77FBA345641AC84FC07B1F81741DFC81C5678315641ECC44BD544CE1741FC47C56087315641'::geometry)
  Filter: ((kind_code)::text = 'street_tree'::text)
  Heap Blocks: exact=1165
  Buffers: shared hit=1214
  ->  Bitmap Index Scan on amenity_points_street_tree_geom_idx  (cost=0.00..496.02 rows=5832 width=0) (actual time=4.462..4.463 rows=5860 loops=1)
        Index Cond: (geom && '0103000020E96400000100000005000000ECC44BD544CE1741FC47C56087315641DCAB4A5B70CF174190144C89C934564198C11928D5F917417271B77FBA345641AC84FC07B1F81741DFC81C5678315641ECC44BD544CE1741FC47C56087315641'::geometry)
        Buffers: shared hit=49
Planning Time: 1.160 ms
Execution Time: 16.555 ms
```
Only `amenity_points_street_tree` is scanned (the other partitions are pruned at plan time).

## B. partitioned, no kind filter

```sql
SELECT p.id FROM amenity_points p WHERE  p.geom && ST_Transform(ST_MakeEnvelope(13.38, 52.50, 13.42, 52.53, 4326), 25833)
```

```text
Append  (cost=169.23..33335.06 rows=12155 width=8) (actual time=5.391..32.500 rows=12067 loops=1)
  Buffers: shared hit=2464
  ->  Bitmap Heap Scan on amenity_points_park_tree p_1  (cost=169.23..16135.36 rows=5799 width=8) (actual time=5.389..12.445 rows=5687 loops=1)
        Recheck Cond: (geom && '0103000020E96400000100000005000000ECC44BD544CE1741FC47C56087315641DCAB4A5B70CF174190144C89C934564198C11928D5F917417271B77FBA345641AC84FC07B1F81741DFC81C5678315641ECC44BD544CE1741FC47C56087315641'::geometry)
        Heap Blocks: exact=970
        Buffers: shared hit=1026
        ->  Bitmap Index Scan on amenity_points_park_tree_geom_idx  (cost=0.00..167.78 rows=5799 width=0) (actual time=4.942..4.943 rows=5687 loops=1)
              Index Cond: (geom && '0103000020E96400000100000005000000ECC44BD544CE1741FC47C56087315641DCAB4A5B70CF174190144C89C934564198C11928D5F917417271B77FBA345641AC84FC07B1F81741DFC81C5678315641ECC44BD544CE1741FC47C56087315641'::geometry)
              Buffers: shared hit=56
  ->  Bitmap Heap Scan on amenity_points_street_tree p_2  (cost=497.48..16252.00 rows=5832 width=8) (actual time=4.871..12.521 rows=5856 loops=1)
        Recheck Cond: (geom && '0103000020E96400000100000005000000ECC44BD544CE1741FC47C56087315641DCAB4A5B70CF174190144C89C934564198C11928D5F917417271B77FBA345641AC84FC07B1F81741DFC81C5678315641ECC44BD544CE1741FC47C56087315641'::geometry)
        Heap Blocks: exact=1165
        Buffers: shared hit=1214
        ->  Bitmap Index Scan on amenity_points_street_tree_geom_idx  (cost=0.00..496.02 rows=5832 width=0) (actual time=4.325..4.326 rows=5860 loops=1)
              Index Cond: (geom && '0103000020E96400000100000005000000ECC44BD544CE1741FC47C56087315641DCAB4A5B70CF174190144C89C934564198C11928D5F917417271B77FBA345641AC84FC07B1F81741DFC81C5678315641ECC44BD544CE1741FC47C56087315641'::geometry)
              Buffers: shared hit=49
  ->  Bitmap Heap Scan on amenity_points_other p_3  (cost=16.21..886.93 rows=524 width=8) (actual time=0.747..1.683 rows=524 loops=1)
        Recheck Cond: (geom && '0103000020E96400000100000005000000ECC44BD544CE1741FC47C56087315641DCAB4A5B70CF174190144C89C934564198C11928D5F917417271B77FBA345641AC84FC07B1F81741DFC81C5678315641ECC44BD544CE1741FC47C56087315641'::geometry)
        Heap Blocks: exact=215
        Buffers: shared hit=224
        ->  Bitmap Index Scan on amenity_points_other_geom_idx  (cost=0.00..16.08 rows=524 width=0) (actual time=0.669..0.669 rows=550 loops=1)
              Index Cond: (geom && '0103000020E96400000100000005000000ECC44BD544CE1741FC47C56087315641DCAB4A5B70CF174190144C89C934564198C11928D5F917417271B77FBA345641AC84FC07B1F81741DFC81C5678315641ECC44BD544CE1741FC47C56087315641'::geometry)
              Buffers: shared hit=9
Planning Time: 1.662 ms
Execution Time: 35.955 ms
```
Without the kind filter every partition's GiST index is probed: the filter is what makes pruning work.

## C. non-partitioned copy, kind filter

```sql
SELECT p.id FROM perf.points_flat p WHERE p.kind_code = 'street_tree' AND p.geom && ST_Transform(ST_MakeEnvelope(13.38, 52.50, 13.42, 52.53, 4326), 25833)
```

```text
Bitmap Heap Scan on points_flat p  (cost=5127.65..23031.45 rows=5713 width=8) (actual time=68.965..77.372 rows=5856 loops=1)
  Recheck Cond: ((geom && '0103000020E96400000100000005000000ECC44BD544CE1741FC47C56087315641DCAB4A5B70CF174190144C89C934564198C11928D5F917417271B77FBA345641AC84FC07B1F81741DFC81C5678315641ECC44BD544CE1741FC47C56087315641'::geometry) AND ((kind_code)::text = 'street_tree'::text))
  Heap Blocks: exact=1161
  Buffers: shared hit=1621
  ->  BitmapAnd  (cost=5127.65..5127.65 rows=5713 width=0) (actual time=68.399..68.403 rows=0 loops=1)
        Buffers: shared hit=460
        ->  Bitmap Index Scan on points_flat_geom_idx  (cost=0.00..360.50 rows=12829 width=0) (actual time=8.374..8.375 rows=12067 loops=1)
              Index Cond: (geom && '0103000020E96400000100000005000000ECC44BD544CE1741FC47C56087315641DCAB4A5B70CF174190144C89C934564198C11928D5F917417271B77FBA345641AC84FC07B1F81741DFC81C5678315641ECC44BD544CE1741FC47C56087315641'::geometry)
              Buffers: shared hit=85
        ->  Bitmap Index Scan on points_flat_kind_code_idx  (cost=0.00..4764.04 rows=434615 width=0) (actual time=59.803..59.804 rows=434765 loops=1)
              Index Cond: ((kind_code)::text = 'street_tree'::text)
              Buffers: shared hit=375
Planning Time: 0.854 ms
Execution Time: 79.220 ms
```
One big GiST holds all 976k points; the kind filter is applied after the index probe.

## Summary (warm execution time)

| Case | ms |
| --- | ---: |
| A. partitioned, kind filter | 16.6 |
| B. partitioned, no kind filter | 36.0 |
| C. non-partitioned copy, kind filter | 79.2 |
