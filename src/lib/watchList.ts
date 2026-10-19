/** The pre-season watch list (docs/tasks/32-watch-list.md, LAGOS_PLAN roadmap step 8).
 *
 * A blended score (0.4 x floods + 0.3 x ...) looks precise and hides its judgement, so each site instead gets three
 * yes/no tests: repeated flooding, a named drainage failure, and no visible fix. The tier is the number passed, each
 * test carries its reason in words, and ties inside a tier break on recency, then the well-searched storm rate, then
 * the name. All rules live in the block below; change them there and nowhere else. */

import type { CauseAttribution, CauseTag } from '../events/types';
import { causeLabel } from './causes';
import { promiseStatus, type PromiseStatus } from './promises';
import type { EvidenceStatus, FloodStrength, SiteClaim, SitePromise, SiteRecord } from '../sites/types';

// ── The three rules, in one place ────────────────────────────────────────
/** Rule 1 (repeated flooding): at least this many strong pluvial catalog days, … */
const RULE_1_MIN_STRONG_DAYS = 2;
/** … and at least one of them inside this many recent seasons before the as-of date. */
const RECENT_SEASONS = 3;
/** Rule 1: strong catalog matches, as in the rain replay — the news named the place or a point near it. */
const STRONG_STRENGTHS: FloodStrength[] = ['name', 'near'];

/** Rule 2 (named drainage failure): cause tags that count as drainage. Building on a channel's setback blocks it as
 *  surely as silt does (System 156), so encroachment counts; construction and reclamation stay out unless a claim says
 *  drains were blocked or undersized. */
const DRAINAGE_CAUSES: CauseTag[] = ['blocked_drainage', 'drainage_capacity', 'setback_encroachment'];
/** Rule 2: attributions that pass on their own; anyone else needs imagery on their side. */
const PASSING_ATTRIBUTIONS: CauseAttribution[] = ['official', 'journalist'];
/** Rule 2: evidence statuses that let even a resident's claim pass ("nothing checked" doesn't). */
const SUPPORTING_EVIDENCE: EvidenceStatus[] = ['supports', 'weak'];

/** Rule 3 (no visible fix): a promise only counts once made; its status is promiseStatus(p, asOf), imagery-only.
 *  A site with no promise passes: nothing was promised and nothing is visibly fixed. */
/** Rule 3: verdicts are free text, so "the verdict says the problem is fixed" is this keyword test (no verdict on
 *  record currently matches it). */
const VERDICT_FIXED_RE = /\b(fixed|resolved|solved|no longer floods?)\b/i;
/** Worst first, for the reason text; mirrors the severity order the site list shows. */
const PROMISE_SEVERITY: PromiseStatus[] = ['overdue', 'no_visible_work', 'stalled', 'in_progress', 'unverifiable', 'delivered'];
// ─────────────────────────────────────────────────────────────────────────

const PROMISE_LABEL: Record<PromiseStatus, string> = {
  delivered: 'delivered',
  in_progress: 'in progress',
  stalled: 'stalled',
  no_visible_work: 'no visible work',
  overdue: 'overdue',
  unverifiable: 'unverifiable',
};

const EVIDENCE_PHRASE: Record<EvidenceStatus, string> = {
  supports: 'imagery supports it',
  weak: 'imagery weakly supports it',
  inconclusive: 'imagery is inconclusive',
  contradicts: 'imagery contradicts it',
  not_checked: 'it was never checked against imagery',
  no_imagery_after: 'no imagery was taken after the event',
};

/** `events/site_rain_summary.json` — the slim digest of the rain replay (pipeline/storm_replay.py). */
export interface RainSummaryStats {
  n_storms: number;
  n_flooded: number;
  rate: number | null;
  wilson_95: (number | null)[];
}

export interface RainSummaryReplay {
  reference_date: string;
  site_cell_2d_mm: number | null;
  not_a_storm_here: boolean;
  n_analogs: number | null;
  n_flooded: number | null;
}

