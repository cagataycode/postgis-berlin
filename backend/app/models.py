"""ORM models for schema v2 (migration 0009).

Rule of thumb: the ORM reads entities and their relationships (feature, tags,
operator, detail); spatial and analytical queries are hand-written SQL in
backend/sql/.
"""

from datetime import date, datetime

from geoalchemy2 import Geometry
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    Numeric,
    SmallInteger,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class DatasetCatalog(Base):
    __tablename__ = "dataset_catalog"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    slug: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    source_organization: Mapped[str | None] = mapped_column(String(255))
    source_url: Mapped[str | None] = mapped_column(Text)
    license_text: Mapped[str | None] = mapped_column(Text)
    source_vintage: Mapped[date | None] = mapped_column(Date)
    imported_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    srid: Mapped[int] = mapped_column(Integer, nullable=False, default=25833)
    geometry_type: Mapped[str | None] = mapped_column(String(64))
    coverage_caveat: Mapped[str | None] = mapped_column(Text)


def _attrs_col() -> Mapped[dict]:
    return mapped_column(JSONB, nullable=False, server_default="{}")


class District(Base):
    __tablename__ = "districts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    official_id: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    catalog_id: Mapped[int] = mapped_column(ForeignKey("dataset_catalog.id"), nullable=False)
    attrs: Mapped[dict] = _attrs_col()
    geom = mapped_column(Geometry(geometry_type="MULTIPOLYGON", srid=25833), nullable=False)


class Neighborhood(Base):
    __tablename__ = "neighborhoods"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    official_id: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    catalog_id: Mapped[int] = mapped_column(ForeignKey("dataset_catalog.id"), nullable=False)
    district_id: Mapped[int | None] = mapped_column(ForeignKey("districts.id"))
    attrs: Mapped[dict] = _attrs_col()
    geom = mapped_column(Geometry(geometry_type="MULTIPOLYGON", srid=25833), nullable=False)


class AmenityKind(Base):
    __tablename__ = "amenity_kind"

    code: Mapped[str] = mapped_column(String(64), primary_key=True)
    label: Mapped[str] = mapped_column(String(128), nullable=False)
    geom_family: Mapped[str] = mapped_column(String(16), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)

    tag_categories: Mapped[list["TagCategory"]] = relationship(
        secondary="kind_tag_category", back_populates="kinds"
    )


