-- U7: amenities within a radius, optionally by kind and tags (AND).
-- Calls the database function amenities_near (migration 0010).
-- Params: :lon, :lat, :radius_m, :kind, :tag_ids (int[]), :limit
SELECT id, kind_code, name, distance_m
FROM amenities_near(
  CAST(:lon AS double precision),
  CAST(:lat AS double precision),
  CAST(:radius_m AS double precision),
  CAST(:kind AS text),
  CAST(:tag_ids AS integer[])
)
LIMIT CAST(:limit AS integer);
