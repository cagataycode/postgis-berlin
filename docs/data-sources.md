# Data sources

All map data is **official Berlin open data**, fetched at import time from the [Geoportal Berlin WFS services](https://gdi.berlin.de/) (or a direct GeoJSON download for districts). No API keys, no third-party commercial data. Provenance is stored per layer in `dataset_catalog`.

| Layer | Publisher | Dataset page | Import endpoint | License |
| --- | --- | --- | --- | --- |
| Districts | Land Berlin / ODIS / TSB | [Bezirksgrenzen](https://daten.odis-berlin.de/de/dataset/bezirksgrenzen/) | [GeoJSON download](https://tsb-opendata.s3.eu-central-1.amazonaws.com/bezirksgrenzen/bezirksgrenzen.geojson) | Open data (see page) |
| Neighborhoods (Ortsteile) | Senatsverwaltung für Stadtentwicklung, Bauen und Wohnen | [ALKIS Ortsteile WFS](https://daten.berlin.de/datensaetze/alkis-berlin-ortsteile-wfs-61bd3084) | `WFS:gdi.berlin.de/services/wfs/alkis_ortsteile` → `alkis_ortsteile:ortsteile` | dl-de/zero-2.0 |
| Green spaces | SenMVKU Berlin | [Grünanlagenbestand WFS](https://daten.berlin.de/datensaetze/grunanlagenbestand-berlin-einschliesslich-der-offentlichen-spielplatze-wfs-737fd0a4) | `…/wfs/gruenanlagen` → `gruenanlagen:gruenanlagen` | dl-de/zero-2.0 |
| Cemeteries | SenMVKU Berlin | [Friedhofsbestand WFS](https://daten.berlin.de/datensaetze/friedhofsbestand-berlin-wfs-b6e64b05) | `…/wfs/friedhofsbestand` → `friedhofsbestand:friedhofsbestand_berlin` | dl-de/zero-2.0 |
| Schools | Senatsverwaltung Berlin | [Schulen WFS](https://daten.berlin.de/datensaetze/schulen-wfs-ebc64e18) | `…/wfs/schulen` → `schulen:schulen` | dl-de/zero-2.0 |
| Daycare (Kitas) | SenBJF Berlin | [Kindertagesstätten WFS](https://daten.berlin.de/datensaetze/kindertagesstatten-wfs-d03b94d2) | `…/wfs/kita` → `kita:kita` | dl-de/zero-2.0 |
| Hospitals | SenWGP Berlin | [Krankenhäuser WFS](https://gdi.berlin.de/geonetwork/srv/api/records/71ad834d-c39a-3568-9789-3aa855ddd176) | `…/wfs/krankenhaeuser` → `plankrankenhaeuser` + `weitere_krankenhaeuser` (merged) | dl-de/zero-2.0 |
| Street trees | SenMVKU Berlin | [Baumbestand WFS](https://daten.berlin.de/datensaetze/baumbestand-berlin-wfs-48ad3a23) | `…/wfs/baumbestand` → `baumbestand:strassenbaeume` | dl-de/zero-2.0 |
| Park trees | SenMVKU Berlin | [Baumbestand WFS](https://daten.berlin.de/datensaetze/baumbestand-berlin-wfs-48ad3a23) | `…/wfs/baumbestand` → `baumbestand:anlagenbaeume` | dl-de/zero-2.0 |
| Bike parking | GB infraVelo GmbH | [Fahrradabstellanlagen seit 2021 WFS](https://daten.berlin.de/datensaetze/fahrradabstellanlagen-seit-2021-wfs-4f226c23) | `…/wfs/fahrradabstellanlagen` → `fahrradabstellanlagen:fahrradabstellanlagen` | dl-de/zero-2.0 |
| EV chargers | SenWEB Berlin | [Elektro-Ladesäulen WFS](https://daten.berlin.de/datensaetze/elektro-ladesaulen-und-ladepunkte-wfs-f306dd51) | `…/wfs/eladesaeulen` → `eladesaeulen:lades_standorte` | dl-de/zero-2.0 |
| Drinking fountains | Berliner Wasserbetriebe | [Trinkwasserbrunnen WFS](https://daten.berlin.de/datensaetze/trinkwasserbrunnen-wfs-47dba2c3) | `…/wfs/trinkwasserbrunnen` → `trinkwasserbrunnen:trinkwasserbrunnen` | dl-de/zero-2.0 |
| Bathing waters | LAGeSo Berlin | [Badegewässerqualität WFS](https://daten.berlin.de/datensaetze/badegewasserqualitat-wfs-6ba85d36) | `…/wfs/badegewaesser` → `badegewaesser:aa_badestellen` | cc-by/4.0 |
| Public toilets | Senatsverwaltung Berlin | [Toiletten WFS](https://daten.berlin.de/datensaetze/toiletten-wfs) | `…/wfs/toiletten` → `toiletten:toiletten` | dl-de/zero-2.0 |
| Playgrounds | SenMVKU Berlin | [Spielplätze WFS](https://daten.berlin.de/datensaetze/spielplaetze-wfs) | `…/wfs/spielplaetze` → `spielplaetze:spielplaetze` | dl-de/zero-2.0 |
| Sports facilities | Senatsverwaltung Berlin | [Sportstandorte WFS](https://daten.berlin.de/datensaetze/sportstandorte-wfs) | `…/wfs/sportstandorte` → `sportstandorte:sportstandorte` | dl-de/zero-2.0 |
| Park & Ride | SenMVKU Berlin | [P+R Anlagen](https://gdi.berlin.de/geonetwork/srv/api/records/c9d9f2e4-1621-3c9a-a281-dae3b3359c31) | `…/wfs/park_and_ride` → `park_and_ride:park_and_ride` | dl-de/zero-2.0 |

All WFS endpoints share the base `https://gdi.berlin.de/services/wfs/…`. Attribution for cc-by data: **Geoportal Berlin / LAGeSo** (BWB where noted). Import config: [`backend/scripts/sources.py`](../backend/scripts/sources.py) (importer: `import_v2.py`).

## Known gaps

Fountain seasonality; private bike racks / chargers; toilet hours/accessibility; no routing distance; P+R umland layer not imported.

## Schema

`dataset_catalog` 1:N feature tables; features get `district_id` at import (`ST_Within` / point-on-surface).

Every feature also keeps **`attrs` (jsonb)** — the full source GeoJSON `properties` object. Curated columns (`name`, type fields, …) stay for teaching joins; map GeoJSON and `/features/{layer}/{id}` flatten `attrs` into feature properties.
