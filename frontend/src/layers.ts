/**
 * Layer registry — single source of truth for the map layers.
 * Owns chip labels/swatches, API paths, and map SourceStyle construction.
 * Must not import from App.tsx (cycle); App.tsx imports from here.
 */

/** Heavy tree inventories — only fetched/rendered at this zoom or deeper. */
export const TREES_MIN_ZOOM = 15;

/** Max lon/lat span (degrees) before we skip fetching zoom-gated layers. */
export const TREES_MAX_BBOX_SPAN = 0.18;

export type SourceStyle = {
  type: "fill" | "circle" | "line";
  paint: Record<string, unknown>;
  outline?: Record<string, unknown>;
  minzoom?: number;
};

/** Amenity-dot circle paint that grows with zoom. */
export function zoomCirclePaint(
  color: string,
  opts?: { low?: number; mid?: number; high?: number; opacity?: number }
) {
  const low = opts?.low ?? 1.8;
  const mid = opts?.mid ?? 3.5;
  const high = opts?.high ?? 6;
  const opacity = opts?.opacity ?? 0.8;
  return {
    "circle-radius": ["interpolate", ["linear"], ["zoom"], 9, low, 13, mid, 16, high] as never,
    "circle-color": color,
    "circle-stroke-width": 0.7,
    "circle-stroke-color": "#fff",
    "circle-opacity": ["interpolate", ["linear"], ["zoom"], 9, opacity * 0.55, 13, opacity] as never,
  };
}

export const LAYERS = {
  districts: {
    label: "Districts",
    kind: "line",
    swatch: "#102a43",
    path: "/districts",
    citywide: true,
    style: {
      type: "line",
      paint: {
        "line-color": "#102a43",
        "line-width": ["interpolate", ["linear"], ["zoom"], 9, 2.4, 13, 4] as never,
        "line-opacity": 0.95,
      },
    },
  },
  neighborhoods: {
    label: "Neighborhoods",
    kind: "line",
    swatch: "#9bb0bf",
    path: "/neighborhoods",
    citywide: true,
    style: {
      type: "line",
      paint: {
        "line-color": "#9bb0bf",
        "line-width": ["interpolate", ["linear"], ["zoom"], 9, 1.8, 13, 3.2] as never,
        "line-opacity": 0.85,
      },
    },
  },
  green_spaces: {
    label: "Parks",
    singular: "Park",
    kind: "fill",
    swatch: "#2f855a",
    path: "/green-spaces",
    style: {
      type: "fill",
      paint: {
        "fill-color": "#2f855a",
        "fill-opacity": 0.18,
      },
      outline: {
        "line-color": "#276749",
        "line-width": 0.8,
        "line-opacity": 0.45,
      },
    },
  },
  cemeteries: {
    label: "Cemeteries",
    singular: "Cemetery",
    kind: "fill",
    swatch: "#5a6b4a",
    path: "/cemeteries",
    style: {
      type: "fill",
      paint: {
        "fill-color": "#5a6b4a",
        "fill-opacity": 0.28,
      },
      outline: {
        "line-color": "#3d4a32",
        "line-width": 0.8,
        "line-opacity": 0.55,
      },
    },
  },
  playgrounds: {
    label: "Playgrounds",
    singular: "Playground",
    kind: "fill",
    swatch: "#c4a035",
    path: "/playgrounds",
    style: {
      type: "fill",
      paint: {
        "fill-color": "#c4a035",
        "fill-opacity": 0.35,
      },
      outline: {
        "line-color": "#8a7020",
        "line-width": 0.9,
        "line-opacity": 0.7,
      },
    },
  },
  schools: {
    label: "Schools",
    kind: "dot",
    swatch: "#c45c26",
    path: "/schools",
    style: {
      type: "circle",
      paint: zoomCirclePaint("#c45c26", { low: 2, mid: 3.5, high: 6.5, opacity: 0.85 }),
    },
  },
  kitas: {
    label: "Daycare",
    singular: "Daycare",
    kind: "dot",
    swatch: "#d4893a",
    path: "/kitas",
    style: {
      type: "circle",
      paint: zoomCirclePaint("#d4893a", { low: 2, mid: 3.5, high: 6.5, opacity: 0.85 }),
    },
  },
  hospitals: {
    label: "Hospitals",
    singular: "Hospital",
    kind: "dot",
    swatch: "#a33b5c",
    path: "/hospitals",
    style: {
      type: "circle",
      paint: zoomCirclePaint("#a33b5c", { low: 2.5, mid: 4.5, high: 7.5, opacity: 0.9 }),
    },
  },
  trees: {
    label: "Street trees",
    singular: "Street tree",
    kind: "dot",
    swatch: "#2f6b3c",
    path: "/trees",
    style: {
      type: "circle",
      paint: {
        "circle-radius": ["interpolate", ["linear"], ["zoom"], 14, 2, 17, 4.5] as never,
        "circle-color": "#2f6b3c",
        "circle-stroke-width": 0,
        "circle-opacity": 0.55,
      },
      minzoom: TREES_MIN_ZOOM,
    },
  },
  park_trees: {
    label: "Park trees",
    singular: "Park tree",
    kind: "dot",
    swatch: "#3d8b55",
    path: "/park-trees",
    style: {
      type: "circle",
      paint: {
        "circle-radius": ["interpolate", ["linear"], ["zoom"], 14, 2, 17, 4.5] as never,
        "circle-color": "#3d8b55",
        "circle-stroke-width": 0,
        "circle-opacity": 0.55,
      },
      minzoom: TREES_MIN_ZOOM,
    },
  },
  bike_parking: {
    label: "Bike parking",
    singular: "Bike parking",
    kind: "dot",
    swatch: "#0f6a5a",
    path: "/bike-parking",
    style: {
      type: "circle",
      paint: zoomCirclePaint("#0f6a5a"),
    },
  },
  ev_chargers: {
    label: "EV chargers",
    singular: "EV charger",
    kind: "dot",
    swatch: "#1a6fbf",
    path: "/ev-chargers",
    style: {
      type: "circle",
      paint: zoomCirclePaint("#1a6fbf"),
    },
  },
  drinking_fountains: {
    label: "Drinking fountains",
    singular: "Drinking fountain",
    kind: "dot",
    swatch: "#3a7ca5",
    path: "/drinking-fountains",
    style: {
      type: "circle",
      paint: zoomCirclePaint("#3a7ca5", { low: 2.2, mid: 4, high: 7, opacity: 0.88 }),
    },
  },
  bathing_waters: {
    label: "Bathing waters",
    singular: "Bathing water",
    kind: "dot",
    swatch: "#0b6e99",
    path: "/bathing-waters",
    style: {
      type: "circle",
      paint: zoomCirclePaint("#0b6e99", { low: 3, mid: 5, high: 8, opacity: 0.92 }),
    },
  },
  toilets: {
    label: "Public toilets",
    singular: "Public toilet",
    kind: "dot",
    swatch: "#6b5b7a",
    path: "/toilets",
    style: {
      type: "circle",
      paint: zoomCirclePaint("#6b5b7a"),
    },
  },
  sports_facilities: {
    label: "Sports facilities",
    singular: "Sports facility",
    kind: "dot",
    swatch: "#b33b3b",
    path: "/sports-facilities",
    style: {
      type: "circle",
      paint: zoomCirclePaint("#b33b3b"),
    },
  },
  park_and_ride: {
    label: "Park & Ride",
    singular: "Park & Ride",
    kind: "dot",
    swatch: "#4a5f8a",
    path: "/park-and-ride",
    style: {
      type: "circle",
      paint: zoomCirclePaint("#4a5f8a", { low: 2.5, mid: 4.5, high: 7.5, opacity: 0.9 }),
    },
  },
} as const;

