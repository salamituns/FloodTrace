/** What's hit by water: roads, facilities, buildings (Task 40, section D).
 *
 * Everything runs in the browser against static files; nothing is sent anywhere.
 * "Wet" means: inside evidence water (a reported flood spot's water body, its
 * depth-not-reported disc, or the July 2024 radar flood map), or inside the
 * rough model's water for one rain scenario.
 *
 * impactsAt() is the one-call summary Task 41 will show in plain words:
 * roads with the length that sits under water, facilities inside the water,
 * and an estimate of how many buildings stand in it.
 */

import { haversineM, loadFloodSpots, type FloodSpot } from './area';

export const MODEL_SCENARIOS_MM = [20, 40, 60, 80, 100, 150] as const;
export type ModelScenario = (typeof MODEL_SCENARIOS_MM)[number];
export const DEFAULT_SCENARIO_MM: ModelScenario = 40;

/** Evidence-water disc radius by geocode confidence (Task 40, section B). */
export function discRadiusM(spot: Pick<FloodSpot, 'confidence'>): number {
  return spot.confidence === 'street' ? 120 : 400;
}

async function getJson<T>(url: string): Promise<T> {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`${url}: HTTP ${res.status}`);
  return res.json() as Promise<T>;
}

async function getOptional<T>(url: string): Promise<T | null> {
  try {
    return await getJson<T>(url);
  } catch {
    return null;
  }
}

// ── rough-model data (events/rough_model/) ────────────────────────────────

export interface ScenarioValidation {
  wet_share_of_built_up: number;
  n_spots_tested: number;
  spots_in_model_water: number;
  spot_hit_rate: number;
  random_baseline_hit_rate: number;
  random_expected_hits: number;
  radar_cells_built_up?: number;
  radar_cells_in_model_water?: number;
  radar_match_rate?: number;
}

export interface RoughModelMeta {
  generated_at: string;
  method: { summary: string; stipple: string; crop: { bounds: number[]; note: string } } & Record<string, unknown>;
  parameters: { scenarios_mm: number[]; storm_note: string; min_depth_m: number } & Record<string, unknown>;
  terrain_verdict: { summary: string; source: string };
  validation: { note?: string } & Record<string, ScenarioValidation | undefined>;
  building_coverage: {
    share_of_built_up_area_with_outlines: number;
    tiles_checked: number;
    tiles_with_buildings: number;
    good_areas: { area: string; median_buildings: number }[];
    poor_areas: { area: string; median_buildings: number }[];
    note: string;
  };
  bounds: [number, number, number, number];
  total_bytes: number;
}

export type Ring = number[][];
export interface WaterPolygonsFile {
  meta: { depth_min_m: number; bounds: number[]; note: string };
  /** scenario mm -> polygons -> rings (lon/lat) */
  scenarios: Record<string, Ring[][]>;
}

export interface RoadLine {
  name: string;
  kind: string;
  coords: [number, number][];
}
export interface RoadsFile {
  meta: Record<string, string>;
  roads: RoadLine[];
}

export interface BuildingCountsFile {
  meta: { cell_deg: number; cell_area_m2: number; source: string; note: string };
  counts: Record<string, number>;
}

export interface FacilityProps {
  name: string;
  kind: string;
  area: string | null;
}
export type FacilitiesFile = GeoJSON.FeatureCollection<GeoJSON.Point, FacilityProps>;

let metaP: Promise<RoughModelMeta | null> | null = null;
export function loadRoughModelMeta(): Promise<RoughModelMeta | null> {
  return (metaP ??= getOptional<RoughModelMeta>('/events/rough_model/meta.json'));
}

let polysP: Promise<WaterPolygonsFile | null> | null = null;
export function loadWaterPolygons(): Promise<WaterPolygonsFile | null> {
  return (polysP ??= getOptional<WaterPolygonsFile>('/events/rough_model/water_polygons.json'));
}

let roadsP: Promise<RoadsFile | null> | null = null;
export function loadRoads(): Promise<RoadsFile | null> {
  return (roadsP ??= getOptional<RoadsFile>('/events/rough_model/roads.json'));
}

let countsP: Promise<BuildingCountsFile | null> | null = null;
export function loadBuildingCounts(): Promise<BuildingCountsFile | null> {
  return (countsP ??= getOptional<BuildingCountsFile>('/events/rough_model/building_counts.json'));
}

let facilitiesP: Promise<FacilitiesFile | null> | null = null;
export function loadFacilities(): Promise<FacilitiesFile | null> {
  return (facilitiesP ??= getOptional<FacilitiesFile>('/events/osm_facilities.geojson'));
}

let radarP: Promise<GeoJSON.FeatureCollection | null> | null = null;
export function loadRadarFlood(): Promise<GeoJSON.FeatureCollection | null> {
  return (radarP ??= getOptional<GeoJSON.FeatureCollection>('/events/lagos-2024-07-03/sar/flood.geojson'));
}

