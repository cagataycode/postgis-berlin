# ERD — schema v2

Conceptual model for the Berlin Amenities study database. Geometry SRID: **EPSG:25833**.

## Entity-relationship sketch

```text
┌─────────────────────┐       1:N        ┌──────────────────┐
│  dataset_catalog    │─────────────────▶│ amenity_points   │
│  PK id              │                  │ PK id            │
│  slug UK            │                  │ FK kind_code     │
│  org, url, license… │                  │ FK catalog_id    │
└─────────────────────┘                  │ FK district_id?  │
          │                              │ geom Point       │
          │ 1:N                          └────────┬─────────┘
          │                                       │
          │                              N:1      │
          │                     ┌─────────────────┘
          │                     │
          ▼                     ▼
┌─────────────────────┐  ┌──────────────────┐
│  amenity_areas      │  │  amenity_kind    │
│  PK id              │  │  PK code         │
│  FK kind_code       │  │  label           │
│  FK catalog_id      │  │  geom_family     │
│  FK district_id?    │  └──────────────────┘
│  geom MultiPolygon  │
└─────────────────────┘

┌─────────────────────┐       1:N        ┌──────────────────┐
│  districts          │─────────────────▶│ neighborhoods    │
│  PK id              │                  │ PK id            │
│  official_id UK     │                  │ FK district_id?  │
│  geom MultiPolygon  │                  │ geom MultiPolygon│
└─────────┬───────────┘                  └──────────────────┘
          │
          │ 1:N (assigned at import)
          ├──────────────────▶ amenity_points.district_id
          └──────────────────▶ amenity_areas.district_id
```

`dataset_catalog` also 1:N → `amenity_areas` (same as points).  
`districts` / `neighborhoods` each have their own `catalog_id` for boundary provenance.

## Cardinalities (for the report)

| Relationship | Cardinality | Join key |
| --- | --- | --- |
| catalog → amenity_points | 1:N | `catalog_id` |
| catalog → amenity_areas | 1:N | `catalog_id` |
| amenity_kind → amenity_points | 1:N | `kind_code` |
| amenity_kind → amenity_areas | 1:N | `kind_code` |
| districts → amenity_* | 1:N | `district_id` |
| districts → neighborhoods | 1:N | `district_id` |

## Why points and areas are separate

Same amenity *role*, different geometry type. Two tables keep PostGIS column typing honest (`Point` vs `MultiPolygon`), allow separate GiST indexes, and still remove ~15 look-alike layer tables.

## Kind codes (initial)

**Points:** `school`, `kita`, `hospital`, `street_tree`, `park_tree`, `bike_parking`, `ev_charger`, `drinking_fountain`, `bathing_water`, `toilet`, `sports_facility`, `park_and_ride`  

**Areas:** `green_space`, `playground`, `cemetery`
