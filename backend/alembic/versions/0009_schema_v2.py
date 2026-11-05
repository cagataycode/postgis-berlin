"""Schema v2: unified amenity tables, tags (M:N), detail tables, audit, read-only role.

Hand-written: Alembic autogenerate does not understand partitions or composite
FKs. Reference DDL with comments: docs/schema-v2/schema.sql. Decisions D1–D12:
docs/module-requirements/implementation-plan.md.

dataset_catalog, districts and neighborhoods already exist with the v2 shape and
are reused. Legacy per-layer tables stay until 0010 (cutover).
"""

from alembic import op

revision = "0009_schema_v2"
down_revision = "0008_more_amenities_v2"
branch_labels = None
depends_on = None

LOOKUPS = """
CREATE TABLE amenity_kind (
  code         varchar(64) PRIMARY KEY,
  label        varchar(128) NOT NULL,
  geom_family  varchar(16) NOT NULL CHECK (geom_family IN ('point', 'area')),
  description  text,
  UNIQUE (code, geom_family)
);

CREATE TABLE operator (
  id            serial PRIMARY KEY,
  official_ref  varchar(64) UNIQUE,
  name          varchar(255) NOT NULL,
  operator_type varchar(64)
);
CREATE UNIQUE INDEX ux_operator_name_no_ref ON operator (name) WHERE official_ref IS NULL;

CREATE TABLE tree_species (
  id             serial PRIMARY KEY,
  botanical_name varchar(255) NOT NULL UNIQUE,
  german_name    varchar(255),
  genus          varchar(128)
);

CREATE FUNCTION set_updated_at() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  NEW.updated_at := now();
  RETURN NEW;
END;
$$;
"""

AMENITIES = """
CREATE SEQUENCE amenity_point_id_seq AS bigint;

CREATE TABLE amenity_points (
  id          bigint NOT NULL DEFAULT nextval('amenity_point_id_seq'),
  kind_code   varchar(64) NOT NULL,
  geom_family varchar(16) NOT NULL DEFAULT 'point' CHECK (geom_family = 'point'),
  source_id   varchar(128) NOT NULL,
  name        varchar(255),
  subtype     varchar(128),
  catalog_id  integer NOT NULL REFERENCES dataset_catalog (id),
  district_id integer REFERENCES districts (id),
  operator_id integer REFERENCES operator (id),
  attrs       jsonb NOT NULL DEFAULT '{}',
  geom        geometry(Point, 25833) NOT NULL,
  updated_at  timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (id, kind_code),
  UNIQUE (kind_code, source_id),
  FOREIGN KEY (kind_code, geom_family) REFERENCES amenity_kind (code, geom_family)
) PARTITION BY LIST (kind_code);

ALTER SEQUENCE amenity_point_id_seq OWNED BY amenity_points.id;

CREATE TABLE amenity_points_street_tree PARTITION OF amenity_points FOR VALUES IN ('street_tree');
CREATE TABLE amenity_points_park_tree   PARTITION OF amenity_points FOR VALUES IN ('park_tree');
CREATE TABLE amenity_points_other       PARTITION OF amenity_points DEFAULT;

CREATE TABLE amenity_areas (
  id          serial PRIMARY KEY,
  kind_code   varchar(64) NOT NULL,
  geom_family varchar(16) NOT NULL DEFAULT 'area' CHECK (geom_family = 'area'),
  source_id   varchar(128) NOT NULL,
  name        varchar(255),
  subtype     varchar(128),
  catalog_id  integer NOT NULL REFERENCES dataset_catalog (id),
  district_id integer REFERENCES districts (id),
  attrs       jsonb NOT NULL DEFAULT '{}',
  geom        geometry(MultiPolygon, 25833) NOT NULL CHECK (ST_IsValid(geom)),
  updated_at  timestamptz NOT NULL DEFAULT now(),
  UNIQUE (kind_code, source_id),
  UNIQUE (id, kind_code),
  FOREIGN KEY (kind_code, geom_family) REFERENCES amenity_kind (code, geom_family)
);

CREATE TRIGGER trg_amenity_points_updated BEFORE UPDATE ON amenity_points
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();
CREATE TRIGGER trg_amenity_areas_updated BEFORE UPDATE ON amenity_areas
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();
"""

