from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db import get_db
from app.layer_registry import (
    LAYER_BY_SLUG,
    LAYER_SQL_NAME,
    LAYERS,
    LayerDef,
    MAX_FILTERED_BBOX_SPAN_DEG,
    render_layer_sql,
)
from app.features import KIND_BY_SLUG, get_feature as get_orm_feature
from app.models import DatasetCatalog, District
from app.sql_loader import load_sql

router = APIRouter(tags=["layers"])


@router.get("/layers")
def list_layers(db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    rows = db.query(DatasetCatalog).order_by(DatasetCatalog.slug).all()
    return [
        {
            "slug": r.slug,
            "name": r.name,
            "description": r.description,
            "source_organization": r.source_organization,
            "source_url": r.source_url,
            "license_text": r.license_text,
            "source_vintage": r.source_vintage.isoformat() if r.source_vintage else None,
            "imported_at": r.imported_at.isoformat() if r.imported_at else None,
            "srid": r.srid,
            "geometry_type": r.geometry_type,
            "coverage_caveat": r.coverage_caveat,
        }
        for r in rows
    ]


@router.get("/layers/{slug}/sql")
def get_layer_sql(slug: str) -> dict[str, str]:
    layer = LAYER_BY_SLUG.get(slug)
    if layer is None:
        raise HTTPException(status_code=404, detail="Unknown layer")
    return {"name": LAYER_SQL_NAME, "slug": layer.slug, "sql": render_layer_sql(layer)}


@router.get("/districts/list")
def list_district_names(db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    rows = db.query(District).order_by(District.name).all()
    return [{"id": d.id, "official_id": d.official_id, "name": d.name} for d in rows]


def _reject_oversized_bbox(layer: LayerDef, bbox: str | None) -> None:
    """Heavy inventories must stay tightly scoped — citywide padded bboxes time out."""
    if not layer.requires_filter or not bbox:
        return
    parts = _parse_bbox(bbox)
    minx, miny, maxx, maxy = parts["minx"], parts["miny"], parts["maxx"], parts["maxy"]
    if None in (minx, miny, maxx, maxy):
        return
    span_x = float(maxx) - float(minx)
    span_y = float(maxy) - float(miny)
    if span_x > MAX_FILTERED_BBOX_SPAN_DEG or span_y > MAX_FILTERED_BBOX_SPAN_DEG:
        raise HTTPException(
            status_code=400,
            detail=(
                f"{layer.slug} bbox too large "
                f"(max {MAX_FILTERED_BBOX_SPAN_DEG}° span); zoom in further"
            ),
        )


def _make_layer_endpoint(layer: LayerDef) -> Callable[..., dict[str, Any]]:
    def get_layer_features(
        bbox: str | None = Query(None, description="minLon,minLat,maxLon,maxLat"),
        district_id: int | None = Query(None),
        db: Session = Depends(get_db),
    ) -> dict[str, Any]:
        if layer.requires_filter and bbox is None and district_id is None:
            raise HTTPException(
                status_code=400,
                detail=f"{layer.slug} requires bbox and/or district_id (citywide dump blocked)",
            )
        _reject_oversized_bbox(layer, bbox)
        return _geojson(db, layer, bbox=bbox, district_id=district_id)

    get_layer_features.__name__ = f"get_{layer.slug}"
    return get_layer_features


for _layer in LAYERS:
    router.add_api_route(
        f"/{_layer.path}",
        _make_layer_endpoint(_layer),
        methods=["GET"],
        name=f"get_{_layer.slug}",
    )


@router.get("/features/{layer}/{feature_id}")
def get_feature(layer: str, feature_id: int, db: Session = Depends(get_db)) -> dict[str, Any]:
    layer_def = LAYER_BY_SLUG.get(layer)
    if layer_def is None:
        raise HTTPException(status_code=404, detail="Unknown layer")
    kind = KIND_BY_SLUG.get(layer)
    if kind is not None:
        feature = get_orm_feature(db, kind, feature_id)
        if feature is None:
            raise HTTPException(status_code=404, detail="Feature not found")
        return feature
    # districts / neighborhoods keep the plain SQL path
    sql = load_sql("feature_by_id.sql").format(table=layer_def.table)
    row = db.execute(text(sql), {"id": feature_id}).scalar()
    if row is None:
        raise HTTPException(status_code=404, detail="Feature not found")
    return row if isinstance(row, dict) else json.loads(row)


def _parse_bbox(bbox: str | None) -> dict[str, float | None]:
    if not bbox:
        return {"minx": None, "miny": None, "maxx": None, "maxy": None}
    parts = [p.strip() for p in bbox.split(",")]
    if len(parts) != 4:
        raise HTTPException(status_code=400, detail="bbox must be minLon,minLat,maxLon,maxLat")
    try:
        minx, miny, maxx, maxy = (float(p) for p in parts)
    except ValueError:
        raise HTTPException(
            status_code=400, detail="bbox must be numeric minLon,minLat,maxLon,maxLat"
        ) from None
    return {"minx": minx, "miny": miny, "maxx": maxx, "maxy": maxy}


def _geojson(
    db: Session,
    layer: LayerDef,
    bbox: str | None = None,
    district_id: int | None = None,
) -> dict[str, Any]:
    params: dict[str, Any] = _parse_bbox(bbox)
    sql = render_layer_sql(layer)
    if ":district_id" in sql:
        params["district_id"] = district_id
    row = db.execute(text(sql), params).scalar()
    if row is None:
        payload: dict[str, Any] = {"type": "FeatureCollection", "features": []}
    else:
        payload = row if isinstance(row, dict) else json.loads(row)
    payload["sql_ref"] = LAYER_SQL_NAME
    return payload
