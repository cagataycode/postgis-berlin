-- Amenity counts per borough (mapped inventory density).
-- Reads the materialized view borough_amenity_stats (refreshed at the end of
-- every import) and pivots kinds into columns. ROLLUP adds a city total row.
-- Output column names are the layer slugs the frontend already uses.
SELECT
  d.id AS district_id,
  COALESCE(d.name, 'Berlin (total)') AS district_name,
  COALESCE(SUM(s.feature_count) FILTER (WHERE s.kind_code = 'street_tree'), 0)::int AS trees,
  COALESCE(SUM(s.feature_count) FILTER (WHERE s.kind_code = 'park_tree'), 0)::int AS park_trees,
  COALESCE(SUM(s.feature_count) FILTER (WHERE s.kind_code = 'bike_parking'), 0)::int AS bike_parking,
  COALESCE(SUM(s.feature_count) FILTER (WHERE s.kind_code = 'ev_charger'), 0)::int AS ev_chargers,
  COALESCE(SUM(s.feature_count) FILTER (WHERE s.kind_code = 'drinking_fountain'), 0)::int AS drinking_fountains,
  COALESCE(SUM(s.feature_count) FILTER (WHERE s.kind_code = 'bathing_water'), 0)::int AS bathing_waters,
  COALESCE(SUM(s.feature_count) FILTER (WHERE s.kind_code = 'toilet'), 0)::int AS toilets,
  COALESCE(SUM(s.feature_count) FILTER (WHERE s.kind_code = 'playground'), 0)::int AS playgrounds,
  COALESCE(SUM(s.feature_count) FILTER (WHERE s.kind_code = 'sports_facility'), 0)::int AS sports_facilities,
  COALESCE(SUM(s.feature_count) FILTER (WHERE s.kind_code = 'kita'), 0)::int AS kitas,
  COALESCE(SUM(s.feature_count) FILTER (WHERE s.kind_code = 'hospital'), 0)::int AS hospitals,
  COALESCE(SUM(s.feature_count) FILTER (WHERE s.kind_code = 'cemetery'), 0)::int AS cemeteries,
  COALESCE(SUM(s.feature_count) FILTER (WHERE s.kind_code = 'park_and_ride'), 0)::int AS park_and_ride
FROM districts d
LEFT JOIN borough_amenity_stats s ON s.district_id = d.id
GROUP BY ROLLUP ((d.id, d.name))
ORDER BY GROUPING(d.id), d.name;
