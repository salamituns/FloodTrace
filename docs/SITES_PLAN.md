# Site pages and promise tracker: plan

Roadmap steps 2–4 in `docs/LAGOS_PLAN.md`. Sites become the main unit: one page per place that keeps failing, with its whole
evidence chain and the official promises made about it. Alpha Beach (System 156) and the Oko-Oba canal are the pilot sites:
both have complete chains.

## Data

### `events/sites.json` (built by `pipeline/build_sites.py`; never hand-edited)
Merges `drainage_sites.json`, `drainage_sites_imagery.json`, `drainage_sites_s2.json`, `drainage_sites_buildings.json`, every
`events/*/evidence.geojson`, and `events/promises.json`.
```
{ meta, sites: [{
  site_id, name, aliases[], structure_name, structure_type: channel|collector|canal|bridge|road|area,
  geometry, location_confidence, located_how,
  floods: [{ event_id, date, evidence_ids[], n_reports, nearest_m }],    // all events, evidence within radius_m (default 400 m)
  claims: [{ claim_id, event_id, cause, attributed_by, who, quote, source_id, url, date,
             evidence_status: supports|weak|inconclusive|contradicts|not_checked|no_imagery_after, status_note }],
  change: {
    wayback: [{ acq_date, file, marked_file }],                         // before/after pairs picked by the page
    s2_wet_season: { aoi, by_year: {YYYY: vegfrac} },                    // same-season medians, not raw monthly steps
    buildings_0_10m: { by_year: {YYYY: frac}, matched_pct, matched_n },  // my matched re-rank, not the raw baseline pct
    summary                                                              // one sentence, written by a reviewer (me)
  },
  promise_ids[], verdict: { text, confidence: strong|moderate|weak|none, reviewed_by, reviewed_at }
}]}
```
`verdict` and `change.summary` are the only reviewer-written fields. The builder keeps them from the previous `sites.json`
(keyed by site_id) and flags them `stale: true` when underlying numbers change.

### `events/promises.json` (researched; reviewer-verified)
```
{ meta, promises: [{
  promise_id, site_id, made_by, role, date_made, source_id, url, quote,       // ≤ 25-word verbatim, Task 03 rules
  kind: build|expand|excavate|dredge|demolish|enforce|maintain|other,
  what, due: { date|null, basis: stated|contract|inferred|none, note },
  updates: [{ date, kind: news|official|imagery, ref, finding }],             // later evidence, newest last
  status, status_reason, last_checked
}]}
```
`status` comes from `promiseStatus()` in `src/lib/promises.ts` (see below), not typed by hand, so every status is reproducible
from its evidence.

## UI

**Mode switch** in the TopBar: `Events | Sites`. URL hash `#site=alpha-beach-156` / `#event=lagos-2024-07-03` for shareable links.

**Sites mode:**
- **Map:** all sites as markers (colour = verdict confidence, ring = worst promise status), channel lines drawn. Click → site page.
- **Right panel = site page:**
  1. *Header:* name, structure, location confidence, verdict sentence.
  2. *Evidence chain card:* claim → structure → dated change → flood(s) → status: one row per claim, each step linked.
  3. *Floods here:* every event with reports at this site, each with "Open in event view" (switches mode at that event's time).
  4. *What changed:* a before/after slider (two Wayback dates, defaulting to the last before the change and the first after),
     a Sentinel-2 wet-season sparkline and an Open Buildings 0–10 m sparkline with the matched-baseline percentile.
  5. *Promises:* status chip, what, who, date made, due, latest update.
  6. *Sources.*
- **Timeline becomes multi-year** (2012 → today): flood events as markers, promise dates as diamonds, the change series as a band.
  This is the "present is the key to the past" view: one axis for causes, floods and responses.

**Events mode** (existing) gains: evidence within a site's radius shows "Part of site: Alpha Beach →".

## Promise status rules (`src/lib/promises.ts`): user contribution
`promiseStatus(p, today)` → `delivered | in_progress | no_visible_work | overdue | unverifiable`. This is a judgment call that
shapes how the app treats officials, so it's left to the user (see the TODO in the file).

## Work split
1. **Cursor, Task 22:** research `events/promises.json` for all 13 sites (seed list below), including later updates.
2. **Droid, Task 23:** `pipeline/build_sites.py` → `events/sites.json` (runs on whatever promises exist; re-run later).
3. **Me:** types, loader, mode switch, site page, map layer, multi-year timeline; reviewer fields for the two pilot sites;
   verification in the browser.
4. **User:** `promiseStatus()`.

Seed promises (from Tasks 17/19, to be verified and extended):
- Agungi: new, bigger collector to the lagoon (MoE, 27 Jun 2024).
- System 156: full excavation from Alpha Beach to Conservation Road "Saturday" (MoE, 27 Jun 2024); dredging and silt removal
  (Wahab, 5 Jul 2024); enforcement to reclaim setbacks.
- Oko-Oba: 8 m expansion with 5 m right of way each side, contravention notices then removal (Guardian, 27 Oct 2022).
- Ijede/Ikorodu: 12-month drainage contract from ~Feb 2025 (Guardian, 8 Aug 2025); contractor to "hasten work".
- Sangotedo: 14-day abatement and 48-hour contravention notices, then enforcement (Punch, 7 Jul 2024); demolition at System 63b
  (Nairametrics, 21 Sep 2024).
- Agric/AFA bridge: completion (opened inbound 8 Sep 2026; outbound pending).

## Status (2026-10-17): pilot built
- `events/promises.json` (Task 22, Cursor): 16 found, 15 kept. Quotes spot-checked verbatim. I removed two `claimed_done`
  updates on the Agungi collector (the 2026 sources are about demolitions, not the collector) and one non-promise (an appeal
  to a contractor mid-storm). Imagery updates added by me after viewing the images. Statuses from `promiseStatus()`
  (imagery only; stalled after 12 months without seen work; 12-month grace; dredge/maintain unverifiable; overdue outranks
  in-progress).
- `events/sites.json` (Task 23, Droid, `pipeline/build_sites.py`): 13 sites, schema-validated, deterministic; reviewer fields
  persist across rebuilds and flip `stale` when inputs change (tested). Verdicts written for alpha-beach-156 (strong) and
  oko-oba-canal (moderate).
- App: Sites mode, site list, site page (verdict, evidence chain, floods → open event, before/after slider with close-ups,
  S2 and Open Buildings sparklines, promises), multi-year timeline, `#site=` links. Checked in the browser; no console errors.
- Known nuances: the System 156 excavation's "due" date is a *start* date ("from Saturday"); it reads overdue because full
  excavation isn't visible by Nov 2024, and would also be overdue under the 12-month grace.
- Fixed 2026-10-18: "Open event" keeps the site in view in Incident mode (max zoom 14). The sites loader retries three times
  with backoff (it treats an HTML response as a failure) and then shows a Retry button.
- 2026-10-18: verdicts for agungi-collector (weak) and agric-bridge (weak) from Task 25 (`events/verdict_evidence.json`; key
  quotes re-checked verbatim). Wahab's 1 Jul 2026 "dammed the downstream" refers to an unnamed Ikorodu drainage contractor,
  not the AFA bridge, so it is not used for agric-bridge. Esri Wayback through the 24 Sep 2026 release still has nothing newer
  than Nov 2024 (Agungi) or Apr 2025 (Agric).
- Next: verdicts for the other 9 sites as evidence allows; imagery updates when Wayback adds late-2025/2026 imagery
  (Ikorodu, Ijede, Agungi demolitions, AFA inbound deck).
