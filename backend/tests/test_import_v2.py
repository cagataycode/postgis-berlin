"""Schema v2 importer: parsing rules (no database) and layer upserts (rolled-back transaction)."""

from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db import engine
from scripts.import_layers import CATALOG, upsert_catalog
from scripts.import_v2 import (
    SPECS,
    InjectedFailure,
    apply_layer,
    clean_text,
    ev_extras,
    kita_extras,
    parse_feature,
    planting_year,
    positive_float,
    positive_int,
    split_values,
    toilet_extras,
    tree_extras,
)

# ─── Parsing (pure functions) ────────────────────────────────────────────────


def test_split_values_distinct_and_trimmed():
    assert split_values("Offene-Arbeit/Situationsansatz/ Offene-Arbeit", "/") == [
        "Offene-Arbeit",
        "Situationsansatz",
    ]
    assert split_values(None, "/") == []
    assert split_values("AC Typ 2 Steckdose; DC CHAdeMO", ";") == ["AC Typ 2 Steckdose", "DC CHAdeMO"]


def test_zero_and_empty_mean_unknown():
    assert positive_int(0) is None
    assert positive_int("") is None
    assert positive_float(0.0) is None
    assert positive_float("15,5") == 15.5
    assert positive_float(0.04) is None  # rounds to 0.0 at numeric(_,1): must not reach the CHECK
    assert positive_float(10_000) is None
    assert planting_year("1975") == 1975
    assert planting_year("0") is None
    assert planting_year("3000") is None
    assert clean_text("  ") is None


def test_ev_extras_connectors_and_power():
    ex = ev_extras(
        {
            "betreiber": "E.ON Drive GmbH",
            "anschluss_1": "AC Typ 2 Steckdose; DC CHAdeMO",
            "anschluss_2": "DC CHAdeMO",
            "ladeleistung_1": "11",
            "ladeleistung_2": "50,0",
            "anzahl_ladepunkte": 2,
            "inbetriebnahme": "2021-01-25T00:00:00+01:00",
            "oeffentlicher_raum": "nein",
        }
    )
    assert ex.tags == [("ev_connector", "AC Typ 2 Steckdose"), ("ev_connector", "DC CHAdeMO")]
    assert ex.detail == {
        "charge_points": 2,
        "max_power_kw": 50.0,
        "commissioned_on": "2021-01-25",
        "public_space": False,
    }
    assert ex.operator_name == "E.ON Drive GmbH" and ex.operator_ref is None


def test_kita_extras_operator_ref_and_zero_capacity():
    ex = kita_extras({"t_nr": "1224", "t_name": "GFJ", "t_art": "freie Träger", "ang_1": "A/B", "e_platz": 0})
    assert (ex.operator_ref, ex.operator_name, ex.operator_type) == ("1224", "GFJ", "freie Träger")
    assert [t[1] for t in ex.tags] == ["A", "B"]
    assert ex.detail == {"capacity": 0}  # 0 places is valid for capacity
    assert kita_extras({"e_platz": ""}).detail == {"capacity": None}


def test_toilet_extras_features():
    ex = toilet_extras(
        {"barrierefrei": "ja", "wickeltisch": "nein", "nutzungsentgelt": 0.0, "betreiber": "Wall GmbH"}
    )
    assert ex.tags == [("toilet_feature", "barrierefrei"), ("toilet_feature", "kostenlos")]
    assert toilet_extras({"nutzungsentgelt": 0.5}).tags == []


def test_tree_extras_zero_height_is_null():
    ex = tree_extras({"art_bot": "Acer", "baumhoehe": 0.0, "kronedurch": 4.5, "stammumfg": 115, "pflanzjahr": ""})
    assert ex.detail["height_m"] is None
    assert ex.detail["crown_diameter_m"] == 4.5
    assert ex.detail["planting_year"] is None
    assert ex.detail["botanical_name"] == "Acer"


def test_source_keys_for_known_problem_layers():
    point = {"type": "Point", "coordinates": [13.4, 52.5]}
    toilet = parse_feature(SPECS["toilets"], {"properties": {"fid": 2, "standort": "WC"}, "geometry": point})
    assert toilet is not None and toilet[0] == "2"  # was NULL for all 525 rows in the legacy importer
    bike = parse_feature(
        SPECS["bike_parking"],
        {"properties": {"gml_id": "fahrradabstellanlagen.1119", "projektnummer": "9040082005"}, "geometry": point},
    )
    assert bike is not None and bike[0] == "fahrradabstellanlagen.1119"


