-- Tree statistics per borough: species diversity, median planting year, top genus.
-- Window-free aggregates incl. ordered-set functions: percentile_cont and mode().
-- Params: none. Covers street and park trees (tree_detail).
SELECT
  d.id AS district_id,
  d.name AS district_name,
  COUNT(*)::int AS tree_count,
  COUNT(DISTINCT td.species_id)::int AS species_count,
  percentile_cont(0.5) WITHIN GROUP (ORDER BY td.planting_year)::float AS median_planting_year,
  mode() WITHIN GROUP (ORDER BY sp.genus) AS top_genus,
  percentile_cont(0.5) WITHIN GROUP (ORDER BY td.height_m)::float AS median_height_m
FROM tree_detail td
JOIN amenity_points p ON p.id = td.point_id AND p.kind_code = td.kind_code
JOIN districts d ON d.id = p.district_id
LEFT JOIN tree_species sp ON sp.id = td.species_id
GROUP BY d.id, d.name
ORDER BY d.name;
