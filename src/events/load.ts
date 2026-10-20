import type { FeatureCollection, Geometry, Point } from 'geojson';
import { HOUR, parseLocal } from '../lib/time';
import type { BuiltupProps, CatalogEntry, CitywideCause, EvidenceProps, KeyEvent, LoadedEvent, RainfallData, SatellitePass, Series } from './types';

const base = (id: string) => `/events/${id}`;

async function getJson<T>(url: string): Promise<T> {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`${url}: HTTP ${res.status}`);
  return res.json() as Promise<T>;
}

/** Optional files: a missing file is normal (not every event has every dataset). */
async function getOptional<T>(url: string): Promise<T | null> {
  try {
    return await getJson<T>(url);
  } catch {
    return null;
  }
}

interface OpenMeteoHourly {
  utc_offset_seconds?: number;
  meta?: { product?: string };
  hourly: { time: string[]; [k: string]: (number | null)[] | string[] };
}

function hourlySeries(src: OpenMeteoHourly, key: string, offsetSec: number, label?: Series['label']): Series {
  const times = src.hourly.time;
  const vals = src.hourly[key] as (number | null)[];
  const s: Series = { t: [], v: [], ...(label ? { stepH: 1, label } : {}) };
  times.forEach((time, i) => {
    const v = vals[i];
    if (v == null) return;
    s.t.push(parseLocal(time, offsetSec));
    s.v.push(v);
  });
  return s;
}

/** Local maxima of the tide inside [start, end]. */
function tideHighs(tide: Series, start: number, end: number): KeyEvent[] {
  const out: KeyEvent[] = [];
  for (let i = 1; i < tide.t.length - 1; i++) {
    const t = tide.t[i];
    if (t < start || t > end) continue;
    if (tide.v[i] >= tide.v[i - 1] && tide.v[i] > tide.v[i + 1]) {
      out.push({ id: `tide-high-${t}`, name: `High tide (+${tide.v[i].toFixed(2)} m)`, t, kind: 'tide-high', timeConfidence: 'approx' });
    }
  }
  return out;
}

interface EventJson {
  id: string;
  name: string;
  timezone: string;
  window: { start: string; end: string };
  focus: { start: string; end: string };
  aoi: { bbox: [number, number, number, number]; points: Record<string, [number, number]> };
  key_events: {
    id: string;
    name: string;
    name_plain?: string;
    time: string;
    time_confidence: KeyEvent['timeConfidence'];
    source: string;
  }[];
  sources: Record<string, string>;
  cause_prelim?: string;
  cause_plain?: string;
  open_questions?: string[];
  open_questions_plain?: string[];
}

interface PassesJson {
  products: {
    name: string;
    acquisition_start_utc: string;
    platform: string;
    relative_orbit: number | null;
    cloud_cover?: number | null;
    collection: string;
  }[];
}

interface RainReanalysisJson {
  product: string;
  note: string;
  points: Record<string, OpenMeteoHourly>;
}

interface ImergJson {
  meta: { product: string; version: string; note: string; run: Record<string, number> };
  times: string[];
  points: Record<string, { series: number[] }>;
  aoi_mean: { series: number[] };
}

interface ImergGridJson {
  meta: { version: string };
  times: string[];
  lon: number[];
  lat: number[];
  data: (number | null)[][][];
}

interface SarStatsJson {
  items: { during: { datetime: string } };
  area_km2_aoi: Record<string, number>;
  coverage: { during_fraction: number };
}

export async function loadCatalog(): Promise<CatalogEntry[]> {
  return (await getJson<{ events: CatalogEntry[] }>('/events/catalog.json')).events;
}

// The built-up grid covers all of Lagos and is the same for every event: fetch it once.
let builtupOnce: Promise<FeatureCollection<Geometry, BuiltupProps> | null> | null = null;
const loadBuiltup = () => (builtupOnce ??= getOptional<FeatureCollection<Geometry, BuiltupProps>>('/events/builtup_grid.geojson'));

type EvidenceJson = FeatureCollection<Point, EvidenceProps> & { meta?: { citywide_cause_statements?: CitywideCause[] } };

