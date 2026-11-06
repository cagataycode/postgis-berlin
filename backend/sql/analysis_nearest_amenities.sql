-- Nearest amenity per layer from a WGS84 click point (EPSG:25833 metres).
-- One LATERAL KNN (<->) per kind; the kind_code filter lets the planner prune
-- amenity_points to a single partition for the two tree kinds.
-- Params: :lon, :lat
WITH pt AS (
  SELECT ST_Transform(
    ST_SetSRID(ST_MakePoint(CAST(:lon AS double precision), CAST(:lat AS double precision)), 4326),
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
  'lon', CAST(:lon AS double precision),
  'lat', CAST(:lat AS double precision),
  'crs', 'EPSG:25833',
  'nearest', COALESCE(
    (SELECT jsonb_agg(to_jsonb(n) ORDER BY n.distance_m) FROM nearest n),
    '[]'::jsonb
  )
);
