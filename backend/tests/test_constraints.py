"""Schema v2: the database itself must reject inconsistent data (migration 0009).

Every test runs inside one outer transaction that is rolled back, so the
database is left unchanged. Each expected failure runs in a SAVEPOINT.
"""

from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError

from app.db import engine

pytestmark = pytest.mark.db

POINT = "ST_SetSRID(ST_MakePoint(390000, 5820000), 25833)"


@pytest.fixture()
def conn():
    with engine.connect() as c:
        outer = c.begin()
        if c.execute(text("SELECT to_regclass('public.amenity_points')")).scalar() is None:
            outer.rollback()
            pytest.skip("schema v2 not migrated (alembic upgrade head)")
        c.execute(text("INSERT INTO dataset_catalog (slug, name) VALUES ('test-v2', 'test')"))
        try:
            yield c
        finally:
            outer.rollback()


def _catalog_id(conn) -> int:
    return conn.execute(text("SELECT id FROM dataset_catalog WHERE slug = 'test-v2'")).scalar_one()


def _point(conn, kind: str, source_id: str) -> int:
    return conn.execute(
        text(
            f"INSERT INTO amenity_points (kind_code, source_id, catalog_id, geom) "
            f"VALUES (:k, :s, :c, {POINT}) RETURNING id"
        ),
        {"k": kind, "s": "zz-" + source_id, "c": _catalog_id(conn)},
    ).scalar_one()


def _tag(conn, category: str, label: str) -> int:
    return conn.execute(
        text("INSERT INTO tag (category_code, label) VALUES (:c, :l) RETURNING id"),
        {"c": category, "l": label},
    ).scalar_one()


def _rejected(conn, sql: str, params: dict | None = None, exc=IntegrityError) -> str:
    """Run sql in a savepoint; return the constraint error text."""
    sp = conn.begin_nested()
    with pytest.raises(exc) as info:
        conn.execute(text(sql), params or {})
    sp.rollback()
    return str(info.value)


def test_seeds_present(conn):
    kinds = conn.execute(text("SELECT count(*) FROM amenity_kind")).scalar()
    allowed = conn.execute(text("SELECT count(*) FROM kind_tag_category")).scalar()
    assert (kinds, allowed) == (15, 3)


def test_area_kind_rejected_in_points(conn):
    msg = _rejected(
        conn,
        f"INSERT INTO amenity_points (kind_code, source_id, catalog_id, geom) "
        f"VALUES ('cemetery', 'zz-c1', {_catalog_id(conn)}, {POINT})",
    )
    assert "amenity_points_kind_code_geom_family_fkey" in msg


def test_point_kind_rejected_in_areas(conn):
    msg = _rejected(
        conn,
        f"INSERT INTO amenity_areas (kind_code, source_id, catalog_id, geom) VALUES "
        f"('school', 'zz-x', {_catalog_id(conn)}, "
        f"ST_Multi(ST_GeomFromText('POLYGON((0 0,1 0,1 1,0 1,0 0))', 25833)))",
    )
    assert "amenity_areas_kind_code_geom_family_fkey" in msg


def test_duplicate_source_key_rejected(conn):
    _point(conn, "kita", "k1")
    msg = _rejected(
        conn,
        f"INSERT INTO amenity_points (kind_code, source_id, catalog_id, geom) "
        f"VALUES ('kita', 'zz-k1', {_catalog_id(conn)}, {POINT})",
    )
    assert "kind_code_source_id_key" in msg


def test_same_source_id_allowed_for_different_kinds(conn):
    _point(conn, "kita", "same")
    _point(conn, "toilet", "same")  # no error


def test_invalid_polygon_rejected(conn):
    msg = _rejected(
        conn,
        f"INSERT INTO amenity_areas (kind_code, source_id, catalog_id, geom) VALUES "
        f"('cemetery', 'zz-bow', {_catalog_id(conn)}, "
        f"ST_Multi(ST_GeomFromText('POLYGON((0 0,1 1,1 0,0 1,0 0))', 25833)))",
    )
    assert "amenity_areas_geom_check" in msg


def test_tag_allowed_on_matching_kind(conn):
    pid = _point(conn, "kita", "k1")
    tid = _tag(conn, "kita_approach", "Montessori")
    conn.execute(
        text("INSERT INTO amenity_point_tag VALUES (:p, 'kita', :t, 'kita_approach')"),
        {"p": pid, "t": tid},
    )


def test_kita_tag_on_toilet_rejected(conn):
    pid = _point(conn, "toilet", "t1")
    tid = _tag(conn, "kita_approach", "Reggio")
    msg = _rejected(
        conn,
        "INSERT INTO amenity_point_tag VALUES (:p, 'toilet', :t, 'kita_approach')",
        {"p": pid, "t": tid},
    )
    assert "amenity_point_tag_kind_code_category_code_fkey" in msg


