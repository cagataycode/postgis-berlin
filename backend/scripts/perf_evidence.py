#!/usr/bin/env python3
"""Phase 7: collect EXPLAIN (ANALYZE, BUFFERS) evidence for the schema v2 design choices.

Writes one text file per experiment to docs/schema-v2/explain/. Needs a database
loaded by scripts/import_v2.py (the real open data, ~980k features). Comparison
copies live in a scratch schema `perf`, which is dropped at the end; the real
tables are only read.

    DATABASE_URL=... python -m scripts.perf_evidence [--only 1,3] [--keep]
"""

from __future__ import annotations

import argparse
import re
import sys
import time
from pathlib import Path

from sqlalchemy import create_engine, text

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.config import settings  # noqa: E402

OUT = Path(__file__).resolve().parents[2] / "docs" / "schema-v2" / "explain"

BBOX = "ST_Transform(ST_MakeEnvelope(13.38, 52.50, 13.42, 52.53, 4326), 25833)"
PROBE = "ST_Transform(ST_SetSRID(ST_MakePoint(13.405, 52.52), 4326), 25833)"

engine = create_engine(settings.database_url, isolation_level="AUTOCOMMIT")


def sql(conn, stmt: str, **params):
    return conn.execute(text(stmt), params)


def plan(conn, query: str, runs: int = 2) -> tuple[str, float]:
    """EXPLAIN ANALYZE the query `runs` times; return the last (warm) plan and its execution ms."""
    last = ""
    for _ in range(runs):
        rows = conn.execute(text(f"EXPLAIN (ANALYZE, BUFFERS) {query}")).fetchall()
        last = "\n".join(r[0] for r in rows)
    m = re.search(r"Execution Time: ([\d.]+) ms", last)
    return last, float(m.group(1)) if m else float("nan")


class Report:
    def __init__(self, name: str, title: str, question: str):
        self.name, self.parts, self.summary = name, [], []
        self.parts.append(f"# {title}\n\n{question}\n")

    def case(self, conn, label: str, query: str, note: str = "") -> float:
        text_plan, ms = plan(conn, query)
        self.parts.append(f"\n## {label}\n\n```sql\n{query.strip()}\n```\n\n```text\n{text_plan}\n```\n")
        if note:
            self.parts.append(f"{note}\n")
        self.summary.append((label, ms))
        return ms

    def text(self, body: str) -> None:
        self.parts.append(f"\n{body}\n")

    def save(self) -> None:
        self.parts.append("\n## Summary (warm execution time)\n\n| Case | ms |\n| --- | ---: |\n")
        self.parts.extend(f"| {l} | {ms:.1f} |\n" for l, ms in self.summary)
        OUT.mkdir(parents=True, exist_ok=True)
        (OUT / f"{self.name}.md").write_text("".join(self.parts), encoding="utf-8")
        print(f"[{self.name}] " + "; ".join(f"{l}: {ms:.1f} ms" for l, ms in self.summary), flush=True)


def prep(conn) -> None:
    sql(conn, "DROP SCHEMA IF EXISTS perf CASCADE")
    sql(conn, "CREATE SCHEMA perf")
    sql(conn, "ANALYZE")


def exp1_partition_pruning(conn) -> None:
    r = Report(
        "01-partition-pruning",
        "1. Street trees in a bbox: partition pruning",
        "Is partitioning `amenity_points` by `kind_code` worth it? Same bbox query on the partitioned table, "
        "without the kind filter, and on a non-partitioned copy of all point rows (one table, GiST on geom, "
        "btree on kind_code).",
    )
    sql(conn, "CREATE TABLE perf.points_flat AS SELECT * FROM amenity_points")
    sql(conn, "CREATE INDEX ON perf.points_flat USING gist (geom)")
    sql(conn, "CREATE INDEX ON perf.points_flat (kind_code)")
    sql(conn, "ANALYZE perf.points_flat")
    q = f"SELECT p.id FROM {{t}} p WHERE {{k}} p.geom && {BBOX}"
    r.case(conn, "A. partitioned, kind filter", q.format(t="amenity_points", k="p.kind_code = 'street_tree' AND"),
           "Only `amenity_points_street_tree` is scanned (the other partitions are pruned at plan time).")
    r.case(conn, "B. partitioned, no kind filter", q.format(t="amenity_points", k=""),
           "Without the kind filter every partition's GiST index is probed: the filter is what makes pruning work.")
    r.case(conn, "C. non-partitioned copy, kind filter", q.format(t="perf.points_flat", k="p.kind_code = 'street_tree' AND"),
           "One big GiST holds all 976k points; the kind filter is applied after the index probe.")
    r.save()


