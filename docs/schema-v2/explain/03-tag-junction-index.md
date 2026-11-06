# 3. Tag filter: junction index (tag_id, point_id)

Kitas carrying tag 16 (Situationsansatz, the most common). The primary key is (point_id, tag_id), so it cannot serve a lookup by tag_id; the extra index `(tag_id, point_id)` does.

## A. with index (tag_id, point_id)

```sql
SELECT p.id FROM amenity_points p WHERE p.kind_code = 'kita' AND p.id IN (SELECT point_id FROM amenity_point_tag WHERE tag_id = 16 AND kind_code = 'kita')
```

```text
Hash Join  (cost=185.55..1137.93 rows=288 width=8) (actual time=7.361..15.533 rows=2074 loops=1)
  Hash Cond: (p.id = amenity_point_tag.point_id)
  Buffers: shared hit=384
  ->  Index Only Scan using amenity_points_other_pkey on amenity_points_other p  (cost=0.29..945.04 rows=2905 width=8) (actual time=2.505..7.838 rows=2905 loops=1)
        Index Cond: (kind_code = 'kita'::text)
        Heap Fetches: 2905
        Buffers: shared hit=342
  ->  Hash  (cost=175.15..175.15 rows=809 width=8) (actual time=4.825..4.827 rows=2074 loops=1)
        Buckets: 4096 (originally 1024)  Batches: 1 (originally 1)  Memory Usage: 114kB
        Buffers: shared hit=42
        ->  Bitmap Heap Scan on amenity_point_tag  (cost=60.04..175.15 rows=809 width=8) (actual time=0.575..2.969 rows=2074 loops=1)
              Recheck Cond: (tag_id = 16)
              Filter: ((kind_code)::text = 'kita'::text)
              Heap Blocks: exact=33
              Buffers: shared hit=42
              ->  Bitmap Index Scan on ix_amenity_point_tag_tag  (cost=0.00..59.84 rows=2074 width=0) (actual time=0.537..0.537 rows=2078 loops=1)
                    Index Cond: (tag_id = 16)
                    Buffers: shared hit=9
Planning:
  Buffers: shared hit=7
Planning Time: 1.498 ms
Execution Time: 16.206 ms
```

## B. without it (PK only)

```sql
SELECT p.id FROM amenity_points p WHERE p.kind_code = 'kita' AND p.id IN (SELECT point_id FROM perf.apt_noidx WHERE tag_id = 16 AND kind_code = 'kita')
```

```text
Hash Join  (cost=289.00..1241.38 rows=288 width=8) (actual time=12.635..20.998 rows=2074 loops=1)
  Hash Cond: (p.id = apt_noidx.point_id)
  Buffers: shared hit=470
  ->  Index Only Scan using amenity_points_other_pkey on amenity_points_other p  (cost=0.29..945.04 rows=2905 width=8) (actual time=2.541..8.023 rows=2905 loops=1)
        Index Cond: (kind_code = 'kita'::text)
        Heap Fetches: 2905
        Buffers: shared hit=342
  ->  Hash  (cost=278.60..278.60 rows=809 width=8) (actual time=10.064..10.066 rows=2074 loops=1)
        Buckets: 4096 (originally 1024)  Batches: 1 (originally 1)  Memory Usage: 114kB
        Buffers: shared hit=128
        ->  Seq Scan on apt_noidx  (cost=0.00..278.60 rows=809 width=8) (actual time=4.258..8.192 rows=2074 loops=1)
              Filter: (((kind_code)::text = 'kita'::text) AND (tag_id = 16))
              Rows Removed by Filter: 7966
              Buffers: shared hit=128
Planning:
  Buffers: shared hit=6
Planning Time: 1.170 ms
Execution Time: 21.662 ms
```

## C. rare tag 14, with index

```sql
SELECT point_id FROM amenity_point_tag WHERE tag_id = 14
```

```text
Index Only Scan using ix_amenity_point_tag_tag on amenity_point_tag  (cost=0.29..26.49 rows=20 width=8) (actual time=0.033..0.082 rows=20 loops=1)
  Index Cond: (tag_id = 14)
  Heap Fetches: 20
  Buffers: shared hit=18
Planning Time: 0.180 ms
Execution Time: 0.133 ms
```

## D. rare tag 14, PK only

```sql
SELECT point_id FROM perf.apt_noidx WHERE tag_id = 14
```

```text
Seq Scan on apt_noidx  (cost=0.00..253.50 rows=20 width=8) (actual time=3.446..5.655 rows=20 loops=1)
  Filter: (tag_id = 14)
  Rows Removed by Filter: 10020
  Buffers: shared hit=128
Planning Time: 0.177 ms
Execution Time: 5.699 ms
```

## Summary (warm execution time)

| Case | ms |
| --- | ---: |
| A. with index (tag_id, point_id) | 16.2 |
| B. without it (PK only) | 21.7 |
| C. rare tag 14, with index | 0.1 |
| D. rare tag 14, PK only | 5.7 |
