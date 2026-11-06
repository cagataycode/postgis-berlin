from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_trees_bbox_rejects_non_numeric():
    res = client.get("/trees", params={"bbox": "1,2,3,x"})
    assert res.status_code == 400


def test_green_spaces_bbox_rejects_short():
    res = client.get("/green-spaces", params={"bbox": "1,2"})
    assert res.status_code == 400


def test_get_layer_sql():
    res = client.get("/layers/bike_parking/sql")
    assert res.status_code == 200
    body = res.json()
    assert body["name"] == "layer_geojson.sql"
    assert body["slug"] == "bike_parking"
    assert "FROM amenity_points" in body["sql"]
    assert "kind_code = 'bike_parking'" in body["sql"]
    assert "attrs" in body["sql"]


def test_park_trees_sql_skips_attrs_and_limits():
    res = client.get("/layers/park_trees/sql")
    assert res.status_code == 200
    body = res.json()
    assert "FROM amenity_points" in body["sql"]
    assert "LIMIT 8000" in body["sql"]
    assert "pt.attrs" not in body["sql"]


def test_park_trees_rejects_oversized_bbox():
    res = client.get(
        "/park-trees",
        params={"bbox": "13.08939,52.36139,13.72061,52.67804"},
    )
    assert res.status_code == 400
    assert "too large" in res.json()["detail"]


def test_get_layer_sql_unknown_layer():
    res = client.get("/layers/nope/sql")
    assert res.status_code == 404