export type LayerSlug = keyof typeof LAYERS;

/** Layer slug → amenity_kind.code (districts and neighborhoods have none). */
export const KIND_CODES: Partial<Record<LayerSlug, string>> = {
  green_spaces: "green_space",
  cemeteries: "cemetery",
  playgrounds: "playground",
  schools: "school",
  kitas: "kita",
  hospitals: "hospital",
  trees: "street_tree",
  park_trees: "park_tree",
  bike_parking: "bike_parking",
  ev_chargers: "ev_charger",
  drinking_fountains: "drinking_fountain",
  bathing_waters: "bathing_water",
  toilets: "toilet",
  sports_facilities: "sports_facility",
  park_and_ride: "park_and_ride",
};

/** Layers whose kind carries tags (?tag= filter): slug → kind_code. */
export const TAGGABLE_LAYERS: Partial<Record<LayerSlug, string>> = {
  kitas: "kita",
  ev_chargers: "ev_charger",
  toilets: "toilet",
};

export function isZoomGated(slug: LayerSlug): boolean {
  return "minzoom" in LAYERS[slug].style && LAYERS[slug].style.minzoom != null;
}

/** Layers that require zoom ≥ TREES_MIN_ZOOM before fetch/render. */
export const ZOOM_GATED_LAYERS = (Object.keys(LAYERS) as LayerSlug[]).filter((slug) =>
  isZoomGated(slug)
);

/** Registry entry widened to one shape so optional props are accessible. */
export type LayerDef = {
  label: string;
  singular?: string;
  kind: "line" | "fill" | "dot";
  swatch: string;
  /** Kebab-case API path for the GeoJSON endpoint. */
  path: string;
  /** Citywide layers are fetched without bbox/borough filters. */
  citywide?: boolean;
  style: SourceStyle;
};

export function layerDef(slug: LayerSlug): LayerDef {
  return LAYERS[slug];
}

/** Singular noun for "Nearest …" lines; undefined for layers without one. */
export function layerSingular(layer: string): string | undefined {
  return layer in LAYERS ? layerDef(layer as LayerSlug).singular : undefined;
}

/** slug → kebab-case API path. */
export const LAYER_PATHS = Object.fromEntries(
  (Object.keys(LAYERS) as LayerSlug[]).map((slug) => [slug, LAYERS[slug].path])
) as Record<LayerSlug, string>;

export function buildSourceStyle(slug: LayerSlug): SourceStyle {
  return LAYERS[slug].style;
}
