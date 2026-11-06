from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import AmenityKind, AmenityPointTag, KindTagCategory, Tag
from app.sql_loader import load_sql
from sqlalchemy import text

router = APIRouter(tags=["tags"])


@router.get("/tags")
def list_tags(
    kind: str | None = Query(None, description="kind_code, e.g. ev_charger"),
    db: Session = Depends(get_db),
) -> list[dict[str, Any]]:
    """Tag vocabulary (U7), optionally limited to what a kind may carry."""
    counts = (
        select(AmenityPointTag.tag_id, func.count().label("n"))
        .group_by(AmenityPointTag.tag_id)
        .subquery()
    )
    stmt = (
        select(Tag, func.coalesce(counts.c.n, 0))
        .outerjoin(counts, counts.c.tag_id == Tag.id)
        .order_by(Tag.category_code, Tag.label)
    )
    if kind is not None:
        if db.get(AmenityKind, kind) is None:
            raise HTTPException(status_code=404, detail="Unknown kind")
        stmt = stmt.join(KindTagCategory, KindTagCategory.category_code == Tag.category_code).where(
            KindTagCategory.kind_code == kind
        )
    return [
        {"id": t.id, "category": t.category_code, "label": t.label, "feature_count": int(n)}
        for t, n in db.execute(stmt).all()
    ]


@router.get("/amenities/near")
def amenities_near(
    lon: float = Query(..., ge=-180, le=180),
    lat: float = Query(..., ge=-90, le=90),
    radius_m: float = Query(500, gt=0, le=5000),
    kind: str | None = None,
    tag: list[int] | None = Query(None, description="tag id; repeat for AND"),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Amenities within a radius via the SQL function amenities_near()."""
    rows = (
        db.execute(
            text(load_sql("amenities_near.sql")),
            {
                "lon": lon,
                "lat": lat,
                "radius_m": radius_m,
                "kind": kind,
                "tag_ids": sorted(set(tag or [])),
                "limit": limit,
            },
        )
        .mappings()
        .all()
    )
    return {
        "lon": lon,
        "lat": lat,
        "radius_m": radius_m,
        "kind": kind,
        "tags": sorted(set(tag or [])),
        "sql_ref": "amenities_near.sql",
        "results": [dict(r) for r in rows],
    }
