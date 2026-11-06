import { useEffect, useRef, useState } from "react";
import maplibregl, { Map, LngLatBoundsLike, Marker } from "maplibre-gl";
import {
  AnalysisResponse,
  BBox,
  DistrictListItem,
  FeatureCollection,
  FeatureDetail,
  LayerMeta,
  NearestAmenities,
  SqlRunResult,
  TagItem,
  api,
  bboxContains,
  boundsToBbox,
  clearApiCache,
  formatBbox,
  padBbox,
} from "./api";
import { PATTERNS, SCHEMA_TABLES, SchemaTable } from "./exercises";
import {
  KIND_CODES,
  LAYERS,
  LayerSlug,
  SourceStyle,
  TAGGABLE_LAYERS,
  TREES_MAX_BBOX_SPAN,
  TREES_MIN_ZOOM,
  ZOOM_GATED_LAYERS,
  buildSourceStyle,
  isZoomGated,
  layerDef,
  layerSingular,
} from "./layers";

type Visibility = Record<LayerSlug, boolean>;

type TaskTab = "nearby" | "compare" | "query";

type CompareMeasure =
  | "bike_parking"
  | "ev_chargers"
  | "drinking_fountains"
  | "toilets"
  | "playgrounds"
  | "sports_facilities"
  | "bathing_waters"
  | "trees"
  | "park_trees"
  | "kitas"
  | "hospitals"
  | "cemeteries"
  | "park_and_ride"
  | "green_pct"
  | "school_park"
  | "operators"
  | "tree_species"
  | "tree_year";

const COMPARE_MEASURES: Array<{ id: CompareMeasure; label: string }> = [
  { id: "bike_parking", label: "Bike parking" },
  { id: "ev_chargers", label: "EV chargers" },
  { id: "drinking_fountains", label: "Fountains" },
  { id: "toilets", label: "Toilets" },
  { id: "playgrounds", label: "Playgrounds" },
  { id: "sports_facilities", label: "Sports" },
  { id: "bathing_waters", label: "Bathing" },
  { id: "trees", label: "Street trees" },
  { id: "park_trees", label: "Park trees" },
  { id: "kitas", label: "Daycare" },
  { id: "hospitals", label: "Hospitals" },
  { id: "cemeteries", label: "Cemeteries" },
  { id: "park_and_ride", label: "Park & Ride" },
  { id: "green_pct", label: "Green cover %" },
  { id: "school_park", label: "School–park median" },
  { id: "operators", label: "Top operator (facilities)" },
  { id: "tree_species", label: "Tree species count" },
  { id: "tree_year", label: "Median planting year" },
];

/** Layers to enable when pinning a Compare measure's SQL. */
const COMPARE_MEASURE_LAYERS: Record<CompareMeasure, LayerSlug[]> = {
  bike_parking: ["districts", "bike_parking"],
  ev_chargers: ["districts", "ev_chargers"],
  drinking_fountains: ["districts", "drinking_fountains"],
  toilets: ["districts", "toilets"],
  playgrounds: ["districts", "playgrounds"],
  sports_facilities: ["districts", "sports_facilities"],
  bathing_waters: ["districts", "bathing_waters"],
  trees: ["districts", "trees"],
  park_trees: ["districts", "park_trees"],
  kitas: ["districts", "kitas"],
  hospitals: ["districts", "hospitals"],
  cemeteries: ["districts", "cemeteries"],
  park_and_ride: ["districts", "park_and_ride"],
  green_pct: ["districts", "green_spaces"],
  school_park: ["districts", "schools", "green_spaces"],
  operators: ["districts", "kitas", "ev_chargers"],
  tree_species: ["districts", "trees", "park_trees"],
  tree_year: ["districts", "trees", "park_trees"],
};

/**
 * Schema v2: amenities share two tables, so layers are found through the kind_code
 * literal ('ev_charger'); districts and neighborhoods still match their table name.
 */
function layersFromSql(sql: string): Set<LayerSlug> {
  const found = new Set<LayerSlug>();
  const lower = sql.toLowerCase();
  for (const slug of Object.keys(LAYERS) as LayerSlug[]) {
    const kind = KIND_CODES[slug];
    const hit = kind
      ? new RegExp(`'${kind}'`).test(lower)
      : new RegExp(`\\b${slug}\\b`).test(lower);
    if (hit) found.add(slug);
  }
  return found;
}

const EMPTY_FC: FeatureCollection = { type: "FeatureCollection", features: [] };

type LayerCounts = Partial<Record<LayerSlug, number>>;

const BERLIN_CENTER: [number, number] = [13.405, 52.52];
/** Soft pan limit — gray mask uses real borough polygons; this stops world wandering. */
const BERLIN_MAX_BOUNDS: LngLatBoundsLike = [
  [12.95, 52.28],
  [13.85, 52.75],
];
const BBOX_PAD = 0.6;
/** Tighter pad for half-million-row tree layers — wide pads become citywide dumps. */
const TREES_BBOX_PAD = 0.15;
const MOVE_DEBOUNCE_MS = 250;
/** Default radius (metres) for :threshold_m binds. */
const DEFAULT_THRESHOLD_M = 500;

/** Map add order: fills first, then dots, then lines — district outlines stay on top. */
const LAYER_ADD_ORDER: LayerSlug[] = [
  "green_spaces",
  "cemeteries",
  "playgrounds",
  "schools",
  "kitas",
  "hospitals",
  "trees",
  "park_trees",
  "bike_parking",
  "ev_chargers",
  "drinking_fountains",
  "bathing_waters",
  "toilets",
  "sports_facilities",
  "park_and_ride",
  "neighborhoods",
  "districts",
];

/** Layers named in the post-load status line. */
const STATUS_LAYERS: LayerSlug[] = [
  "green_spaces",
  "cemeteries",
  "playgrounds",
  "bike_parking",
  "ev_chargers",
  "drinking_fountains",
  "toilets",
  "sports_facilities",
  "kitas",
  "hospitals",
  "park_and_ride",
  "trees",
  "park_trees",
];

const WORLD_RING: [number, number][] = [
  [-180, -85],
  [-180, 85],
  [180, 85],
  [180, -85],
  [-180, -85],
];

type QueryDoc = {
  title: string;
  filename: string | null;
  sql: string;
  savedSql: string;
  caveat?: string;
};

const KNOWN_BINDS = [
  "threshold_m",
  "district_id",
  "minx",
  "miny",
  "maxx",
  "maxy",
  "lon",
  "lat",
  "tag_ids",
  "n_tags",
  "top_n",
  "kind",
  "radius_m",
  "limit",
] as const;

const ANALYSIS_TITLES: Record<string, string> = {
  "analysis_nearest_amenities.sql": "Nearest amenities",
  "analysis_amenity_density_by_borough.sql": "Amenity counts",
  "analysis_green_by_borough.sql": "Green cover",
  "analysis_school_green_proximity.sql": "School–park median",
  "analysis_operators.sql": "Top operators",
  "analysis_trees_by_borough.sql": "Tree statistics",
  "amenities_near.sql": "Amenities near a point",
};

function titleForSqlFile(name: string): string {
  return ANALYSIS_TITLES[name] ?? name;
}

function makeDoc(
  title: string,
  sql: string,
  opts?: { filename?: string | null; caveat?: string }
): QueryDoc {
  return {
    title,
    filename: opts?.filename ?? null,
    sql,
    savedSql: sql,
    caveat: opts?.caveat,
  };
}

function detectBinds(sql: string): string[] {
  return KNOWN_BINDS.filter((b) => sql.includes(`:${b}`));
}

function fillBindsFromMap(sql: string, values: Record<string, number | null>): string {
  let out = sql;
  for (const key of KNOWN_BINDS) {
    if (!out.includes(`:${key}`)) continue;
    const v = values[key];
    const lit = v == null || Number.isNaN(v) ? "NULL" : String(v);
    out = out.split(`:${key}`).join(lit);
  }
  return out;
}

/** Ring signed area: positive = CCW (GeoJSON exterior). */
function ringArea(ring: [number, number][]): number {
  let sum = 0;
  for (let i = 0; i < ring.length - 1; i++) {
    sum += ring[i][0] * ring[i + 1][1] - ring[i + 1][0] * ring[i][1];
  }
  return sum / 2;
}

function asHoleRing(ring: [number, number][]): [number, number][] {
  const closed =
    ring.length > 0 && (ring[0][0] !== ring[ring.length - 1][0] || ring[0][1] !== ring[ring.length - 1][1])
      ? [...ring, ring[0]]
      : [...ring];
  // Holes must be opposite winding to the exterior (WORLD_RING is CCW).
  return ringArea(closed) > 0 ? closed.reverse() : closed;
}