export async function loadEvent(id: string): Promise<LoadedEvent> {
  const dir = base(id);
  const ev = await getJson<EventJson>(`${dir}/event.json`);
  const [tideRaw, rainRaw, passesRaw, drainage, sarStats, sarFlood, sarRain, evidenceRaw, imerg, grid, builtup] = await Promise.all([
    // EOT20 covers every year and is used for all events when present; Open-Meteo's series starts ~2022.
    getOptional<OpenMeteoHourly>(`${dir}/tide_eot20.json`).then(async (t) => t ?? getJson<OpenMeteoHourly>(`${dir}/tide.json`)),
    getJson<RainReanalysisJson>(`${dir}/rainfall_reanalysis.json`),
    getJson<PassesJson>(`${dir}/satellite_passes.json`),
    getJson<FeatureCollection>(`${dir}/drainage_osm.geojson`),
    getOptional<SarStatsJson>(`${dir}/sar/stats.json`),
    getOptional<FeatureCollection>(`${dir}/sar/flood.geojson`),
    getOptional<FeatureCollection>(`${dir}/sar/rain_cells.geojson`),
    getOptional<EvidenceJson>(`${dir}/evidence.geojson`),
    getOptional<ImergJson>(`${dir}/rainfall_imerg.json`),
    getOptional<ImergGridJson>(`${dir}/rainfall_imerg_grid.json`),
    loadBuiltup(),
  ]);

  const offset = tideRaw.utc_offset_seconds ?? 0;
  const tide = hourlySeries(tideRaw, 'sea_level_height_msl', offset);
  const tideProduct = tideRaw.meta?.product?.startsWith('EOT20') ? 'EOT20 tide model' : 'Open-Meteo marine model';
  const focus = { start: Date.parse(ev.focus.start), end: Date.parse(ev.focus.end) };

  // Prefer satellite IMERG (30-min, interval-start stamps) over hourly reanalysis (stamps mark the hour's end).
  const imergT = imerg?.times.map((s) => Date.parse(s));
  const imergSeries = (v: number[]): Series => ({ t: imergT!, v, stepH: 0.5, label: 'start' });
  const rainfall: RainfallData = imerg
    ? {
        product: `GPM IMERG v${imerg.meta.version} ${imerg.meta.run.late ? 'Final/Late' : 'Final'} (30-min, 0.1°)`,
        note: imerg.meta.note,
        kind: 'imerg',
        byPoint: {
          ...Object.fromEntries(Object.entries(imerg.points).map(([name, p]) => [name, imergSeries(p.series)])),
          aoi_mean: imergSeries(imerg.aoi_mean.series),
        },
      }
    : {
        product: rainRaw.product,
        note: rainRaw.note,
        kind: 'reanalysis',
        byPoint: Object.fromEntries(
          Object.entries(rainRaw.points).map(([name, p]) => [name, hourlySeries(p, 'precipitation', p.utc_offset_seconds ?? offset, 'end')]),
        ),
      };

  const keyEvents: KeyEvent[] = [
    ...ev.key_events.map((k) => ({
      id: k.id,
      name: k.name,
      namePlain: k.name_plain,
      t: Date.parse(k.time),
      kind: (k.id === 'sar-pass' ? 'satellite' : k.id === 'rain-onset' ? 'rain-onset' : 'documented') as KeyEvent['kind'],
      timeConfidence: k.time_confidence,
      sourceUrl: ev.sources[k.source]?.startsWith('http') ? ev.sources[k.source] : undefined,
    })),
    ...tideHighs(tide, focus.start, focus.end),
  ].sort((a, b) => a.t - b.t);

  const passes: SatellitePass[] = passesRaw.products
    .map((p) => ({
      name: p.name,
      t: Date.parse(p.acquisition_start_utc),
      platform: p.platform,
      relativeOrbit: p.relative_orbit,
      cloudCover: p.cloud_cover ?? null,
      collection: p.collection,
    }))
    .sort((a, b) => a.t - b.t);

  const evidence = (evidenceRaw?.features ?? []).map((f) => {
    const when = f.properties.observed_at ?? f.properties.published_at;
    return {
      props: f.properties,
      position: f.geometry.coordinates.slice(0, 2) as [number, number],
      t: when ? Date.parse(when) : null,
    };
  });

  return {
    id: ev.id,
    name: ev.name,
    causePrelim: ev.cause_prelim ?? null,
    causePlain: ev.cause_plain ?? ev.cause_prelim ?? null,
    openQuestions: ev.open_questions ?? [],
    openQuestionsPlain: ev.open_questions_plain ?? ev.open_questions ?? [],
    timezone: ev.timezone,
    window: { start: Date.parse(ev.window.start), end: Date.parse(ev.window.end) },
    focus,
    bbox: ev.aoi.bbox,
    points: ev.aoi.points,
    keyEvents,
    sources: ev.sources,
    tide,
    tideProduct,
    rainfall,
    rainGrid: grid
      ? {
          times: grid.times.map((s) => Date.parse(s)),
          stepH: 0.5,
          lon: grid.lon,
          lat: grid.lat,
          cellDeg: grid.lon.length > 1 ? Math.abs(grid.lon[1] - grid.lon[0]) : 0.1,
          data: grid.data,
          product: `GPM IMERG v${grid.meta.version} (30-min, 0.1°)`,
        }
      : null,
    passes,
    sar:
      sarStats && sarFlood && sarRain
        ? { observedAt: Date.parse(sarStats.items.during.datetime), flood: sarFlood, rainCells: sarRain, stats: sarStats }
        : null,
    drainage,
    evidence,
    citywideCauses: evidenceRaw?.meta?.citywide_cause_statements ?? [],
    builtup,
  };
}

/** Linear interpolation; NaN outside the series. */
export function sampleSeries(s: Series, t: number): number {
  const { t: ts, v } = s;
  if (!ts.length || t < ts[0] || t > ts[ts.length - 1]) return NaN;
  let lo = 0;
  let hi = ts.length - 1;
  while (hi - lo > 1) {
    const mid = (lo + hi) >> 1;
    if (ts[mid] <= t) lo = mid;
    else hi = mid;
  }
  const f = ts[hi] === ts[lo] ? 0 : (t - ts[lo]) / (ts[hi] - ts[lo]);
  return v[lo] + (v[hi] - v[lo]) * f;
}

/** Rain (mm) from a rate series (mm/h) over the window (t − hours, t], counting each interval's overlap. */
export function accumulate(s: Series, t: number, hours: number): number {
  const step = (s.stepH ?? 1) * HOUR;
  const from = t - hours * HOUR;
  let sum = 0;
  for (let i = 0; i < s.t.length; i++) {
    const a = s.label === 'end' ? s.t[i] - step : s.t[i];
    const overlap = Math.min(a + step, t) - Math.max(a, from);
    if (overlap > 0) sum += s.v[i] * (overlap / HOUR);
  }
  return sum;
}
