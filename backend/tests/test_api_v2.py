"""Phase 4: layer endpoints and analyses run on the v2 tables."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.db import engine
from app.main import app

pytestmark = pytest.mark.db
client = TestClient(app)
BBOX = "13.3,52.45,13.5,52.57"


@pytest.fixture(scope="module", autouse=True)
def _need_data():
    try:
        with engine.connect() as c:
            ok = c.execute(
                text("SELECT to_regclass('borough_amenity_stats') IS NOT NULL "
                     "AND EXISTS (SELECT 1 FROM amenity_points WHERE kind_code = 'ev_charger')")
            ).scalar()
    except Exception:  # noqa: BLE001
        ok = False
    if not ok:
        pytest.skip("needs migration 0010 and imported v2 data")


def _n(res) -> int:
    assert res.status_code == 200, res.text
    return len(res.json()["features"])


def test_layer_filters_by_kind():
    props = client.get("/schools").json()["features"][0]["properties"]
    assert props["layer"] == "schools" and "school_type" in props


def test_tag_filter_uses_and_semantics():
    all_n = _n(client.get("/ev-chargers", params={"bbox": BBOX}))
    one = _n(client.get("/ev-chargers", params={"bbox": BBOX, "tag": 1}))
    both = _n(client.get("/ev-chargers", params={"bbox": BBOX, "tag": [1, 2]}))
    assert all_n >= one >= both


def test_tag_on_untagged_layer_is_rejected():
    assert client.get("/schools", params={"tag": 1}).status_code == 400


def test_tags_vocabulary_limited_by_kind():
    tags = client.get("/tags", params={"kind": "kita"}).json()
    if not tags:
        pytest.skip("no kita tags (sample data)")
    assert {t["category"] for t in tags} == {"kita_approach"}
    assert client.get("/tags", params={"kind": "nope"}).status_code == 404


def test_amenities_near_function():
    res = client.get("/amenities/near", params={"lon": 13.4, "lat": 52.52, "radius_m": 500, "kind": "kita"})
    rows = res.json()["results"]
    if not rows:
        pytest.skip("no kita within 500 m of the probe point (sample data)")
    assert all(r["kind_code"] == "kita" and r["distance_m"] <= 500 for r in rows)
    assert [r["distance_m"] for r in rows] == sorted(r["distance_m"] for r in rows)


def test_nearest_amenities_covers_every_layer():
    nearest = client.get("/analyses/nearest-amenities", params={"lon": 13.4, "lat": 52.52}).json()["nearest"]
    assert len(nearest) == 14
    assert [n["distance_m"] for n in nearest] == sorted(n["distance_m"] for n in nearest)


def test_density_total_row_equals_sum():
    rows = client.get("/analyses/amenity-density-by-borough").json()["results"]
    *districts, total = rows
    assert total["district_name"] == "Berlin (total)"
    assert total["kitas"] == sum(r["kitas"] for r in districts) > 0


def test_operator_report_ranks_per_borough():
    res = client.get("/analyses/operators", params={"top_n": 2}).json()["results"]
    if not res:
        pytest.skip("no operators in the data (sample data)")
    assert all(r["rank"] <= 2 for r in res)
    kita = client.get("/analyses/operators", params={"top_n": 1, "kind": "kita"}).json()["results"]
    assert all(r["kita_capacity"] >= 0 for r in kita)


def test_green_and_school_proximity():
    green = client.get("/analyses/green-by-borough").json()["results"]
    assert len(green) >= 1
    prox = client.get("/analyses/school-green-proximity").json()["results"]
    if prox:
        assert prox[0]["median_m"] >= 0


def test_playground_read_only_role_can_read_new_objects():
    res = client.post("/sql/run", json={"sql": "SELECT count(*) FROM borough_amenity_stats"})
    assert res.status_code == 200
