"""Schema v2 analytics objects: amenities_near() and borough_amenity_stats.

amenities_near: SQL function used by the tag/radius search (U7).
borough_amenity_stats: materialized view of feature counts per (district, kind);
refreshed at the end of every import (scripts/import_v2.py).
The legacy-table drop (cutover) comes in a later migration.
"""

from alembic import op

revision = "0010_v2_analytics"
down_revision = "0009_schema_v2"
branch_labels = None
depends_on = None

AMENITIES_NEAR = """
CREATE FUNCTION amenities_near(
  lon double precision,
  lat double precision,
  radius_m double precision,
  kind text DEFAULT NULL,
  tag_ids integer[] DEFAULT NULL
) RETURNS TABLE (id bigint, kind_code varchar, name varchar, distance_m double precision)
LANGUAGE sql STABLE AS $$
  WITH c AS (
    SELECT ST_Transform(ST_SetSRID(ST_MakePoint(lon, lat), 4326), 25833) AS g
  )
  SELECT p.id, p.kind_code, p.name, ST_Distance(p.geom, c.g)
  FROM amenity_points p, c
  WHERE ST_DWithin(p.geom, c.g, radius_m)
    AND (kind IS NULL OR p.kind_code = kind)
    AND (
      tag_ids IS NULL OR cardinality(tag_ids) = 0
      OR p.id IN (
        SELECT t.point_id FROM amenity_point_tag t
        WHERE t.kind_code = p.kind_code AND t.tag_id = ANY (tag_ids)
        GROUP BY t.point_id
        HAVING count(*) = cardinality(tag_ids)
      )
    )
  ORDER BY p.geom <-> c.g
$$;
"""

STATS = """
CREATE MATERIALIZED VIEW borough_amenity_stats AS
SELECT district_id, kind_code, count(*)::int AS feature_count
FROM (
  SELECT district_id, kind_code FROM amenity_points
  UNION ALL
  SELECT district_id, kind_code FROM amenity_areas
) f
WHERE district_id IS NOT NULL
GROUP BY district_id, kind_code;

CREATE UNIQUE INDEX ux_borough_amenity_stats ON borough_amenity_stats (district_id, kind_code);
"""

GRANTS = """
DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'berlin_ro') THEN
    GRANT SELECT ON borough_amenity_stats TO berlin_ro;
    GRANT EXECUTE ON FUNCTION amenities_near(double precision, double precision, double precision, text, integer[]) TO berlin_ro;
  END IF;
EXCEPTION WHEN insufficient_privilege THEN
  RAISE NOTICE 'skipping berlin_ro grants';
END
$$;
"""


def upgrade() -> None:
    conn = op.get_bind()
    for block in (AMENITIES_NEAR, STATS, GRANTS):
        conn.exec_driver_sql(block)


def downgrade() -> None:
    conn = op.get_bind()
    conn.exec_driver_sql("DROP MATERIALIZED VIEW borough_amenity_stats")
    conn.exec_driver_sql(
        "DROP FUNCTION amenities_near(double precision, double precision, double precision, text, integer[])"
    )
