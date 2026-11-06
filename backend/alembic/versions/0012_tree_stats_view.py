"""Materialized view borough_tree_stats: the tree report computed once per import.

Phase 7 measured the live query at ~11 s (two ordered-set aggregates over 962k
rows, sorts spilling to disk). The view is refreshed at the end of every import,
like borough_amenity_stats; the API reads it in milliseconds.
"""

from alembic import op

revision = "0012_tree_stats_view"
down_revision = "0011_drop_legacy"
branch_labels = None
depends_on = None

VIEW = """
CREATE MATERIALIZED VIEW borough_tree_stats AS
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
GROUP BY d.id, d.name;

CREATE UNIQUE INDEX ux_borough_tree_stats ON borough_tree_stats (district_id);
"""

GRANT = """
DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'berlin_ro') THEN
    GRANT SELECT ON borough_tree_stats TO berlin_ro;
  END IF;
EXCEPTION WHEN insufficient_privilege THEN
  RAISE NOTICE 'skipping berlin_ro grant';
END
$$;
"""


def upgrade() -> None:
    conn = op.get_bind()
    conn.exec_driver_sql(VIEW)
    conn.exec_driver_sql(GRANT)


def downgrade() -> None:
    op.get_bind().exec_driver_sql("DROP MATERIALIZED VIEW borough_tree_stats")
