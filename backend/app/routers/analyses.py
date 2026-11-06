from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db import get_db
from app.sql_loader import load_sql

router = APIRouter(prefix="/analyses", tags=["analyses"])


@router.get("/nearest-amenities")
def nearest_amenities(
    lon: float = Query(..., ge=-180, le=180),
    lat: float = Query(..., ge=-90, le=90),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    row = db.execute(
        text(load_sql("analysis_nearest_amenities.sql")),
        {"lon": lon, "lat": lat},
    ).scalar()
    payload = row if isinstance(row, dict) else {}
    return {
        "id": "nearest-amenities",
        "title": "Nearest amenities",
        "inputs": [
            "trees",
            "park_trees",
            "bike_parking",
            "ev_chargers",
            "drinking_fountains",
            "bathing_waters",
            "toilets",
            "playgrounds",
            "sports_facilities",
            "kitas",
            "hospitals",
            "cemeteries",
            "park_and_ride",
            "green_spaces",
        ],
        "operation": (
            "Transform WGS84 point to EPSG:25833; KNN (<->) nearest feature per amenity layer; "
            "return planar distance in metres"
        ),
        "units": {"distance": "metres"},
        "crs": "EPSG:25833",
        "caveat": (
            "Mapped open-data inventories only. Distances are Euclidean in EPSG:25833, "
            "not walking or routing distance."
        ),
        "sql_ref": "analysis_nearest_amenities.sql",
        **payload,
    }


@router.get("/operators")
def operators_by_borough(
    top_n: int = Query(3, ge=1, le=20),
    kind: str | None = Query(None, description="restrict to one kind_code"),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """U8: top operators per borough (rank() OVER PARTITION BY district)."""
    rows = (
        db.execute(text(load_sql("analysis_operators.sql")), {"top_n": top_n, "kind": kind})
        .mappings()
        .all()
    )
    return {
        "id": "operators",
        "title": "Top operators by borough",
        "inputs": ["amenity_points", "operator", "kita_detail", "districts"],
        "operation": (
            "COUNT features per (district, operator); rank() OVER (PARTITION BY district "
            "ORDER BY count DESC); SUM kita capacity from kita_detail"
        ),
        "units": {"feature_count": "features", "kita_capacity": "places"},
        "crs": "EPSG:25833",
        "top_n": top_n,
        "kind": kind,
        "caveat": (
            "Only features with a published operator are counted (Kitas, EV chargers, "
            "some toilets). Tied operators share a rank."
        ),
        "sql_ref": "analysis_operators.sql",
        "results": [dict(r) for r in rows],
    }


@router.get("/trees-by-borough")
def trees_by_borough(db: Session = Depends(get_db)) -> dict[str, Any]:
    rows = db.execute(text(load_sql("analysis_trees_by_borough.sql"))).mappings().all()
    return {
        "id": "trees-by-borough",
        "title": "Tree statistics by borough",
        "inputs": ["tree_detail", "tree_species", "amenity_points", "districts"],
        "operation": (
            "COUNT(DISTINCT species_id), percentile_cont(0.5) of planting_year and height, "
            "mode() WITHIN GROUP genus per district"
        ),
        "units": {"tree_count": "trees", "median_planting_year": "year", "median_height_m": "m"},
        "crs": "EPSG:25833",
        "caveat": (
            "Street and park trees in the open inventories; planting year and height are "
            "missing for many trees and are left out of the medians."
        ),
        "sql_ref": "analysis_trees_by_borough.sql",
        "results": [dict(r) for r in rows],
    }


@router.get("/amenity-density-by-borough")
def amenity_density_by_borough(db: Session = Depends(get_db)) -> dict[str, Any]:
    rows = db.execute(text(load_sql("analysis_amenity_density_by_borough.sql"))).mappings().all()
    return {
        "id": "amenity-density-by-borough",
        "title": "Amenity counts by borough",
        "inputs": [
            "borough_amenity_stats",
            "districts",
            "trees",
            "park_trees",
            "bike_parking",
            "ev_chargers",
            "drinking_fountains",
            "bathing_waters",
            "toilets",
            "playgrounds",
            "sports_facilities",
            "kitas",
            "hospitals",
            "cemeteries",
            "park_and_ride",
        ],
        "operation": "Pivot borough_amenity_stats (COUNT per district and kind); ROLLUP adds a city total",
        "units": {"count": "features"},
        "crs": "EPSG:25833",
        "caveat": (
            "Counts come from a materialized view refreshed at the end of each import; "
            "district assignment is point-in-polygon at import — not a service-need ranking."
        ),
        "sql_ref": "analysis_amenity_density_by_borough.sql",
        "results": [dict(r) for r in rows],
    }


@router.get("/green-by-borough")
def green_by_borough(db: Session = Depends(get_db)) -> dict[str, Any]:
    rows = db.execute(text(load_sql("analysis_green_by_borough.sql"))).mappings().all()
    return {
        "id": "green-by-borough",
        "title": "Mapped public green by borough",
        "inputs": ["districts", "green_spaces"],
        "operation": "COUNT features and SUM ST_Area(geom) per district_id (EPSG:25833)",
        "units": {"count": "features", "area": "m²", "share": "% of district land area"},
        "crs": "EPSG:25833",
        "caveat": "Mapped public green inventory coverage — not planning need or private greenery.",
        "sql_ref": "analysis_green_by_borough.sql",
        "results": [dict(r) for r in rows],
    }


@router.get("/school-green-proximity")
def school_green_proximity(
    threshold_m: float = Query(500, ge=0),
    district_id: int | None = None,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    rows = (
        db.execute(
            text(load_sql("analysis_school_green_proximity.sql")),
            {"threshold_m": threshold_m, "district_id": district_id},
        )
        .mappings()
        .all()
    )
    return {
        "id": "school-green-proximity",
        "title": "School-to-green proximity",
        "inputs": ["schools", "green_spaces"],
        "operation": (
            "Shortest planar ST_Distance from each school point to nearest green polygon edge; "
            "summarize median, p90, and count beyond threshold per borough"
        ),
        "units": {"distance": "metres"},
        "crs": "EPSG:25833",
        "threshold_m": threshold_m,
        "caveat": "Euclidean proximity to mapped green inventory only — not walking distance.",
        "sql_ref": "analysis_school_green_proximity.sql",
        "results": [dict(r) for r in rows],
    }
