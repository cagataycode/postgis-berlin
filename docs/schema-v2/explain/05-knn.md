# 5. Nearest neighbours: index-ordered scan

Five nearest street trees to a point in Mitte: `ORDER BY geom <-> point LIMIT 5` (GiST distance ordering) vs `ORDER BY ST_Distance(geom, point)` (no index, full sort).

## A. KNN operator <->

```sql
SELECT id, ST_Distance(geom, ST_Transform(ST_SetSRID(ST_MakePoint(13.405, 52.52), 4326), 25833)) AS d FROM amenity_points WHERE kind_code = 'street_tree' ORDER BY geom <-> ST_Transform(ST_SetSRID(ST_MakePoint(13.405, 52.52), 4326), 25833) LIMIT 5
```

```text
Limit  (cost=0.28..71.38 rows=5 width=24) (actual time=0.522..0.588 rows=5 loops=1)
  Buffers: shared hit=8
  ->  Result  (cost=0.28..6184035.10 rows=434869 width=24) (actual time=0.520..0.582 rows=5 loops=1)
        Buffers: shared hit=8
        ->  Index Scan using amenity_points_street_tree_geom_idx on amenity_points_street_tree amenity_points  (cost=0.28..472030.79 rows=434869 width=48) (actual time=0.515..0.565 rows=5 loops=1)
              Order By: (geom <-> '0101000020E96400004E4279098DE91741917B2E0AAA335641'::geometry)
              Filter: ((kind_code)::text = 'street_tree'::text)
              Buffers: shared hit=8
Planning Time: 0.674 ms
Execution Time: 0.670 ms
```

## B. ORDER BY ST_Distance

```sql
SELECT id, ST_Distance(geom, ST_Transform(ST_SetSRID(ST_MakePoint(13.405, 52.52), 4326), 25833)) AS d FROM amenity_points WHERE kind_code = 'street_tree' ORDER BY ST_Distance(geom, ST_Transform(ST_SetSRID(ST_MakePoint(13.405, 52.52), 4326), 25833)) LIMIT 5
```

```text
Limit  (cost=2311606.03..2311606.61 rows=5 width=16) (actual time=1969.209..2025.712 rows=5 loops=1)
  Buffers: shared hit=6180 read=33386
  ->  Gather Merge  (cost=2311606.03..2353887.81 rows=362390 width=16) (actual time=1759.724..1816.213 rows=5 loops=1)
        Workers Planned: 2
        Workers Launched: 2
        Buffers: shared hit=6180 read=33386
        ->  Sort  (cost=2310606.00..2311058.99 rows=181195 width=16) (actual time=1433.689..1433.724 rows=5 loops=3)
              Sort Key: (st_distance(amenity_points.geom, '0101000020E96400004E4279098DE91741917B2E0AAA335641'::geometry))
              Sort Method: top-N heapsort  Memory: 25kB
              Buffers: shared hit=6180 read=33386
              Worker 0:  Sort Method: top-N heapsort  Memory: 25kB
              Worker 1:  Sort Method: top-N heapsort  Memory: 25kB
              ->  Parallel Seq Scan on amenity_points_street_tree amenity_points  (cost=0.00..2306690.44 rows=181195 width=16) (actual time=658.329..1285.890 rows=144922 loops=3)
                    Filter: ((kind_code)::text = 'street_tree'::text)
                    Buffers: shared hit=6102 read=33386
Planning Time: 1.528 ms
JIT:
  Functions: 13
  Options: Inlining true, Optimization true, Expressions true, Deforming true
  Timing: Generation 22.466 ms, Inlining 727.953 ms, Optimization 769.854 ms, Emission 681.565 ms, Total 2201.837 ms
Execution Time: 2029.484 ms
```

## C. production query: one LATERAL KNN per kind

