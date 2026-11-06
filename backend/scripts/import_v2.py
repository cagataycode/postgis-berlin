#!/usr/bin/env python3
"""Load Berlin open data into the schema-v2 tables (migration 0009).

One transaction per layer (docs/schema-v2/acid-and-transactions.md):

  tx A  import_run row 'running'                       (own commit)
  tx B  stage -> upsert -> delete missing -> derive district_id
        -> operators -> tags -> detail tables           (commit or rollback)
  tx C  import_run row 'committed' | 'failed'          (own commit)

`apply_layer()` never commits, so tests can run it inside a rolled-back
transaction. Reuses catalog metadata and file/WFS helpers from import_layers.py,
which stays the entry point for the legacy tables until the phase 6 cutover.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Callable, Iterable

from sqlalchemy import text

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from scripts.import_layers import (  # noqa: E402
    CATALOG,
    DEFAULT_ORDER,
    IMPORT_CONFIG,
    TARGET_SRID,
    attrs_json,
    first_prop,
    load_geojson_features,
    resolve_path,
    upsert_catalog,
)
from app.db import SessionLocal, engine  # noqa: E402


class InjectedFailure(RuntimeError):
    """Raised by --fail-after-rows to demonstrate rollback."""


# ─── Value cleaning ──────────────────────────────────────────────────────────


def clean_text(value, limit: int | None = None) -> str | None:
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None
    return s[:limit] if limit else s


def positive_int(value, maximum: int | None = None) -> int | None:
    """Source uses 0 / '' for unknown: both become NULL."""
    try:
        n = int(float(str(value).replace(",", ".")))
    except (TypeError, ValueError):
        return None
    if n <= 0 or (maximum is not None and n > maximum):
        return None
    return n


def positive_float(value, maximum: float = 9999.9) -> float | None:
    """Round to the column scale first, then test: 0.04 -> 0.0 would violate CHECK (> 0)."""
    try:
        x = round(float(str(value).replace(",", ".")), 1)
    except (TypeError, ValueError):
        return None
    if x <= 0 or x > maximum:
        return None
    return x


def planting_year(value) -> int | None:
    year = positive_int(value)
    return year if year is not None and 1500 <= year <= 2100 else None


def iso_date(value) -> str | None:
    s = clean_text(value)
    if not s:
        return None
    try:
        return date.fromisoformat(s[:10]).isoformat()
    except ValueError:
        return None


def split_values(value, sep: str) -> list[str]:
    """Split a multi-valued source field into distinct, ordered, non-empty parts."""
    out: list[str] = []
    for part in str(value or "").split(sep):
        part = part.strip()
        if part and part not in out:
            out.append(part)
    return out


# ─── Per-layer extras: operator, tags, detail ────────────────────────────────


@dataclass
class Extras:
    operator_ref: str | None = None
    operator_name: str | None = None
    operator_type: str | None = None
    tags: list[tuple[str, str]] = field(default_factory=list)
    detail: dict = field(default_factory=dict)


def _kita_capacity(p: dict) -> int | None:
    """0 places is legitimate (CHECK capacity >= 0); empty is NULL."""
    try:
        n = int(float(str(p.get("e_platz")).replace(",", ".")))
    except (TypeError, ValueError):
        return None
    return n if n >= 0 else None


def kita_extras(p: dict) -> Extras:
    return Extras(
        operator_ref=clean_text(p.get("t_nr"), 64),
        operator_name=clean_text(p.get("t_name"), 255),
        operator_type=clean_text(p.get("t_art"), 64),
        tags=[("kita_approach", a) for a in split_values(p.get("ang_1"), "/")],
        detail={"capacity": _kita_capacity(p)},
    )


def ev_extras(p: dict) -> Extras:
    labels: list[str] = []
    powers: list[float] = []
    for i in range(1, 5):
        for conn in split_values(p.get(f"anschluss_{i}"), ";"):
            if conn not in labels:
                labels.append(conn)
        kw = positive_float(p.get(f"ladeleistung_{i}"))
        if kw is not None:
            powers.append(kw)
    public = {"ja": True, "nein": False}.get(str(p.get("oeffentlicher_raum") or "").strip().lower())
    return Extras(
        operator_name=clean_text(p.get("betreiber"), 255),
        tags=[("ev_connector", c) for c in labels],
        detail={
            "charge_points": positive_int(p.get("anzahl_ladepunkte"), 32767),
            "max_power_kw": max(powers) if powers else None,
            "commissioned_on": iso_date(p.get("inbetriebnahme")),
            "public_space": public,
        },
    )


def toilet_extras(p: dict) -> Extras:
    tags: list[tuple[str, str]] = []
    if str(p.get("barrierefrei") or "").strip().lower() == "ja":
        tags.append(("toilet_feature", "barrierefrei"))
    if str(p.get("wickeltisch") or "").strip().lower() == "ja":
        tags.append(("toilet_feature", "Wickeltisch"))
    try:
        if p.get("nutzungsentgelt") is not None and float(p["nutzungsentgelt"]) == 0:
            tags.append(("toilet_feature", "kostenlos"))
    except (TypeError, ValueError):
        pass
    return Extras(operator_name=clean_text(p.get("betreiber"), 255), tags=tags)


def tree_extras(p: dict) -> Extras:
    return Extras(
        detail={
            "botanical_name": clean_text(p.get("art_bot"), 255),
            "german_name": clean_text(p.get("art_dtsch"), 255),
            "genus": clean_text(p.get("gattung"), 128),
            "planting_year": planting_year(p.get("pflanzjahr")),
            "trunk_circumference_cm": positive_int(p.get("stammumfg"), 2_000_000),
            "height_m": positive_float(p.get("baumhoehe")),
            "crown_diameter_m": positive_float(p.get("kronedurch")),
        }
    )


def J(key: str, sqltype: str) -> str:
    return f"(s.detail->>'{key}')::{sqltype}"


# detail table -> [(column, SQL expression over staging alias s)]
DETAIL_COLUMNS: dict[str, list[tuple[str, str]]] = {
    "tree_detail": [
        ("species_id", "(SELECT sp.id FROM tree_species sp WHERE sp.botanical_name = s.detail->>'botanical_name')"),
        ("planting_year", J("planting_year", "smallint")),
        ("trunk_circumference_cm", J("trunk_circumference_cm", "integer")),
        ("height_m", J("height_m", "numeric(5,1)")),
        ("crown_diameter_m", J("crown_diameter_m", "numeric(5,1)")),
    ],
    "kita_detail": [("capacity", J("capacity", "integer"))],
    "ev_charger_detail": [
        ("charge_points", J("charge_points", "smallint")),
        ("max_power_kw", J("max_power_kw", "numeric(6,1)")),
        ("commissioned_on", J("commissioned_on", "date")),
        ("public_space", J("public_space", "boolean")),
    ],
}


@dataclass(frozen=True)
class LayerSpec:
    layer: str
    kind: str
    family: str  # 'point' | 'area'
    id_keys: tuple[str, ...]
    name_keys: tuple[str, ...]
    subtype_keys: tuple[str, ...] = ()
    extras: Callable[[dict], Extras] | None = None
    detail_table: str | None = None

    @property
    def table(self) -> str:
        return "amenity_points" if self.family == "point" else "amenity_areas"


def _legacy(layer: str) -> dict:
    return IMPORT_CONFIG[layer]


def _spec(layer: str, kind: str, **over) -> LayerSpec:
    cfg = _legacy(layer)
    family = "point" if cfg["kind"] == "point" else "area"
    return LayerSpec(
        layer=layer,
        kind=kind,
        family=family,
        id_keys=over.get("id_keys", cfg["source_id_keys"]),
        name_keys=over.get("name_keys", cfg["name_keys"]),
        subtype_keys=over.get("subtype_keys", cfg["extra_keys"]),
        extras=over.get("extras"),
        detail_table=over.get("detail_table"),
    )


SPECS: dict[str, LayerSpec] = {
    s.layer: s
    for s in (
        _spec("green_spaces", "green_space"),
        _spec("schools", "school"),
        _spec("bike_parking", "bike_parking", id_keys=("gml_id", "source_id")),
        _spec("ev_chargers", "ev_charger", extras=ev_extras, detail_table="ev_charger_detail"),
        _spec("drinking_fountains", "drinking_fountain"),
        _spec("bathing_waters", "bathing_water"),
        _spec(
            "toilets",
            "toilet",
            id_keys=("fid", "nummer", "id", "source_id"),
            name_keys=("standort", "ortsangabe", "strasse", "name"),
            subtype_keys=("modelltyp", "anlagenart", "art", "facility_type"),
            extras=toilet_extras,
        ),
        _spec("playgrounds", "playground"),
        _spec("sports_facilities", "sports_facility", id_keys=("id", "objekt_id", "source_id")),
        _spec("kitas", "kita", extras=kita_extras, detail_table="kita_detail"),
        _spec("hospitals", "hospital"),
        _spec("cemeteries", "cemetery"),
        _spec("park_and_ride", "park_and_ride"),
        LayerSpec(
            "trees", "street_tree", "point", ("gisid", "pitid", "source_id"),
            ("art_dtsch", "namenr", "name"), extras=tree_extras, detail_table="tree_detail",
        ),
        LayerSpec(
            "park_trees", "park_tree", "point", ("gisid", "pitid", "source_id"),
            ("art_dtsch", "namenr", "name"), extras=tree_extras, detail_table="tree_detail",
        ),
    )
}
STAGE_COLUMNS = (
    "source_id, name, subtype, attrs, geom_json, "
    "operator_ref, operator_name, operator_type, tags, detail"
)


def parse_feature(spec: LayerSpec, feat: dict) -> tuple | None:
    """Feature -> staging row, or None if it has no key or geometry."""
    props = feat.get("properties") or {}
    geometry = feat.get("geometry")
    source_id = clean_text(first_prop(props, spec.id_keys), 128)
    if not geometry or source_id is None:
        return None
    extras = spec.extras(props) if spec.extras else Extras()
    return (
        source_id,
        clean_text(first_prop(props, spec.name_keys), 255),
        clean_text(first_prop(props, spec.subtype_keys), 128) if spec.subtype_keys else None,
        attrs_json(props),
        json.dumps(geometry),
        extras.operator_ref,
        extras.operator_name,
        extras.operator_type,
        json.dumps(extras.tags, ensure_ascii=False),
        json.dumps(extras.detail, ensure_ascii=False),
    )


# ─── Applying one layer (no commit) ──────────────────────────────────────────


def _geom_sql(spec: LayerSpec) -> str:
    raw = "ST_GeomFromGeoJSON(s.geom_json)"
    if spec.family == "point":
        return f"ST_Transform(ST_SetSRID(ST_PointOnSurface(ST_MakeValid({raw})), 4326), {TARGET_SRID})"
    return (
        f"ST_Multi(ST_CollectionExtract(ST_MakeValid("
        f"ST_Transform(ST_SetSRID({raw}, 4326), {TARGET_SRID})), 3))"
    )


def _stage(session, spec: LayerSpec, rows: Iterable[tuple]) -> int:
    # ON COMMIT DROP covers the CLI; callers that never commit (tests) need this.
    session.execute(text("DROP TABLE IF EXISTS pg_temp.stg"))
    session.execute(text("DROP TABLE IF EXISTS pg_temp.stg_tag"))
    session.execute(
        text(
            """
            CREATE TEMP TABLE stg (
              source_id text NOT NULL, name text, subtype text, attrs jsonb,
              geom_json text, operator_ref text, operator_name text, operator_type text,
              tags jsonb, detail jsonb, operator_id integer, district_id integer, geom geometry
            ) ON COMMIT DROP
            """
        )
    )
    raw = session.connection().connection.driver_connection
    n = 0
    with raw.cursor() as cur:
        with cur.copy(f"COPY stg ({STAGE_COLUMNS}) FROM STDIN") as copy:
            for row in rows:
                copy.write_row(row)
                n += 1
                if n % 100_000 == 0:
                    print(f"  staged {n:,}", flush=True)
    return n


def apply_layer(
    session,
    layer: str,
    features: Iterable[dict],
    catalog_id: int,
    *,
    fail_after_rows: int | None = None,
) -> dict:
    """Upsert one layer. Caller owns the transaction. Returns row counts."""
    spec = SPECS[layer]
    kind, table = spec.kind, spec.table
    skipped = 0

    def rows() -> Iterable[tuple]:
        nonlocal skipped
        staged = 0
        for feat in features:
            row = parse_feature(spec, feat)
            if row is None:
                skipped += 1
                continue
            yield row
            staged += 1
            if fail_after_rows is not None and staged >= fail_after_rows:
                return

    staged = _stage(session, spec, rows())
    if staged == 0:
        raise ValueError(f"{layer}: no usable features in source; refusing to wipe kind '{kind}'")

    dup = session.execute(
        text("SELECT source_id, count(*) FROM stg GROUP BY 1 HAVING count(*) > 1 LIMIT 3")
    ).all()
    if dup:
        raise ValueError(f"{layer}: duplicate source_id in source file, e.g. {dup}")

    session.execute(
        text(f"UPDATE stg s SET geom = {_geom_sql(spec)}")
    )
    empty = session.execute(
        text("DELETE FROM stg WHERE geom IS NULL OR ST_IsEmpty(geom)")
    ).rowcount
    skipped += empty

    # D9: derive district_id here, in the unindexed staging table, so each feature row is
    # written once. (Updating it afterwards rewrote every row and every index: minutes for trees.)
    _district_parts(session)
    point = "s.geom" if spec.family == "point" else "ST_PointOnSurface(s.geom)"
    session.execute(
        text(
            f"UPDATE stg s SET district_id = "
            f"(SELECT min(dp.id) FROM district_parts dp WHERE ST_Intersects(dp.geom, {point}))"
        )
    )

    # Operators first, so features can reference them.
    session.execute(
        text(
            """
            INSERT INTO operator (official_ref, name, operator_type)
            SELECT DISTINCT ON (operator_ref) operator_ref, operator_name, operator_type
            FROM stg WHERE operator_ref IS NOT NULL AND operator_name IS NOT NULL
            ORDER BY operator_ref
            ON CONFLICT (official_ref) DO UPDATE
              SET name = EXCLUDED.name, operator_type = EXCLUDED.operator_type
              WHERE (operator.name, operator.operator_type)
                    IS DISTINCT FROM (EXCLUDED.name, EXCLUDED.operator_type)
            """
        )
    )
    session.execute(
        text(
            """
            INSERT INTO operator (name, operator_type)
            SELECT DISTINCT ON (operator_name) operator_name, operator_type
            FROM stg WHERE operator_ref IS NULL AND operator_name IS NOT NULL
            ORDER BY operator_name
            ON CONFLICT (name) WHERE official_ref IS NULL DO NOTHING
            """
        )
    )
    session.execute(
        text(
            """
            UPDATE stg s SET operator_id = o.id FROM operator o
            WHERE (s.operator_ref IS NOT NULL AND o.official_ref = s.operator_ref)
               OR (s.operator_ref IS NULL AND o.official_ref IS NULL AND o.name = s.operator_name)
            """
        )
    )

    existing = session.execute(
        text(
            f"SELECT count(*) FROM stg s JOIN {table} t "
            f"ON t.kind_code = :kind AND t.source_id = s.source_id"
        ),
        {"kind": kind},
    ).scalar_one()

    operator_col = ", operator_id" if spec.family == "point" else ""
    operator_val = ", s.operator_id" if spec.family == "point" else ""
    operator_set = ", operator_id = EXCLUDED.operator_id" if spec.family == "point" else ""
    distinct_cols = "name, subtype, catalog_id, district_id, attrs, geom" + operator_col
    changed = session.execute(
        text(
            f"""
            INSERT INTO {table} AS t (kind_code, source_id, name, subtype, catalog_id, district_id, attrs, geom{operator_col})
            SELECT :kind, s.source_id, s.name, s.subtype, :cid, s.district_id, s.attrs, s.geom{operator_val}
            FROM stg s
            ON CONFLICT (kind_code, source_id) DO UPDATE SET
              name = EXCLUDED.name, subtype = EXCLUDED.subtype, catalog_id = EXCLUDED.catalog_id,
              district_id = EXCLUDED.district_id, attrs = EXCLUDED.attrs, geom = EXCLUDED.geom{operator_set}
            WHERE ({", ".join("t." + c.strip() for c in distinct_cols.split(","))})
                  IS DISTINCT FROM ({", ".join("EXCLUDED." + c.strip() for c in distinct_cols.split(","))})
            """
        ),
        {"kind": kind, "cid": catalog_id},
    ).rowcount
    deleted = session.execute(
        text(
            f"""
            DELETE FROM {table} t
            WHERE t.kind_code = :kind
              AND NOT EXISTS (SELECT 1 FROM stg s WHERE s.source_id = t.source_id)
            """
        ),
        {"kind": kind},
    ).rowcount

    if fail_after_rows is not None:
        raise InjectedFailure(
            f"injected failure after {staged} staged rows "
            f"({changed} upserted, {deleted} deleted) in tx; expecting rollback"
        )

    if spec.family == "point":
        _apply_tags(session, spec)
    if spec.detail_table:
        _apply_details(session, spec)

    usable = staged - empty
    inserted_rows = usable - existing
    return {
        "staged": usable,
        "inserted": inserted_rows,
        "updated": changed - inserted_rows,
        "deleted": deleted,
        "skipped": skipped,
    }


def _district_parts(session) -> None:
    """Subdivided, indexed copy of the borough polygons for fast point-in-polygon.

    The 12 borough polygons have very many vertices; testing each point against
    the full polygons took minutes for ~430k trees (measured). Small pieces plus
    a GiST index make it a cheap index probe.
    """
    session.execute(text("DROP TABLE IF EXISTS pg_temp.district_parts"))
    session.execute(
        text("CREATE TEMP TABLE district_parts AS SELECT id, ST_Subdivide(geom, 128) AS geom FROM districts")
    )
    session.execute(text("CREATE INDEX ON district_parts USING gist (geom)"))
    session.execute(text("ANALYZE district_parts"))


def assign_districts(session, spec: LayerSpec, *, only_touched: bool) -> None:
    """Re-derive district_id for a whole kind (used when district boundaries change).

    Layer imports derive it while staging instead (see apply_layer).

    Boundary points intersect two districts; the lowest district id wins (deterministic).
    """
    _district_parts(session)
    geom = "p2.geom" if spec.family == "point" else "ST_PointOnSurface(p2.geom)"
    touched = "AND p2.updated_at = now()" if only_touched else ""
    session.execute(
        text(
            f"""
            UPDATE {spec.table} p SET district_id = x.did
            FROM (
              SELECT p2.id,
                     (SELECT min(dp.id) FROM district_parts dp
                      WHERE ST_Intersects(dp.geom, {geom})) AS did
              FROM {spec.table} p2
              WHERE p2.kind_code = :kind {touched}
            ) x
            WHERE p.id = x.id AND p.kind_code = :kind
              AND p.district_id IS DISTINCT FROM x.did
            """
        ),
        {"kind": spec.kind},
    )


def _apply_tags(session, spec: LayerSpec) -> None:
    if spec.extras is None:
        return
    session.execute(
        text(
            """
            INSERT INTO tag (category_code, label)
            SELECT DISTINCT e->>0, e->>1 FROM stg s, jsonb_array_elements(s.tags) e
            ON CONFLICT (category_code, label) DO NOTHING
            """
        )
    )
    session.execute(
        text(
            """
            CREATE TEMP TABLE stg_tag ON COMMIT DROP AS
            SELECT DISTINCT p.id AS point_id, p.kind_code, tg.id AS tag_id, tg.category_code
            FROM stg s
            JOIN amenity_points p ON p.kind_code = :kind AND p.source_id = s.source_id
            CROSS JOIN LATERAL jsonb_array_elements(s.tags) e
            JOIN tag tg ON tg.category_code = e->>0 AND tg.label = e->>1
            """
        ),
        {"kind": spec.kind},
    )
    session.execute(
        text(
            """
            INSERT INTO amenity_point_tag (point_id, kind_code, tag_id, category_code)
            SELECT point_id, kind_code, tag_id, category_code FROM stg_tag
            ON CONFLICT (point_id, tag_id) DO NOTHING
            """
        )
    )
    session.execute(
        text(
            """
            DELETE FROM amenity_point_tag a
            WHERE a.kind_code = :kind
              AND NOT EXISTS (SELECT 1 FROM stg_tag t WHERE t.point_id = a.point_id AND t.tag_id = a.tag_id)
            """
        ),
        {"kind": spec.kind},
    )


def _apply_details(session, spec: LayerSpec) -> None:
    table = spec.detail_table
    cols = DETAIL_COLUMNS[table]
    names = ", ".join(c for c, _ in cols)
    if table == "tree_detail":
        session.execute(
            text(
                """
                INSERT INTO tree_species (botanical_name, german_name, genus)
                SELECT DISTINCT ON (detail->>'botanical_name')
                       detail->>'botanical_name', detail->>'german_name', detail->>'genus'
                FROM stg WHERE detail->>'botanical_name' IS NOT NULL
                ORDER BY detail->>'botanical_name'
                ON CONFLICT (botanical_name) DO UPDATE
                  SET german_name = EXCLUDED.german_name, genus = EXCLUDED.genus
                  WHERE (tree_species.german_name, tree_species.genus)
                        IS DISTINCT FROM (EXCLUDED.german_name, EXCLUDED.genus)
                """
            )
        )
    session.execute(
        text(
            f"""
            INSERT INTO {table} AS t (point_id, kind_code, {names})
            SELECT p.id, p.kind_code, {", ".join(expr for _, expr in cols)}
            FROM stg s
            JOIN amenity_points p ON p.kind_code = :kind AND p.source_id = s.source_id
            ON CONFLICT (point_id, kind_code) DO UPDATE SET
              {", ".join(f"{c} = EXCLUDED.{c}" for c, _ in cols)}
            WHERE ({", ".join("t." + c for c, _ in cols)})
                  IS DISTINCT FROM ({", ".join("EXCLUDED." + c for c, _ in cols)})
            """
        ),
        {"kind": spec.kind},
    )


# ─── Boundaries ──────────────────────────────────────────────────────────────

_BOUNDARY_GEOM = (
    "ST_Multi(ST_CollectionExtract(ST_MakeValid("
    "ST_Transform(ST_SetSRID(ST_GeomFromGeoJSON(:geom), 4326), :srid)), 3))"
)


def _upsert_boundary(
    session, table: str, features: list[dict], catalog_id: int, id_keys, name_keys
) -> tuple[int, int]:
    """Upsert boundaries; returns (features read, rows actually inserted or changed)."""
    n = changed = 0
    for feat in features:
        props = feat.get("properties") or {}
        official = clean_text(first_prop(props, id_keys), 32)
        if official is None or not feat.get("geometry"):
            continue
        result = session.execute(
            text(
                f"""
                INSERT INTO {table} AS t (official_id, name, catalog_id, attrs, geom)
                VALUES (:official_id, :name, :cid, CAST(:attrs AS jsonb), {_BOUNDARY_GEOM})
                ON CONFLICT (official_id) DO UPDATE SET
                  name = EXCLUDED.name, catalog_id = EXCLUDED.catalog_id,
                  attrs = EXCLUDED.attrs, geom = EXCLUDED.geom
                WHERE (t.name, t.catalog_id, t.attrs, t.geom)
                      IS DISTINCT FROM (EXCLUDED.name, EXCLUDED.catalog_id, EXCLUDED.attrs, EXCLUDED.geom)
                """
            ),
            {
                "official_id": official,
                "name": clean_text(first_prop(props, name_keys), 128) or "Unknown",
                "cid": catalog_id,
                "attrs": attrs_json(props),
                "geom": json.dumps(feat["geometry"]),
                "srid": TARGET_SRID,
            },
        )
        n += 1
        changed += result.rowcount
    return n, changed


def apply_districts(session, features: list[dict], catalog_id: int) -> dict:
    n, changed = _upsert_boundary(
        session, "districts", features, catalog_id,
        ("Gemeinde_schluessel", "official_id", "name"), ("Gemeinde_name", "name"),
    )
    if changed == 0:  # boundaries unchanged: derived district_id values are still valid
        return {"staged": n, "inserted": 0, "updated": 0, "deleted": 0, "skipped": len(features) - n}
    # Boundaries changed: re-derive district_id for every kind and neighborhood.
    for spec in SPECS.values():
        assign_districts(session, spec, only_touched=False)
    session.execute(
        text(
            "UPDATE neighborhoods n SET district_id = x.did FROM ("
            " SELECT n2.id, (SELECT d.id FROM districts d WHERE ST_Intersects(ST_PointOnSurface(n2.geom), d.geom)"
            "  ORDER BY d.id LIMIT 1) AS did FROM neighborhoods n2) x"
            " WHERE n.id = x.id AND n.district_id IS DISTINCT FROM x.did"
        )
    )
    return {"staged": n, "inserted": None, "updated": None, "deleted": 0, "skipped": len(features) - n}


def apply_neighborhoods(session, features: list[dict], catalog_id: int) -> dict:
    n, _ = _upsert_boundary(
        session, "neighborhoods", features, catalog_id,
        ("sch", "uuid", "official_id", "name"), ("nam", "name"),
    )
    session.execute(
        text(
            "UPDATE neighborhoods n SET district_id = x.did FROM ("
            " SELECT n2.id, (SELECT d.id FROM districts d WHERE ST_Intersects(ST_PointOnSurface(n2.geom), d.geom)"
            "  ORDER BY d.id LIMIT 1) AS did FROM neighborhoods n2) x"
            " WHERE n.id = x.id AND n.district_id IS DISTINCT FROM x.did"
        )
    )
    return {"staged": n, "inserted": None, "updated": None, "deleted": 0, "skipped": len(features) - n}


# ─── CLI: one transaction per layer + import_run audit ───────────────────────

V2_LAYERS = ["districts", "neighborhoods", *[l for l in DEFAULT_ORDER if l in SPECS]]


def _start_run(catalog_id: int) -> int:
    with SessionLocal() as s:
        run_id = s.execute(
            text("INSERT INTO import_run (catalog_id) VALUES (:c) RETURNING id"), {"c": catalog_id}
        ).scalar_one()
        s.commit()
    return run_id


def _finish_run(run_id: int, status: str, counts: dict | None, error: str | None) -> None:
    counts = counts or {}
    with SessionLocal() as s:
        s.execute(
            text(
                """
                UPDATE import_run SET finished_at = now(), status = :status,
                  rows_inserted = :i, rows_updated = :u, rows_deleted = :d, error = :e
                WHERE id = :id
                """
            ),
            {
                "status": status, "id": run_id, "e": error,
                "i": counts.get("inserted"), "u": counts.get("updated"), "d": counts.get("deleted"),
            },
        )
        s.commit()


def import_layer(layer: str, source: str, fail_after_rows: int | None = None) -> dict:
    meta = CATALOG[layer]
    path = resolve_path(layer, source)
    print(f"[{layer}] reading {path.name}", flush=True)
    features = load_geojson_features(path)

    with SessionLocal() as s:
        catalog_id = upsert_catalog(s, meta)
        s.commit()
    run_id = _start_run(catalog_id)

    started = time.time()
    session = SessionLocal()
    try:
        if layer == "districts":
            counts = apply_districts(session, features, catalog_id)
        elif layer == "neighborhoods":
            counts = apply_neighborhoods(session, features, catalog_id)
        else:
            counts = apply_layer(session, layer, features, catalog_id, fail_after_rows=fail_after_rows)
        session.commit()
    except Exception as exc:  # noqa: BLE001
        session.rollback()
        _finish_run(run_id, "failed", None, f"{type(exc).__name__}: {exc}"[:2000])
        print(f"[{layer}] FAILED, rolled back: {exc}", file=sys.stderr, flush=True)
        raise
    finally:
        session.close()

    _finish_run(run_id, "committed", counts, None)
    print(f"[{layer}] committed in {time.time() - started:.1f}s: {counts}", flush=True)
    return counts


def analyze(layers: list[str]) -> None:
    tables = {"districts", "neighborhoods"} | {SPECS[l].table for l in layers if l in SPECS}
    extra = {"operator", "tag", "amenity_point_tag", "tree_species", "tree_detail", "kita_detail", "ev_charger_detail"}
    with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
        for t in sorted(tables | extra):
            conn.execute(text(f"ANALYZE {t}"))
        # borough_amenity_stats (migration 0010) feeds the density analysis.
        if conn.execute(text("SELECT to_regclass('borough_amenity_stats')")).scalar() is not None:
            conn.execute(text("REFRESH MATERIALIZED VIEW CONCURRENTLY borough_amenity_stats"))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", choices=["open", "samples"], default="open")
    parser.add_argument("--layers", help="Comma-separated layer slugs (default: all).")
    parser.add_argument(
        "--fail-after-rows", type=int,
        help="Demo: stage only N rows, apply them, then raise; the layer must roll back.",
    )
    args = parser.parse_args()
    selected = [s.strip() for s in args.layers.split(",") if s.strip()] if args.layers else V2_LAYERS
    for layer in selected:
        if layer not in V2_LAYERS:
            raise SystemExit(f"Unknown layer: {layer}")
    ordered = [l for l in V2_LAYERS if l in selected]  # districts and neighborhoods first
    for layer in ordered:
        import_layer(layer, args.source, args.fail_after_rows)
    analyze(ordered)


if __name__ == "__main__":
    main()