def exp2_composite_gist(conn) -> None:
    r = Report(
        "02-composite-gist",
        "2. Composite GiST (kind_code, geom) vs plain GiST on the `other` partition",
        "`amenity_points_other` holds the 13 small kinds (13k rows). Does a `btree_gist` composite index "
        "beat a plain GiST on `geom` plus the kind filter?",
    )
    sql(conn, "CREATE EXTENSION IF NOT EXISTS btree_gist")
    sql(conn, "CREATE TABLE perf.other_plain AS SELECT * FROM amenity_points_other")
    sql(conn, "CREATE TABLE perf.other_comp AS SELECT * FROM amenity_points_other")
    sql(conn, "CREATE INDEX ix_plain ON perf.other_plain USING gist (geom)")
    sql(conn, "CREATE INDEX ix_comp ON perf.other_comp USING gist (kind_code, geom)")
    sql(conn, "ANALYZE perf.other_plain")
    sql(conn, "ANALYZE perf.other_comp")
    for kind, label in (("kita", "kita (2.9k rows)"), ("ev_charger", "ev_charger (5k rows)"), ("hospital", "hospital (111 rows)")):
        for t, name in (("perf.other_plain", "plain GiST"), ("perf.other_comp", "composite GiST")):
            r.case(conn, f"{kind}, {name}",
                   f"SELECT p.id FROM {t} p WHERE p.kind_code = '{kind}' AND p.geom && {BBOX}")
    sizes = sql(conn, "SELECT pg_relation_size('perf.ix_plain'), pg_relation_size('perf.ix_comp')").one()
    r.text(f"Index size: plain {sizes[0] / 1024:.0f} kB, composite {sizes[1] / 1024:.0f} kB.")
    r.save()


def exp3_tag_index(conn) -> None:
    r = Report(
        "03-tag-junction-index",
        "3. Tag filter: junction index (tag_id, point_id)",
        "Kitas carrying tag 16 (Situationsansatz, the most common). The primary key is (point_id, tag_id), "
        "so it cannot serve a lookup by tag_id; the extra index `(tag_id, point_id)` does.",
    )
    sql(conn, "CREATE TABLE perf.apt_noidx AS SELECT point_id, kind_code, tag_id, category_code FROM amenity_point_tag")
    sql(conn, "ALTER TABLE perf.apt_noidx ADD PRIMARY KEY (point_id, tag_id)")
    sql(conn, "ANALYZE perf.apt_noidx")
    q = "SELECT p.id FROM amenity_points p WHERE p.kind_code = 'kita' AND p.id IN (SELECT point_id FROM {t} WHERE tag_id = 16 AND kind_code = 'kita')"
    r.case(conn, "A. with index (tag_id, point_id)", q.format(t="amenity_point_tag"))
    r.case(conn, "B. without it (PK only)", q.format(t="perf.apt_noidx"))
    rare = "SELECT point_id FROM {t} WHERE tag_id = 14"
    r.case(conn, "C. rare tag 14, with index", rare.format(t="amenity_point_tag"))
    r.case(conn, "D. rare tag 14, PK only", rare.format(t="perf.apt_noidx"))
    r.save()


def exp4_gin(conn) -> None:
    r = Report(
        "04-gin-attrs",
        "4. `attrs @>` : GIN (jsonb_path_ops) vs sequential scan",
        "Containment lookups on the raw source properties. Real indexes vs copies of the same rows without GIN.",
    )
    sql(conn, "CREATE TABLE perf.other_nogin AS SELECT * FROM amenity_points_other")
    sql(conn, "CREATE TABLE perf.street_nogin AS SELECT * FROM amenity_points_street_tree")
    sql(conn, "ANALYZE perf.other_nogin")
    sql(conn, "ANALYZE perf.street_nogin")
    a = """{"betreiber": "Wall GmbH"}"""
    r.case(conn, "A. EV chargers by operator, GIN (amenity_points_other)",
           f"SELECT id FROM amenity_points_other WHERE attrs @> '{a}'")
    r.case(conn, "B. same, no GIN", f"SELECT id FROM perf.other_nogin WHERE attrs @> '{a}'")
    b = """{"gattung": "Ginkgo"}"""
    r.case(conn, "C. street trees, genus Ginkgo, GIN (435k rows)",
           f"SELECT id FROM amenity_points_street_tree WHERE attrs @> '{b}'")
    r.case(conn, "D. same, no GIN", f"SELECT id FROM perf.street_nogin WHERE attrs @> '{b}'")
    sizes = sql(conn, "SELECT pg_relation_size('amenity_points_street_tree_attrs_idx'), "
                      "pg_relation_size('amenity_points_street_tree')").one()
    r.text(f"GIN index on street trees: {sizes[0] / 1e6:.0f} MB for a {sizes[1] / 1e6:.0f} MB table.")
    r.save()


