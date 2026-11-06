# 7. `/analyses/trees-by-borough` (the slow report)

The query behind the endpoint, as shipped in phase 4.

## A. live query (phase 4 version)

```sql
SELECT d.id AS district_id, d.name AS district_name, COUNT(*)::int AS tree_count, COUNT(DISTINCT td.species_id)::int AS species_count, percentile_cont(0.5) WITHIN GROUP (ORDER BY td.planting_year)::float AS median_planting_year, mode() WITHIN GROUP (ORDER BY sp.genus) AS top_genus, percentile_cont(0.5) WITHIN GROUP (ORDER BY td.height_m)::float AS median_height_m FROM tree_detail td JOIN amenity_points p ON p.id = td.point_id AND p.kind_code = td.kind_code JOIN districts d ON d.id = p.district_id LEFT JOIN tree_species sp ON sp.id = td.species_id GROUP BY d.id, d.name ORDER BY d.name
```

```text
Sort  (cost=210137.67..210137.70 rows=12 width=74) (actual time=10658.636..10696.108 rows=12 loops=1)
  Sort Key: d.name
  Sort Method: quicksort  Memory: 25kB
  Buffers: shared hit=4099 read=87558, temp read=16768 written=16913
  ->  GroupAggregate  (cost=145105.99..210137.46 rows=12 width=74) (actual time=5845.059..10695.290 rows=12 loops=1)
        Group Key: d.id
        Buffers: shared hit=4077 read=87558, temp read=16768 written=16913
        ->  Gather Merge  (cost=145105.99..200606.47 rows=476536 width=36) (actual time=5197.852..6768.014 rows=961630 loops=1)
              Workers Planned: 2
              Workers Launched: 2
              Buffers: shared hit=4077 read=87558, temp read=16613 written=16757
              ->  Sort  (cost=144105.97..144602.36 rows=198557 width=36) (actual time=4949.614..5362.029 rows=320543 loops=3)
                    Sort Key: d.id, td.species_id
                    Sort Method: external merge  Disk: 14656kB
                    Buffers: shared hit=4077 read=87558, temp read=16613 written=16757
                    Worker 0:  Sort Method: external merge  Disk: 14432kB
                    Worker 1:  Sort Method: external merge  Disk: 14384kB
                    ->  Hash Left Join  (cost=21228.38..121201.75 rows=198557 width=36) (actual time=2337.712..3979.902 rows=320543 loops=3)
                          Hash Cond: (td.species_id = sp.id)
                          Buffers: shared hit=4001 read=87558, temp read=11179 written=11304
                          ->  Hash Join  (cost=21197.77..120647.55 rows=198557 width=29) (actual time=2334.898..3539.136 rows=320543 loops=3)
                                Hash Cond: (p.district_id = d.id)
                                Buffers: shared hit=3971 read=87558, temp read=11179 written=11304
                                ->  Parallel Hash Join  (cost=21196.50..119940.46 rows=198762 width=15) (actual time=2119.224..2882.226 rows=320848 loops=3)
                                      Hash Cond: ((p.id = td.point_id) AND ((p.kind_code)::text = (td.kind_code)::text))
                                      Buffers: shared hit=3906 read=87558, temp read=11179 written=11304
                                      ->  Parallel Append  (cost=0.00..89101.40 rows=406581 width=23) (actual time=0.895..631.366 rows=325255 loops=3)
                                            Buffers: shared hit=3464 read=79516
                                            ->  Parallel Seq Scan on amenity_points_park_tree p_1  (cost=0.00..44681.18 rows=219918 width=22) (actual time=0.666..233.618 rows=175927 loops=3)
                                                  Buffers: shared hit=416 read=42066
                                            ->  Parallel Seq Scan on amenity_points_street_tree p_2  (cost=0.00..41299.55 rows=181155 width=24) (actual time=0.535..327.184 rows=217382 loops=2)
                                                  Buffers: shared hit=2038 read=37450
                                            ->  Parallel Seq Scan on amenity_points_other p_3  (cost=0.00..1087.76 rows=7776 width=22) (actual time=0.546..16.465 rows=13220 loops=1)
                                                  Buffers: shared hit=1010
                                      ->  Parallel Hash  (cost=12438.60..12438.60 rows=401060 width=29) (actual time=939.743..939.774 rows=320848 loops=3)
                                            Buckets: 131072  Batches: 16  Memory Usage: 5248kB
                                            Buffers: shared hit=386 read=8042, temp written=5984
                                            ->  Parallel Seq Scan on tree_detail td  (cost=0.00..12438.60 rows=401060 width=29) (actual time=0.859..319.873 rows=320848 loops=3)
                                                  Buffers: shared hit=386 read=8042
                                ->  Hash  (cost=1.12..1.12 rows=12 width=18) (actual time=214.580..214.581 rows=12 loops=3)
                                      Buckets: 1024  Batches: 1  Memory Usage: 9kB
                                      Buffers: shared hit=3
                                      ->  Seq Scan on districts d  (cost=0.00..1.12 rows=12 width=18) (actual time=213.864..213.953 rows=12 loops=3)
                                            Buffers: shared hit=3
                          ->  Hash  (cost=19.16..19.16 rows=916 width=11) (actual time=2.359..2.360 rows=916 loops=3)
                                Buckets: 1024  Batches: 1  Memory Usage: 49kB
                                Buffers: shared hit=30
                                ->  Seq Scan on tree_species sp  (cost=0.00..19.16 rows=916 width=11) (actual time=0.342..1.311 rows=916 loops=3)
                                      Buffers: shared hit=30
Planning:
  Buffers: shared hit=32
Planning Time: 6.846 ms
JIT:
  Functions: 101
  Options: Inlining false, Optimization false, Expressions true, Deforming true
  Timing: Generation 51.952 ms, Inlining 0.000 ms, Optimization 44.772 ms, Emission 598.187 ms, Total 694.912 ms
Execution Time: 10714.268 ms
```
Two sorts spill to disk (work_mem 4 MB) and ~88k pages are read: the cost is the ordered-set aggregates over 962k rows, not a missing index.

## B. read from materialized view borough_tree_stats

```sql
SELECT * FROM borough_tree_stats ORDER BY district_name
```

```text
Sort  (cost=1.34..1.37 rows=12 width=48) (actual time=0.066..0.073 rows=12 loops=1)
  Sort Key: district_name
  Sort Method: quicksort  Memory: 25kB
  Buffers: shared hit=1
  ->  Seq Scan on borough_tree_stats  (cost=0.00..1.12 rows=12 width=48) (actual time=0.014..0.022 rows=12 loops=1)
        Buffers: shared hit=1
Planning Time: 0.151 ms
Execution Time: 0.119 ms
```
Refreshed once per import (about the cost of A); the API reads it in well under a millisecond.

## Summary (warm execution time)

| Case | ms |
| --- | ---: |
| A. live query (phase 4 version) | 10714.3 |
| B. read from materialized view borough_tree_stats | 0.1 |
