/** Berlin SQL explore kit: schema glossary + ready-made patterns to run and analyze (schema v2). */

import type { LayerSlug } from "./layers";

export type SchemaColumn = {
  name: string;
  note?: string;
};

export type SchemaTable = {
  table: string;
  label: string;
  about: string;
  alias?: string;
  columns: SchemaColumn[];
};

const ID = { name: "id", note: "PK" };
const DISTRICT = { name: "district_id", note: "FK → districts.id (derived at import)" };
const ATTRS = { name: "attrs", note: "raw source properties (jsonb, provenance only)" };
const KIND = { name: "kind_code", note: "FK → amenity_kind.code, e.g. ev_charger" };

/** Glossary of tables and fields in this database (schema v2). */
export const SCHEMA_TABLES: SchemaTable[] = [
  {
    table: "districts",
    label: "Boroughs (Bezirke)",
    about: "12 Berlin borough polygons. Amenities link here via district_id.",
    alias: "d",
    columns: [
      ID,
      { name: "name", note: "e.g. Mitte" },
      { name: "official_id" },
      ATTRS,
      { name: "geom", note: "MULTIPOLYGON · EPSG:25833" },
    ],
  },
  {
    table: "neighborhoods",
    label: "Neighborhoods (Ortsteile)",
    about: "Finer place boundaries inside boroughs.",
    alias: "n",
    columns: [
      ID,
      { name: "name" },
      { name: "district_id", note: "FK → districts.id" },
      ATTRS,
      { name: "geom", note: "MULTIPOLYGON" },
    ],
  },
  {
    table: "amenity_kind",
    label: "Amenity kinds",
    about: "Lookup of the 15 kinds. geom_family says which table a kind lives in.",
    alias: "k",
    columns: [
      { name: "code", note: "PK, e.g. kita, street_tree" },
      { name: "label" },
      { name: "geom_family", note: "point | area; UNIQUE (code, geom_family)" },
    ],
  },
  {
    table: "amenity_points",
    label: "Amenity points",
    about:
      "All point amenities in one table, list-partitioned by kind_code (street_tree, park_tree, other). Always filter on kind_code.",
    alias: "p",
    columns: [
      ID,
      KIND,
      { name: "source_id", note: "natural key; UNIQUE (kind_code, source_id)" },
      { name: "name" },
      { name: "subtype", note: "kind-specific type, e.g. school type" },
      DISTRICT,
      { name: "operator_id", note: "FK → operator.id" },
      ATTRS,
      { name: "geom", note: "POINT · EPSG:25833" },
      { name: "updated_at", note: "set by trigger" },
    ],
  },
  {
    table: "amenity_areas",
    label: "Amenity areas",
    about: "Parks, playgrounds and cemeteries (polygons, validity checked by the database).",
    alias: "a",
    columns: [
      ID,
      KIND,
      { name: "source_id", note: "UNIQUE (kind_code, source_id)" },
      { name: "name" },
      { name: "subtype" },
      DISTRICT,
      ATTRS,
      { name: "geom", note: "MULTIPOLYGON · CHECK ST_IsValid" },
    ],
  },
  {
    table: "tag",
    label: "Tags",
    about: "Vocabulary: EV connector types, Kita approaches, toilet features.",
    alias: "t",
    columns: [
      ID,
      { name: "category_code", note: "FK → tag_category.code" },
      { name: "label" },
    ],
  },
  {
    table: "amenity_point_tag",
    label: "Point ⟷ tag (M:N)",
    about:
      "Junction between points and tags. Carries kind_code and category_code so composite foreign keys reject a Kita tag on a toilet.",
    alias: "apt",
    columns: [
      { name: "point_id", note: "FK (point_id, kind_code) → amenity_points" },
      { name: "kind_code" },
      { name: "tag_id", note: "FK (tag_id, category_code) → tag" },
      { name: "category_code", note: "FK (kind_code, category_code) → kind_tag_category" },
    ],
  },
  {
    table: "kind_tag_category",
    label: "Kind ⟷ tag category (M:N)",
    about: "Which tag categories each kind may carry (3 rows).",
    alias: "ktc",
    columns: [{ name: "kind_code" }, { name: "category_code" }],
  },
  {
    table: "tag_category",
    label: "Tag categories",
    about: "ev_connector, kita_approach, toilet_feature.",
    alias: "tc",
    columns: [{ name: "code", note: "PK" }, { name: "label" }],
  },
  {
    table: "operator",
    label: "Operators",
    about: "Who runs a facility. Kitas have an official_ref (t_nr); EV and toilet operators are matched by name.",
    alias: "o",
    columns: [
      ID,
      { name: "official_ref", note: "unique when present" },
      { name: "name" },
      { name: "operator_type" },
    ],
  },
  {
    table: "tree_species",
    label: "Tree species",
    about: "Botanical name → German name and genus (3NF extraction from the tree layers).",
    alias: "sp",
    columns: [ID, { name: "botanical_name", note: "UNIQUE" }, { name: "german_name" }, { name: "genus" }],
  },
  {
    table: "tree_detail",
    label: "Tree details (1:1)",
    about: "Typed facts for street and park trees. One row per tree.",
    alias: "td",
    columns: [
      { name: "point_id", note: "PK/FK with kind_code → amenity_points" },
      { name: "kind_code", note: "CHECK street_tree | park_tree" },
      { name: "species_id", note: "FK → tree_species.id" },
      { name: "planting_year", note: "smallint" },
      { name: "trunk_circumference_cm" },
      { name: "height_m", note: "NULL = unknown (source 0)" },
      { name: "crown_diameter_m" },
    ],
  },
  {
    table: "kita_detail",
    label: "Kita details (1:1)",
    about: "Capacity per Kita.",
    alias: "kd",
    columns: [{ name: "point_id" }, { name: "kind_code", note: "CHECK = kita" }, { name: "capacity", note: "CHECK ≥ 0" }],
  },
  {
    table: "ev_charger_detail",
    label: "EV charger details (1:1)",
    about: "Charge points, power and commissioning date per charging site.",
    alias: "ed",
    columns: [
      { name: "point_id" },
      { name: "kind_code", note: "CHECK = ev_charger" },
      { name: "charge_points" },
      { name: "max_power_kw" },
      { name: "commissioned_on", note: "date" },
      { name: "public_space", note: "boolean" },
    ],
  },
  {
    table: "borough_amenity_stats",
    label: "Borough stats (materialized view)",
    about: "Feature count per borough and kind; refreshed at the end of every import.",
    alias: "bs",
    columns: [{ name: "district_id" }, { name: "kind_code" }, { name: "feature_count" }],
  },
  {
    table: "import_run",
    label: "Import audit",
    about: "One row per layer import: status running | committed | failed, row counts, error text.",
    alias: "ir",
    columns: [
      ID,
      { name: "catalog_id", note: "FK → dataset_catalog.id" },
      { name: "status" },
      { name: "rows_inserted" },
      { name: "rows_updated" },
      { name: "rows_deleted" },
      { name: "error" },
    ],
  },
];

