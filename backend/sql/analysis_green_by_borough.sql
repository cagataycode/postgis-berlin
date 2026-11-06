-- Mapped public green by borough (parks/green polygons only — geometry area).
-- district_id was set at import (point-on-surface of each polygon).
SELECT
  d.id AS district_id,
  d.name AS district_name,
  COUNT(g.id)::int AS feature_count,
  COALESCE(SUM(ST_Area(g.geom)), 0)::float AS area_m2,
  CASE
    WHEN ST_Area(d.geom) > 0
    THEN (COALESCE(SUM(ST_Area(g.geom)), 0) / ST_Area(d.geom) * 100.0)::float
    ELSE 0
  END AS pct_of_district_area
FROM districts d
LEFT JOIN amenity_areas g ON g.district_id = d.id AND g.kind_code = 'green_space'
GROUP BY d.id, d.name, d.geom
ORDER BY d.name;