def test_junction_with_wrong_category_rejected(conn):
    pid = _point(conn, "kita", "k1")
    tid = _tag(conn, "ev_connector", "CCS")
    msg = _rejected(
        conn,
        "INSERT INTO amenity_point_tag VALUES (:p, 'kita', :t, 'kita_approach')",
        {"p": pid, "t": tid},
    )
    assert "amenity_point_tag_tag_id_category_code_fkey" in msg


def test_junction_with_wrong_kind_rejected(conn):
    pid = _point(conn, "kita", "k1")
    tid = _tag(conn, "kita_approach", "Reggio")
    msg = _rejected(
        conn,
        "INSERT INTO amenity_point_tag VALUES (:p, 'toilet', :t, 'kita_approach')",
        {"p": pid, "t": tid},
    )
    assert "amenity_point_tag_point_id_kind_code_fkey" in msg


def test_junction_rows_cascade_with_point(conn):
    pid = _point(conn, "kita", "k1")
    tid = _tag(conn, "kita_approach", "Montessori")
    conn.execute(
        text("INSERT INTO amenity_point_tag VALUES (:p, 'kita', :t, 'kita_approach')"),
        {"p": pid, "t": tid},
    )
    conn.execute(text("DELETE FROM amenity_points WHERE id = :p"), {"p": pid})
    assert conn.execute(text("SELECT count(*) FROM amenity_point_tag")).scalar() == 0


def test_detail_row_for_wrong_kind_rejected(conn):
    pid = _point(conn, "kita", "k1")
    msg = _rejected(
        conn, "INSERT INTO tree_detail (point_id, kind_code) VALUES (:p, 'kita')", {"p": pid}
    )
    assert "tree_detail_kind_code_check" in msg


def test_tree_height_zero_rejected(conn):
    pid = _point(conn, "street_tree", "s1")
    msg = _rejected(
        conn,
        "INSERT INTO tree_detail (point_id, kind_code, height_m) VALUES (:p, 'street_tree', 0)",
        {"p": pid},
    )
    assert "tree_detail_height_m_check" in msg


def test_points_routed_to_partitions(conn):
    _point(conn, "street_tree", "s1")
    _point(conn, "park_tree", "p1")
    _point(conn, "school", "sc1")
    rows = dict(
        conn.execute(
            text(
                "SELECT tableoid::regclass::text, count(*) FROM amenity_points "
                "WHERE source_id IN ('zz-s1','zz-p1','zz-sc1') GROUP BY 1"
            )
        ).all()
    )
    assert rows == {
        "amenity_points_street_tree": 1,
        "amenity_points_park_tree": 1,
        "amenity_points_other": 1,
    }


def test_kind_filter_prunes_partitions(conn):
    plan = "\n".join(
        r[0]
        for r in conn.execute(
            text("EXPLAIN SELECT id FROM amenity_points WHERE kind_code = 'street_tree'")
        )
    )
    assert "amenity_points_street_tree" in plan
    assert "amenity_points_park_tree" not in plan
    assert "amenity_points_other" not in plan


def test_updated_at_trigger_overrides_manual_value(conn):
    pid = _point(conn, "kita", "k1")
    after = conn.execute(
        text(
            "UPDATE amenity_points SET updated_at = '2000-01-01' "
            "WHERE id = :p RETURNING updated_at > '2020-01-01'"
        ),
        {"p": pid},
    ).scalar_one()
    assert after is True


def test_import_run_status_check(conn):
    msg = _rejected(
        conn,
        "INSERT INTO import_run (catalog_id, status) "
        "SELECT id, 'half-done' FROM dataset_catalog WHERE slug = 'test-v2'",
    )
    assert "import_run_status_check" in msg


def test_readonly_role_cannot_write():
    from sqlalchemy import create_engine

    from app.config import settings

    ro_url = settings.database_url_ro
    ro = create_engine(ro_url)
    try:
        with ro.connect() as c:
            if c.execute(text("SELECT to_regclass('public.amenity_points')")).scalar() is None:
                pytest.skip("schema v2 not migrated")
            assert c.execute(text("SELECT count(*) FROM amenity_kind")).scalar() == 15
            sp = c.begin_nested()
            with pytest.raises(DBAPIError):
                c.execute(text("DELETE FROM amenity_kind"))
            sp.rollback()
    except Exception as exc:  # noqa: BLE001
        if "password authentication failed" in str(exc) or "role" in str(exc):
            pytest.skip("berlin_ro role not available")
        raise
    finally:
        ro.dispose()