def test_features_without_key_or_geometry_are_skipped():
    point = {"type": "Point", "coordinates": [13.4, 52.5]}
    assert parse_feature(SPECS["kitas"], {"properties": {}, "geometry": point}) is None
    assert parse_feature(SPECS["kitas"], {"properties": {"e_nr": "1"}, "geometry": None}) is None


# ─── Database behaviour (rolled back) ────────────────────────────────────────




@pytest.fixture()
def session():
    conn = engine.connect()
    outer = conn.begin()
    try:
        if conn.execute(text("SELECT to_regclass('public.amenity_points')")).scalar() is None:
            pytest.skip("schema v2 not migrated (alembic upgrade head)")
        s = Session(bind=conn, join_transaction_mode="create_savepoint")
        yield s
        s.close()
    finally:
        outer.rollback()
        conn.close()


def _point(lon: float, lat: float) -> dict:
    return {"type": "Point", "coordinates": [lon, lat]}


def _kita(nr: str, name: str, approaches: str, op: str = "1224", capacity: int = 20, lonlat=(13.40, 52.52)) -> dict:
    return {
        "properties": {
            "e_nr": nr, "e_name": name, "e_art": "Kindertagesstätte", "ang_1": approaches,
            "t_nr": op, "t_name": "GFJ", "t_art": "freie Träger", "e_platz": capacity,
        },
        "geometry": _point(*lonlat),
    }


def _catalog(session) -> int:
    return upsert_catalog(session, CATALOG["kitas"])


def _scalar(session, sql: str, **params):
    return session.execute(text(sql), params).scalar_one()


@pytest.mark.db
def test_apply_layer_creates_operator_tags_and_details(session):
    cid = _catalog(session)
    counts = apply_layer(
        session, "kitas",
        [_kita("T1", "Kita A", "Offene-Arbeit/Situationsansatz"), _kita("T2", "Kita B", "Situationsansatz", capacity=0)],
        cid,
    )
    assert counts["inserted"] == 2 and counts["deleted"] >= 0
    assert _scalar(session, "SELECT count(*) FROM amenity_points WHERE kind_code='kita'") == 2
    # one shared operator row (3NF), referenced by both kitas
    assert _scalar(session, "SELECT count(DISTINCT operator_id) FROM amenity_points WHERE kind_code='kita'") == 1
    assert _scalar(session, "SELECT count(*) FROM operator WHERE official_ref='1224'") == 1
    # M:N: 3 links, 2 distinct tags
    assert _scalar(session, "SELECT count(*) FROM amenity_point_tag WHERE kind_code='kita'") == 3
    assert _scalar(session, "SELECT count(DISTINCT tag_id) FROM amenity_point_tag WHERE kind_code='kita'") == 2
    assert _scalar(session, "SELECT sum(capacity) FROM kita_detail") == 20


@pytest.mark.db
def test_second_identical_run_changes_nothing_and_keeps_ids(session):
    cid = _catalog(session)
    feats = [_kita("T1", "Kita A", "A/B"), _kita("T2", "Kita B", "B")]
    apply_layer(session, "kitas", feats, cid)
    ids = session.execute(text("SELECT id FROM amenity_points WHERE kind_code='kita' ORDER BY id")).scalars().all()
    again = apply_layer(session, "kitas", feats, cid)
    assert (again["inserted"], again["updated"], again["deleted"]) == (0, 0, 0)
    assert session.execute(text("SELECT id FROM amenity_points WHERE kind_code='kita' ORDER BY id")).scalars().all() == ids


@pytest.mark.db
def test_changed_row_is_updated_in_place(session):
    cid = _catalog(session)
    apply_layer(session, "kitas", [_kita("T1", "Old name", "A")], cid)
    pid = _scalar(session, "SELECT id FROM amenity_points WHERE kind_code='kita'")
    counts = apply_layer(session, "kitas", [_kita("T1", "New name", "A")], cid)
    assert (counts["inserted"], counts["updated"]) == (0, 1)
    assert _scalar(session, "SELECT id FROM amenity_points WHERE kind_code='kita'") == pid
    assert _scalar(session, "SELECT name FROM amenity_points WHERE id=:i", i=pid) == "New name"


