"""Cutover: drop the 15 legacy per-layer tables (replaced by amenity_points / amenity_areas).

Their rows live in the v2 tables (migration 0009, scripts/import_v2.py); no
compatibility views are kept. downgrade() recreates the tables empty, in the
shape the legacy migrations gave them; re-run an importer for data.
"""

import sqlalchemy as sa
from alembic import op
from geoalchemy2 import Geometry
from sqlalchemy.dialects import postgresql

revision = "0011_drop_legacy"
down_revision = "0010_v2_analytics"
branch_labels = None
depends_on = None

# (table, type column, geometry type)
LEGACY = (
    ("green_spaces", "space_type", "MULTIPOLYGON"),
    ("cemeteries", "denomination", "MULTIPOLYGON"),
    ("playgrounds", "space_type", "MULTIPOLYGON"),
    ("schools", "school_type", "POINT"),
    ("kitas", "facility_type", "POINT"),
    ("hospitals", "hospital_type", "POINT"),
    ("trees", "species", "POINT"),
    ("park_trees", "species", "POINT"),
    ("bike_parking", "facility_type", "POINT"),
    ("ev_chargers", "charger_type", "POINT"),
    ("drinking_fountains", "fountain_type", "POINT"),
    ("bathing_waters", "quality_rating", "POINT"),
    ("toilets", "facility_type", "POINT"),
    ("sports_facilities", "facility_type", "POINT"),
    ("park_and_ride", "facility_type", "POINT"),
)


def upgrade() -> None:
    for table, _, _ in LEGACY:
        op.drop_table(table)


def downgrade() -> None:
    for table, type_col, geom_type in LEGACY:
        op.create_table(
            table,
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("source_id", sa.String(128)),
            sa.Column("name", sa.String(255)),
            sa.Column(type_col, sa.String(128)),
            sa.Column("catalog_id", sa.Integer(), sa.ForeignKey("dataset_catalog.id"), nullable=False),
            sa.Column("district_id", sa.Integer(), sa.ForeignKey("districts.id")),
            sa.Column(
                "attrs",
                postgresql.JSONB(astext_type=sa.Text()),
                nullable=False,
                server_default=sa.text("'{}'::jsonb"),
            ),
            sa.Column("geom", Geometry(geometry_type=geom_type, srid=25833), nullable=False),
        )
        op.create_index(f"ix_{table}_geom", table, ["geom"], postgresql_using="gist")
        op.create_index(f"ix_{table}_district_id", table, ["district_id"])
