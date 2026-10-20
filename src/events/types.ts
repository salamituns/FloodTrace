import type { Feature, FeatureCollection, Geometry, Point } from 'geojson';

export type LonLat = [number, number];

export interface CatalogEntry {
  id: string;
  name: string;
  date: string;
  areas: string[];
  status: string;
  headline: string;
  built: boolean;
}

/** A regularly or irregularly sampled time series (epoch ms → value). */
export interface Series {
  t: number[];
  v: number[];
  /** For rates sampled over intervals: interval length in hours and whether t marks its start or end. */
  stepH?: number;
  label?: 'start' | 'end';
}

export type KeyEventKind = 'documented' | 'satellite' | 'tide-high' | 'rain-onset';

export interface KeyEvent {
  id: string;
  name: string;
  /** Resident wording; fall back to `name` when absent. */
  namePlain?: string;
  t: number;
  kind: KeyEventKind;
  timeConfidence: 'exact' | 'approx' | 'day' | 'unknown';
  sourceUrl?: string;
}

export interface SatellitePass {
  name: string;
  t: number;
  platform: string;
  relativeOrbit: number | null;
  cloudCover: number | null;
  collection: string;
}

export interface EvidenceProps {
  id: string;
  kind: 'news_report' | 'news_photo' | 'video' | 'official_statement' | 'social_post';
  source_id: string;
  source_url: string;
  publisher: string;
  published_at: string | null;
  observed_at: string | null;
  time_confidence: 'exact' | 'approx' | 'day' | 'unknown';
  location_name: string;
  location_confidence: 'point' | 'street' | 'neighbourhood' | 'lga';
  geocode_method: string;
  claim: string;
  depth_note: string | null;
  quote: string | null;
  verified: boolean;
  read_status: 'read' | 'headline_only';
  quote_check?: string | null;
  /** Causes the source explicitly attributes the flooding here to (Task 15); absent until tagged. */
  causes?: CauseTag[];
  cause_quote?: string | null;
  cause_attributed_by?: CauseAttribution | null;
  cause_who?: string | null;
}

export type CauseTag =
  | 'heavy_rain'
  | 'blocked_drainage'
  | 'drainage_capacity'
  | 'setback_encroachment'
  | 'construction'
  | 'canal_overflow'
  | 'lagoon_tide'
  | 'ocean_surge'
  | 'dam_release'
  | 'land_reclamation'
  | 'low_lying_terrain';

export type CauseAttribution = 'official' | 'journalist' | 'resident' | 'expert';

/** A statement blaming the flood on a cause for the city as a whole, not a mapped place. */
export interface CitywideCause {
  source_id: string;
  url: string;
  who: string | null;
  date: string | null;
  causes: CauseTag[];
  cause_quote: string | null;
  cause_attributed_by?: CauseAttribution;
}

/** ~1 km cell with GHSL built-up fraction (0–1) per epoch: b1975 … b2020, and d2000_2020. */
export interface BuiltupProps {
  b2000: number;
  b2020: number;
  d2000_2020: number;
  [epoch: string]: number;
}

export interface EvidenceItem {
  props: EvidenceProps;
  position: LonLat;
  /** Best-known time the flooding was seen (observed_at, else published_at). */
  t: number | null;
}

export interface RainfallData {
  product: string;
  note: string;
  kind: 'imerg' | 'reanalysis';
  byPoint: Record<string, Series>;
}

/** Gridded rain rate for the map: data[t][i][j] at lat[i], lon[j] (cell centres), interval-start times. */
export interface RainGrid {
  times: number[];
  stepH: number;
  lon: number[];
  lat: number[];
  cellDeg: number;
  data: (number | null)[][][];
  product: string;
}

export interface LoadedEvent {
  id: string;
  name: string;
  causePrelim: string | null;
  /** Resident wording of the likely cause; falls back to `causePrelim`. */
  causePlain: string | null;
  openQuestions: string[];
  /** Resident wording of each open question; falls back to `openQuestions`. */
  openQuestionsPlain: string[];
  timezone: string;
  window: { start: number; end: number };
  focus: { start: number; end: number };
  bbox: [number, number, number, number];
  points: Record<string, LonLat>;
  keyEvents: KeyEvent[];
  sources: Record<string, string>;
  tide: Series;
  tideProduct: string;
  rainfall: RainfallData;
  rainGrid: RainGrid | null;
  passes: SatellitePass[];
  sar: {
    observedAt: number;
    flood: FeatureCollection;
    rainCells: FeatureCollection;
    stats: { area_km2_aoi: Record<string, number>; coverage: { during_fraction: number } };
  } | null;
  drainage: FeatureCollection;
  evidence: EvidenceItem[];
  citywideCauses: CitywideCause[];
  /** Shared across events (not event-specific); null until the built-up grid exists. */
  builtup: FeatureCollection<Geometry, BuiltupProps> | null;
}

export type PointFeature = Feature<Point, EvidenceProps>;
export type AnyFeature = Feature<Geometry>;
