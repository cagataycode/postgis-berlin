"""Phase 7: plan assertions for the design choices (partition pruning, index use).

Plans are read with plain EXPLAIN on the loaded database, so they check the
planner's choice, not timings. Skipped when the v2 data is not loaded.
"""

from __future__ import annotations

import pytest
from sqlalchemy import text

from app.db import engine

pytestmark = pytest.mark.db

BBOX = "ST_Transform(ST_MakeEnvelope(13.38, 52.50, 13.42, 52.53, 4326), 25833)"


@pytest.fixture(scope="module")
def conn():
    with engine.connect() as c:
        try:
            n = c.execute(text("SELECT count(*) FROM amenity_points_street_tree")).scalar()
        except Exception:  # noqa: BLE001
            pytest.skip("schema v2 not migrated")
        if not n or n < 100_000:
            pytest.skip("needs the full street-tree import")
        yield c


def _plan(conn, query: str) -> str:
    return "\n".join(r[0] for r in conn.execute(text(f"EXPLAIN {query}")).fetchall())


def test_street_tree_bbox_scans_only_its_partition(conn):
    plan = _plan(conn, f"SELECT id FROM amenity_points WHERE kind_code = 'street_tree' AND geom && {BBOX}")
    assert "amenity_points_street_tree" in plan
    assert "amenity_points_park_tree" not in plan
    assert "amenity_points_other" not in plan
    assert "Seq Scan" not in plan


def test_small_kind_uses_default_partition_only(conn):
    plan = _plan(conn, "SELECT id FROM amenity_points WHERE kind_code = 'kita'")
    assert "amenity_points_other" in plan
    assert "amenity_points_street_tree" not in plan


def test_knn_is_index_ordered_without_sort(conn):
    plan = _plan(
        conn,
        "SELECT id FROM amenity_points WHERE kind_code = 'street_tree' "
        "ORDER BY geom <-> ST_SetSRID(ST_MakePoint(391000, 5820000), 25833) LIMIT 5",
    )
    assert "Index Scan" in plan and "geom" in plan
    assert "Sort" not in plan


def test_tag_lookup_uses_the_tag_first_index(conn):
    conn.execute(text("SET LOCAL enable_seqscan = off"))
    plan = _plan(conn, "SELECT point_id FROM amenity_point_tag WHERE tag_id = 16")
    assert "ix_amenity_point_tag_tag" in plan


def test_attrs_containment_can_use_gin(conn):
    conn.execute(text("SET LOCAL enable_seqscan = off"))
    plan = _plan(conn, """SELECT id FROM amenity_points_street_tree WHERE attrs @> '{"gattung": "Ginkgo"}'""")
    assert "attrs_idx" in plan
