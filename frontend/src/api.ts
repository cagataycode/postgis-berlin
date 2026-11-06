import { LAYER_PATHS, LayerSlug } from "./layers";

const API_BASE = import.meta.env.VITE_API_BASE ?? "/api";

const responseCache = new Map<string, { expires: number; data: unknown }>();
const inflight = new Map<string, Promise<unknown>>();

const DEFAULT_TTL_MS = 10 * 60 * 1000;

async function getJson<T>(path: string, opts?: { ttlMs?: number; cache?: boolean }): Promise<T> {
  const cacheable = opts?.cache !== false;
  const ttlMs = opts?.ttlMs ?? DEFAULT_TTL_MS;
  const key = path;

  if (cacheable) {
    const hit = responseCache.get(key);
    if (hit && hit.expires > Date.now()) {
      return hit.data as T;
    }
    const pending = inflight.get(key);
    if (pending) {
      return pending as Promise<T>;
    }
  }

  const request = (async () => {
    const res = await fetch(`${API_BASE}${path}`);
    if (!res.ok) {
      throw new Error(`${res.status} ${res.statusText}`);
    }
    const data = (await res.json()) as T;
    if (cacheable) {
      responseCache.set(key, { expires: Date.now() + ttlMs, data });
    }
    return data;
  })();

  if (cacheable) {
    inflight.set(key, request);
    try {
      return await request;
    } finally {
      inflight.delete(key);
    }
  }

  return request;
}

export function clearApiCache(): void {
  responseCache.clear();
  inflight.clear();
}

export type LayerMeta = {
  slug: string;
  name: string;
  description?: string;
  source_organization?: string;
  source_url?: string;
  license_text?: string;
  source_vintage?: string | null;
  imported_at?: string | null;
  srid: number;
  geometry_type?: string;
  coverage_caveat?: string;
};

export type DistrictListItem = { id: number; official_id: string; name: string };

export type FeatureCollection = {
  type: "FeatureCollection";
  features: Array<{
    type: "Feature";
    id?: number | string;
    geometry: { type: string; coordinates: unknown };
    properties?: Record<string, unknown> | null;
  }>;
  sql_ref?: string;
};

export type AnalysisResponse = {
  id: string;
  title: string;
  inputs: string[];
  operation: string;
  units: Record<string, string>;
  crs: string;
  caveat: string;
  threshold_m?: number;
  sql_ref?: string;
  results: Record<string, unknown>[];
};

export type NearestAmenities = {
  id: string;
  title: string;
  lon: number;
  lat: number;
  crs: string;
  caveat: string;
  sql_ref?: string;
  nearest: Array<{
    layer: string;
    id?: number;
    name?: string | null;
    distance_m: number;
  }>;
};

export type TagItem = { id: number; category: string; label: string; feature_count: number };

export type FeatureDetail = {
  type: "Feature";
  id: number;
  geometry: { type: string; coordinates: unknown };
  properties: {
    id: number;
    layer_kind: string;
    name?: string | null;
    subtype?: string | null;
    district?: string | null;
    operator?: { id: number; name: string; official_ref: string | null; operator_type: string | null } | null;
    tags?: Array<{ id: number; category: string; label: string }>;
    detail?: Record<string, unknown> | null;
    [key: string]: unknown;
  };
};

export type SqlFile = { name: string; sql: string };

export type LayerSql = { name: string; slug: string; sql: string };

export type SqlRunResult = {
  explain: boolean;
  plan: string | null;
  columns: string[];
  rows: unknown[][];
  row_count: number;
  truncated: boolean;
  geojson: FeatureCollection | null;
};

export type BBox = [west: number, south: number, east: number, north: number];

export function formatBbox(bbox: BBox): string {
  return bbox.map((n) => n.toFixed(5)).join(",");
}

/** Expand viewport bbox so small pans stay inside a loaded tile. */
export function padBbox(bbox: BBox, factor = 0.5): BBox {
  const [w, s, e, n] = bbox;
  const dx = (e - w) * factor;
  const dy = (n - s) * factor;
  return [w - dx, s - dy, e + dx, n + dy];
}

export function bboxContains(outer: BBox, inner: BBox): boolean {
  return inner[0] >= outer[0] && inner[1] >= outer[1] && inner[2] <= outer[2] && inner[3] <= outer[3];
}

export function boundsToBbox(bounds: {
  getWest(): number;
  getSouth(): number;
  getEast(): number;
  getNorth(): number;
}): BBox {
  return [bounds.getWest(), bounds.getSouth(), bounds.getEast(), bounds.getNorth()];
}

function layerQuery(bbox?: string, districtId?: number, tags?: number[]): string {
  const q = new URLSearchParams();
  if (bbox) q.set("bbox", bbox);
  if (districtId) q.set("district_id", String(districtId));
  for (const t of tags ?? []) q.append("tag", String(t));
  const qs = q.toString();
  return qs ? `?${qs}` : "";
}

export const api = {
  layers: () => getJson<LayerMeta[]>("/layers", { ttlMs: 60_000 }),
  districtsList: () => getJson<DistrictListItem[]>("/districts/list", { ttlMs: 60_000 }),
  layer: (slug: LayerSlug, bbox?: string, districtId?: number, tags?: number[]) =>
    getJson<FeatureCollection>(`${LAYER_PATHS[slug]}${layerQuery(bbox, districtId, tags)}`),
  /** Tag vocabulary a kind may carry (U7). */
  tags: (kind: string) => getJson<TagItem[]>(`/tags?kind=${encodeURIComponent(kind)}`, { ttlMs: 60_000 }),
  /** One feature with tags, operator and typed detail (loaded through the ORM). */
  feature: (slug: LayerSlug, id: number) =>
    getJson<FeatureDetail>(`/features/${slug}/${id}`, { cache: false }),
  operators: (topN = 3) => getJson<AnalysisResponse>(`/analyses/operators?top_n=${topN}`),
  treesByBorough: () => getJson<AnalysisResponse>("/analyses/trees-by-borough"),
  layerSql: (slug: LayerSlug) => getJson<LayerSql>(`/layers/${slug}/sql`, { ttlMs: 60_000 }),
  /** Point checks are not cached — each click is a distinct query. */
  nearestAmenities: (lon: number, lat: number) =>
    getJson<NearestAmenities>(`/analyses/nearest-amenities?lon=${lon}&lat=${lat}`, { cache: false }),
  amenityDensityByBorough: () => getJson<AnalysisResponse>("/analyses/amenity-density-by-borough"),
  greenByBorough: () => getJson<AnalysisResponse>("/analyses/green-by-borough"),
  schoolGreenProximity: (threshold = 500, districtId?: number) => {
    const q = new URLSearchParams({ threshold_m: String(threshold) });
    if (districtId) q.set("district_id", String(districtId));
    return getJson<AnalysisResponse>(`/analyses/school-green-proximity?${q}`);
  },
  sqlFile: (name: string) => getJson<SqlFile>(`/sql/${encodeURIComponent(name)}`, { ttlMs: 60_000 }),
  runSql: async (sql: string, explain = false): Promise<SqlRunResult> => {
    const res = await fetch(`${API_BASE}/sql/run`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ sql, explain }),
    });
    if (!res.ok) {
      let detail = `${res.status} ${res.statusText}`;
      try {
        const body = (await res.json()) as { detail?: string };
        if (body.detail) detail = body.detail;
      } catch {
        /* ignore */
      }
      throw new Error(detail);
    }
    return (await res.json()) as SqlRunResult;
  },
};