class Operator(Base):
    __tablename__ = "operator"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    official_ref: Mapped[str | None] = mapped_column(String(64), unique=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    operator_type: Mapped[str | None] = mapped_column(String(64))


class TreeSpecies(Base):
    __tablename__ = "tree_species"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    botanical_name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    german_name: Mapped[str | None] = mapped_column(String(255))
    genus: Mapped[str | None] = mapped_column(String(128))


class TagCategory(Base):
    __tablename__ = "tag_category"

    code: Mapped[str] = mapped_column(String(64), primary_key=True)
    label: Mapped[str] = mapped_column(String(128), nullable=False)

    tags: Mapped[list["Tag"]] = relationship(back_populates="category")
    kinds: Mapped[list[AmenityKind]] = relationship(
        secondary="kind_tag_category", back_populates="tag_categories"
    )


class KindTagCategory(Base):
    """M:N #2: which tag categories are allowed on which kind."""

    __tablename__ = "kind_tag_category"

    kind_code: Mapped[str] = mapped_column(ForeignKey("amenity_kind.code"), primary_key=True)
    category_code: Mapped[str] = mapped_column(ForeignKey("tag_category.code"), primary_key=True)


class Tag(Base):
    __tablename__ = "tag"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    category_code: Mapped[str] = mapped_column(ForeignKey("tag_category.code"), nullable=False)
    label: Mapped[str] = mapped_column(String(255), nullable=False)

    category: Mapped[TagCategory] = relationship(back_populates="tags")


class AmenityPoint(Base):
    """Partitioned parent table (LIST on kind_code); composite PK (id, kind_code)."""

    __tablename__ = "amenity_points"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    kind_code: Mapped[str] = mapped_column(String(64), primary_key=True)
    geom_family: Mapped[str] = mapped_column(String(16), nullable=False, server_default="point")
    source_id: Mapped[str] = mapped_column(String(128), nullable=False)
    name: Mapped[str | None] = mapped_column(String(255))
    subtype: Mapped[str | None] = mapped_column(String(128))
    catalog_id: Mapped[int] = mapped_column(ForeignKey("dataset_catalog.id"), nullable=False)
    district_id: Mapped[int | None] = mapped_column(ForeignKey("districts.id"))
    operator_id: Mapped[int | None] = mapped_column(ForeignKey("operator.id"))
    attrs: Mapped[dict] = _attrs_col()
    geom = mapped_column(Geometry(geometry_type="POINT", srid=25833), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        ForeignKeyConstraint(["kind_code", "geom_family"], ["amenity_kind.code", "amenity_kind.geom_family"]),
    )

    kind: Mapped[AmenityKind] = relationship(viewonly=True)
    catalog: Mapped[DatasetCatalog] = relationship()
    district: Mapped[District | None] = relationship()
    operator: Mapped[Operator | None] = relationship()
    tag_links: Mapped[list["AmenityPointTag"]] = relationship(
        back_populates="point", cascade="all, delete-orphan", passive_deletes=True
    )
    tags: Mapped[list[Tag]] = relationship(
        secondary="amenity_point_tag", viewonly=True, order_by="Tag.id"
    )
    tree_detail: Mapped["TreeDetail | None"] = relationship(back_populates="point", uselist=False)
    kita_detail: Mapped["KitaDetail | None"] = relationship(back_populates="point", uselist=False)
    ev_charger_detail: Mapped["EvChargerDetail | None"] = relationship(
        back_populates="point", uselist=False
    )


class AmenityArea(Base):
    __tablename__ = "amenity_areas"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    kind_code: Mapped[str] = mapped_column(String(64), nullable=False)
    geom_family: Mapped[str] = mapped_column(String(16), nullable=False, server_default="area")
    source_id: Mapped[str] = mapped_column(String(128), nullable=False)
    name: Mapped[str | None] = mapped_column(String(255))
    subtype: Mapped[str | None] = mapped_column(String(128))
    catalog_id: Mapped[int] = mapped_column(ForeignKey("dataset_catalog.id"), nullable=False)
    district_id: Mapped[int | None] = mapped_column(ForeignKey("districts.id"))
    attrs: Mapped[dict] = _attrs_col()
    geom = mapped_column(Geometry(geometry_type="MULTIPOLYGON", srid=25833), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        ForeignKeyConstraint(["kind_code", "geom_family"], ["amenity_kind.code", "amenity_kind.geom_family"]),
    )

    kind: Mapped[AmenityKind] = relationship(viewonly=True)
    catalog: Mapped[DatasetCatalog] = relationship()
    district: Mapped[District | None] = relationship()


class AmenityPointTag(Base):
    """Association object for M:N #1 (point <-> tag); carries kind_code/category_code."""

    __tablename__ = "amenity_point_tag"

    point_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    kind_code: Mapped[str] = mapped_column(String(64), nullable=False)
    tag_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    category_code: Mapped[str] = mapped_column(String(64), nullable=False)

    __table_args__ = (
        ForeignKeyConstraint(
            ["point_id", "kind_code"],
            ["amenity_points.id", "amenity_points.kind_code"],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(["tag_id", "category_code"], ["tag.id", "tag.category_code"]),
        ForeignKeyConstraint(
            ["kind_code", "category_code"],
            ["kind_tag_category.kind_code", "kind_tag_category.category_code"],
        ),
    )

    point: Mapped[AmenityPoint] = relationship(back_populates="tag_links")
    tag: Mapped[Tag] = relationship()


class _DetailMixin:
    """1:1 subtype tables keyed by (point_id, kind_code)."""

    point_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    kind_code: Mapped[str] = mapped_column(String(64), primary_key=True)


def _point_fk(_table: str) -> tuple:
    return (
        ForeignKeyConstraint(
            ["point_id", "kind_code"],
            ["amenity_points.id", "amenity_points.kind_code"],
            ondelete="CASCADE",
        ),
    )


class TreeDetail(_DetailMixin, Base):
    __tablename__ = "tree_detail"
    __table_args__ = _point_fk("tree_detail")

    species_id: Mapped[int | None] = mapped_column(ForeignKey("tree_species.id"))
    planting_year: Mapped[int | None] = mapped_column(SmallInteger)
    trunk_circumference_cm: Mapped[int | None] = mapped_column(Integer)
    height_m: Mapped[Decimal | None] = mapped_column(Numeric(5, 1))
    crown_diameter_m: Mapped[Decimal | None] = mapped_column(Numeric(5, 1))

    point: Mapped[AmenityPoint] = relationship(back_populates="tree_detail")
    species: Mapped[TreeSpecies | None] = relationship()


class KitaDetail(_DetailMixin, Base):
    __tablename__ = "kita_detail"
    __table_args__ = _point_fk("kita_detail")

    capacity: Mapped[int | None] = mapped_column(Integer)

    point: Mapped[AmenityPoint] = relationship(back_populates="kita_detail")


class EvChargerDetail(_DetailMixin, Base):
    __tablename__ = "ev_charger_detail"
    __table_args__ = _point_fk("ev_charger_detail")

    charge_points: Mapped[int | None] = mapped_column(SmallInteger)
    max_power_kw: Mapped[Decimal | None] = mapped_column(Numeric(6, 1))
    commissioned_on: Mapped[date | None] = mapped_column(Date)
    public_space: Mapped[bool | None] = mapped_column(Boolean)

    point: Mapped[AmenityPoint] = relationship(back_populates="ev_charger_detail")


class ImportRun(Base):
    __tablename__ = "import_run"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    catalog_id: Mapped[int] = mapped_column(ForeignKey("dataset_catalog.id"), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default="running")
    rows_inserted: Mapped[int | None] = mapped_column(Integer)
    rows_updated: Mapped[int | None] = mapped_column(Integer)
    rows_deleted: Mapped[int | None] = mapped_column(Integer)
    error: Mapped[str | None] = mapped_column(Text)
