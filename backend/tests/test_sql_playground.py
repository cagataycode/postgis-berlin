import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.main import app
from app.routers.sql import _validate_select


client = TestClient(app)


def test_validate_select_allows_with():
    sql = _validate_select("WITH x AS (SELECT 1 AS n) SELECT * FROM x")
    assert "WITH x AS" in sql


def test_validate_select_rejects_writes():
    with pytest.raises(HTTPException) as exc:
        _validate_select("DELETE FROM trees")
    assert exc.value.status_code == 400


def test_validate_select_rejects_select_into():
    with pytest.raises(HTTPException) as exc:
        _validate_select("SELECT * INTO foo FROM trees")
    assert exc.value.status_code == 400


def test_validate_select_rejects_lock_clause():
    with pytest.raises(HTTPException) as exc:
        _validate_select("SELECT * FROM trees FOR UPDATE")
    assert exc.value.status_code == 400


def test_validate_select_rejects_set_config():
    with pytest.raises(HTTPException) as exc:
        _validate_select("SELECT set_config('statement_timeout','0',false)")
    assert exc.value.status_code == 400


def test_validate_select_rejects_pg_read_file():
    with pytest.raises(HTTPException) as exc:
        _validate_select("SELECT pg_read_file('/etc/passwd')")
    assert exc.value.status_code == 400


def test_validate_select_allows_forbidden_word_in_literal():
    sql = _validate_select("SELECT 'x -- delete' AS note")
    assert "AS note" in sql


def test_validate_select_allows_forbidden_word_in_comment():
    sql = _validate_select("-- mentions delete\nSELECT 1")
    assert "SELECT 1" in sql


def test_validate_select_rejects_multi_statement():
    with pytest.raises(HTTPException) as exc:
        _validate_select("SELECT 1; SELECT 2")
    assert exc.value.status_code == 400


def test_validate_select_allows_semicolon_in_comment():
    sql = _validate_select("-- lon/lat; null bbox\nSELECT 1 AS n")
    assert "SELECT 1 AS n" in sql


def test_validate_layer_geojson_sql():
    from app.layer_registry import LAYER_BY_SLUG, render_layer_sql

    sql = render_layer_sql(LAYER_BY_SLUG["ev_chargers"])
    cleaned = _validate_select(sql)
    assert "FROM amenity_points" in cleaned
    assert "kind_code = 'ev_charger'" in cleaned


def test_get_sql_file():
    res = client.get("/sql/analysis_green_by_borough.sql")
    assert res.status_code == 200
    body = res.json()
    assert body["name"] == "analysis_green_by_borough.sql"
    assert "FROM districts" in body["sql"]


def test_get_sql_file_rejects_path_traversal():
    res = client.get("/sql/../main.py")
    assert res.status_code == 404


@pytest.mark.db
def test_run_sql_select():
    res = client.post("/sql/run", json={"sql": "SELECT 1 AS n", "explain": False})
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["columns"] == ["n"]
    assert body["rows"] == [[1]]
    assert body["explain"] is False
