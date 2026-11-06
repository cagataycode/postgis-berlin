from __future__ import annotations

import json
import re
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db import get_db_ro
from app.sql_loader import SQL_DIR, load_sql

router = APIRouter(prefix="/sql", tags=["sql"])

STATEMENT_TIMEOUT_MS = 5000
ROW_CAP = 500

# Block multi-statements and write/admin verbs; learning playground is SELECT-only.
_FORBIDDEN = re.compile(
    r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|CREATE|TRUNCATE|GRANT|REVOKE|COPY|"
    r"CALL|EXECUTE|DO|VACUUM|ANALYZE|REINDEX|CLUSTER|COMMENT|SECURITY|"
    r"SET\s+ROLE|SET\s+SESSION|RESET|LOAD|LISTEN|NOTIFY|PREPARE|DEALLOCATE|"
    r"LOCK|UNLISTEN|DISCARD|REASSIGN|REFRESH\s+MATERIALIZED|INTO|"
    r"FOR\s+UPDATE|FOR\s+NO\s+KEY\s+UPDATE|FOR\s+SHARE|FOR\s+KEY\s+SHARE|"
    r"SET_CONFIG|PG_READ_FILE|PG_LS_DIR|PG_STAT_FILE|PG_TERMINATE_BACKEND|"
    r"PG_CANCEL_BACKEND|LO_IMPORT|LO_EXPORT)\b",
    re.IGNORECASE,
)
# Comments and string/quoted-identifier literals: stripped before the forbidden
# scan so e.g. 'not a delete' or a comment mentioning DELETE stays allowed.
_COMMENTS_AND_LITERALS = re.compile(
    r"--[^\n]*"  # line comment
    r"|/\*.*?\*/"  # block comment
    r"|'(?:[^']|'')*'"  # string literal with '' escape
    r'|"(?:[^"]|"")*"',  # quoted identifier with "" escape
    re.DOTALL,
)
_NAME_OK = re.compile(r"^[a-z0-9_]+\.sql$")


def _allowed_sql_names() -> set[str]:
    return {p.name for p in SQL_DIR.glob("*.sql")}


@router.get("/{name}")
def get_sql_file(name: str) -> dict[str, str]:
    if not _NAME_OK.match(name) or name not in _allowed_sql_names():
        raise HTTPException(status_code=404, detail="Unknown SQL file")
    return {"name": name, "sql": load_sql(name)}


class RunSqlBody(BaseModel):
    sql: str = Field(..., min_length=1, max_length=20_000)
    explain: bool = False


def _validate_select(sql: str) -> str:
    cleaned = sql.strip().rstrip(";").strip()
    if not cleaned:
        raise HTTPException(status_code=400, detail="Empty SQL")
    # Strip comments/literals before multi-statement + verb checks so a
    # semicolon or "DELETE" inside a comment does not reject a valid SELECT.
    scan = _COMMENTS_AND_LITERALS.sub(" ", cleaned)
    if ";" in scan:
        raise HTTPException(status_code=400, detail="Only a single statement is allowed")
    if _FORBIDDEN.search(scan):
        raise HTTPException(status_code=400, detail="Only SELECT / WITH … SELECT is allowed")
    head = cleaned
    while True:
        nxt = re.sub(r"^/\*.*?\*/", "", head, count=1, flags=re.DOTALL).lstrip()
        nxt = re.sub(r"^--[^\n]*(?:\n|$)", "", nxt, count=1).lstrip()
        if nxt == head:
            break
        head = nxt
    upper = head.upper()
    if not (upper.startswith("SELECT") or upper.startswith("WITH")):
        raise HTTPException(status_code=400, detail="Query must start with SELECT or WITH")
    return cleaned


def _cell_to_jsonable(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, (dict, list)):
        return value
    if hasattr(value, "isoformat"):
        try:
            return value.isoformat()
        except Exception:  # noqa: BLE001
            pass
    return str(value)


def _try_parse_geojson_value(value: Any) -> dict[str, Any] | None:
    if isinstance(value, dict) and value.get("type") in (
        "FeatureCollection",
        "Feature",
        "Point",
        "MultiPoint",
        "LineString",
        "MultiLineString",
        "Polygon",
        "MultiPolygon",
        "GeometryCollection",
    ):
        return value
    if isinstance(value, str) and value.lstrip().startswith("{"):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return None
        if isinstance(parsed, dict) and parsed.get("type"):
            return parsed
    return None


def _geojson_from_rows(columns: list[str], rows: list[list[Any]]) -> dict[str, Any] | None:
    """Build a FeatureCollection from result columns that look like GeoJSON."""
    features: list[dict[str, Any]] = []

    for row in rows:
        props: dict[str, Any] = {}
        geom: dict[str, Any] | None = None
        feature: dict[str, Any] | None = None
        collection: dict[str, Any] | None = None

        for col, raw in zip(columns, row):
            parsed = _try_parse_geojson_value(raw)
            if parsed is None:
                props[col] = raw
                continue
            t = parsed.get("type")
            if t == "FeatureCollection":
                collection = parsed
            elif t == "Feature":
                feature = parsed
            elif t in (
                "Point",
                "MultiPoint",
                "LineString",
                "MultiLineString",
                "Polygon",
                "MultiPolygon",
                "GeometryCollection",
            ):
                geom = parsed
            else:
                props[col] = parsed

        if collection and isinstance(collection.get("features"), list):
            features.extend(collection["features"])
            continue
        if feature:
            features.append(feature)
            continue
        if geom:
            features.append({"type": "Feature", "properties": props, "geometry": geom})

    if not features:
        return None
    return {"type": "FeatureCollection", "features": features}


@router.post("/run")
def run_sql(body: RunSqlBody, db: Session = Depends(get_db_ro)) -> dict[str, Any]:
    cleaned = _validate_select(body.sql)
    query = f"EXPLAIN (ANALYZE, BUFFERS)\n{cleaned}" if body.explain else cleaned

    try:
        db.execute(text(f"SET LOCAL statement_timeout = '{STATEMENT_TIMEOUT_MS}'"))
        result = db.execute(text(query))
        if body.explain:
            plan_lines = [str(row[0]) for row in result.fetchall()]
            db.commit()
            return {
                "explain": True,
                "plan": "\n".join(plan_lines),
                "columns": [],
                "rows": [],
                "row_count": len(plan_lines),
                "truncated": False,
                "geojson": None,
            }

        columns = list(result.keys())
        raw_rows = result.fetchmany(ROW_CAP + 1)
        truncated = len(raw_rows) > ROW_CAP
        raw_rows = raw_rows[:ROW_CAP]
        rows = [[_cell_to_jsonable(c) for c in row] for row in raw_rows]
        geojson = _geojson_from_rows(columns, rows)
        db.commit()
        return {
            "explain": False,
            "plan": None,
            "columns": columns,
            "rows": rows,
            "row_count": len(rows),
            "truncated": truncated,
            "geojson": geojson,
        }
    except HTTPException:
        db.rollback()
        raise
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