export interface RainSummarySite {
  site_id: string;
  name: string;
  cell_id: string;
  threshold_40mm: { all_years: RainSummaryStats; well_searched_years: RainSummaryStats };
  replays: Record<string, RainSummaryReplay>;
}

export interface RainSummary {
  meta: { well_searched_years: string[] } & Record<string, unknown>;
  sites: RainSummarySite[];
}

export interface WatchTest {
  key: 'repeated_flooding' | 'named_drainage_failure' | 'no_visible_fix';
  label: string;
  pass: boolean;
  /** Why, in words, tied to the evidence it came from. */
  reason: string;
}

export interface WatchRow {
  site_id: string;
  name: string;
  /** The tier is the number of tests passed; the list orders by tier, then the tie-breaks below. */
  tier: number;
  tests: WatchTest[];
  /** Tie-break 1: strong pluvial days in the last RECENT_SEASONS seasons. */
  recent_strong_days: number;
  /** Tie-break 2: well-searched-years flood rate for storms >= 40 mm at the site cell; null when there are none. */
  well_searched_rate_40mm: number | null;
  as_of: string;
}

const pad = (n: number) => (n < 10 ? '0' : '') + n;
const isoDate = (d: Date) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;

/**
 * A season is one flood year (Apr–Nov, with the once-a-year Dec–Mar search attached to it). The last n seasons before
 * asOf are the n latest season-years already started (1 April on or before asOf): for a 1 March asOf that is the three
 * calendar years before it, and a mid-season asOf also counts the season in progress.
 */
function lastSeasons(asOf: Date, n: number): string[] {
  const years: string[] = [];
  for (let y = asOf.getFullYear(); years.length < n && y >= 1900; y--) {
    if (new Date(y, 3, 1) <= asOf) years.push(`${y}`);
  }
  return years;
}

/** Rule 1: strong pluvial catalog days on or before asOf. Every year counts: a flood on record is a flood, and the
 *  thin-year flag only adjusts rates (the rain replay), never discards an observed flood. */
function repeatedFlooding(site: SiteRecord, recentYears: Set<string>, asOfIso: string): { test: WatchTest; recentDays: number } {
  const strong = (site.catalog_floods ?? []).filter(
    (f) => STRONG_STRENGTHS.includes(f.strength) && f.flood_type === 'pluvial' && f.date <= asOfIso,
  );
  const last = strong.length ? [...strong].sort((a, b) => a.date.localeCompare(b.date))[strong.length - 1].date : null;
  const recentDays = strong.filter((f) => recentYears.has(f.date.slice(0, 4))).length;
  const days = (n: number) => `${n} strong pluvial flood day${n === 1 ? '' : 's'}`;
  const pass = strong.length >= RULE_1_MIN_STRONG_DAYS && recentDays >= 1;
  let reason: string;
  if (pass) {
    reason = `${days(strong.length)}; last ${last}`;
  } else if (strong.length === 0) {
    reason = 'no strong pluvial flood day on record';
  } else if (strong.length < RULE_1_MIN_STRONG_DAYS) {
    reason = `only ${days(strong.length)} (${last})`;
  } else {
    reason = `${days(strong.length)}, but the most recent (${last}) is outside the last ${RECENT_SEASONS} seasons`;
  }
  return {
    test: { key: 'repeated_flooding', label: 'Repeated flooding', pass, reason },
    recentDays,
  };
}