/** report url -> "8 Jul 2022"-style date, so depth quotes can cite their source date. */
let datesP: Promise<Map<string, string>> | null = null;
export function loadReportDates(): Promise<Map<string, string>> {
  return (datesP ??= (async () => {
    const days = await getOptional<{ days: { date: string; reports?: { url?: string }[] }[] }>('/events/flood_days.json');
    const map = new Map<string, string>();
    if (!days) return map;
    for (const d of days.days) {
      for (const r of d.reports ?? []) {
        if (r.url && !map.has(r.url)) map.set(r.url, d.date);
      }
    }
    return map;
  })());
}

// ── wet tests ────────────────────────────────────────────────────────────

export interface WaterTest {
  isWet(lon: number, lat: number): boolean;
  isEmpty: boolean;
}

/** Even-odd point-in-rings; holes (inner rings) come out dry automatically. */
function pointInRings(x: number, y: number, rings: Ring[]): boolean {
  let inside = false;
  for (const ring of rings) {
    for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
      const yi = ring[i][1];
      const yj = ring[j][1];
      if ((yi > y) !== (yj > y) && x < ((ring[j][0] - ring[i][0]) * (y - yi)) / (yj - yi) + ring[i][0]) inside = !inside;
    }
  }
  return inside;
}

function ringsOf(geom: GeoJSON.Geometry | null | undefined): Ring[] {
  if (!geom) return [];
  switch (geom.type) {
    case 'Polygon':
      return geom.coordinates;
    case 'MultiPolygon':
      return geom.coordinates.flat();
    default:
      return [];
  }
}

interface Poly {
  rings: Ring[];
  w: number;
  s: number;
  e: number;
  n: number;
}

function polyOf(multi: Ring[][]): Poly[] {
  const out: Poly[] = [];
  for (const rings of multi) {
    let w = Infinity;
    let s = Infinity;
    let e = -Infinity;
    let n = -Infinity;
    for (const ring of rings) {
      for (const [x, y] of ring) {
        if (x < w) w = x;
        if (x > e) e = x;
        if (y < s) s = y;
        if (y > n) n = y;
      }
    }
    if (rings.length) out.push({ rings, w, s, e, n });
  }
  return out;
}

export function evidenceWaterTest(spots: FloodSpot[], radar: GeoJSON.FeatureCollection | null): WaterTest {
  const discs = spots.map((s) => ({ lon: s.lon, lat: s.lat, m: discRadiusM(s) }));
  const polys = (radar?.features ?? []).filter((f) => (f.properties as { class?: string } | null)?.class === 'open_flood')
    .map((f) => polyOf([ringsOf(f.geometry)]))
    .flat();
  return {
    isEmpty: discs.length === 0 && polys.length === 0,
    isWet(lon, lat) {
      for (const d of discs) {
        if (haversineM(lon, lat, d.lon, d.lat) <= d.m) return true;
      }
      for (const p of polys) {
        if (lon >= p.w && lon <= p.e && lat >= p.s && lat <= p.n && pointInRings(lon, lat, p.rings)) return true;
      }
      return false;
    },
  };
}

export function modelWaterTest(file: WaterPolygonsFile | null, scenario: number): WaterTest {
  const polys = polyOf(file?.scenarios[String(scenario)] ?? []);
  return {
    isEmpty: polys.length === 0,
    isWet(lon, lat) {
      for (const p of polys) {
        if (lon >= p.w && lon <= p.e && lat >= p.s && lat <= p.n && pointInRings(lon, lat, p.rings)) return true;
      }
      return false;
    },
  };
}

export function combineWaterTests(tests: WaterTest[]): WaterTest {
  return {
    isEmpty: tests.every((t) => t.isEmpty),
    isWet(lon, lat) {
      return tests.some((t) => t.isWet(lon, lat));
    },
  };
}

// ── roads through water ──────────────────────────────────────────────────

export interface RoadSegment {
  name: string;
  kind: string;
  wet: boolean;
  positions: [number, number][];
  lengthM: number;
}

/** Split each road into vertex-to-vertex segments near the centre and flag the
 *  ones whose midpoint sits in water. Wet runs and dry runs are kept apart so
 *  the map can draw the hit stretch in a different colour. */