TAGS = """
CREATE TABLE tag_category (
  code  varchar(64) PRIMARY KEY,
  label varchar(128) NOT NULL
);

CREATE TABLE tag (
  id            serial PRIMARY KEY,
  category_code varchar(64) NOT NULL REFERENCES tag_category (code),
  label         varchar(255) NOT NULL,
  UNIQUE (category_code, label),
  UNIQUE (id, category_code)
);

CREATE TABLE kind_tag_category (
  kind_code     varchar(64) NOT NULL REFERENCES amenity_kind (code),
  category_code varchar(64) NOT NULL REFERENCES tag_category (code),
  PRIMARY KEY (kind_code, category_code)
);

CREATE TABLE amenity_point_tag (
  point_id      bigint  NOT NULL,
  kind_code     varchar(64) NOT NULL,
  tag_id        integer NOT NULL,
  category_code varchar(64) NOT NULL,
  PRIMARY KEY (point_id, tag_id),
  FOREIGN KEY (point_id, kind_code) REFERENCES amenity_points (id, kind_code) ON DELETE CASCADE,
  FOREIGN KEY (tag_id, category_code) REFERENCES tag (id, category_code),
  FOREIGN KEY (kind_code, category_code) REFERENCES kind_tag_category (kind_code, category_code)
);
"""

DETAILS = """
CREATE TABLE tree_detail (
  point_id               bigint NOT NULL,
  kind_code              varchar(64) NOT NULL CHECK (kind_code IN ('street_tree', 'park_tree')),
  species_id             integer REFERENCES tree_species (id),
  planting_year          smallint CHECK (planting_year BETWEEN 1500 AND 2100),
  trunk_circumference_cm integer CHECK (trunk_circumference_cm > 0),
  height_m               numeric(5,1) CHECK (height_m > 0),
  crown_diameter_m       numeric(5,1) CHECK (crown_diameter_m > 0),
  PRIMARY KEY (point_id, kind_code),
  FOREIGN KEY (point_id, kind_code) REFERENCES amenity_points (id, kind_code) ON DELETE CASCADE
);

CREATE TABLE kita_detail (
  point_id  bigint NOT NULL,
  kind_code varchar(64) NOT NULL CHECK (kind_code = 'kita'),
  capacity  integer CHECK (capacity >= 0),
  PRIMARY KEY (point_id, kind_code),
  FOREIGN KEY (point_id, kind_code) REFERENCES amenity_points (id, kind_code) ON DELETE CASCADE
);

CREATE TABLE ev_charger_detail (
  point_id        bigint NOT NULL,
  kind_code       varchar(64) NOT NULL CHECK (kind_code = 'ev_charger'),
  charge_points   smallint CHECK (charge_points > 0),
  max_power_kw    numeric(6,1) CHECK (max_power_kw > 0),
  commissioned_on date,
  public_space    boolean,
  PRIMARY KEY (point_id, kind_code),
  FOREIGN KEY (point_id, kind_code) REFERENCES amenity_points (id, kind_code) ON DELETE CASCADE
);

CREATE TABLE import_run (
  id            serial PRIMARY KEY,
  catalog_id    integer NOT NULL REFERENCES dataset_catalog (id),
  started_at    timestamptz NOT NULL DEFAULT now(),
  finished_at   timestamptz,
  status        varchar(16) NOT NULL DEFAULT 'running'
                CHECK (status IN ('running', 'committed', 'failed')),
  rows_inserted integer,
  rows_updated  integer,
  rows_deleted  integer,
  error         text
);
"""