function namedDrainage(site: SiteRecord): WatchTest {
  const candidates = (site.claims ?? []).filter((c) => DRAINAGE_CAUSES.includes(c.cause));
  const hits = candidates.filter(
    (c) => (c.attributed_by !== null && PASSING_ATTRIBUTIONS.includes(c.attributed_by)) || SUPPORTING_EVIDENCE.includes(c.evidence_status),
  );
  // Best first: an official or journalist's word, then the stronger imagery finding, then the most recent.
  const rank = (c: SiteClaim) =>
    (c.attributed_by !== null && PASSING_ATTRIBUTIONS.includes(c.attributed_by) ? 0 : 1) * 2 +
    (c.evidence_status === 'supports' ? 0 : c.evidence_status === 'weak' ? 1 : 2);
  const pool = hits.length ? hits : candidates;
  const best = [...pool].sort((a, b) => rank(a) - rank(b) || (b.date ?? '').localeCompare(a.date ?? ''))[0] ?? null;
  const whoBit = (c: SiteClaim) =>
    c.who && c.attributed_by ? `${c.who} (${c.attributed_by})` : c.who ?? (c.attributed_by ? `A ${c.attributed_by}` : 'An unattributed claim');
  let reason: string;
  if (!best) {
    reason = 'no claim names a drainage cause here';
  } else {
    reason = `${whoBit(best)} blamed ${causeLabel(best.cause).toLowerCase()} ${hits.length ? '—' : 'but'} ${EVIDENCE_PHRASE[best.evidence_status]}`;
  }
  return { key: 'named_drainage_failure', label: 'Named drainage failure', pass: hits.length > 0, reason };
}

function noVisibleFix(site: SiteRecord, promises: Record<string, SitePromise>, asOf: Date, asOfIso: string): WatchTest {
  const mine = (site.promise_ids ?? [])
    .map((id) => promises[id])
    .filter((p): p is SitePromise => !!p)
    .filter((p) => p.date_made <= asOfIso); // a promise not yet made as of asOf is not evidence of a fix
  const statuses = mine.map((p) => promiseStatus(p, asOf));
  const delivered = mine.find((_p, i) => statuses[i] === 'delivered') ?? null;
  const worst = statuses.length ? PROMISE_SEVERITY.find((s) => statuses.includes(s)) ?? null : null;
  const verdictFixed = !!site.verdict && VERDICT_FIXED_RE.test(site.verdict.text);
  const pass = !delivered && !verdictFixed;
  let reason: string;
  if (delivered) {
    reason = `a promise shows delivered in imagery: "${delivered.what}"${verdictFixed ? '; the verdict also says the problem is fixed' : ''}`;
  } else if (verdictFixed) {
    reason = 'the verdict says the problem is fixed';
  } else if (mine.length === 0) {
    reason = 'no promise on record; nothing was promised and nothing is visibly fixed';
  } else {
    reason = `no promise delivered as of ${asOfIso}; worst status: ${PROMISE_LABEL[worst!]}`;
  }
  return { key: 'no_visible_fix', label: 'No visible fix', pass, reason };
}

/** Ranks every site by the three rules above, as of `asOf`. Pure: same inputs, same rows. */
export function buildWatchList(
  sites: SiteRecord[],
  promises: Record<string, SitePromise>,
  rainSummary: RainSummary,
  asOf: Date,
): WatchRow[] {
  const asOfIso = isoDate(asOf);
  const recentYears = new Set(lastSeasons(asOf, RECENT_SEASONS));
  const rainBySite = new Map(rainSummary.sites.map((s) => [s.site_id, s]));
  const rows: WatchRow[] = sites.map((site) => {
    const repeated = repeatedFlooding(site, recentYears, asOfIso);
    const tests = [repeated.test, namedDrainage(site), noVisibleFix(site, promises, asOf, asOfIso)];
    const rain = rainBySite.get(site.site_id) ?? null;
    return {
      site_id: site.site_id,
      name: site.name,
      tier: tests.filter((t) => t.pass).length,
      tests,
      recent_strong_days: repeated.recentDays,
      well_searched_rate_40mm: rain ? rain.threshold_40mm.well_searched_years.rate : null,
      as_of: asOfIso,
    };
  });
  // Tier first, then the tie-breaks: recent strong days, the well-searched >= 40 mm rate, then the name.
  rows.sort(
    (a, b) =>
      b.tier - a.tier ||
      b.recent_strong_days - a.recent_strong_days ||
      (b.well_searched_rate_40mm ?? -1) - (a.well_searched_rate_40mm ?? -1) ||
      a.name.localeCompare(b.name),
  );
  return rows;
}
