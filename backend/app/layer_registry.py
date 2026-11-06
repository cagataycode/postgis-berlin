"""Layer registry: single source of truth for the map layers."""

from __future__ import annotations

from dataclasses import dataclass

from app.sql_loader import load_sql

LAYER_SQL_NAME = "layer_geojson.sql"

# Max lon/lat span for requires_filter layers (blocks citywide-ish dumps).
MAX_FILTERED_BBOX_SPAN_DEG = 0.2


@dataclass(frozen=True)
class LayerDef:
    slug: str  # snake_case layer slug
    path: str  # kebab-case URL path segment
    table: str  # districts / neighborhoods, else amenity_points / amenity_areas
    alias: str  # SQL alias in rendered queries
    extra_col: str | None  # extra per-layer properties column
    official_id: bool  # include official_id in properties
    has_district_id: bool  # include district_id property and district filter clause
    requires_filter: bool  # block unfiltered citywide dumps
    include_attrs: bool = True  # merge source attrs into map GeoJSON properties
    feature_limit: int | None = None  # hard cap for huge inventories
    kind_code: str | None = None  # amenity_kind.code (None for districts/neighborhoods)
    extra_src: str = "subtype"  # amenity column that feeds extra_col
    taggable: bool = False  # kind has a tag category (?tag= filter)


# Column order: slug, path, table, alias, extra_col, official_id, has_district_id, requires_filter.
# Amenity layers read amenity_points / amenity_areas filtered by kind_code (D1, D12).
P, A = "amenity_points", "amenity_areas"
LAYERS: tuple[LayerDef, ...] = (
    LayerDef("districts", "districts", "districts", "d", None, True, False, False),
    LayerDef("neighborhoods", "neighborhoods", "neighborhoods", "n", None, True, True, False),
    LayerDef("green_spaces", "green-spaces", A, "g", "space_type", False, True, False, kind_code="green_space"),
    LayerDef("cemeteries", "cemeteries", A, "c", "denomination", False, True, False, kind_code="cemetery"),
    LayerDef("schools", "schools", P, "s", "school_type", False, True, False, kind_code="school"),
    LayerDef("kitas", "kitas", P, "k", "facility_type", False, True, False, kind_code="kita", taggable=True),
    LayerDef("hospitals", "hospitals", P, "h", "hospital_type", False, True, False, kind_code="hospital"),
    LayerDef(
        "trees", "trees", P, "t", "species", False, True, True,
        include_attrs=False, feature_limit=8_000, kind_code="street_tree", extra_src="name",
    ),
    LayerDef(
        "park_trees", "park-trees", P, "pt", "species", False, True, True,
        include_attrs=False, feature_limit=8_000, kind_code="park_tree", extra_src="name",
    ),
    LayerDef("bike_parking", "bike-parking", P, "b", "facility_type", False, True, False, kind_code="bike_parking"),
    LayerDef("ev_chargers", "ev-chargers", P, "e", "charger_type", False, True, False, kind_code="ev_charger", taggable=True),
    LayerDef("drinking_fountains", "drinking-fountains", P, "f", "fountain_type", False, True, False, kind_code="drinking_fountain"),
    LayerDef("bathing_waters", "bathing-waters", P, "w", "quality_rating", False, True, False, kind_code="bathing_water"),
    LayerDef("toilets", "toilets", P, "o", "facility_type", False, True, False, kind_code="toilet", taggable=True),
    LayerDef("playgrounds", "playgrounds", A, "p", "space_type", False, True, False, kind_code="playground"),
    LayerDef("sports_facilities", "sports-facilities", P, "sf", "facility_type", False, True, False, kind_code="sports_facility"),
    LayerDef("park_and_ride", "park-and-ride", P, "pr", "facility_type", False, True, False, kind_code="park_and_ride"),
)

# Legacy layer slug -> kind_code, for the ORM feature lookup and analyses.
KIND_BY_SLUG: dict[str, str] = {l.slug: l.kind_code for l in LAYERS if l.kind_code}
AREA_KINDS: frozenset[str] = frozenset(l.kind_code for l in LAYERS if l.kind_code and l.table == A)

LAYER_BY_SLUG: dict[str, LayerDef] = {layer.slug: layer for layer in LAYERS}


def render_layer_sql(layer: LayerDef) -> str:
    """Render the shared layer_geojson.sql template for one layer."""
    a = layer.alias

    curated = [f"      'id', {a}.id,"]
    if layer.official_id:
        curated.append(f"      'official_id', {a}.official_id,")
    curated.append(f"      'name', {a}.name,")
    if layer.extra_col:
        curated.append(f"      '{layer.extra_col}', {a}.{layer.extra_src},")
    if layer.has_district_id:
        curated.append(f"      'district_id', {a}.district_id,")
    curated.append(f"      'layer', '{layer.slug}',")
    curated.append(f"      'catalog_id', {a}.catalog_id")
    curated_obj = "jsonb_build_object(\n" + "\n".join(curated) + "\n    )"

    if layer.include_attrs:
        properties_expr = f"COALESCE({a}.attrs, '{{}}'::jsonb) || {curated_obj}"
    else:
        properties_expr = curated_obj

    where = []
    if layer.kind_code:
        where.append(f"{a}.kind_code = '{layer.kind_code}'")
    if layer.has_district_id:
        where.append(
            f"(CAST(:district_id AS integer) IS NULL OR {a}.district_id = CAST(:district_id AS integer))"
        )
    if layer.requires_filter:
        # Citywide dump blocked: require bbox and/or district filter.
        where.append(
            "(\n"
            "      CAST(:district_id AS integer) IS NOT NULL\n"
            "      OR CAST(:minx AS double precision) IS NOT NULL\n"
            "    )"
        )
    where.append(
        "(\n"
        "      CAST(:minx AS double precision) IS NULL\n"
        f"      OR {a}.geom && ST_Transform(\n"
        "           ST_MakeEnvelope(\n"
        "             CAST(:minx AS double precision),\n"
        "             CAST(:miny AS double precision),\n"
        "             CAST(:maxx AS double precision),\n"
        "             CAST(:maxy AS double precision),\n"
        "             4326\n"
        "           ),\n"
        "           25833\n"
        "         )\n"
        "    )"
    )

    if layer.taggable:
        # U7: AND semantics -- a feature must carry every requested tag.
        where.append(
            "(\n"
            "      CAST(:n_tags AS integer) = 0\n"
            f"      OR {a}.id IN (\n"
            "        SELECT apt.point_id FROM amenity_point_tag apt\n"
            f"        WHERE apt.kind_code = '{layer.kind_code}'\n"
            "          AND apt.tag_id = ANY(CAST(:tag_ids AS integer[]))\n"
            "        GROUP BY apt.point_id\n"
            "        HAVING count(*) = CAST(:n_tags AS integer)\n"
            "      )\n"
            "    )"
        )

    limit_clause = f"LIMIT {int(layer.feature_limit)}" if layer.feature_limit else ""

    return load_sql(LAYER_SQL_NAME).format(
        slug=layer.slug,
        table=layer.table,
        alias=a,
        district_param=", :district_id" if layer.has_district_id else "",
        tag_param=", :tag_ids, :n_tags" if layer.taggable else "",
        properties_expr=properties_expr,
        where_clause="\n    AND ".join(where),
        limit_clause=limit_clause,
    )
