-- U8 operator report: top operators per borough with kita capacity.
-- CTE aggregates features per (district, operator); rank() OVER PARTITION BY
-- district picks the top N. Ties share a rank, so a borough can list more than N.
-- Params: :top_n, :kind (NULL = all kinds)
WITH per_operator AS (
  SELECT
    p.district_id,
    o.id AS operator_id,
    o.name AS operator_name,
    o.operator_type,
    COUNT(*)::int AS feature_count,
    COUNT(*) FILTER (WHERE p.kind_code = 'kita')::int AS kita_count,
    COALESCE(SUM(kd.capacity), 0)::int AS kita_capacity
  FROM amenity_points p
  JOIN operator o ON o.id = p.operator_id
  LEFT JOIN kita_detail kd ON kd.point_id = p.id AND kd.kind_code = p.kind_code
  WHERE p.district_id IS NOT NULL
    AND (CAST(:kind AS text) IS NULL OR p.kind_code = CAST(:kind AS text))
  GROUP BY p.district_id, o.id, o.name, o.operator_type
),
ranked AS (
  SELECT *, rank() OVER (PARTITION BY district_id ORDER BY feature_count DESC, operator_name) AS rnk
  FROM per_operator
)
SELECT
  r.district_id,
  d.name AS district_name,
  r.rnk::int AS rank,
  r.operator_id,
  r.operator_name,
  r.operator_type,
  r.feature_count,
  r.kita_count,
  r.kita_capacity
FROM ranked r
JOIN districts d ON d.id = r.district_id
WHERE r.rnk <= CAST(:top_n AS integer)
ORDER BY d.name, r.rnk, r.operator_name;