INDEXES = """
CREATE INDEX ix_amenity_points_geom     ON amenity_points USING gist (geom);
CREATE INDEX ix_amenity_areas_geom      ON amenity_areas  USING gist (geom);
CREATE INDEX ix_amenity_points_district ON amenity_points (district_id);
CREATE INDEX ix_amenity_points_operator ON amenity_points (operator_id);
CREATE INDEX ix_amenity_points_catalog  ON amenity_points (catalog_id);
CREATE INDEX ix_amenity_areas_district  ON amenity_areas (district_id);
CREATE INDEX ix_amenity_areas_catalog   ON amenity_areas (catalog_id);
CREATE INDEX ix_tree_detail_species     ON tree_detail (species_id);
CREATE INDEX ix_amenity_point_tag_tag   ON amenity_point_tag (tag_id, point_id);
CREATE INDEX ix_amenity_points_attrs    ON amenity_points USING gin (attrs jsonb_path_ops);
CREATE INDEX ix_amenity_areas_attrs     ON amenity_areas  USING gin (attrs jsonb_path_ops);
"""

SEEDS = """
INSERT INTO amenity_kind (code, label, geom_family) VALUES
  ('school', 'School', 'point'),
  ('kita', 'Daycare (Kita)', 'point'),
  ('hospital', 'Hospital', 'point'),
  ('street_tree', 'Street tree', 'point'),
  ('park_tree', 'Park tree', 'point'),
  ('bike_parking', 'Bike parking', 'point'),
  ('ev_charger', 'EV charger', 'point'),
  ('drinking_fountain', 'Drinking fountain', 'point'),
  ('bathing_water', 'Bathing water', 'point'),
  ('toilet', 'Public toilet', 'point'),
  ('sports_facility', 'Sports facility', 'point'),
  ('park_and_ride', 'Park & Ride', 'point'),
  ('green_space', 'Green space / park', 'area'),
  ('playground', 'Playground', 'area'),
  ('cemetery', 'Cemetery', 'area');

INSERT INTO tag_category (code, label) VALUES
  ('ev_connector', 'EV connector type'),
  ('kita_approach', 'Kita pedagogical approach'),
  ('toilet_feature', 'Toilet feature');

INSERT INTO kind_tag_category (kind_code, category_code) VALUES
  ('ev_charger', 'ev_connector'),
  ('kita', 'kita_approach'),
  ('toilet', 'toilet_feature');
"""

# D11: read-only role for the SQL playground. Local-dev password; override the
# role (and DATABASE_URL_RO) in any shared environment. Skipped with a notice if
# the migrating user may not create roles.
READONLY_ROLE = """
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'berlin_ro') THEN
    CREATE ROLE berlin_ro LOGIN PASSWORD 'berlin_ro';
  END IF;
  EXECUTE format('GRANT CONNECT ON DATABASE %%I TO berlin_ro', current_database());
  GRANT USAGE ON SCHEMA public TO berlin_ro;
  GRANT SELECT ON ALL TABLES IN SCHEMA public TO berlin_ro;
  ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO berlin_ro;
  ALTER ROLE berlin_ro SET default_transaction_read_only = on;
EXCEPTION WHEN insufficient_privilege THEN
  RAISE NOTICE 'skipping berlin_ro: migrating user cannot create/grant roles';
END
$$;
"""

DROP_READONLY_ROLE = """
DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'berlin_ro') THEN
    DROP OWNED BY berlin_ro;
    DROP ROLE berlin_ro;
  END IF;
EXCEPTION WHEN insufficient_privilege THEN
  RAISE NOTICE 'skipping drop of berlin_ro: insufficient privilege';
END
$$;
"""


def upgrade() -> None:
    conn = op.get_bind()
    for block in (LOOKUPS, AMENITIES, TAGS, DETAILS, INDEXES, SEEDS, READONLY_ROLE):
        conn.exec_driver_sql(block)


def downgrade() -> None:
    conn = op.get_bind()
    conn.exec_driver_sql(DROP_READONLY_ROLE)
    for table in (
        "import_run",
        "ev_charger_detail",
        "kita_detail",
        "tree_detail",
        "amenity_point_tag",
        "kind_tag_category",
        "tag",
        "tag_category",
        "amenity_areas",
        "amenity_points",  # drops its partitions
        "tree_species",
        "operator",
        "amenity_kind",
    ):
        conn.exec_driver_sql(f"DROP TABLE {table}")
    conn.exec_driver_sql("DROP FUNCTION set_updated_at()")