/** World polygon with Berlin borough exteriors punched as holes → gray outside the city. */
function berlinOutsideMask(districts: FeatureCollection): FeatureCollection {
  const holes: [number, number][][] = [];
  for (const f of districts.features) {
    const g = f.geometry;
    if (g.type === "Polygon") {
      const coords = g.coordinates as [number, number][][];
      const exterior = coords[0];
      if (exterior?.length >= 4) holes.push(asHoleRing(exterior));
    } else if (g.type === "MultiPolygon") {
      const coords = g.coordinates as [number, number][][][];
      for (const poly of coords) {
        const exterior = poly[0];
        if (exterior?.length >= 4) holes.push(asHoleRing(exterior));
      }
    }
  }
  return {
    type: "FeatureCollection",
    features: [
      {
        type: "Feature",
        properties: { layer: "berlin_mask" },
        geometry: {
          type: "Polygon",
          coordinates: [WORLD_RING, ...holes],
        },
      },
    ],
  };
}

function ensureBerlinMask(map: Map, districts: FeatureCollection) {
  const mask = berlinOutsideMask(districts);
  if (!mask.features[0] || (mask.features[0].geometry as { coordinates: unknown[] }).coordinates.length < 2) {
    return;
  }
  if (map.getSource("berlin_mask")) {
    (map.getSource("berlin_mask") as maplibregl.GeoJSONSource).setData(mask as never);
  } else {
    map.addSource("berlin_mask", { type: "geojson", data: mask as never });
    map.addLayer(
      {
        id: "berlin_mask-layer",
        type: "fill",
        source: "berlin_mask",
        paint: {
          "fill-color": "#9aa3a0",
          "fill-opacity": 0.72,
        },
      },
      // Sit above basemap, under data layers when those exist.
      map.getLayer("green_spaces-layer") ? "green_spaces-layer" : undefined
    );
  }
}

/**
 * Sync checkbox state to map layer visibility. Trees stay gated by zoom.
 * dimAmenities hides inventory layers while a query overlay owns their geometry.
 */
function applyLayerVisibility(map: Map, vis: Visibility, dimAmenities = false) {
  (Object.keys(vis) as LayerSlug[]).forEach((key) => {
    let visible = vis[key];
    if (isZoomGated(key) && visible && map.getZoom() < TREES_MIN_ZOOM) {
      visible = false;
    }
    if (dimAmenities && key !== "districts" && key !== "neighborhoods") {
      visible = false;
    }
    const value = visible ? "visible" : "none";
    for (const suffix of ["-layer", "-outline", "-line", "-label"]) {
      const layerId = `${key}${suffix}`;
      if (map.getLayer(layerId)) {
        map.setLayoutProperty(layerId, "visibility", value);
      }
    }
  });
}

