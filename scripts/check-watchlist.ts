/**
 * Unit checks for src/lib/watchList.ts (Task 32, docs/tasks/32-watch-list.md).
 *
 * The repo has no test runner (no vitest/jest in package.json), so this runs on tsx:
 *
 *   npx tsx scripts/check-watchlist.ts
 *
 * It checks the three named cases on small fixtures, then prints the real watch list
 * as of 2026-03-01 and 2027-03-01 (tier, tests and reasons per site).
 */
import { readFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { buildWatchList, type RainSummary, type RainSummarySite } from '../src/lib/watchList';
import { promiseStatus, type OfficialPromise } from '../src/lib/promises';
import type { CatalogFlood, FloodStrength, SiteClaim, SitePromise, SiteRecord } from '../src/sites/types';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const read = <T>(rel: string): T => JSON.parse(readFileSync(path.join(root, rel), 'utf8')) as T;

let failed = 0;
function check(ok: boolean, msg: string): void {
  console.log(`${ok ? 'ok' : 'FAIL'} - ${msg}`);
  if (!ok) failed += 1;
}

// ── fixtures ─────────────────────────────────────────────────────────────
const WELL_YEARS = ['2016', '2017', '2018', '2019', '2020', '2021', '2022', '2025', '2026']; // 2023/2024 thin

const flood = (date: string, strength: FloodStrength = 'name'): CatalogFlood => ({
  date,
  flood_type: 'pluvial',
  episode_id: null,
  strength,
  matched_areas: [],
  distance_m: null,
  n_outlets: 1,
  promote: true,
  tier_a_event_id: null,
  sources: [],
});

const claim = (claim_id: string, over: Partial<SiteClaim>): SiteClaim => ({
  claim_id,
  event_id: 'ev',
  cause: 'blocked_drainage',
  attributed_by: null,
  who: null,
  quote: null,
  source_id: null,
  url: null,
  date: null,
  evidence_status: 'not_checked',
  ...over,
});

const site = (site_id: string, over: Partial<SiteRecord>): SiteRecord => ({
  site_id,
  name: site_id,
  aliases: [],
  structure_name: 'a drain',
  structure_type: 'drain',
  geometry: { type: 'Point', coordinates: [3.4, 6.5] },
  location_confidence: 'point',
  floods: [],
  claims: [],
  change: {},
  promise_ids: [],
  verdict: null,
  ...over,
});

const rainSite = (site_id: string): RainSummarySite => ({
  site_id,
  name: site_id,
  cell_id: 'c6.5N3.4E',
  threshold_40mm: {
    all_years: { n_storms: 100, n_flooded: 1, rate: 0.01, wilson_95: [0, 0.05] },
    well_searched_years: { n_storms: 80, n_flooded: 1, rate: 0.0125, wilson_95: [0, 0.06] },
  },
  replays: {},
});

const rain = (siteIds: string[]): RainSummary => ({
  meta: { well_searched_years: WELL_YEARS },
  sites: siteIds.map(rainSite),
});

const asOf = new Date('2026-03-01T00:00:00');

// ── case 1: a site with no promise passes test 3 ─────────────────────────
const noPromiseSite = site('no-promise', {
  catalog_floods: [flood('2021-07-16'), flood('2025-08-04')],
  claims: [claim('c1', { cause: 'blocked_drainage', attributed_by: 'official', who: 'The Commissioner', evidence_status: 'inconclusive' })],
});
{
  const rows = buildWatchList([noPromiseSite], {}, rain(['no-promise']), asOf);
  const t3 = rows[0].tests[2];
  check(t3.pass && /no promise on record/i.test(t3.reason), `no-promise site passes test 3 with "no promise on record" (reason: ${t3.reason})`);
  check(rows[0].tier === 3, `no-promise site is tier 3 (got tier ${rows[0].tier})`);
}

// ── case 2: a delivered promise fails test 3 ─────────────────────────────
const deliveredPromise: SitePromise = {
  promise_id: 'p-delivered',
  site_id: 'delivered-site',
  made_by: 'The State',
  date_made: '2020-01-01',
  kind: 'build',
  what: 'a new collector drain',
  quote: 'We will build it.',
  url: 'https://example.com',
  due: { date: null, basis: 'none' },
  updates: [{ date: '2021-01-01', kind: 'imagery', ref: 'r', finding: 'done' }],
  status: 'delivered',
};
{
  const withDelivery = site('delivered-site', {
    catalog_floods: [flood('2021-07-16'), flood('2025-08-04')],
    claims: [claim('c2', { cause: 'blocked_drainage', attributed_by: 'official', evidence_status: 'inconclusive' })],
    promise_ids: ['p-delivered'],
  });
  check(promiseStatus(deliveredPromise, asOf) === 'delivered', 'fixture promise really is delivered under promiseStatus');
  const rows = buildWatchList([withDelivery], { 'p-delivered': deliveredPromise }, rain(['delivered-site']), asOf);
  const t3 = rows[0].tests[2];
  check(!t3.pass && /is done/.test(t3.reason), `delivered promise fails test 3 (reason: ${t3.reason})`);
  check(rows[0].tier === 2, `delivered site is tier 2, below the no-promise tier 3 (got tier ${rows[0].tier})`);
}

// ── case 3: floods in a thin year still count for test 1 (thin only adjusts rates) ─
{
  const thinOnly = site('thin-only', {
    catalog_floods: [flood('2024-07-03'), flood('2024-06-27')],
    claims: [claim('c3', { cause: 'drainage_capacity', attributed_by: 'resident', who: 'A resident', evidence_status: 'inconclusive' })],
  });
  const rows = buildWatchList([thinOnly], {}, rain(['thin-only']), asOf);
  const t1 = rows[0].tests[0];
  check(t1.pass && /2 flood days reported/.test(t1.reason), `thin-year floods count for test 1 (reason: ${t1.reason})`);
}

// ── case 4: building on a channel setback is a drainage failure for test 2 ─
{
  const setback = site('setback', {
    claims: [claim('c4', { cause: 'setback_encroachment', attributed_by: 'official', who: 'An official', evidence_status: 'supports' })],
  });
  const rows = buildWatchList([setback], {}, rain(['setback']), asOf);
  check(rows[0].tests[1].pass, `setback encroachment passes test 2 (reason: ${rows[0].tests[1].reason})`);
}

// ── extra: a resident's claim passes test 2 when imagery supports it ─────
{
  const supported = site('resident-supported', {
    catalog_floods: [flood('2021-07-16'), flood('2025-08-04')],
    claims: [claim('c4', { cause: 'blocked_drainage', attributed_by: 'resident', who: 'A resident', evidence_status: 'supports' })],
  });
  const rows = buildWatchList([supported], {}, rain(['resident-supported']), asOf);
  const t2 = rows[0].tests[1];
  check(t2.pass && /imagery agrees/i.test(t2.reason), `resident's claim with supporting imagery passes test 2 (reason: ${t2.reason})`);
}

// ── the real list, printed ──────────────────────────────────────────────
const { sites } = read<{ sites: SiteRecord[] }>('events/sites.json');
const { promises } = read<{ promises: OfficialPromise[] }>('events/promises.json');
const summary = read<RainSummary>('events/site_rain_summary.json');
const promiseMap: Record<string, SitePromise> = {};
for (const p of promises) promiseMap[p.promise_id] = { ...p, updates: p.updates ?? [], status: promiseStatus(p, new Date()) };

for (const iso of ['2026-03-01', '2027-03-01']) {
  const rows = buildWatchList(sites, promiseMap, summary, new Date(`${iso}T00:00:00`));
  console.log(`\n=== Pre-season watch list as of ${iso} ===`);
  for (const r of rows) {
    console.log(`${['Lowest', 'Low', 'Medium', 'High'][r.tier]} priority (tier ${r.tier}) · ${r.name} (${r.site_id}) · tie-breaks: ${r.recent_strong_days} recent flood day(s), well-searched >=40 mm rate ${r.well_searched_rate_40mm ?? 'n/a'}`);
    for (const t of r.tests) console.log(`  ${t.pass ? 'PASS' : 'FAIL'}  ${t.label}: ${t.reason}`);
  }
}

if (failed > 0) {
  console.error(`\n${failed} check(s) failed`);
  process.exit(1);
}
console.log('\nall checks passed');
