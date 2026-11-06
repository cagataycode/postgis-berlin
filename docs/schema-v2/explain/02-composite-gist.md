# 2. Composite GiST (kind_code, geom) vs plain GiST on the `other` partition

`amenity_points_other` holds the 13 small kinds (13k rows). Does a `btree_gist` composite index beat a plain GiST on `geom` plus the kind filter?

## kita, plain GiST

```sql
SELECT p.id FROM perf.other_plain p WHERE p.kind_code = 'kita' AND p.geom && ST_Transform(ST_MakeEnvelope(13.38, 52.50, 13.42, 52.53, 4326), 25833)
```

```text
Bitmap Heap Scan on other_plain p  (cost=16.11..894.78 rows=115 width=8) (actual time=1.473..1.621 rows=78 loops=1)
  Recheck Cond: (geom && '0103000020E96400000100000005000000ECC44BD544CE1741FC47C56087315641DCAB4A5B70CF174190144C89C934564198C11928D5F917417271B77FBA345641AC84FC07B1F81741DFC81C5678315641ECC44BD544CE1741FC47C56087315641'::geometry)
  Filter: ((kind_code)::text = 'kita'::text)
  Rows Removed by Filter: 446
  Heap Blocks: exact=198
  Buffers: shared hit=206
  ->  Bitmap Index Scan on ix_plain  (cost=0.00..16.08 rows=524 width=0) (actual time=0.635..0.635 rows=524 loops=1)
        Index Cond: (geom && '0103000020E96400000100000005000000ECC44BD544CE1741FC47C56087315641DCAB4A5B70CF174190144C89C934564198C11928D5F917417271B77FBA345641AC84FC07B1F81741DFC81C5678315641ECC44BD544CE1741FC47C56087315641'::geometry)
        Buffers: shared hit=8
Planning Time: 0.722 ms
Execution Time: 1.745 ms
```

## kita, composite GiST

```sql
SELECT p.id FROM perf.other_comp p WHERE p.kind_code = 'kita' AND p.geom && ST_Transform(ST_MakeEnvelope(13.38, 52.50, 13.42, 52.53, 4326), 25833)
```

```text
Bitmap Heap Scan on other_comp p  (cost=9.45..340.49 rows=115 width=8) (actual time=1.883..1.984 rows=78 loops=1)
  Recheck Cond: (((kind_code)::text = 'kita'::text) AND (geom && '0103000020E96400000100000005000000ECC44BD544CE1741FC47C56087315641DCAB4A5B70CF174190144C89C934564198C11928D5F917417271B77FBA345641AC84FC07B1F81741DFC81C5678315641ECC44BD544CE1741FC47C56087315641'::geometry))
  Heap Blocks: exact=21
  Buffers: shared hit=38
  ->  Bitmap Index Scan on ix_comp  (cost=0.00..9.43 rows=115 width=0) (actual time=1.865..1.866 rows=78 loops=1)
        Index Cond: (((kind_code)::text = 'kita'::text) AND (geom && '0103000020E96400000100000005000000ECC44BD544CE1741FC47C56087315641DCAB4A5B70CF174190144C89C934564198C11928D5F917417271B77FBA345641AC84FC07B1F81741DFC81C5678315641ECC44BD544CE1741FC47C56087315641'::geometry))
        Buffers: shared hit=17
Planning Time: 0.496 ms
Execution Time: 2.084 ms
```

## ev_charger, plain GiST

```sql
SELECT p.id FROM perf.other_plain p WHERE p.kind_code = 'ev_charger' AND p.geom && ST_Transform(ST_MakeEnvelope(13.38, 52.50, 13.42, 52.53, 4326), 25833)
```

```text
Bitmap Heap Scan on other_plain p  (cost=16.13..894.80 rows=197 width=8) (actual time=0.865..1.542 rows=282 loops=1)
  Recheck Cond: (geom && '0103000020E96400000100000005000000ECC44BD544CE1741FC47C56087315641DCAB4A5B70CF174190144C89C934564198C11928D5F917417271B77FBA345641AC84FC07B1F81741DFC81C5678315641ECC44BD544CE1741FC47C56087315641'::geometry)
  Filter: ((kind_code)::text = 'ev_charger'::text)
  Rows Removed by Filter: 242
  Heap Blocks: exact=198
  Buffers: shared hit=206
  ->  Bitmap Index Scan on ix_plain  (cost=0.00..16.08 rows=524 width=0) (actual time=0.586..0.587 rows=524 loops=1)
        Index Cond: (geom && '0103000020E96400000100000005000000ECC44BD544CE1741FC47C56087315641DCAB4A5B70CF174190144C89C934564198C11928D5F917417271B77FBA345641AC84FC07B1F81741DFC81C5678315641ECC44BD544CE1741FC47C56087315641'::geometry)
        Buffers: shared hit=8
Planning Time: 0.480 ms
Execution Time: 1.692 ms
```

## ev_charger, composite GiST

