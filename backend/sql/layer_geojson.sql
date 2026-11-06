-- Bbox GeoJSON for the {slug} layer (rendered by app.layer_registry.render_layer_sql).
-- Params: :minx, :miny, :maxx, :maxy (WGS84 lon/lat — null bbox = all features){district_param}{tag_param}
-- Source attrs merge under curated keys when enabled (curated wins on collision).
SELECT jsonb_build_object(
  'type', 'FeatureCollection',
  'features', COALESCE(jsonb_agg(feature), '[]'::jsonb)
)
FROM (
  SELECT jsonb_build_object(
    'type', 'Feature',
    'id', {alias}.id,
    'geometry', ST_AsGeoJSON(ST_Transform({alias}.geom, 4326))::jsonb,
    'properties', {properties_expr}
  ) AS feature
  FROM {table} {alias}
  WHERE {where_clause}
  {limit_clause}
) q;
