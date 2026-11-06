-- School-to-green proximity (Euclidean edge distance in EPSG:25833).
-- Uses KNN (<->) for nearest green polygon per school.
-- Params: :threshold_m, :district_id
WITH distances AS (
  SELECT
    s.id AS school_id,
    s.name AS school_name,
    s.district_id,
    d.name AS district_name,
    nearest.dist_m
  FROM amenity_points s
  JOIN districts d ON d.id = s.district_id
  CROSS JOIN LATERAL (
    SELECT ST_Distance(s.geom, g.geom) AS dist_m
    FROM amenity_areas g
    WHERE g.kind_code = 'green_space'
    ORDER BY s.geom <-> g.geom
    LIMIT 1
  ) nearest
  WHERE s.kind_code = 'school'
    AND (CAST(:district_id AS integer) IS NULL OR s.district_id = CAST(:district_id AS integer))
)
SELECT
  district_id,
  district_name,
  COUNT(*)::int AS school_count,
  percentile_cont(0.5) WITHIN GROUP (ORDER BY dist_m)::float AS median_m,
  percentile_cont(0.9) WITHIN GROUP (ORDER BY dist_m)::float AS p90_m,
  COUNT(*) FILTER (WHERE dist_m > CAST(:threshold_m AS double precision))::int AS beyond_threshold_count
FROM distances
GROUP BY district_id, district_name
ORDER BY district_name;