@pytest.mark.db
def test_rows_missing_from_source_are_deleted_with_their_tags(session):
    cid = _catalog(session)
    apply_layer(session, "kitas", [_kita("T1", "A", "X"), _kita("T2", "B", "Y")], cid)
    counts = apply_layer(session, "kitas", [_kita("T1", "A", "X")], cid)
    assert counts["deleted"] == 1
    assert _scalar(session, "SELECT count(*) FROM amenity_points WHERE kind_code='kita'") == 1
    assert _scalar(session, "SELECT count(*) FROM amenity_point_tag WHERE kind_code='kita'") == 1  # cascade + stale cleanup


@pytest.mark.db
def test_dropped_tag_is_removed_from_junction(session):
    cid = _catalog(session)
    apply_layer(session, "kitas", [_kita("T1", "A", "X/Y")], cid)
    apply_layer(session, "kitas", [_kita("T1", "A", "X")], cid)
    assert _scalar(session, "SELECT count(*) FROM amenity_point_tag WHERE kind_code='kita'") == 1


@pytest.mark.db
def test_failure_rolls_back_the_layer(session):
    cid = _catalog(session)
    apply_layer(session, "kitas", [_kita("T1", "A", "X"), _kita("T2", "B", "Y")], cid)
    before = _scalar(session, "SELECT count(*) FROM amenity_points WHERE kind_code='kita'")
    sp = session.begin_nested()
    with pytest.raises(InjectedFailure):
        apply_layer(session, "kitas", [_kita("T1", "A", "X"), _kita("T2", "B", "Y")], cid, fail_after_rows=1)
    sp.rollback()
    assert _scalar(session, "SELECT count(*) FROM amenity_points WHERE kind_code='kita'") == before


@pytest.mark.db
def test_duplicate_source_ids_in_file_are_rejected(session):
    cid = _catalog(session)
    with pytest.raises(ValueError, match="duplicate source_id"):
        apply_layer(session, "kitas", [_kita("T1", "A", "X"), _kita("T1", "B", "Y")], cid)


@pytest.mark.db
def test_empty_source_refuses_to_wipe_the_kind(session):
    cid = _catalog(session)
    apply_layer(session, "kitas", [_kita("T1", "A", "X")], cid)
    with pytest.raises(ValueError, match="refusing to wipe"):
        apply_layer(session, "kitas", [], cid)
    assert _scalar(session, "SELECT count(*) FROM amenity_points WHERE kind_code='kita'") == 1


@pytest.mark.db
def test_district_is_derived_for_points_inside_a_district(session):
    cid = _catalog(session)
    session.execute(
        text(
            """
            INSERT INTO districts (official_id, name, catalog_id, geom)
            VALUES ('TEST-D', 'Test district', :c,
              ST_Multi(ST_Transform(ST_SetSRID(ST_GeomFromText(
                'POLYGON((9.9 49.9,10.1 49.9,10.1 50.1,9.9 50.1,9.9 49.9))'), 4326), 25833)))
            """
        ),
        {"c": cid},
    )
    apply_layer(session, "kitas", [_kita("T1", "A", "X", lonlat=(10.0, 50.0))], cid)  # outside Berlin: no overlap with real districts
    assert _scalar(
        session,
        "SELECT d.official_id FROM amenity_points p JOIN districts d ON d.id = p.district_id "
        "WHERE p.kind_code='kita' AND p.source_id='T1'",
    ) == "TEST-D"


@pytest.mark.db
def test_tree_species_lookup_and_unknown_height(session):
    cid = upsert_catalog(session, CATALOG["trees"])
    tree = lambda gid, h: {  # noqa: E731
        "properties": {"gisid": gid, "art_bot": "Acer pseudoplatanus", "art_dtsch": "Berg-Ahorn",
                       "gattung": "Acer", "baumhoehe": h, "pflanzjahr": "1975"},
        "geometry": _point(13.4, 52.5),
    }
    apply_layer(session, "trees", [tree("g1", 0.0), tree("g2", 12.5)], cid)
    assert _scalar(session, "SELECT count(*) FROM tree_species WHERE botanical_name='Acer pseudoplatanus'") == 1
    assert _scalar(session, "SELECT count(*) FROM tree_detail WHERE kind_code='street_tree' AND height_m IS NULL") >= 1
    assert _scalar(session, "SELECT count(DISTINCT species_id) FROM tree_detail WHERE kind_code='street_tree'") == 1
