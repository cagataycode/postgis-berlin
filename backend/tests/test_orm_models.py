"""Phase 3: the ORM reads v2 entities, relationships and the read-only engine."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session, configure_mappers

from app.db import SessionLocal, engine, engine_ro
from app.main import app
from app.models import AmenityPoint, AmenityPointTag, KitaDetail, Tag

pytestmark = pytest.mark.db
client = TestClient(app)


def test_mappers_configure():
    configure_mappers()


@pytest.fixture()
def session():
    with engine.connect() as c:
        if c.execute(text("SELECT to_regclass('public.amenity_points')")).scalar() is None:
            pytest.skip("schema v2 not migrated")
    s = SessionLocal()
    try:
        yield s
    finally:
        s.close()


def _first_id(session: Session, kind: str, with_tag: bool = False):
    q = select(AmenityPoint).where(AmenityPoint.kind_code == kind)
    if with_tag:
        q = q.where(AmenityPoint.tag_links.any())
    q = q.order_by(AmenityPoint.id).limit(1)
    return session.execute(q).scalar_one_or_none()


def test_tags_through_association_object(session):
    p = _first_id(session, "ev_charger", with_tag=True)
    if p is None:
        pytest.skip("no imported EV chargers")
    assert p.tags and all(isinstance(t, Tag) for t in p.tags)
    assert all(isinstance(l, AmenityPointTag) for l in p.tag_links)
    assert {l.category_code for l in p.tag_links} == {"ev_connector"}


def test_one_to_one_detail(session):
    p = _first_id(session, "kita")
    if p is None:
        pytest.skip("no imported kitas")
    assert isinstance(p.kita_detail, KitaDetail)
    assert p.tree_detail is None and p.ev_charger_detail is None


def test_feature_endpoint_returns_tags_operator_detail(session):
    p = _first_id(session, "ev_charger", with_tag=True)
    if p is None:
        pytest.skip("no imported EV chargers")
    res = client.get(f"/features/ev_chargers/{p.id}")
    assert res.status_code == 200
    body = res.json()
    props = body["properties"]
    assert body["geometry"]["type"] == "Point"
    assert props["tags"] and props["tags"][0]["category"] == "ev_connector"
    assert "charge_points" in props["detail"]
    assert "operator" in props


def test_feature_endpoint_area_and_404(session):
    assert client.get("/features/kitas/0").status_code == 404
    assert client.get("/features/nope/1").status_code == 404


def test_feature_wrong_kind_is_not_found(session):
    p = _first_id(session, "kita")
    if p is None:
        pytest.skip("no imported kitas")
    assert client.get(f"/features/ev_chargers/{p.id}").status_code == 404


def test_read_only_engine_cannot_write():
    try:
        with engine_ro.connect() as c:
            c.execute(text("SELECT 1"))
    except Exception:  # noqa: BLE001
        pytest.skip("berlin_ro not available")
    with engine_ro.connect() as c:
        with pytest.raises(DBAPIError):
            c.execute(text("DELETE FROM operator WHERE false"))