export function classifyRoads(roads: RoadLine[], test: WaterTest, lon: number, lat: number, radiusM: number): RoadSegment[] {
  const out: RoadSegment[] = [];
  const cos = Math.max(Math.cos((lat * Math.PI) / 180), 0.2);
  const mDegLon = 111320 * cos;
  const mDegLat = 111320;
  for (const r of roads) {
    let lastWet: boolean | null = null;
    let run: [number, number][] = [];
    let runLen = 0;
    const push = () => {
      if (run.length >= 2 && lastWet !== null) out.push({ name: r.name, kind: r.kind, wet: lastWet, positions: run, lengthM: runLen });
      run = [];
      runLen = 0;
    };
    for (let i = 0; i + 1 < r.coords.length; i++) {
      const a = r.coords[i];
      const b = r.coords[i + 1];
      const mx = (a[0] + b[0]) / 2;
      const my = (a[1] + b[1]) / 2;
      const dx = (mx - lon) * mDegLon;
      const dy = (my - lat) * mDegLat;
      if (dx * dx + dy * dy > (radiusM + 25) ** 2) {
        push();
        lastWet = null;
        continue;
      }
      const wet = test.isWet(mx, my);
      if (wet !== lastWet) {
        push();
        run = [a];
        lastWet = wet;
      }
      run.push(b);
      runLen += haversineM(a[0], a[1], b[0], b[1]);
    }
    push();
  }
  return out;
}

// ── building counts ──────────────────────────────────────────────────────

/** Buildings per m² at a point, from OSM footprint counts per ~550 m cell.
 *  A cell with no entry means nothing is mapped there (OSM coverage is patchy). */
function buildingDensity(counts: BuildingCountsFile, lon: number, lat: number): number {
  const n = counts.counts[`${Math.floor(lon / counts.meta.cell_deg)}/${Math.floor(lat / counts.meta.cell_deg)}`];
  return n === undefined ? 0 : n / counts.meta.cell_area_m2;
}

/** Buildings per m², summed over the water inside the circle: an estimate, because
 *  the counts come per ~550 m cell. "About N buildings", not a census. */
function estimateBuildings(test: WaterTest, counts: BuildingCountsFile | null, lon: number, lat: number, radiusM: number): number {
  if (!counts || test.isEmpty) return 0;
  const step = Math.max(12, radiusM / 60);
  const mDegLat = 111320;
  const mDegLon = 111320 * Math.max(Math.cos((lat * Math.PI) / 180), 0.2);
  let total = 0;
  for (let dy = -radiusM; dy <= radiusM; dy += step) {
    for (let dx = -radiusM; dx <= radiusM; dx += step) {
      if (dx * dx + dy * dy > radiusM * radiusM) continue;
      const x = lon + dx / mDegLon;
      const y = lat + dy / mDegLat;
      if (!test.isWet(x, y)) continue;
      total += buildingDensity(counts, x, y) * step * step;
    }
  }
  return total;
}

// ── the one-call summary (Task 41) ───────────────────────────────────────

export interface Impacts {
  /** Is the spot itself in the water? */
  pointWet: boolean;
  roads: { name: string; lengthUnderWaterM: number }[];
  facilities: { name: string; kind: string }[];
  /** Estimated number of buildings standing in the water inside the circle. */
  buildings: number;
  buildingsAreEstimate: boolean;
}

export async function impactsAt(
  lon: number,
  lat: number,
  radiusM: number,
  source: 'evidence' | 'model',
  scenario: ModelScenario = DEFAULT_SCENARIO_MM,
): Promise<Impacts> {
  const [spotsFile, radar, roadsFile, facilities, counts, polys] = await Promise.all([
    loadFloodSpots().catch(() => null),
    loadRadarFlood(),
    loadRoads(),
    loadFacilities(),
    loadBuildingCounts(),
    loadWaterPolygons(),
  ]);
  const spots = spotsFile?.spots ?? [];
  const test =
    source === 'evidence'
      ? evidenceWaterTest(spots, radar)
      : modelWaterTest(polys, scenario);
  if (test.isEmpty) {
    return { pointWet: false, roads: [], facilities: [], buildings: 0, buildingsAreEstimate: true };
  }

  const segs = roadsFile ? classifyRoads(roadsFile.roads, test, lon, lat, radiusM) : [];
  const byRoad = new Map<string, number>();
  for (const s of segs) {
    if (s.wet) byRoad.set(s.name, (byRoad.get(s.name) ?? 0) + s.lengthM);
  }
  const roads = [...byRoad.entries()]
    .map(([name, lengthUnderWaterM]) => ({ name, lengthUnderWaterM: Math.round(lengthUnderWaterM) }))
    .filter((r) => r.lengthUnderWaterM > 0)
    .sort((a, b) => b.lengthUnderWaterM - a.lengthUnderWaterM);

  const facilitiesHit = (facilities?.features ?? [])
    .filter((f) => {
      const [x, y] = f.geometry.coordinates;
      return haversineM(lon, lat, x, y) <= radiusM && test.isWet(x, y);
    })
    .map((f) => ({ name: f.properties.name, kind: f.properties.kind }));

  return {
    pointWet: test.isWet(lon, lat),
    roads,
    facilities: facilitiesHit,
    buildings: Math.round(estimateBuildings(test, counts, lon, lat, radiusM)),
    buildingsAreEstimate: true,
  };
}