```sql
-- Nearest amenity per layer from a WGS84 click point (EPSG:25833 metres).
-- One LATERAL KNN (<->) per kind; the kind_code filter lets the planner prune
-- amenity_points to a single partition for the two tree kinds.
-- Params: 13.405, 52.52
WITH pt AS (
  SELECT ST_Transform(
    ST_SetSRID(ST_MakePoint(CAST(13.405 AS double precision), CAST(52.52 AS double precision)), 4326),
    25833
  ) AS geom
),
kinds(layer, kind_code, family) AS (
  VALUES
    ('trees', 'street_tree', 'point'),
    ('park_trees', 'park_tree', 'point'),
    ('bike_parking', 'bike_parking', 'point'),
    ('ev_chargers', 'ev_charger', 'point'),
    ('drinking_fountains', 'drinking_fountain', 'point'),
    ('bathing_waters', 'bathing_water', 'point'),
    ('toilets', 'toilet', 'point'),
    ('sports_facilities', 'sports_facility', 'point'),
    ('kitas', 'kita', 'point'),
    ('hospitals', 'hospital', 'point'),
    ('park_and_ride', 'park_and_ride', 'point'),
    ('playgrounds', 'playground', 'area'),
    ('cemeteries', 'cemetery', 'area'),
    ('green_spaces', 'green_space', 'area')
),
nearest AS (
  SELECT k.layer, n.id, n.name, n.distance_m
  FROM kinds k
  CROSS JOIN pt
  CROSS JOIN LATERAL (
    SELECT p.id, p.name, ST_Distance(p.geom, pt.geom) AS distance_m
    FROM amenity_points p
    WHERE p.kind_code = k.kind_code
    ORDER BY p.geom <-> pt.geom
    LIMIT 1
  ) n
  WHERE k.family = 'point'
  UNION ALL
  SELECT k.layer, n.id, n.name, n.distance_m
  FROM kinds k
  CROSS JOIN pt
  CROSS JOIN LATERAL (
    SELECT a.id::bigint AS id, a.name, ST_Distance(a.geom, pt.geom) AS distance_m
    FROM amenity_areas a
    WHERE a.kind_code = k.kind_code
    ORDER BY a.geom <-> pt.geom
    LIMIT 1
  ) n
  WHERE k.family = 'area'
)
SELECT jsonb_build_object(
  'lon', CAST(13.405 AS double precision),
  'lat', CAST(52.52 AS double precision),
  'crs', 'EPSG:25833',
  'nearest', COALESCE(
    (SELECT jsonb_agg(to_jsonb(n) ORDER BY n.distance_m) FROM nearest n),
    '[]'::jsonb
  )
);
```

