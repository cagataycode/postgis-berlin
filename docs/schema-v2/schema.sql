-- Schema v2 — proposed DDL (study design; not applied by Alembic yet).
-- Requires: CREATE EXTENSION postgis;
-- SRID: EPSG:25833 (ETRS89 / UTM zone 33N)

CREATE TABLE dataset_catalog (
  id                  serial PRIMARY KEY,
  slug                varchar(64) NOT NULL UNIQUE,
  name                varchar(255) NOT NULL,
  description         text,
  source_organization varchar(255),
  source_url          text,
  license_text        text,
  source_vintage      date,
  imported_at         timestamptz NOT NULL DEFAULT now(),
  srid                integer NOT NULL DEFAULT 25833,
  geometry_type       varchar(64),
  coverage_caveat     text
);

CREATE TABLE amenity_kind (
  code         varchar(64) PRIMARY KEY,
  label        varchar(128) NOT NULL,
  geom_family  varchar(16) NOT NULL CHECK (geom_family IN ('point', 'area')),
  description  text
);

CREATE TABLE districts (
  id          serial PRIMARY KEY,
  official_id varchar(32) NOT NULL UNIQUE,
  name        varchar(128) NOT NULL,
  catalog_id  integer NOT NULL REFERENCES dataset_catalog (id),
  attrs       jsonb NOT NULL DEFAULT '{}',
  geom        geometry(MultiPolygon, 25833) NOT NULL
);

CREATE TABLE neighborhoods (
  id          serial PRIMARY KEY,
  official_id varchar(32) NOT NULL UNIQUE,
  name        varchar(128) NOT NULL,
  catalog_id  integer NOT NULL REFERENCES dataset_catalog (id),
  district_id integer REFERENCES districts (id),
  attrs       jsonb NOT NULL DEFAULT '{}',
  geom        geometry(MultiPolygon, 25833) NOT NULL
);

CREATE TABLE operator (
  id            serial PRIMARY KEY,
  name          varchar(255) NOT NULL UNIQUE,
  operator_type varchar(64)
);

CREATE TABLE amenity_points (
  id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  kind_code   varchar(64) NOT NULL REFERENCES amenity_kind (code),
  source_id   varchar(128),
  name        varchar(255),
  subtype     varchar(128),
  catalog_id  integer NOT NULL REFERENCES dataset_catalog (id),
  district_id integer REFERENCES districts (id),
  operator_id integer REFERENCES operator (id),
  attrs       jsonb NOT NULL DEFAULT '{}',
  geom        geometry(Point, 25833) NOT NULL
);

CREATE TABLE amenity_areas (
  id          serial PRIMARY KEY,
  kind_code   varchar(64) NOT NULL REFERENCES amenity_kind (code),
  source_id   varchar(128),
  name        varchar(255),
  subtype     varchar(128),
  catalog_id  integer NOT NULL REFERENCES dataset_catalog (id),
  district_id integer REFERENCES districts (id),
  attrs       jsonb NOT NULL DEFAULT '{}',
  geom        geometry(MultiPolygon, 25833) NOT NULL
);

-- Many-to-many: amenity_points <-> tag
CREATE TABLE tag_category (
  code  varchar(64) PRIMARY KEY,
  label varchar(128) NOT NULL
);

CREATE TABLE tag (
  id            serial PRIMARY KEY,
  category_code varchar(64) NOT NULL REFERENCES tag_category (code),
  label         varchar(255) NOT NULL,
  UNIQUE (category_code, label)
);

CREATE TABLE amenity_point_tag (
  point_id bigint  NOT NULL REFERENCES amenity_points (id) ON DELETE CASCADE,
  tag_id   integer NOT NULL REFERENCES tag (id),
  PRIMARY KEY (point_id, tag_id)
);

-- Spatial (GiST)
CREATE INDEX ix_districts_geom ON districts USING gist (geom);
CREATE INDEX ix_neighborhoods_geom ON neighborhoods USING gist (geom);
CREATE INDEX ix_amenity_points_geom ON amenity_points USING gist (geom);
CREATE INDEX ix_amenity_areas_geom ON amenity_areas USING gist (geom);

CREATE EXTENSION IF NOT EXISTS btree_gist;
CREATE INDEX ix_amenity_points_kind_geom ON amenity_points USING gist (kind_code, geom);

-- Relational filters (btree)
CREATE INDEX ix_amenity_points_kind ON amenity_points (kind_code);
CREATE INDEX ix_amenity_points_district ON amenity_points (district_id);
CREATE INDEX ix_amenity_points_catalog ON amenity_points (catalog_id);
CREATE INDEX ix_amenity_areas_kind ON amenity_areas (kind_code);
CREATE INDEX ix_amenity_areas_district ON amenity_areas (district_id);
CREATE INDEX ix_amenity_areas_catalog ON amenity_areas (catalog_id);
CREATE INDEX ix_neighborhoods_district ON neighborhoods (district_id);
CREATE INDEX ix_amenity_points_operator ON amenity_points (operator_id);
CREATE INDEX ix_amenity_point_tag_tag ON amenity_point_tag (tag_id, point_id);

-- Level 2: jsonb containment
CREATE INDEX ix_amenity_points_attrs ON amenity_points USING gin (attrs jsonb_path_ops);

-- Seed kinds (codes used by import mapping)
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

-- Optional teaching / compatibility views (examples)
-- CREATE VIEW schools AS
--   SELECT * FROM amenity_points WHERE kind_code = 'school';
-- CREATE VIEW green_spaces AS
--   SELECT * FROM amenity_areas WHERE kind_code = 'green_space';