```sql
SELECT p.id FROM perf.other_comp p WHERE p.kind_code = 'ev_charger' AND p.geom && ST_Transform(ST_MakeEnvelope(13.38, 52.50, 13.42, 52.53, 4326), 25833)
```

```text
Bitmap Heap Scan on other_comp p  (cost=10.29..506.85 rows=197 width=8) (actual time=1.997..2.358 rows=282 loops=1)
  Recheck Cond: (((kind_code)::text = 'ev_charger'::text) AND (geom && '0103000020E96400000100000005000000ECC44BD544CE1741FC47C56087315641DCAB4A5B70CF174190144C89C934564198C11928D5F917417271B77FBA345641AC84FC07B1F81741DFC81C5678315641ECC44BD544CE1741FC47C56087315641'::geometry))
  Heap Blocks: exact=77
  Buffers: shared hit=95
  ->  Bitmap Index Scan on ix_comp  (cost=0.00..10.25 rows=197 width=0) (actual time=1.963..1.963 rows=282 loops=1)
        Index Cond: (((kind_code)::text = 'ev_charger'::text) AND (geom && '0103000020E96400000100000005000000ECC44BD544CE1741FC47C56087315641DCAB4A5B70CF174190144C89C934564198C11928D5F917417271B77FBA345641AC84FC07B1F81741DFC81C5678315641ECC44BD544CE1741FC47C56087315641'::geometry))
        Buffers: shared hit=18
Planning Time: 0.505 ms
Execution Time: 2.511 ms
```

## hospital, plain GiST

```sql
SELECT p.id FROM perf.other_plain p WHERE p.kind_code = 'hospital' AND p.geom && ST_Transform(ST_MakeEnvelope(13.38, 52.50, 13.42, 52.53, 4326), 25833)
```

```text
Bitmap Heap Scan on other_plain p  (cost=16.08..894.75 rows=4 width=8) (actual time=1.420..1.430 rows=4 loops=1)
  Recheck Cond: (geom && '0103000020E96400000100000005000000ECC44BD544CE1741FC47C56087315641DCAB4A5B70CF174190144C89C934564198C11928D5F917417271B77FBA345641AC84FC07B1F81741DFC81C5678315641ECC44BD544CE1741FC47C56087315641'::geometry)
  Filter: ((kind_code)::text = 'hospital'::text)
  Rows Removed by Filter: 520
  Heap Blocks: exact=198
  Buffers: shared hit=206
  ->  Bitmap Index Scan on ix_plain  (cost=0.00..16.08 rows=524 width=0) (actual time=0.593..0.594 rows=524 loops=1)
        Index Cond: (geom && '0103000020E96400000100000005000000ECC44BD544CE1741FC47C56087315641DCAB4A5B70CF174190144C89C934564198C11928D5F917417271B77FBA345641AC84FC07B1F81741DFC81C5678315641ECC44BD544CE1741FC47C56087315641'::geometry)
        Buffers: shared hit=8
Planning Time: 0.477 ms
Execution Time: 1.509 ms
```

## hospital, composite GiST

```sql
SELECT p.id FROM perf.other_comp p WHERE p.kind_code = 'hospital' AND p.geom && ST_Transform(ST_MakeEnvelope(13.38, 52.50, 13.42, 52.53, 4326), 25833)
```

```text
Bitmap Heap Scan on other_comp p  (cost=4.32..19.63 rows=4 width=8) (actual time=1.013..1.024 rows=4 loops=1)
  Recheck Cond: (((kind_code)::text = 'hospital'::text) AND (geom && '0103000020E96400000100000005000000ECC44BD544CE1741FC47C56087315641DCAB4A5B70CF174190144C89C934564198C11928D5F917417271B77FBA345641AC84FC07B1F81741DFC81C5678315641ECC44BD544CE1741FC47C56087315641'::geometry))
  Heap Blocks: exact=3
  Buffers: shared hit=14
  ->  Bitmap Index Scan on ix_comp  (cost=0.00..4.32 rows=4 width=0) (actual time=1.002..1.002 rows=4 loops=1)
        Index Cond: (((kind_code)::text = 'hospital'::text) AND (geom && '0103000020E96400000100000005000000ECC44BD544CE1741FC47C56087315641DCAB4A5B70CF174190144C89C934564198C11928D5F917417271B77FBA345641AC84FC07B1F81741DFC81C5678315641ECC44BD544CE1741FC47C56087315641'::geometry))
        Buffers: shared hit=11
Planning Time: 0.486 ms
Execution Time: 1.106 ms
```

Index size: plain 536 kB, composite 1048 kB.

## Summary (warm execution time)

| Case | ms |
| --- | ---: |
| kita, plain GiST | 1.7 |
| kita, composite GiST | 2.1 |
| ev_charger, plain GiST | 1.7 |
| ev_charger, composite GiST | 2.5 |
| hospital, plain GiST | 1.5 |
| hospital, composite GiST | 1.1 |
