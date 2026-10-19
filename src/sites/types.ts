import type { Geometry } from 'geojson';
import type { CauseAttribution, CauseTag } from '../events/types';
import type { OfficialPromise, PromiseStatus } from '../lib/promises';

/** `events/sites.json`, built by `pipeline/build_sites.py` (schema: docs/SITES_PLAN.md). */

export type EvidenceStatus = 'supports' | 'weak' | 'inconclusive' | 'contradicts' | 'not_checked' | 'no_imagery_after';
export type VerdictConfidence = 'strong' | 'moderate' | 'weak' | 'none';

export interface SiteFlood {
  event_id: string;
  date: string;
  evidence_ids: string[];
  n_reports: number;
  nearest_m: number;
}

/** How a catalog flood day matched a site (docs/tasks/29-site-flood-counts.md). */
export type FloodStrength = 'name' | 'near' | 'area';
export type FloodType = 'pluvial' | 'riverine' | 'lagoon' | 'coastal';

export interface CatalogSource {
  url: string;
  publisher: string;
  quote: string;
}

/** One Tier B flood-day catalog entry that matched this site. */
export interface CatalogFlood {
  date: string;
  flood_type: FloodType;
  episode_id: string | null;
  strength: FloodStrength;
  matched_areas: string[];
  distance_m: number | null;
  n_outlets: number;
  promote: boolean;
  tier_a_event_id: string | null;
  sources: CatalogSource[];
}

export interface CatalogSummary {
  n_days: number;
  n_days_strong: number;
  years_with_flood: number[];
  years_searched: number[];
  per_searched_year: number;
  riverine_days: number;
  note: string;
}

export interface SiteClaim {
  claim_id: string;
  event_id: string;
  cause: CauseTag;
  attributed_by: CauseAttribution | null;
  who: string | null;
  quote: string | null;
  source_id: string | null;
  url: string | null;
  date: string | null;
  evidence_status: EvidenceStatus;
  status_note?: string | null;
}

export interface WaybackChip {
  file: string;
  marked_file?: string | null;
  resolution_m?: number | null;
}

export interface WaybackImage extends WaybackChip {
  acq_date: string;
  /** Full-resolution close-ups at points along long lines; only on key dates. */
  detail_chips?: (WaybackChip & { station: string })[];
}

export interface SiteChange {
  wayback: WaybackImage[];
  s2_wet_season?: { aoi: string; by_year: Record<string, number> } | null;
  buildings_0_10m?: {
    by_year: Record<string, number>;
    matched_pct?: number | null;
    matched_n?: number | null;
    excluded?: string | null;
  } | null;
  summary?: string | null;
  stale?: boolean;
}

export interface SiteVerdict {
  text: string;
  confidence: VerdictConfidence;
  reviewed_by: string;
  reviewed_at: string;
  stale?: boolean;
}

export interface SiteRecord {
  site_id: string;
  name: string;
  aliases: string[];
  structure_name: string;
  structure_type: string;
  geometry: Geometry;
  location_confidence: string;
  located_how?: string;
  floods: SiteFlood[];
  /** Catalog matches; optional so an older sites.json without them still loads. */
  catalog_floods?: CatalogFlood[];
  catalog_summary?: CatalogSummary;
  claims: SiteClaim[];
  change: SiteChange;
  promise_ids: string[];
  verdict: SiteVerdict | null;
}

export interface SitePromise extends OfficialPromise {
  role?: string;
  status: PromiseStatus;
}

export interface LoadedSites {
  sites: SiteRecord[];
  promises: Record<string, SitePromise>;
}
