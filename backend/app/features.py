"""ORM data layer: one feature with its tags, operator and typed detail.

Entity reads go through the ORM; spatial/analytical queries stay in backend/sql/.
"""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload, selectinload

from app.models import AmenityArea, AmenityPoint, AmenityPointTag, TreeDetail

# Legacy layer slug -> kind_code (phase 4 moves this into the registry).
KIND_BY_SLUG: dict[str, str] = {
    "green_spaces": "green_space",
    "cemeteries": "cemetery",
    "playgrounds": "playground",
    "schools": "school",
    "kitas": "kita",
    "hospitals": "hospital",
    "trees": "street_tree",
    "park_trees": "park_tree",
    "bike_parking": "bike_parking",
    "ev_chargers": "ev_charger",
    "drinking_fountains": "drinking_fountain",
    "bathing_waters": "bathing_water",
    "toilets": "toilet",
    "sports_facilities": "sports_facility",
    "park_and_ride": "park_and_ride",
}
AREA_KINDS = {"green_space", "cemetery", "playground"}


def _num(v: Any) -> Any:
    return float(v) if hasattr(v, "as_tuple") else v


def _detail(point: AmenityPoint) -> dict[str, Any] | None:
    d = point.tree_detail or point.kita_detail or point.ev_charger_detail
    if d is None:
        return None
    out = {
        c.name: _num(getattr(d, c.name))
        for c in d.__table__.columns
        if c.name not in ("point_id", "kind_code")
    }
    if point.tree_detail is not None:
        sp = point.tree_detail.species
        out["species"] = (
            {"botanical_name": sp.botanical_name, "german_name": sp.german_name, "genus": sp.genus}
            if sp
            else None
        )
        out.pop("species_id", None)
    return {k: (v.isoformat() if hasattr(v, "isoformat") else v) for k, v in out.items()}


def get_feature(db: Session, kind_code: str, feature_id: int) -> dict[str, Any] | None:
    """GeoJSON Feature for an amenity, or None. Filters on kind_code so the
    planner can prune to a single partition."""
    is_area = kind_code in AREA_KINDS
    model = AmenityArea if is_area else AmenityPoint
    geojson = func.ST_AsGeoJSON(func.ST_Transform(model.geom, 4326))
    stmt = select(model, geojson).where(model.id == feature_id, model.kind_code == kind_code)
    stmt = stmt.options(joinedload(model.district), joinedload(model.catalog))
    if not is_area:
        stmt = stmt.options(
            joinedload(AmenityPoint.operator),
            selectinload(AmenityPoint.tag_links).joinedload(AmenityPointTag.tag),
            joinedload(AmenityPoint.tree_detail).joinedload(TreeDetail.species),
            joinedload(AmenityPoint.kita_detail),
            joinedload(AmenityPoint.ev_charger_detail),
        )
    row = db.execute(stmt).first()
    if row is None:
        return None
    obj, geom_text = row

    props: dict[str, Any] = dict(obj.attrs or {})
    props.update(
        id=obj.id,
        layer_kind=obj.kind_code,
        source_id=obj.source_id,
        name=obj.name,
        subtype=obj.subtype,
        catalog_id=obj.catalog_id,
        district_id=obj.district_id,
        district=obj.district.name if obj.district else None,
        updated_at=obj.updated_at.isoformat() if obj.updated_at else None,
    )
    if not is_area:
        props["operator"] = (
            {
                "id": obj.operator.id,
                "name": obj.operator.name,
                "official_ref": obj.operator.official_ref,
                "operator_type": obj.operator.operator_type,
            }
            if obj.operator
            else None
        )
        props["tags"] = [
            {"id": link.tag.id, "category": link.category_code, "label": link.tag.label}
            for link in sorted(obj.tag_links, key=lambda x: x.tag_id)
        ]
        props["detail"] = _detail(obj)
    return {
        "type": "Feature",
        "id": obj.id,
        "geometry": json.loads(geom_text),
        "properties": props,
    }
