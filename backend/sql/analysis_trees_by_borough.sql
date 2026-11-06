-- Tree statistics per borough: species diversity, median planting year, top genus.
-- Reads the materialized view borough_tree_stats (migration 0012), refreshed at the end of
-- every import. The live query took ~11 s (docs/schema-v2/explain/07-trees-by-borough.md);
-- the view is defined as:
--
--   SELECT d.id, d.name, COUNT(*) AS tree_count,
--          COUNT(DISTINCT td.species_id) AS species_count,
--          percentile_cont(0.5) WITHIN GROUP (ORDER BY td.planting_year) AS median_planting_year,
--          mode() WITHIN GROUP (ORDER BY sp.genus) AS top_genus,
--          percentile_cont(0.5) WITHIN GROUP (ORDER BY td.height_m) AS median_height_m
--   FROM tree_detail td
--   JOIN amenity_points p ON p.id = td.point_id AND p.kind_code = td.kind_code
--   JOIN districts d ON d.id = p.district_id
--   LEFT JOIN tree_species sp ON sp.id = td.species_id
--   GROUP BY d.id, d.name;
SELECT district_id, district_name, tree_count, species_count,
       median_planting_year, top_genus, median_height_m
FROM borough_tree_stats
ORDER BY district_name;