```text
Result  (cost=32.74..32.75 rows=1 width=32) (actual time=119.632..119.654 rows=1 loops=1)
  Buffers: shared hit=10171
  CTE pt
    ->  Result  (cost=0.00..0.01 rows=1 width=32) (actual time=0.002..0.004 rows=1 loops=1)
  CTE kinds
    ->  Values Scan on "*VALUES*"  (cost=0.00..0.18 rows=14 width=96) (actual time=0.005..0.066 rows=14 loops=1)
  InitPlan 3 (returns $6)
    ->  Aggregate  (cost=32.54..32.55 rows=1 width=32) (actual time=119.534..119.551 rows=1 loops=1)
          Buffers: shared hit=10171
          ->  Sort  (cost=32.53..32.53 rows=2 width=40) (actual time=119.059..119.083 rows=14 loops=1)
                Sort Key: "*SELECT* 1".distance_m
                Sort Method: quicksort  Memory: 26kB
                Buffers: shared hit=10171
                ->  Append  (cost=0.74..32.52 rows=2 width=40) (actual time=0.651..119.007 rows=14 loops=1)
                      Buffers: shared hit=10171
                      ->  Subquery Scan on "*SELECT* 1"  (cost=0.74..15.30 rows=1 width=40) (actual time=0.649..116.547 rows=11 loops=1)
                            Buffers: shared hit=10134
                            ->  Nested Loop  (cost=0.74..15.29 rows=1 width=63) (actual time=0.642..116.507 rows=11 loops=1)
                                  Buffers: shared hit=10134
                                  ->  CTE Scan on pt  (cost=0.00..0.02 rows=1 width=32) (actual time=0.011..0.013 rows=1 loops=1)
                                  ->  Nested Loop  (cost=0.74..15.26 rows=1 width=63) (actual time=0.622..116.474 rows=11 loops=1)
                                        Buffers: shared hit=10134
                                        ->  CTE Scan on kinds k  (cost=0.00..0.32 rows=1 width=64) (actual time=0.014..0.122 rows=11 loops=1)
                                              Filter: (family = 'point'::text)
                                              Rows Removed by Filter: 3
                                        ->  Limit  (cost=0.74..14.93 rows=1 width=39) (actual time=10.573..10.574 rows=1 loops=11)
                                              Buffers: shared hit=10134
                                              ->  Result  (cost=0.74..13675979.57 rows=964177 width=39) (actual time=10.572..10.572 rows=1 loops=11)
                                                    Buffers: shared hit=10134
                                                    ->  Merge Append  (cost=0.74..1011514.67 rows=964177 width=63) (actual time=10.566..10.567 rows=1 loops=11)
                                                          Sort Key: ((p.geom <-> pt.geom))
                                                          Buffers: shared hit=10134
                                                          ->  Index Scan using amenity_points_park_tree_geom_idx on amenity_points_park_tree p_1  (cost=0.29..521603.26 rows=527986 width=63) (actual time=0.699..0.700 rows=1 loops=1)
                                                                Order By: (geom <-> pt.geom)
                                                                Filter: ((kind_code)::text = k.kind_code)
                                                                Buffers: shared hit=5
                                                          ->  Index Scan using amenity_points_street_tree_geom_idx on amenity_points_street_tree p_2  (cost=0.28..472030.79 rows=434869 width=63) (actual time=0.568..0.568 rows=1 loops=1)
                                                                Order By: (geom <-> pt.geom)
                                                                Filter: ((kind_code)::text = k.kind_code)
                                                                Buffers: shared hit=4
                                                          ->  Index Scan using amenity_points_other_geom_idx on amenity_points_other p_3  (cost=0.15..5418.80 rows=1322 width=63) (actual time=12.759..12.759 rows=1 loops=9)
                                                                Order By: (geom <-> pt.geom)
                                                                Filter: ((kind_code)::text = k.kind_code)
                                                                Rows Removed by Filter: 1196
                                                                Buffers: shared hit=10125
                      ->  Subquery Scan on "*SELECT* 2"  (cost=0.15..17.21 rows=1 width=40) (actual time=0.842..2.443 rows=3 loops=1)
                            Buffers: shared hit=37
                            ->  Nested Loop  (cost=0.15..17.20 rows=1 width=73) (actual time=0.819..2.283 rows=3 loops=1)
                                  Buffers: shared hit=34
                                  ->  CTE Scan on pt pt_1  (cost=0.00..0.02 rows=1 width=32) (actual time=0.005..0.006 rows=1 loops=1)
                                  ->  Nested Loop  (cost=0.15..17.17 rows=1 width=73) (actual time=0.803..2.263 rows=3 loops=1)
                                        Buffers: shared hit=34
                                        ->  CTE Scan on kinds k_1  (cost=0.00..0.32 rows=1 width=64) (actual time=0.016..0.024 rows=3 loops=1)
                                              Filter: (family = 'area'::text)
                                              Rows Removed by Filter: 11
                                        ->  Limit  (cost=0.15..16.83 rows=1 width=49) (actual time=0.741..0.742 rows=1 loops=3)
                                              Buffers: shared hit=34
                                              ->  Index Scan using ix_amenity_areas_geom on amenity_areas a  (cost=0.15..25994.29 rows=1558 width=49) (actual time=0.735..0.735 rows=1 loops=3)
                                                    Order By: (geom <-> pt_1.geom)
                                                    Filter: ((kind_code)::text = k_1.kind_code)
                                                    Rows Removed by Filter: 7
                                                    Buffers: shared hit=34
Planning Time: 2.935 ms
Execution Time: 120.114 ms
```

## Summary (warm execution time)

| Case | ms |
| --- | ---: |
| A. KNN operator <-> | 0.7 |
| B. ORDER BY ST_Distance | 2029.5 |
| C. production query: one LATERAL KNN per kind | 120.1 |