def exp5_knn(conn) -> None:
    r = Report(
        "05-knn",
        "5. Nearest neighbours: index-ordered scan",
        "Five nearest street trees to a point in Mitte: `ORDER BY geom <-> point LIMIT 5` (GiST distance "
        "ordering) vs `ORDER BY ST_Distance(geom, point)` (no index, full sort).",
    )
    r.case(conn, "A. KNN operator <->",
           f"SELECT id, ST_Distance(geom, {PROBE}) AS d FROM amenity_points WHERE kind_code = 'street_tree' "
           f"ORDER BY geom <-> {PROBE} LIMIT 5")
    r.case(conn, "B. ORDER BY ST_Distance",
           f"SELECT id, ST_Distance(geom, {PROBE}) AS d FROM amenity_points WHERE kind_code = 'street_tree' "
           f"ORDER BY ST_Distance(geom, {PROBE}) LIMIT 5")
    r.case(conn, "C. production query: one LATERAL KNN per kind",
           open(Path(__file__).resolve().parents[1] / "sql" / "analysis_nearest_amenities.sql").read()
           .replace(":lon", "13.405").replace(":lat", "52.52"))
    r.save()


def exp6_load_cost(conn) -> None:
    r = Report(
        "06-gin-load-cost",
        "6. Cost of the GIN index on bulk load",
        "Insert 50k street-tree rows into two copies of the partition: all indexes vs the same without GIN "
        "on `attrs`. Times are wall-clock for the INSERT.",
    )
    for name, gin in (("ld_all", True), ("ld_nogin", False)):
        sql(conn, f"CREATE TABLE perf.{name} (LIKE amenity_points_street_tree INCLUDING DEFAULTS)")
        sql(conn, f"CREATE INDEX ON perf.{name} USING gist (geom)")
        sql(conn, f"CREATE INDEX ON perf.{name} (district_id)")
        sql(conn, f"CREATE INDEX ON perf.{name} (operator_id)")
        sql(conn, f"CREATE INDEX ON perf.{name} (catalog_id)")
        sql(conn, f"CREATE UNIQUE INDEX ON perf.{name} (id, kind_code)")
        sql(conn, f"CREATE UNIQUE INDEX ON perf.{name} (kind_code, source_id)")
        if gin:
            sql(conn, f"CREATE INDEX ON perf.{name} USING gin (attrs jsonb_path_ops)")
    rows = []
    for name in ("ld_all", "ld_nogin"):
        t = time.time()
        sql(conn, f"INSERT INTO perf.{name} SELECT * FROM amenity_points_street_tree ORDER BY id LIMIT 50000")
        rows.append((name, time.time() - t))
    r.summary = [("with GIN (7 indexes)", rows[0][1] * 1000), ("without GIN (6 indexes)", rows[1][1] * 1000)]
    r.text(f"50,000 rows: with GIN {rows[0][1]:.1f} s, without {rows[1][1]:.1f} s "
           f"({rows[0][1] / rows[1][1]:.1f}x).")
    r.save()


def exp7_tree_stats(conn) -> None:
    r = Report(
        "07-trees-by-borough",
        "7. `/analyses/trees-by-borough` (the slow report)",
        "The query behind the endpoint, as shipped in phase 4.",
    )
    live = (
        "SELECT d.id AS district_id, d.name AS district_name, COUNT(*)::int AS tree_count, "
        "COUNT(DISTINCT td.species_id)::int AS species_count, "
        "percentile_cont(0.5) WITHIN GROUP (ORDER BY td.planting_year)::float AS median_planting_year, "
        "mode() WITHIN GROUP (ORDER BY sp.genus) AS top_genus, "
        "percentile_cont(0.5) WITHIN GROUP (ORDER BY td.height_m)::float AS median_height_m "
        "FROM tree_detail td JOIN amenity_points p ON p.id = td.point_id AND p.kind_code = td.kind_code "
        "JOIN districts d ON d.id = p.district_id LEFT JOIN tree_species sp ON sp.id = td.species_id "
        "GROUP BY d.id, d.name ORDER BY d.name"
    )
    r.case(conn, "A. live query (phase 4 version)", live,
           "Two sorts spill to disk (work_mem 4 MB) and ~88k pages are read: the cost is the ordered-set "
           "aggregates over 962k rows, not a missing index.")
    r.case(conn, "B. read from materialized view borough_tree_stats",
           "SELECT * FROM borough_tree_stats ORDER BY district_name",
           "Refreshed once per import (about the cost of A); the API reads it in well under a millisecond.")
    r.save()


EXPERIMENTS = {1: exp1_partition_pruning, 2: exp2_composite_gist, 3: exp3_tag_index, 4: exp4_gin,
               5: exp5_knn, 6: exp6_load_cost, 7: exp7_tree_stats}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--only", help="comma-separated experiment numbers")
    ap.add_argument("--keep", action="store_true", help="keep the scratch schema `perf`")
    args = ap.parse_args()
    chosen = [int(x) for x in args.only.split(",")] if args.only else sorted(EXPERIMENTS)
    with engine.connect() as conn:
        prep(conn)
        try:
            for n in chosen:
                EXPERIMENTS[n](conn)
        finally:
            if not args.keep:
                sql(conn, "DROP SCHEMA IF EXISTS perf CASCADE")


if __name__ == "__main__":
    main()