export default function App() {
  const mapRef = useRef<Map | null>(null);
  const mapNode = useRef<HTMLDivElement | null>(null);
  const markerRef = useRef<Marker | null>(null);
  const loadedExtentRef = useRef<BBox | null>(null);
  const loadedDistrictRef = useRef<number | "">("");
  const loadSeqRef = useRef(0);
  const densityLoadedRef = useRef(false);
  /** Which zoom-gated layers currently have fetched data. */
  const zoomGatedLoadedRef = useRef<Record<string, boolean>>({});
  const treesZoomOkRef = useRef(false);

  const [layers, setLayers] = useState<LayerMeta[]>([]);
  const [districts, setDistricts] = useState<DistrictListItem[]>([]);
  const [selectedDistrict, setSelectedDistrict] = useState<number | "">("");
  const [visibility, setVisibility] = useState<Visibility>({
    districts: true,
    neighborhoods: false,
    green_spaces: false,
    cemeteries: false,
    schools: false,
    kitas: false,
    hospitals: false,
    trees: false,
    park_trees: false,
    bike_parking: true,
    ev_chargers: true,
    drinking_fountains: true,
    bathing_waters: true,
    toilets: false,
    playgrounds: false,
    sports_facilities: false,
    park_and_ride: false,
  });
  const visibilityRef = useRef(visibility);
  visibilityRef.current = visibility;
  const [status, setStatus] = useState("Loading map…");
  const [layerError, setLayerError] = useState<string | null>(null);
  const [nearestError, setNearestError] = useState<string | null>(null);
  const [nearest, setNearest] = useState<NearestAmenities | null>(null);
  const [density, setDensity] = useState<AnalysisResponse | null>(null);
  const [greenBorough, setGreenBorough] = useState<AnalysisResponse | null>(null);
  const [schoolGreen, setSchoolGreen] = useState<AnalysisResponse | null>(null);
  const [operatorStats, setOperatorStats] = useState<AnalysisResponse | null>(null);
  const [treeStats, setTreeStats] = useState<AnalysisResponse | null>(null);
  const [tagVocab, setTagVocab] = useState<Record<string, TagItem[]>>({});
  const [tagFilter, setTagFilter] = useState<Partial<Record<LayerSlug, number[]>>>({});
  const tagFilterRef = useRef(tagFilter);
  tagFilterRef.current = tagFilter;
  const tagKey = JSON.stringify(tagFilter);
  const [featureDetail, setFeatureDetail] = useState<FeatureDetail | null>(null);
  const [mapZoom, setMapZoom] = useState(10.4);
  const [queryDoc, setQueryDoc] = useState<QueryDoc | null>(null);
  const [pendingReplace, setPendingReplace] = useState<QueryDoc | null>(null);
  const [sqlOffer, setSqlOffer] = useState<QueryDoc | null>(null);
  const [lastClick, setLastClick] = useState<{ lon: number; lat: number } | null>(null);
  const [taskTab, setTaskTab] = useState<TaskTab>("nearby");
  const [compareMeasure, setCompareMeasure] = useState<CompareMeasure>("bike_parking");
  const [layerCounts, setLayerCounts] = useState<LayerCounts>({});
  const [sqlRun, setSqlRun] = useState<SqlRunResult | null>(null);
  const [sqlBusy, setSqlBusy] = useState(false);
  const [sqlError, setSqlError] = useState<string | null>(null);
  const [showQueryOnMap, setShowQueryOnMap] = useState(false);
  const [activePatternId, setActivePatternId] = useState<string | null>(null);
  const [glossaryOpen, setGlossaryOpen] = useState(false);
  const [panelPct, setPanelPct] = useState(() => {
    try {
      const raw = localStorage.getItem("berlin-panel-pct-v2");
      const n = raw == null ? NaN : Number(raw);
      if (Number.isFinite(n) && n >= 20 && n <= 80) return n;
    } catch {
      /* ignore */
    }
    return 40;
  });
  const [draggingSplit, setDraggingSplit] = useState(false);
  const appRef = useRef<HTMLDivElement | null>(null);
  const taskTabRef = useRef(taskTab);
  taskTabRef.current = taskTab;

  const treesZoomOk = mapZoom >= TREES_MIN_ZOOM;
  // Chip hint uses zoom only; actual fetch also checks viewport span.
  const selectedDistrictName =
    selectedDistrict === ""
      ? null
      : districts.find((d) => d.id === selectedDistrict)?.name ?? null;
  const queryBinds = queryDoc ? detectBinds(queryDoc.sql) : [];
  const queryDirty = queryDoc != null && queryDoc.sql !== queryDoc.savedSql;
  const activePattern = PATTERNS.find((p) => p.id === activePatternId) ?? null;

  useEffect(() => {
    try {
      localStorage.setItem("berlin-panel-pct-v2", String(panelPct));
    } catch {
      /* ignore */
    }
    const map = mapRef.current;
    if (map) {
      requestAnimationFrame(() => map.resize());
    }
  }, [panelPct]);

  useEffect(() => {
    const onResize = () => {
      const map = mapRef.current;
      if (map) requestAnimationFrame(() => map.resize());
    };
    window.addEventListener("resize", onResize);
    return () => window.removeEventListener("resize", onResize);
  }, []);

  useEffect(() => {
    if (!draggingSplit) return;

    const onMove = (e: PointerEvent) => {
      const root = appRef.current;
      if (!root) return;
      const rect = root.getBoundingClientRect();
      if (rect.width <= 0) return;
      const pct = ((e.clientX - rect.left) / rect.width) * 100;
      setPanelPct(Math.min(80, Math.max(20, pct)));
    };
    const onUp = () => setDraggingSplit(false);

    window.addEventListener("pointermove", onMove);
    window.addEventListener("pointerup", onUp);
    window.addEventListener("pointercancel", onUp);
    document.body.style.cursor = "col-resize";
    document.body.style.userSelect = "none";

    return () => {
      window.removeEventListener("pointermove", onMove);
      window.removeEventListener("pointerup", onUp);
      window.removeEventListener("pointercancel", onUp);
      document.body.style.cursor = "";
      document.body.style.userSelect = "";
    };
  }, [draggingSplit]);

  useEffect(() => {
    if (!mapNode.current || mapRef.current) return;
    const map = new maplibregl.Map({
      container: mapNode.current,
      // Free vector basemap (OpenFreeMap) — no API key. Place labels hidden below.
      style: "https://tiles.openfreemap.org/styles/positron",
      center: BERLIN_CENTER,
      zoom: 10.4,
      minZoom: 9,
      maxZoom: 18,
      maxBounds: BERLIN_MAX_BOUNDS,
      renderWorldCopies: false,
    });
    map.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-right");
    mapRef.current = map;
    map.on("load", () => {
      // Drop basemap place names so Ortsteil labels aren't duplicated.
      for (const layer of map.getStyle().layers ?? []) {
        if (layer.type !== "symbol") continue;
        const id = layer.id;
        if (id.startsWith("label_") || id === "airport") {
          map.setLayoutProperty(id, "visibility", "none");
        }
      }
      setStatus("Click the map to find nearby amenities");
      setMapZoom(map.getZoom());
    });

    const showFeatureAt = async (m: Map, point: maplibregl.PointLike) => {
      const layerIds = (Object.keys(KIND_CODES) as LayerSlug[])
        .flatMap((slug) => [`${slug}-layer`, `${slug}-outline`])
        .filter((id) => m.getLayer(id));
      const hit = m
        .queryRenderedFeatures(point, { layers: layerIds })
        .find((f) => typeof f.properties?.layer === "string" && f.properties?.id != null);
      if (!hit) {
        setFeatureDetail(null);
        return;
      }
      try {
        setFeatureDetail(
          await api.feature(hit.properties!.layer as LayerSlug, Number(hit.properties!.id))
        );
      } catch {
        setFeatureDetail(null);
      }
    };

    const onClick = async (e: maplibregl.MapMouseEvent) => {
      const { lng, lat } = e.lngLat;
      if (markerRef.current) markerRef.current.remove();
      markerRef.current = new maplibregl.Marker({ color: "#1f5c4d" }).setLngLat([lng, lat]).addTo(map);
      setLastClick({ lon: lng, lat });
      void showFeatureAt(map, e.point);
      try {
        setNearestError(null);
        setStatus(`Looking up ${lng.toFixed(5)}, ${lat.toFixed(5)}…`);
        const result = await api.nearestAmenities(lng, lat);
        setNearest(result);
        if (taskTabRef.current === "compare") {
          setTaskTab("nearby");
        }
        if (result.sql_ref) {
          try {
            const file = await api.sqlFile(result.sql_ref);
            setSqlOffer(
              makeDoc(titleForSqlFile(file.name), file.sql, { filename: file.name, caveat: result.caveat })
            );
          } catch {
            /* ignore inspector fetch errors */
          }
        }
        const closest = result.nearest?.[0];
        setStatus(
          closest
            ? `Nearest: ${layerSingular(closest.layer) ?? closest.layer} at ${closest.distance_m.toFixed(0)} m`
            : "No amenities loaded yet — run the import script"
        );
      } catch (err) {
        setNearestError(err instanceof Error ? err.message : "Lookup failed");
        setStatus("Lookup failed");
      }
    };
    map.on("click", onClick);

    const onZoom = () => setMapZoom(map.getZoom());
    map.on("zoom", onZoom);
    map.on("zoomend", onZoom);

    return () => {
      map.off("click", onClick);
      map.off("zoom", onZoom);
      map.off("zoomend", onZoom);
      markerRef.current?.remove();
      map.remove();
      mapRef.current = null;
    };
  }, []);

  useEffect(() => {
    // Drop any in-memory GeoJSON left from a previous sample import.
    clearApiCache();
    Promise.all([api.layers(), api.districtsList()])
      .then(([layerMeta, districtList]) => {
        setLayers(layerMeta);
        setDistricts(districtList);
      })
      .catch((err: Error) => setLayerError(err.message));
  }, []);

  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;

    const loadLayers = async (force: boolean) => {
      const districtId = selectedDistrict === "" ? undefined : selectedDistrict;
      const viewport = boundsToBbox(map.getBounds());
      const zoomOk = map.getZoom() >= TREES_MIN_ZOOM;
      const viewportSpanOk =
        viewport[2] - viewport[0] <= TREES_MAX_BBOX_SPAN &&
        viewport[3] - viewport[1] <= TREES_MAX_BBOX_SPAN;
      const treesOk = zoomOk && (districtId != null || viewportSpanOk);
      const wantZoomGated = Object.fromEntries(
        ZOOM_GATED_LAYERS.map((slug) => [
          slug,
          Boolean(visibilityRef.current[slug] && treesOk),
        ])
      ) as Record<string, boolean>;
      const gatedFingerprint = ZOOM_GATED_LAYERS.map(
        (slug) => `${slug}:${wantZoomGated[slug] ? 1 : 0}`
      ).join(",");
      const loadedFingerprint = ZOOM_GATED_LAYERS.map(
        (slug) => `${slug}:${zoomGatedLoadedRef.current[slug] ? 1 : 0}`
      ).join(",");

      if (districtId != null) {
        if (
          !force &&
          loadedDistrictRef.current === selectedDistrict &&
          gatedFingerprint === loadedFingerprint
        ) {
          return;
        }
      } else {
        if (
          !force &&
          loadedExtentRef.current &&
          bboxContains(loadedExtentRef.current, viewport) &&
          gatedFingerprint === loadedFingerprint
        ) {
          return;
        }
      }

      const fetchBbox =
        districtId != null ? undefined : formatBbox(padBbox(viewport, BBOX_PAD));
      const treesFetchBbox =
        districtId != null
          ? undefined
          : formatBbox(padBbox(viewport, TREES_BBOX_PAD));
      const extentToStore =
        districtId != null ? null : padBbox(viewport, BBOX_PAD);

      const seq = ++loadSeqRef.current;
      const slugs = Object.keys(LAYERS) as LayerSlug[];
      try {
        setLayerError(null);
        setStatus("Loading layers…");

        const [featureCollections, dens, green] = await Promise.all([
          Promise.all(
            slugs.map((slug) => {
              if (isZoomGated(slug) && !wantZoomGated[slug]) {
                return Promise.resolve(EMPTY_FC);
              }
              if (layerDef(slug).citywide) return api.layer(slug);
              const bbox = isZoomGated(slug) ? treesFetchBbox : fetchBbox;
              return api.layer(slug, bbox, districtId, tagFilterRef.current[slug]);
            })
          ),
          densityLoadedRef.current
            ? Promise.resolve(null as AnalysisResponse | null)
            : api.amenityDensityByBorough(),
          densityLoadedRef.current
            ? Promise.resolve(null as AnalysisResponse | null)
            : api.greenByBorough(),
        ]);

        if (seq !== loadSeqRef.current) return;

        const data = {} as Record<LayerSlug, FeatureCollection>;
        slugs.forEach((slug, i) => {
          data[slug] = featureCollections[i];
        });

        if (dens) {
          setDensity(dens);
          densityLoadedRef.current = true;
        }
        if (green) setGreenBorough(green);

        setLayerCounts((prev) => {
          const next: LayerCounts = { ...prev };
          for (const slug of slugs) {
            if (isZoomGated(slug) && !wantZoomGated[slug]) continue;
            next[slug] = data[slug].features.length;
          }
          return next;
        });

        ensureBerlinMask(map, data.districts);

        // Parks/fills first; borough outlines added last so they stay readable on top.
        for (const slug of LAYER_ADD_ORDER) {
          ensureSource(map, slug, data[slug], buildSourceStyle(slug));
          if (slug === "neighborhoods") ensureNeighborhoodLabels(map);
        }
        if (map.getLayer("berlin_mask-layer") && map.getLayer("neighborhoods-line")) {
          map.moveLayer("berlin_mask-layer", "neighborhoods-line");
        }
        if (map.getLayer("neighborhoods-line") && map.getLayer("districts-line")) {
          map.moveLayer("neighborhoods-line", "districts-line");
        }
        if (map.getLayer("neighborhoods-label") && map.getLayer("districts-line")) {
          map.moveLayer("neighborhoods-label", "districts-line");
        }
        if (map.getLayer("districts-line")) {
          map.moveLayer("districts-line");
        }

        applyLayerVisibility(map, visibilityRef.current);
        loadedExtentRef.current = extentToStore;
        loadedDistrictRef.current = selectedDistrict;
        zoomGatedLoadedRef.current = { ...wantZoomGated };
        treesZoomOkRef.current = zoomOk;

        setStatus(
          `Loaded ${STATUS_LAYERS.map(
            (slug) => `${LAYERS[slug].label} ${data[slug].features.length}`
          ).join(", ")}`
        );
      } catch (err) {
        if (seq !== loadSeqRef.current) return;
        setLayerError(err instanceof Error ? err.message : "Failed to load layers");
        setStatus("Layer load failed");
      }
    };

    const run = () => {
      void loadLayers(true);
    };

    if (map.isStyleLoaded()) run();
    else map.once("load", run);

    let debounceTimer: ReturnType<typeof setTimeout> | null = null;
    const onMoveEnd = () => {
      if (selectedDistrict !== "") {
        // Still re-check zoom-gated layers while focused on a borough.
        const zoomOk = map.getZoom() >= TREES_MIN_ZOOM;
        const anyVisibleGated = ZOOM_GATED_LAYERS.some(
          (slug) => visibilityRef.current[slug]
        );
        // Borough filter skips bbox span checks — zoom alone gates fetch.
        if (anyVisibleGated && zoomOk !== treesZoomOkRef.current) {
          void loadLayers(true);
        }
        return;
      }
      if (debounceTimer) clearTimeout(debounceTimer);
      debounceTimer = setTimeout(() => {
        void loadLayers(false);
      }, MOVE_DEBOUNCE_MS);
    };
    map.on("moveend", onMoveEnd);
    map.on("zoomend", onMoveEnd);

    return () => {
      map.off("moveend", onMoveEnd);
      map.off("zoomend", onMoveEnd);
      if (debounceTimer) clearTimeout(debounceTimer);
    };
  }, [selectedDistrict, tagKey]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    // Query overlay owns amenity geometry — dim inventory layers underneath so points aren't doubled.
    const overlayActive = Boolean(showQueryOnMap && sqlRun?.geojson?.features?.length);
    applyLayerVisibility(map, visibility, overlayActive);
    // Turning a zoom-gated layer on at sufficient zoom/span should fetch it.
    const vp = boundsToBbox(map.getBounds());
    const spanOk =
      selectedDistrict !== "" ||
      (vp[2] - vp[0] <= TREES_MAX_BBOX_SPAN && vp[3] - vp[1] <= TREES_MAX_BBOX_SPAN);
    const needsFetch = ZOOM_GATED_LAYERS.some(
      (slug) =>
        visibility[slug] &&
        map.getZoom() >= TREES_MIN_ZOOM &&
        spanOk &&
        !zoomGatedLoadedRef.current[slug]
    );
    if (needsFetch) {
      loadedExtentRef.current = null;
      loadedDistrictRef.current = "";
      map.fire("moveend");
    }
    for (const slug of ZOOM_GATED_LAYERS) {
      if (!visibility[slug] && zoomGatedLoadedRef.current[slug]) {
        const src = map.getSource(slug) as maplibregl.GeoJSONSource | undefined;
        src?.setData(EMPTY_FC as never);
        zoomGatedLoadedRef.current[slug] = false;
      }
    }
  }, [visibility, mapZoom, showQueryOnMap, sqlRun]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    if (showQueryOnMap && sqlRun?.geojson) {
      ensureUserQueryOverlay(map, sqlRun.geojson);
    } else {
      for (const id of ["user_query-fill", "user_query-outline", "user_query-circle"]) {
        if (map.getLayer(id)) map.setLayoutProperty(id, "visibility", "none");
      }
    }
  }, [showQueryOnMap, sqlRun]);

  const fitDistrict = (districtId: number | "") => {
    const map = mapRef.current;
    if (!map) return;
    const src = map.getSource("districts") as maplibregl.GeoJSONSource | undefined;
    const data = (src as unknown as { _data?: FeatureCollection })?._data;
    if (!data?.features?.length) return;

    if (districtId === "") {
      const bounds = new maplibregl.LngLatBounds();
      for (const feature of data.features) {
        if (feature.geometry.type === "GeometryCollection") continue;
        flattenCoords(feature.geometry.coordinates).forEach(([lng, lat]) => bounds.extend([lng, lat]));
      }
      if (!bounds.isEmpty()) map.fitBounds(bounds as LngLatBoundsLike, { padding: 48, duration: 0 });
      return;
    }

    const feature = data.features.find((f) => f.properties?.id === districtId);
    if (!feature || feature.geometry.type === "GeometryCollection") return;
    const bounds = new maplibregl.LngLatBounds();
    flattenCoords(feature.geometry.coordinates).forEach(([lng, lat]) => bounds.extend([lng, lat]));
    if (!bounds.isEmpty()) map.fitBounds(bounds as LngLatBoundsLike, { padding: 48, duration: 0 });
  };

  const selectBorough = (districtId: number | "") => {
    setSelectedDistrict(districtId);
    fitDistrict(districtId);
  };

  const getBindValues = (): Record<string, number | null> => {
    const map = mapRef.current;
    const bounds = map?.getBounds();
    const center = map?.getCenter();
    return {
      minx: bounds ? Number(bounds.getWest().toFixed(5)) : null,
      miny: bounds ? Number(bounds.getSouth().toFixed(5)) : null,
      maxx: bounds ? Number(bounds.getEast().toFixed(5)) : null,
      maxy: bounds ? Number(bounds.getNorth().toFixed(5)) : null,
      lon: lastClick?.lon ?? (center ? Number(center.lng.toFixed(5)) : BERLIN_CENTER[0]),
      lat: lastClick?.lat ?? (center ? Number(center.lat.toFixed(5)) : BERLIN_CENTER[1]),
      district_id: selectedDistrict === "" ? null : selectedDistrict,
      threshold_m: DEFAULT_THRESHOLD_M,
      tag_ids: null,
      n_tags: 0,
      top_n: 3,
      kind: null,
      radius_m: 400,
      limit: 50,
    };
  };

  /** Sync layer checkboxes to tables in the SQL; draw GeoJSON results on the map. */
  const applyQueryToMap = (sql: string, result: SqlRunResult | null, explain: boolean) => {
    const mentioned = layersFromSql(sql);
    if (mentioned.size > 0) {
      setVisibility((prev) => {
        const next = { ...prev };
        for (const key of Object.keys(LAYERS) as LayerSlug[]) {
          next[key] = mentioned.has(key);
        }
        return next;
      });
    }

    const fc = !explain ? result?.geojson : null;
    if (fc?.features?.length) {
      setShowQueryOnMap(true);
      requestAnimationFrame(() => {
        const map = mapRef.current;
        if (!map) return;
        ensureUserQueryOverlay(map, fc);
        const bounds = new maplibregl.LngLatBounds();
        for (const feature of fc.features) {
          if (!feature.geometry || feature.geometry.type === "GeometryCollection") continue;
          flattenCoords(feature.geometry.coordinates).forEach(([lng, lat]) =>
            bounds.extend([lng, lat])
          );
        }
        if (!bounds.isEmpty()) {
          map.fitBounds(bounds as LngLatBoundsLike, {
            padding: 56,
            maxZoom: 16,
            duration: 0,
          });
        }
      });
    } else if (!explain) {
      setShowQueryOnMap(false);
    }
  };

  const applyDocument = (next: QueryDoc, patternId: string | null = null) => {
    setQueryDoc({ ...next, savedSql: next.sql });
    setPendingReplace(null);
    setActivePatternId(patternId);
    setSqlRun(null);
    setSqlError(null);
    setTaskTab("query");
  };

  const requestReplace = (next: QueryDoc) => {
    if (queryDoc && queryDoc.sql !== queryDoc.savedSql) {
      setPendingReplace(next);
      setActivePatternId(null);
      setTaskTab("query");
      return;
    }
    applyDocument(next, null);
  };

  const openPattern = (id: string) => {
    const p = PATTERNS.find((x) => x.id === id);
    if (!p) return;
    const next = makeDoc(p.title, p.sql.trim());
    if (queryDoc && queryDoc.sql !== queryDoc.savedSql) {
      setPendingReplace(next);
      setActivePatternId(id);
      return;
    }
    applyDocument(next, id);
  };

  const insertIntoSql = (token: string) => {
    setQueryDoc((d) => {
      if (!d) {
        const isTable = SCHEMA_TABLES.some((t) => t.table === token);
        const sql = isTable
          ? `SELECT id, name, district_id,\n  ST_AsGeoJSON(ST_Transform(geom, 4326))::json AS geometry\nFROM ${token}\nORDER BY id\nLIMIT 50`
          : `SELECT ${token}\nFROM amenity_points\nWHERE kind_code = 'bike_parking'\nLIMIT 50`;
        return makeDoc(isTable ? token : "Scratch", sql);
      }
      const sql = d.sql;
      const trimmed = sql.trimEnd();
      const next = /[,(]$|\s$|\($/.test(trimmed)
        ? `${sql}${token}`
        : `${sql}${sql.endsWith("\n") ? "" : " "}${token}`;
      return { ...d, sql: next };
    });
    setActivePatternId(null);
  };

  const openReferenceFile = async () => {
    if (!activePattern) return;
    try {
      if (activePattern.refLayer) {
        const file = await api.layerSql(activePattern.refLayer);
        applyDocument(
          makeDoc(LAYERS[activePattern.refLayer].label, file.sql, { filename: file.name }),
          null
        );
        return;
      }
      if (!activePattern.refFile) return;
      const file = await api.sqlFile(activePattern.refFile);
      applyDocument(makeDoc(titleForSqlFile(file.name), file.sql, { filename: file.name }), null);
    } catch (err) {
      setSqlError(err instanceof Error ? err.message : "Could not load SQL file");
    }
  };

  const inspectLayerSql = async (key: LayerSlug) => {
    try {
      setLayerError(null);
      const file = await api.layerSql(key);
      const catalog = layers.find((l) => l.slug === key);
      setVisibility((v) => ({ ...v, [key]: true }));
      requestReplace(
        makeDoc(LAYERS[key].label, file.sql, {
          filename: file.name,
          caveat: catalog?.coverage_caveat,
        })
      );
    } catch (err) {
      setLayerError(err instanceof Error ? err.message : "Could not load SQL");
    }
  };

  const showNearestQuery = () => {
    if (!sqlOffer) return;
    requestReplace(sqlOffer);
  };

  const clearPin = () => {
    markerRef.current?.remove();
    markerRef.current = null;
    setNearest(null);
    setFeatureDetail(null);
    setNearestError(null);
    setSqlOffer(null);
    setStatus("Click the map to find nearby amenities");
  };

  useEffect(() => {
    // Tag vocabularies for the filter row (small, loaded once).
    for (const kind of Object.values(TAGGABLE_LAYERS)) {
      if (!kind) continue;
      api
        .tags(kind)
        .then((tags) => setTagVocab((v) => ({ ...v, [kind]: tags })))
        .catch(() => undefined);
    }
  }, []);

  useEffect(() => {
    if (taskTab !== "compare") return;
    if (compareMeasure === "operators" && !operatorStats) {
      api.operators(1).then(setOperatorStats).catch(() => undefined);
    }
    if ((compareMeasure === "tree_species" || compareMeasure === "tree_year") && !treeStats) {
      // ~10 s on the full inventory: fetched only when one of the tree measures is opened.
      api.treesByBorough().then(setTreeStats).catch(() => undefined);
    }
  }, [taskTab, compareMeasure, operatorStats, treeStats]);

  useEffect(() => {
    if (taskTab !== "compare" || schoolGreen) return;
    let cancelled = false;
    api
      .schoolGreenProximity()
      .then((res) => {
        if (!cancelled) setSchoolGreen(res);
      })
      .catch(() => {
        if (!cancelled) {
          setSchoolGreen({
            id: "school-green-proximity",
            title: "School-to-green proximity",
            inputs: [],
            operation: "",
            units: {},
            crs: "EPSG:25833",
            caveat: "Could not load school–park proximity for this session.",
            results: [],
          });
        }
      });
    return () => {
      cancelled = true;
    };
  }, [taskTab, schoolGreen]);

  const runDocument = async (explain: boolean) => {
    if (!queryDoc) return;
    setSqlBusy(true);
    setSqlError(null);
    try {
      const sql = fillBindsFromMap(queryDoc.sql, getBindValues());
      const result = await api.runSql(sql, explain);
      setSqlRun(result);
      applyQueryToMap(queryDoc.sql, result, explain);
    } catch (err) {
      setSqlError(err instanceof Error ? err.message : "Query failed");
      setSqlRun(null);
      setShowQueryOnMap(false);
    } finally {
      setSqlBusy(false);
    }
  };

  const visibleLegendKeys = (Object.keys(LAYERS) as LayerSlug[]).filter((key) => {
    if (!visibility[key]) return false;
    if (isZoomGated(key) && !treesZoomOk) return false;
    return true;
  });

  return (
    <div
      className={`app${draggingSplit ? " app-resizing" : ""}`}
      ref={appRef}
      style={{ ["--panel-pct" as string]: `${panelPct}%` }}
    >
      <aside className={`panel panel-tab-${taskTab}`}>
        <header className="panel-chrome">
          <div className="panel-chrome-row">
            <h1 className="brand">Berlin Amenities</h1>
            <button
              type="button"
              className="context-borough"
              onClick={() => selectBorough("")}
              title="Clear borough filter"
            >
              {selectedDistrictName ?? "All boroughs"}
            </button>
          </div>
          <div className="layer-grid" role="group" aria-label="Layers">
            {(Object.keys(LAYERS) as LayerSlug[]).map((key) => {
              const count = layerCounts[key];
              const waitingZoom = isZoomGated(key) && visibility[key] && !treesZoomOk;
              const on = visibility[key];
              return (
                <div key={key} className={`layer-chip${on ? " layer-chip-on" : ""}`}>
                  <button
                    type="button"
                    className="layer-chip-toggle"
                    aria-pressed={on}
                    title={waitingZoom ? `Zoom to ${TREES_MIN_ZOOM}` : LAYERS[key].label}
                    onClick={() => setVisibility((v) => ({ ...v, [key]: !v[key] }))}
                  >
                    <span
                      className={`swatch swatch-${LAYERS[key].kind}`}
                      style={{ background: LAYERS[key].swatch }}
                    />
                    <span className="layer-chip-label">{LAYERS[key].label}</span>
                    {waitingZoom ? (
                      <span className="layer-count">z{TREES_MIN_ZOOM}</span>
                    ) : count != null ? (
                      <span className="layer-count">{count}</span>
                    ) : null}
                  </button>
                  <button
                    type="button"
                    className="layer-chip-sql"
                    title={`Open ${key} SQL`}
                    onClick={() => void inspectLayerSql(key)}
                  >
                    SQL
                  </button>
                </div>
              );
            })}
          </div>
          <TagFilterRow
            visibility={visibility}
            vocab={tagVocab}
            selected={tagFilter}
            onToggle={(slug, id) =>
              setTagFilter((cur) => {
                const now = cur[slug] ?? [];
                const next = now.includes(id) ? now.filter((x) => x !== id) : [...now, id];
                return { ...cur, [slug]: next };
              })
            }
          />
          {layerError && <p className="error">Layer error: {layerError}</p>}
        </header>

        <div className="task-slot">
          <div className="task-tabs" role="tablist" aria-label="Data pane tasks">
            {(
              [
                ["nearby", "Nearby"],
                ["compare", "Compare"],
                ["query", "Query"],
              ] as const
            ).map(([id, label]) => (
              <button
                key={id}
                type="button"
                role="tab"
                id={`tab-${id}`}
                aria-selected={taskTab === id}
                aria-controls={`panel-${id}`}
                className={`task-tab${taskTab === id ? " task-tab-active" : ""}`}
                onClick={() => setTaskTab(id)}
              >
                {label}
              </button>
            ))}
          </div>

          {taskTab === "nearby" && (
            <div className="task-panel" role="tabpanel" id="panel-nearby" aria-labelledby="tab-nearby">
              {nearestError && <p className="error">{nearestError}</p>}
              {!nearest && !nearestError && (
                <p className="hint">Click the map to look up nearest amenities.</p>
              )}
              {featureDetail && (
                <FeatureCard feature={featureDetail} onClose={() => setFeatureDetail(null)} />
              )}
              {nearest && (
                <NearestPanel
                  result={nearest}
                  onClear={clearPin}
                  onShowQuery={sqlOffer ? showNearestQuery : undefined}
                />
              )}
            </div>
          )}

          {taskTab === "compare" && (
            <div className="task-panel" role="tabpanel" id="panel-compare" aria-labelledby="tab-compare">
              <ComparePanel
                measure={compareMeasure}
                onMeasureChange={setCompareMeasure}
                density={density}
                greenBorough={greenBorough}
                schoolGreen={schoolGreen}
                operatorStats={operatorStats}
                treeStats={treeStats}
                selectedDistrict={selectedDistrict}
                onSelectBorough={selectBorough}
                onShowQuery={(doc) => {
                  const keys = COMPARE_MEASURE_LAYERS[compareMeasure];
                  setVisibility((v) => {
                    const next = { ...v };
                    for (const key of keys) next[key] = true;
                    return next;
                  });
                  requestReplace(doc);
                }}
              />
            </div>
          )}

          {taskTab === "query" && (
            <div
              className="task-panel query-grid"
              role="tabpanel"
              id="panel-query"
              aria-labelledby="tab-query"
            >
              {(sqlOffer &&
                (!queryDoc ||
                  queryDoc.filename !== sqlOffer.filename ||
                  queryDoc.sql !== sqlOffer.sql)) ||
              pendingReplace ? (
                <div className="query-alerts">
                  {sqlOffer &&
                    (!queryDoc ||
                      queryDoc.filename !== sqlOffer.filename ||
                      queryDoc.sql !== sqlOffer.sql) && (
                      <div className="sql-offer">
                        <span>Nearest query ready</span>
                        <button
                          type="button"
                          className="secondary starter-btn"
                          onClick={showNearestQuery}
                        >
                          Open
                        </button>
                      </div>
                    )}
                  {pendingReplace && (
                    <div className="sql-replace-confirm">
                      <span>Replace edited SQL?</span>
                      <div className="nearby-actions">
                        <button
                          type="button"
                          className="starter-btn"
                          onClick={() => applyDocument(pendingReplace, activePatternId)}
                        >
                          Replace
                        </button>
                        <button
                          type="button"
                          className="secondary starter-btn"
                          onClick={() => setPendingReplace(null)}
                        >
                          Keep
                        </button>
                      </div>
                    </div>
                  )}
                </div>
              ) : null}

              <div className="query-nav">
                <div className="query-patterns" aria-label="Patterns">
                  {PATTERNS.map((p) => (
                    <button
                      key={p.id}
                      type="button"
                      className={`pattern-chip${activePatternId === p.id ? " pattern-chip-active" : ""}`}
                      title={p.blurb}
                      onClick={() => openPattern(p.id)}
                    >
                      {p.title}
                    </button>
                  ))}
                  <button
                    type="button"
                    className={`pattern-chip pattern-chip-meta${glossaryOpen ? " pattern-chip-active" : ""}`}
                    aria-pressed={glossaryOpen}
                    onClick={() => setGlossaryOpen((o) => !o)}
                  >
                    Glossary
                  </button>
                </div>
              </div>

              <div className="query-main">
                <div className="query-doc-head">
                  <h3 className="query-doc-title">{queryDoc?.title ?? "SQL"}</h3>
                  {queryDirty && <span className="query-doc-dirty">Edited</span>}
                  {queryBinds.length > 0 && (
                    <span className="bind-inline" title="Filled from map at Run">
                      {queryBinds.map((k) => `:${k}`).join(" ")}
                    </span>
                  )}
                </div>
                {activePattern && <p className="query-analyze">{activePattern.analyze}</p>}
                <textarea
                  className="sql-editor"
                  value={queryDoc?.sql ?? ""}
                  placeholder="Pick a pattern, or write SELECT …"
                  onChange={(e) => {
                    const sql = e.target.value;
                    setActivePatternId(null);
                    setQueryDoc((d) => (d ? { ...d, sql } : makeDoc("Scratch", sql)));
                  }}
                  spellCheck={false}
                  aria-label="SQL editor"
                />
                <div className="sql-actions">
                  <button
                    type="button"
                    disabled={sqlBusy || !queryDoc?.sql.trim()}
                    onClick={() => void runDocument(false)}
                  >
                    Run
                  </button>
                  <button
                    type="button"
                    className="secondary"
                    disabled={sqlBusy || !queryDoc?.sql.trim()}
                    onClick={() => void runDocument(true)}
                  >
                    Explain
                  </button>
                  {(activePattern?.refFile || activePattern?.refLayer) && (
                    <button
                      type="button"
                      className="secondary"
                      disabled={sqlBusy}
                      onClick={() => void openReferenceFile()}
                    >
                      App file
                    </button>
                  )}
                  {sqlRun?.geojson?.features?.length ? (
                    <label className="layer-check">
                      <input
                        type="checkbox"
                        checked={showQueryOnMap}
                        onChange={(e) => setShowQueryOnMap(e.target.checked)}
                      />
                      Map
                    </label>
                  ) : null}
                </div>
                {sqlError && <p className="error">{sqlError}</p>}
              </div>

              <div className="query-results">
                {sqlRun ? <SqlResultPanel result={sqlRun} /> : <p className="hint">Results appear here.</p>}
              </div>
            </div>
          )}
        </div>
      </aside>
      <div
        className="split-handle"
        role="separator"
        aria-orientation="vertical"
        aria-label="Resize data pane"
        aria-valuemin={20}
        aria-valuemax={80}
        aria-valuenow={Math.round(panelPct)}
        tabIndex={0}
        onPointerDown={(e) => {
          e.preventDefault();
          setDraggingSplit(true);
        }}
        onKeyDown={(e) => {
          if (e.key === "ArrowLeft") {
            e.preventDefault();
            setPanelPct((p) => Math.max(20, p - 2));
          } else if (e.key === "ArrowRight") {
            e.preventDefault();
            setPanelPct((p) => Math.min(80, p + 2));
          } else if (e.key === "Home") {
            e.preventDefault();
            setPanelPct(36);
          }
        }}
      />
      <div className="map-wrap">
        <div className="map" ref={mapNode} />
        <div className="map-chip">Berlin open data · distances in metres (EPSG:25833)</div>
        {(visibleLegendKeys.length > 0 || (showQueryOnMap && sqlRun?.geojson?.features?.length)) && (
          <div className="legend" aria-label="Map legend">
            <div className="legend-title">Legend</div>
            {visibleLegendKeys.map((key) => (
              <div className="legend-row" key={key}>
                <span
                  className={`swatch swatch-${LAYERS[key].kind}`}
                  style={{
                    background: LAYERS[key].swatch,
                    opacity: LAYERS[key].kind === "fill" ? 0.7 : 1,
                  }}
                />
                {LAYERS[key].label}
              </div>
            ))}
            {showQueryOnMap && sqlRun?.geojson?.features?.length ? (
              <div className="legend-row">
                <span className="swatch swatch-dot" style={{ background: "#c45c26" }} />
                {queryDoc?.title ?? "Query result"}
              </div>
            ) : null}
          </div>
        )}
        <div className="status">{status}</div>
      </div>
      {glossaryOpen && (
        <GlossaryDialog
          tables={SCHEMA_TABLES}
          highlight={activePattern?.tables ?? []}
          onInsert={insertIntoSql}
          onClose={() => setGlossaryOpen(false)}
        />
      )}
    </div>
  );
}

function NearestPanel({
  result,
  onClear,
  onShowQuery,
}: {
  result: NearestAmenities;
  onClear: () => void;
  onShowQuery?: () => void;
}) {
  const hits = result.nearest ?? [];
  const maxDist = hits.length > 0 ? Math.max(...hits.map((h) => h.distance_m), 1) : 1;

  return (
    <div className="analysis-card nearby-card">
      <div className="nearby-head">
        <h3 className="nearby-title">Nearest</h3>
        <div className="nearby-actions">
          {onShowQuery && (
            <button type="button" className="secondary starter-btn" onClick={onShowQuery}>
              SQL
            </button>
          )}
          <button type="button" className="secondary starter-btn" onClick={onClear}>
            Clear
          </button>
        </div>
      </div>
      {hits.length > 0 ? (
        <ul className="hit-list hit-list-bars">
          {hits.map((n, i) => (
            <li key={`${n.layer}-${i}`}>
              <div className="hit-meta">
                <span>
                  {layerSingular(n.layer) ?? n.layer}
                  {n.name ? ` — ${n.name}` : ""}
                </span>
                <span className="hit-dist">{n.distance_m.toFixed(0)} m</span>
              </div>
              <div className="hit-bar-track" aria-hidden="true">
                <span
                  className="hit-bar"
                  style={{ width: `${Math.max(4, (n.distance_m / maxDist) * 100)}%` }}
                />
              </div>
            </li>
          ))}
        </ul>
      ) : (
        <p className="empty">No amenity rows yet.</p>
      )}
    </div>
  );
}

/** Tag chips (U7) for the visible layers whose kind carries tags; AND semantics on the server. */
function TagFilterRow({
  visibility,
  vocab,
  selected,
  onToggle,
}: {
  visibility: Visibility;
  vocab: Record<string, TagItem[]>;
  selected: Partial<Record<LayerSlug, number[]>>;
  onToggle: (slug: LayerSlug, tagId: number) => void;
}) {
  const slugs = (Object.keys(TAGGABLE_LAYERS) as LayerSlug[]).filter(
    (slug) => visibility[slug] && (vocab[TAGGABLE_LAYERS[slug]!]?.length ?? 0) > 0
  );
  if (slugs.length === 0) return null;
  return (
    <div className="tag-filter" aria-label="Tag filters">
      {slugs.map((slug) => (
        <details key={slug} className="tag-filter-group">
          <summary>
            {LAYERS[slug].label} tags
            {(selected[slug]?.length ?? 0) > 0 && ` (${selected[slug]!.length})`}
          </summary>
          <div className="tag-chips">
            {vocab[TAGGABLE_LAYERS[slug]!].map((t) => (
              <button
                key={t.id}
                type="button"
                className={`tag-chip${selected[slug]?.includes(t.id) ? " tag-chip-on" : ""}`}
                aria-pressed={selected[slug]?.includes(t.id) ?? false}
                title={`${t.feature_count} features`}
                onClick={() => onToggle(slug, t.id)}
              >
                {t.label}
              </button>
            ))}
          </div>
        </details>
      ))}
    </div>
  );
}

const DETAIL_LABELS: Record<string, string> = {
  planting_year: "Planted",
  trunk_circumference_cm: "Trunk (cm)",
  height_m: "Height (m)",
  crown_diameter_m: "Crown (m)",
  capacity: "Places",
  charge_points: "Charge points",
  max_power_kw: "Max power (kW)",
  commissioned_on: "Commissioned",
  public_space: "Public space",
};

/** One feature with its tags, operator and typed detail (GET /features/{layer}/{id}). */
function FeatureCard({ feature, onClose }: { feature: FeatureDetail; onClose: () => void }) {
  const p = feature.properties;
  const species = (p.detail as { species?: { botanical_name: string; german_name?: string } | null } | null)
    ?.species;
  const detailRows = Object.entries(p.detail ?? {}).filter(
    ([k, v]) => v != null && k !== "species" && DETAIL_LABELS[k]
  );
  return (
    <div className="analysis-card feature-card">
      <div className="nearby-head">
        <h3 className="nearby-title">{p.name ?? "Unnamed"}</h3>
        <button type="button" className="secondary starter-btn" onClick={onClose}>
          Close
        </button>
      </div>
      <p className="hint">
        {p.layer_kind.replace(/_/g, " ")}
        {p.subtype ? ` · ${p.subtype}` : ""}
        {p.district ? ` · ${p.district}` : ""}
      </p>
      {p.operator && (
        <p className="feature-line">
          <strong>Operator</strong> {p.operator.name}
          {p.operator.operator_type ? ` (${p.operator.operator_type})` : ""}
        </p>
      )}
      {species && (
        <p className="feature-line">
          <strong>Species</strong> {species.german_name ?? species.botanical_name}
          {species.german_name ? ` · ${species.botanical_name}` : ""}
        </p>
      )}
      {detailRows.length > 0 && (
        <dl className="feature-detail">
          {detailRows.map(([k, v]) => (
            <div key={k}>
              <dt>{DETAIL_LABELS[k]}</dt>
              <dd>{typeof v === "boolean" ? (v ? "yes" : "no") : String(v)}</dd>
            </div>
          ))}
        </dl>
      )}
      {(p.tags?.length ?? 0) > 0 && (
        <div className="tag-chips">
          {p.tags!.map((t) => (
            <span key={t.id} className="tag-chip tag-chip-static">
              {t.label}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}

function GlossaryDialog({
  tables,
  highlight,
  onInsert,
  onClose,
}: {
  tables: SchemaTable[];
  highlight: string[];
  onInsert: (token: string) => void;
  onClose: () => void;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  const closing = useRef(false);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    el.showModal();
    return () => {
      closing.current = true;
      if (el.open) el.close();
    };
  }, []);

  return (
    <dialog
      ref={ref}
      className="glossary-dialog"
      aria-labelledby="glossary-title"
      onClose={() => {
        if (!closing.current) onClose();
      }}
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div className="glossary-dialog-card">
        <header className="glossary-dialog-head">
          <h2 id="glossary-title">Tables</h2>
          <button type="button" className="secondary starter-btn" onClick={onClose}>
            Close
          </button>
        </header>
        <div className="glossary-dialog-body">
          <SchemaGlossary tables={tables} highlight={highlight} onInsert={onInsert} />
        </div>
      </div>
    </dialog>
  );
}

function SchemaGlossary({
  tables,
  highlight = [],
  onInsert,
}: {
  tables: SchemaTable[];
  highlight?: string[];
  onInsert: (token: string) => void;
}) {
  if (!tables.length) return null;
  const hi = new Set(highlight);
  return (
    <dl className="glossary-list">
      {tables.map((t) => (
        <div
          className={`glossary-entry${hi.has(t.table) ? " glossary-entry-hot" : ""}`}
          key={t.table}
        >
          <dt>
            <button
              type="button"
              className="schema-chip schema-chip-table"
              title={`Insert ${t.table}`}
              onClick={() => onInsert(t.table)}
            >
              {t.table}
            </button>
            <span className="glossary-entry-label">{t.label}</span>
          </dt>
          <dd>
            <p className="glossary-about">{t.about}</p>
            <div className="schema-cheat-cols">
              {t.columns.map((c) => (
                <button
                  key={c.name}
                  type="button"
                  className="schema-chip"
                  title={c.note ? `${c.name} (${c.note})` : `Insert ${c.name}`}
                  onClick={() => onInsert(c.name)}
                >
                  <code>{c.name}</code>
                  {c.note && <span className="schema-chip-note">{c.note}</span>}
                </button>
              ))}
            </div>
          </dd>
        </div>
      ))}
    </dl>
  );
}

function SqlResultPanel({ result }: { result: SqlRunResult }) {
  if (result.explain) {
    return (
      <div className="analysis-card">
        <h3>EXPLAIN plan</h3>
        <pre className="sql-pre">{result.plan}</pre>
      </div>
    );
  }
  return (
    <div className="analysis-card">
      <h3>
        Results · {result.row_count}
        {result.truncated ? "+" : ""} rows
        {result.geojson ? ` · ${result.geojson.features.length} map features` : ""}
      </h3>
      {result.columns.length > 0 ? (
        <div className="sql-table-wrap">
          <table className="coverage-table density-table">
            <thead>
              <tr>
                {result.columns.map((c) => (
                  <th key={c}>{c}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {result.rows.slice(0, 50).map((row, i) => (
                <tr key={i}>
                  {row.map((cell, j) => (
                    <td key={j}>{formatCell(cell)}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <p className="hint">No rows.</p>
      )}
    </div>
  );
}

function formatCell(cell: unknown): string {
  if (cell == null) return "null";
  if (typeof cell === "object") return JSON.stringify(cell).slice(0, 80);
  return String(cell);
}

type CompareRow = {
  id: number | "";
  name: string;
  value: number | null;
  secondary?: string;
};

function ComparePanel({
  measure,
  onMeasureChange,
  density,
  greenBorough,
  schoolGreen,
  operatorStats,
  treeStats,
  selectedDistrict,
  onSelectBorough,
  onShowQuery,
}: {
  measure: CompareMeasure;
  onMeasureChange: (m: CompareMeasure) => void;
  density: AnalysisResponse | null;
  greenBorough: AnalysisResponse | null;
  schoolGreen: AnalysisResponse | null;
  operatorStats: AnalysisResponse | null;
  treeStats: AnalysisResponse | null;
  selectedDistrict: number | "";
  onSelectBorough: (id: number | "") => void;
  onShowQuery: (doc: QueryDoc) => void;
}) {
  const analysis =
    measure === "green_pct"
      ? greenBorough
      : measure === "school_park"
        ? schoolGreen
        : measure === "operators"
          ? operatorStats
          : measure === "tree_species" || measure === "tree_year"
            ? treeStats
            : density;

  const districtIdOf = (r: Record<string, unknown>): number | "" =>
    typeof r.district_id === "number" ? r.district_id : "";

  const rows: CompareRow[] = (() => {
    if (measure === "green_pct") {
      return (greenBorough?.results ?? [])
        .map((r) => ({
          id: districtIdOf(r),
          name: String(r.district_name ?? "—"),
          value: typeof r.pct_of_district_area === "number" ? r.pct_of_district_area : null,
        }))
        .sort((a, b) => (b.value ?? 0) - (a.value ?? 0));
    }
    if (measure === "school_park") {
      return (schoolGreen?.results ?? [])
        .map((r) => ({
          id: districtIdOf(r),
          name: String(r.district_name ?? "—"),
          value: typeof r.median_m === "number" ? r.median_m : null,
          secondary:
            typeof r.p90_m === "number" ? `p90 ${r.p90_m.toFixed(0)} m` : undefined,
        }))
        .sort((a, b) => (a.value ?? Infinity) - (b.value ?? Infinity));
    }
    if (measure === "operators") {
      return (operatorStats?.results ?? [])
        .filter((r) => r.rank === 1)
        .map((r) => ({
          id: districtIdOf(r),
          name: String(r.district_name ?? "—"),
          value: typeof r.feature_count === "number" ? r.feature_count : null,
          secondary: String(r.operator_name ?? ""),
        }))
        .sort((a, b) => (b.value ?? 0) - (a.value ?? 0));
    }
    if (measure === "tree_species") {
      return (treeStats?.results ?? [])
        .map((r) => ({
          id: districtIdOf(r),
          name: String(r.district_name ?? "—"),
          value: typeof r.species_count === "number" ? r.species_count : null,
          secondary: r.top_genus ? `top genus ${String(r.top_genus)}` : undefined,
        }))
        .sort((a, b) => (b.value ?? 0) - (a.value ?? 0));
    }
    if (measure === "tree_year") {
      return (treeStats?.results ?? [])
        .map((r) => ({
          id: districtIdOf(r),
          name: String(r.district_name ?? "—"),
          value: typeof r.median_planting_year === "number" ? r.median_planting_year : null,
        }))
        .sort((a, b) => (a.value ?? Infinity) - (b.value ?? Infinity));
    }
    const key = measure;
    return (density?.results ?? [])
      .filter((r) => typeof r.district_id === "number") // drop the ROLLUP total row
      .map((r) => ({
        id: districtIdOf(r),
        name: String(r.district_name ?? "—"),
        value: Number(r[key] ?? 0),
      }))
      .sort((a, b) => (b.value ?? 0) - (a.value ?? 0));
  })();

  const maxValue = Math.max(...rows.map((r) => r.value ?? 0), 1);
  const unit =
    measure === "green_pct" ? "%" : measure === "school_park" ? "m" : "";

  const showQuery = async () => {
    const ref = analysis?.sql_ref;
    if (!ref) return;
    try {
      const file = await api.sqlFile(ref);
      onShowQuery(
        makeDoc(titleForSqlFile(file.name), file.sql, {
          filename: file.name,
          caveat: analysis?.caveat,
        })
      );
    } catch {
      /* ignore */
    }
  };

  return (
    <div className="analysis-card compare-card">
      <div className="compare-controls">
        <label className="compare-measure">
          <span className="sr-only">Measure</span>
          <select
            value={measure}
            onChange={(e) => onMeasureChange(e.target.value as CompareMeasure)}
          >
            {COMPARE_MEASURES.map((m) => (
              <option key={m.id} value={m.id}>
                {m.label}
              </option>
            ))}
          </select>
        </label>
        {analysis?.sql_ref && (
          <button type="button" className="secondary starter-btn" onClick={() => void showQuery()}>
            SQL
          </button>
        )}
      </div>
      <div className="compare-grid">
        <button
          type="button"
          className={`compare-row${!selectedDistrict ? " compare-row-active" : ""}`}
          onClick={() => onSelectBorough("")}
        >
          <span className="compare-name">All boroughs</span>
          <span className="compare-value">Viewport</span>
        </button>
        {!analysis && <p className="hint">Loading…</p>}
        {rows.map((r) => {
          const pct = r.value == null ? 0 : (r.value / maxValue) * 100;
          const label =
            r.value == null
              ? "—"
              : measure === "tree_year"
                ? String(Math.round(r.value))
                : measure === "green_pct"
                ? `${r.value.toFixed(1)}%`
                : measure === "school_park"
                  ? `${r.value.toFixed(0)} m`
                  : String(r.value);
          return (
            <button
              type="button"
              key={r.name}
              className={`compare-row${selectedDistrict === r.id ? " compare-row-active" : ""}`}
              onClick={() => (typeof r.id === "number" ? onSelectBorough(r.id) : onSelectBorough(""))}
            >
              <span className="compare-name">
                {r.name}
                {r.secondary && <span className="compare-secondary">{r.secondary}</span>}
              </span>
              <span className="pct-cell compare-bar">
                <span className="pct-bar" style={{ width: `${Math.min(pct, 100)}%` }} />
                <span className="pct-label">
                  {label}
                  {unit && measure !== "green_pct" && measure !== "school_park" ? ` ${unit}` : ""}
                </span>
              </span>
            </button>
          );
        })}
      </div>
    </div>
  );
}

function ensureNeighborhoodLabels(map: Map) {
  if (map.getLayer("neighborhoods-label") || !map.getSource("neighborhoods")) return;
  map.addLayer({
    id: "neighborhoods-label",
    type: "symbol",
    source: "neighborhoods",
    minzoom: 11,
    layout: {
      "text-field": ["get", "name"],
      "text-size": ["interpolate", ["linear"], ["zoom"], 11, 11, 14, 14],
      "text-font": ["Noto Sans Regular"],
      "text-max-width": 8,
      "text-padding": 2,
      visibility: "none",
    },
    paint: {
      "text-color": "#3d4f58",
      "text-halo-color": "rgba(252, 252, 250, 0.95)",
      "text-halo-width": 1.4,
      "text-opacity": 0.95,
    },
  } as never);
}

function ensureUserQueryOverlay(map: Map, data: FeatureCollection) {
  if (map.getSource("user_query")) {
    (map.getSource("user_query") as maplibregl.GeoJSONSource).setData(data as never);
  } else {
    map.addSource("user_query", { type: "geojson", data: data as never });
  }

  if (!map.getLayer("user_query-fill")) {
    map.addLayer({
      id: "user_query-fill",
      type: "fill",
      source: "user_query",
      filter: [
        "any",
        ["==", ["geometry-type"], "Polygon"],
        ["==", ["geometry-type"], "MultiPolygon"],
      ],
      paint: { "fill-color": "#c45c26", "fill-opacity": 0.35 },
    } as never);
  }
  if (!map.getLayer("user_query-outline")) {
    map.addLayer({
      id: "user_query-outline",
      type: "line",
      source: "user_query",
      filter: [
        "any",
        ["==", ["geometry-type"], "Polygon"],
        ["==", ["geometry-type"], "MultiPolygon"],
        ["==", ["geometry-type"], "LineString"],
        ["==", ["geometry-type"], "MultiLineString"],
      ],
      paint: { "line-color": "#8a3a12", "line-width": 1.4 },
    } as never);
  }
  if (!map.getLayer("user_query-circle")) {
    map.addLayer({
      id: "user_query-circle",
      type: "circle",
      source: "user_query",
      filter: [
        "any",
        ["==", ["geometry-type"], "Point"],
        ["==", ["geometry-type"], "MultiPoint"],
      ],
      paint: {
        "circle-radius": 6,
        "circle-color": "#c45c26",
        "circle-stroke-width": 1.5,
        "circle-stroke-color": "#fff",
        "circle-opacity": 0.95,
      },
    } as never);
  }
  for (const id of ["user_query-fill", "user_query-outline", "user_query-circle"]) {
    if (map.getLayer(id)) map.setLayoutProperty(id, "visibility", "visible");
  }
}

function ensureSource(map: Map, id: string, data: FeatureCollection, style: SourceStyle) {
  if (map.getSource(id)) {
    (map.getSource(id) as maplibregl.GeoJSONSource).setData(data as never);
    const mainId = style.type === "line" ? `${id}-line` : `${id}-layer`;
    if (map.getLayer(mainId)) {
      for (const [key, value] of Object.entries(style.paint)) {
        map.setPaintProperty(mainId, key, value as never);
      }
    }
    if (style.outline && map.getLayer(`${id}-outline`)) {
      for (const [key, value] of Object.entries(style.outline)) {
        map.setPaintProperty(`${id}-outline`, key, value as never);
      }
    }
    return;
  }

  map.addSource(id, { type: "geojson", data: data as never });

  if (style.type === "line") {
    map.addLayer({
      id: `${id}-line`,
      type: "line",
      source: id,
      paint: style.paint,
      ...(style.minzoom != null ? { minzoom: style.minzoom } : {}),
    } as never);
    return;
  }

  map.addLayer({
    id: `${id}-layer`,
    type: style.type,
    source: id,
    paint: style.paint,
    ...(style.minzoom != null ? { minzoom: style.minzoom } : {}),
  } as never);

  if (style.outline) {
    map.addLayer({
      id: `${id}-outline`,
      type: "line",
      source: id,
      paint: style.outline,
      ...(style.minzoom != null ? { minzoom: style.minzoom } : {}),
    } as never);
  }
}

function flattenCoords(coords: unknown): [number, number][] {
  const out: [number, number][] = [];
  const walk = (node: unknown) => {
    if (!Array.isArray(node)) return;
    if (typeof node[0] === "number" && typeof node[1] === "number") {
      out.push([node[0] as number, node[1] as number]);
      return;
    }
    node.forEach(walk);
  };
  walk(coords);
  return out;
}