export type ReadyPattern = {
  id: string;
  title: string;
  blurb: string;
  /** Short note on what to look at when you Run / Explain. */
  analyze: string;
  sql: string;
  tables: string[];
  refFile?: string;
  refLayer?: LayerSlug;
};

const GEO = (alias: string) =>
  `ST_AsGeoJSON(ST_Transform(${alias}.geom, 4326))::json AS geometry`;

/** BBox predicate shared by the "in view" patterns. */
const BBOX = (alias: string) => `${alias}.geom && ST_Transform(
  ST_MakeEnvelope(:minx, :miny, :maxx, :maxy, 4326),
  25833
)`;

const CLICK_PT = `WITH pt AS (
  SELECT ST_Transform(
    ST_SetSRID(ST_MakePoint(CAST(:lon AS double precision), CAST(:lat AS double precision)), 4326),
    25833
  ) AS geom
)`;

/** Complete, ready-to-run queries. :binds fill from the map at Run. */
export const PATTERNS: ReadyPattern[] = [
  {
    id: "bikes-in-view",
    title: "Bike racks in view",
    blurb: "What the map is showing for bike parking right now.",
    analyze: "Pan/zoom and Run again — :minx… follow the viewport. Explain shows the GiST index on geom.",
    tables: ["amenity_points"],
    refLayer: "bike_parking",
    sql: `SELECT p.id, p.name, p.subtype, p.district_id,
  ${GEO("p")}
FROM amenity_points p
WHERE p.kind_code = 'bike_parking'
  AND ${BBOX("p")}
ORDER BY p.id
LIMIT 200;`,
  },
  {
    id: "fountains-in-view",
    title: "Fountains in view",
    blurb: "Drinking fountains inside the current map frame.",
    analyze: "Same bbox pattern — change the kind_code literal to explore another point kind.",
    tables: ["amenity_points"],
    refLayer: "drinking_fountains",
    sql: `SELECT p.id, p.name, p.district_id,
  ${GEO("p")}
FROM amenity_points p
WHERE p.kind_code = 'drinking_fountain'
  AND ${BBOX("p")}
ORDER BY p.id
LIMIT 200;`,
  },
  {
    id: "sports-in-view",
    title: "Sports facilities in view",
    blurb: "Sports / recreation sites inside the current map frame.",
    analyze: "Same bbox pattern; sports facilities live in the DEFAULT partition with the other small kinds.",
    tables: ["amenity_points"],
    refLayer: "sports_facilities",
    sql: `SELECT p.id, p.name, p.subtype, p.district_id,
  ${GEO("p")}
FROM amenity_points p
WHERE p.kind_code = 'sports_facility'
  AND ${BBOX("p")}
ORDER BY p.id
LIMIT 200;`,
  },
  {
    id: "trees-in-view",
    title: "Street trees in view",
    blurb: "Trees in the current viewport (keep the map zoomed in).",
    analyze:
      "Explain: only amenity_points_street_tree is scanned (partition pruning), then its GiST index. Drop the kind_code line and compare.",
    tables: ["amenity_points"],
    refLayer: "trees",
    sql: `SELECT p.id, p.name, p.district_id,
  ${GEO("p")}
FROM amenity_points p
WHERE p.kind_code = 'street_tree'
  AND ${BBOX("p")}
ORDER BY p.id
LIMIT 300;`,
  },
  {
    id: "park-trees-in-view",
    title: "Park trees in view",
    blurb: "Anlagenbäume in the current viewport (zoom in first).",
    analyze: "Same pattern on the park_tree partition — compare species mix in parks vs streets.",
    tables: ["amenity_points"],
    refLayer: "park_trees",
    sql: `SELECT p.id, p.name, p.district_id,
  ${GEO("p")}
FROM amenity_points p
WHERE p.kind_code = 'park_tree'
  AND ${BBOX("p")}
ORDER BY p.id
LIMIT 300;`,
  },
  {
    id: "tree-details-in-view",
    title: "Trees with species and size",
    blurb: "1:1 detail table and species lookup joined to street trees in view.",
    analyze:
      "Join key is (point_id, kind_code) — the same composite key as the foreign key. Heights of 0 in the source are NULL here.",
    tables: ["amenity_points", "tree_detail", "tree_species"],
    sql: `SELECT p.id, sp.botanical_name, sp.genus, td.planting_year, td.height_m,
  ${GEO("p")}
FROM amenity_points p
JOIN tree_detail td ON td.point_id = p.id AND td.kind_code = p.kind_code
LEFT JOIN tree_species sp ON sp.id = td.species_id
WHERE p.kind_code = 'street_tree'
  AND ${BBOX("p")}
ORDER BY p.id
LIMIT 200;`,
  },
  {
    id: "nearest-toilet",
    title: "Nearest toilets to click",
    blurb: "Five closest public toilets to your last map click.",
    analyze: "Click the map first. <-> is KNN distance; ST_Distance is metres in EPSG:25833.",
    tables: ["amenity_points"],
    refFile: "analysis_nearest_amenities.sql",
    sql: `${CLICK_PT}
SELECT p.id, p.name,
  ST_Distance(p.geom, pt.geom) AS distance_m,
  ${GEO("p")}
FROM amenity_points p, pt
WHERE p.kind_code = 'toilet'
ORDER BY p.geom <-> pt.geom
LIMIT 5;`,
  },
  {
    id: "nearest-park",
    title: "Nearest parks to click",
    blurb: "Five closest parks to your click.",
    analyze: "Same KNN pattern on polygons (amenity_areas) — distance is still planar metres.",
    tables: ["amenity_areas"],
    sql: `${CLICK_PT}
SELECT a.id, a.name, a.subtype,
  ST_Distance(a.geom, pt.geom) AS distance_m,
  ${GEO("a")}
FROM amenity_areas a, pt
WHERE a.kind_code = 'green_space'
ORDER BY a.geom <-> pt.geom
LIMIT 5;`,
  },
  {
    id: "nearest-hospital",
    title: "Nearest hospitals to click",
    blurb: "Five closest hospitals to your last map click.",
    analyze: "Click the map first. subtype is plan vs other.",
    tables: ["amenity_points"],
    refFile: "analysis_nearest_amenities.sql",
    sql: `${CLICK_PT}
SELECT p.id, p.name, p.subtype,
  ST_Distance(p.geom, pt.geom) AS distance_m,
  ${GEO("p")}
FROM amenity_points p, pt
WHERE p.kind_code = 'hospital'
ORDER BY p.geom <-> pt.geom
LIMIT 5;`,
  },
  {
    id: "near-click-function",
    title: "Chargers within 400 m (function)",
    blurb: "Calls the SQL function amenities_near() around your last click.",
    analyze:
      "The function takes lon, lat, radius, kind and an optional tag-id array. Add 1 to the array to require the first tag.",
    tables: ["amenity_points", "amenity_point_tag"],
    refFile: "amenities_near.sql",
    sql: `SELECT id, kind_code, name, ROUND(distance_m::numeric) AS metres
FROM amenities_near(:lon, :lat, 400, 'ev_charger', NULL)
LIMIT 20;`,
  },
  {
    id: "playgrounds-with-borough",
    title: "Playgrounds + borough name",
    blurb: "Join playgrounds to districts through district_id.",
    analyze: "a.district_id → d.id. Rows with NULL district_id disappear in a plain JOIN.",
    tables: ["amenity_areas", "districts"],
    sql: `SELECT a.id, a.name, d.name AS borough,
  ${GEO("a")}
FROM amenity_areas a
JOIN districts d ON a.district_id = d.id
WHERE a.kind_code = 'playground'
ORDER BY d.name, a.name
LIMIT 100;`,
  },
  {
    id: "schools-with-borough",
    title: "Schools + borough name",
    blurb: "Join schools to districts through district_id.",
    analyze: "Same FK join — p.district_id → d.id. Try filtering WHERE d.name = 'Mitte'.",
    tables: ["amenity_points", "districts"],
    sql: `SELECT p.id, p.name, p.subtype AS school_type, d.name AS borough,
  ${GEO("p")}
FROM amenity_points p
JOIN districts d ON p.district_id = d.id
WHERE p.kind_code = 'school'
ORDER BY d.name, p.name
LIMIT 100;`,
  },
  {
    id: "bathing-with-borough",
    title: "Bathing waters + borough",
    blurb: "Official bathing sites with their Bezirk name.",
    analyze: "Small kind — drop the LIMIT and still get every site. subtype holds the quality rating.",
    tables: ["amenity_points", "districts"],
    sql: `SELECT p.id, p.name, p.subtype AS quality_rating, d.name AS borough,
  ${GEO("p")}
FROM amenity_points p
JOIN districts d ON p.district_id = d.id
WHERE p.kind_code = 'bathing_water'
ORDER BY d.name, p.name;`,
  },
  {
    id: "chargers-by-borough",
    title: "EV chargers per borough",
    blurb: "How many chargers in each Bezirk.",
    analyze:
      "The kind filter sits in the ON clause so LEFT JOIN still keeps boroughs with zero chargers. COUNT(p.id) skips NULLs.",
    tables: ["districts", "amenity_points"],
    refFile: "analysis_amenity_density_by_borough.sql",
    sql: `SELECT d.id, d.name AS borough,
  COUNT(p.id)::int AS chargers
FROM districts d
LEFT JOIN amenity_points p ON p.district_id = d.id AND p.kind_code = 'ev_charger'
GROUP BY d.id, d.name
ORDER BY chargers DESC, d.name;`,
  },
  {
    id: "kitas-by-borough",
    title: "Daycare capacity per borough",
    blurb: "Kita count and total places by Bezirk, through the 1:1 detail table.",
    analyze: "kita_detail holds the typed capacity column; SUM ignores NULLs.",
    tables: ["districts", "amenity_points", "kita_detail"],
    refFile: "analysis_amenity_density_by_borough.sql",
    sql: `SELECT d.id, d.name AS borough,
  COUNT(p.id)::int AS kitas,
  COALESCE(SUM(kd.capacity), 0)::int AS places
FROM districts d
LEFT JOIN amenity_points p ON p.district_id = d.id AND p.kind_code = 'kita'
LEFT JOIN kita_detail kd ON kd.point_id = p.id AND kd.kind_code = p.kind_code
GROUP BY d.id, d.name
ORDER BY places DESC, d.name;`,
  },
  {
    id: "borough-stats-view",
    title: "Counts from the materialized view",
    blurb: "Pre-aggregated counts per borough and kind.",
    analyze: "Instant, because the work was done at import. Compare with counting amenity_points directly.",
    tables: ["borough_amenity_stats", "districts"],
    sql: `SELECT d.name AS borough, s.kind_code, s.feature_count
FROM borough_amenity_stats s
JOIN districts d ON d.id = s.district_id
ORDER BY d.name, s.feature_count DESC
LIMIT 100;`,
  },
  {
    id: "green-cover",
    title: "Park area share by borough",
    blurb: "Mapped park area as a share of each borough.",
    analyze: "ST_Area on polygons in EPSG:25833. Compare with the Compare tab green cover measure.",
    tables: ["districts", "amenity_areas"],
    refFile: "analysis_green_by_borough.sql",
    sql: `SELECT d.name AS borough,
  COUNT(a.id)::int AS park_features,
  ROUND(
    (COALESCE(SUM(ST_Area(a.geom)), 0) / NULLIF(ST_Area(d.geom), 0) * 100)::numeric,
    1
  ) AS park_pct
FROM districts d
LEFT JOIN amenity_areas a ON a.district_id = d.id AND a.kind_code = 'green_space'
GROUP BY d.id, d.name, d.geom
ORDER BY park_pct DESC NULLS LAST;`,
  },
  {
    id: "charger-connectors",
    title: "EV connector types (many-to-many)",
    blurb: "Chargers per connector tag, through the junction table.",
    analyze:
      "One charger can carry several connector tags, so the counts add up to more than the number of chargers. The junction is amenity_point_tag.",
    tables: ["amenity_point_tag", "tag", "amenity_points"],
    sql: `SELECT t.label AS connector, COUNT(*)::int AS chargers
FROM amenity_point_tag apt
JOIN tag t ON t.id = apt.tag_id AND t.category_code = apt.category_code
WHERE apt.kind_code = 'ev_charger'
GROUP BY t.label
ORDER BY chargers DESC;`,
  },
  {
    id: "kita-approach-filter",
    title: "Kitas with two approaches (AND)",
    blurb: "Kitas that carry both tag 13 and tag 16.",
    analyze:
      "GROUP BY … HAVING count(*) = 2 is the AND filter used by the ?tag= endpoint. List tag ids with: SELECT * FROM tag.",
    tables: ["amenity_point_tag", "amenity_points"],
    sql: `SELECT p.id, p.name,
  ${GEO("p")}
FROM amenity_points p
WHERE p.kind_code = 'kita'
  AND p.id IN (
    SELECT apt.point_id
    FROM amenity_point_tag apt
    WHERE apt.kind_code = 'kita' AND apt.tag_id IN (13, 16)
    GROUP BY apt.point_id
    HAVING COUNT(*) = 2
  )
LIMIT 100;`,
  },
  {
    id: "operator-ranking",
    title: "Top operator per borough",
    blurb: "Which operator runs the most mapped facilities in each Bezirk.",
    analyze:
      "rank() OVER (PARTITION BY district) numbers operators inside each borough; ties share a rank. Full version: Show query.",
    tables: ["amenity_points", "operator", "districts"],
    refFile: "analysis_operators.sql",
    sql: `WITH per_operator AS (
  SELECT p.district_id, o.name AS operator, COUNT(*)::int AS facilities
  FROM amenity_points p
  JOIN operator o ON o.id = p.operator_id
  WHERE p.district_id IS NOT NULL
  GROUP BY p.district_id, o.name
)
SELECT d.name AS borough, r.operator, r.facilities
FROM (
  SELECT *, rank() OVER (PARTITION BY district_id ORDER BY facilities DESC) AS rnk
  FROM per_operator
) r
JOIN districts d ON d.id = r.district_id
WHERE r.rnk = 1
ORDER BY d.name;`,
  },
  {
    id: "tree-species-top",
    title: "Most common street-tree species",
    blurb: "Species lookup joined to the tree detail table.",
    analyze: "Scans ~435k tree_detail rows for street trees; EXPLAIN shows the hash join to tree_species.",
    tables: ["tree_detail", "tree_species"],
    refFile: "analysis_trees_by_borough.sql",
    sql: `SELECT sp.german_name, sp.genus, COUNT(*)::int AS trees
FROM tree_detail td
JOIN tree_species sp ON sp.id = td.species_id
WHERE td.kind_code = 'street_tree'
GROUP BY sp.german_name, sp.genus
ORDER BY trees DESC
LIMIT 15;`,
  },
  {
    id: "partition-pruning",
    title: "Partition pruning (use Explain)",
    blurb: "Count of street trees — run with Explain.",
    analyze:
      "Plan lists only amenity_points_street_tree. Change the literal to 'kita' and the plan switches to amenity_points_other.",
    tables: ["amenity_points"],
    sql: `SELECT COUNT(*) AS street_trees
FROM amenity_points
WHERE kind_code = 'street_tree';`,
  },
  {
    id: "charger-details",
    title: "EV charger details",
    blurb: "Power and commissioning date from the 1:1 detail table.",
    analyze: "Typed columns instead of jsonb: max_power_kw is numeric and checked > 0.",
    tables: ["amenity_points", "ev_charger_detail", "operator"],
    sql: `SELECT p.id, p.name, o.name AS operator, ed.charge_points, ed.max_power_kw, ed.commissioned_on
FROM amenity_points p
JOIN ev_charger_detail ed ON ed.point_id = p.id AND ed.kind_code = p.kind_code
LEFT JOIN operator o ON o.id = p.operator_id
WHERE p.kind_code = 'ev_charger'
ORDER BY ed.max_power_kw DESC NULLS LAST
LIMIT 50;`,
  },
  {
    id: "charger-source-attrs",
    title: "EV charger source fields",
    blurb: "Full open-data properties for chargers (attrs jsonb).",
    analyze: "attrs keeps every source key for provenance (betreiber, ladeleistung_1, …). Typed facts live in the detail tables.",
    tables: ["amenity_points"],
    sql: `SELECT p.id, p.name, p.subtype, p.attrs
FROM amenity_points p
WHERE p.kind_code = 'ev_charger'
ORDER BY p.id
LIMIT 50;`,
  },
  {
    id: "import-history",
    title: "Import history",
    blurb: "The audit table written by every layer import.",
    analyze: "status failed rows keep the error text even though the import itself rolled back.",
    tables: ["import_run"],
    sql: `SELECT ir.id, c.slug AS layer, ir.status, ir.rows_inserted, ir.rows_updated, ir.rows_deleted,
  ir.finished_at - ir.started_at AS took
FROM import_run ir
JOIN dataset_catalog c ON c.id = ir.catalog_id
ORDER BY ir.id DESC
LIMIT 30;`,
  },
];
