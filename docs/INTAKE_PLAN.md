# Event intake: plan (roadmap step 1)

Goal: grow from 5 forensic events toward every Lagos flood that left a public record. Per-site flood odds (step 7)
need many events. They also need honest "no flood" days, so search effort has to be recorded, not just hits.

## What we learned from the first catalog (Tasks 06–11)
- **Rain-first discovery yields little.** Of the top 25 candidates ranked by population-weighted rain, 5 were confirmed
  floods and 18 had no flood report found. The 16 Jul 2021 Marina flood was #87 in the point scan.
- **That fits the agreed cause position.** Drainage decides where water collects, so floods also happen on moderate-rain days
  that a rain threshold never surfaces.
- **Old records are thin.** Online news before ~2010 is patchy, so treat it like the fossil record:
  "no report" ≠ "no flood" (preservation bias).

## Design: two tiers, two discovery tracks

**Tier B: catalog record (cheap; the bulk; this is what step 7 needs).** One JSON record per flood day:
- date (± confidence);
- named Lagos areas, each geocoded with its confidence;
- sources (url, publisher, date, read status, ≤ 25-word quote);
- impacts as reported;
- causes named (Task 15 tags);
- the IMERG grid rain signature for that day (already computed in `rain_history_grid_daily.json`, 2000 → present).

No event folder.

**Tier A: forensic event package (expensive; selected).** Today's event folders:
- IMERG 30-min, EOT20 tide, satellite passes, OSM drains;
- reviewed evidence with causes;
- a dossier.

An event is promoted from B to A when it meets the promotion rule (decision 3 below).

**Track 1: news-first sweep (new).** Search month by month across the wet seasons (Apr–Nov) for "flood" + Lagos coverage,
2010 → today. Outlets: Punch, Vanguard, Guardian NG, Premium Times, Channels, TVC, Daily Trust, BBC Pidgin, Nairametrics,
plus the X accounts of LASEMA, MoE and NEMA. Every month gets a search log (queries, outlets, hits) whether or not it finds
anything. That log is what makes a "no flood" month usable.

**Track 2: rain-first (existing).** Candidates from `catalog_ranked.json` keep being reviewed in pwr order (25 done so
far). The two tracks cross-check each other:
- floods found by news on low-rain days are the drainage-failure signal;
- heavy-rain days with no news are the "no flood" controls.

## Pipeline
1. `pipeline/intake/news_sweep`: an agent task, run per year and resumable. Writes `events/intake/reports_<year>.json`
   and `events/intake/search_log.json`.
2. `pipeline/intake/merge.py`: groups reports into flood days (same or next day, overlapping areas), geocodes the areas
   with `pipeline/geocode.py`, attaches the rain signature, and matches rain candidates. Writes `events/flood_days.json`
   (the Tier B catalog).
3. `pipeline/build_event.py <event_id> --start --end [--focus]`: the Tier A builder. Writes `event.json` from a template,
   then runs `fetch_open_data.py`, `imerg.py` and `tide_eot20.py`, plus `sar_flood.py` only if a Sentinel-1 pass falls
   in the focus window. Updates `catalog.json`. It does once, from one command, what was done by hand for the last 3 events.
4. Evidence + causes for a Tier A event: the existing agent task, Task 12 + Task 15 rules in one brief template.
5. Review (me), before anything reaches the app:
   - every official quote and every casualty number re-read at its source;
   - 1 in 5 other quotes re-read;
   - every geocode with location confidence `street` or finer checked on the map.
6. `pipeline/build_sites.py` re-run. Site floods and claims pick up new events automatically.

**App:** the Sites timeline and site pages read Tier B too. A site's "Floods here" lists catalog days with a source link,
even without an event folder.

## Decisions (settled with the user, 2026-10-18: all as proposed)
1. **What counts as a flood day (Tier B)?**
   - at least one readable source (not headline-only) that names a place in Lagos State and a date, and
     describes water on streets or in homes.
   - Warnings, forecasts and "residents fear" stories don't count.
2. **How far back?** 2010 → today for the sweep. Earlier years only through the rain-first track, flagged
   low-coverage.
3. **Promotion to Tier A?**
   - Any of the following:
     - deaths reported by an official or named source;
     - ≥ 3 independent outlets;
     - an official naming a structure, which feeds the sites.
   - Otherwise stay Tier B.
4. **Cadence:** one intake pass after each wet-season month, plus a full annual pass in December (IMERG Final
   lags ~3.5 months, so rain signatures for the latest months use IMERG Late and are flagged).

## Work split
- **Cursor:** Task 26, the news sweep. Pilot on 2 years first (2019, 2023) to measure yield and time, then the rest.
- **Droid:** Task 27, `build_event.py` + `merge.py`. Test by rebuilding `lagos-2021-07-16` into a scratch folder and diffing
  it against the reviewed one.
- **Me:** the review rules, the Tier B reader in the app, promotion decisions.

## Status (2026-10-18): pilot done
- **`build_event.py` (Task 27): accepted.**
  - Rebuilding `lagos-2021-07-16` reproduced the reviewed folder; only `retrieved_at` timestamps differ.
  - It's idempotent.
- **News sweep pilot (Task 26, 2019 + 2023):**
  - 23 reports → 11 flood days (after merging 2019-10-11 into 10-12) in ~4.7 h.
  - Quotes spot-checked verbatim.
  - **Recall is imperfect.** Anadolu (23 Oct 2019) reports 6 dead in Lagos floods blamed on an Oyan Dam release; the pilot
    has 20 Oct 2019 with no deaths. 2023 yielded only 4 days, in a year the state called wetter than 2021–22.
  - Before the full run: add a second pass per month (Anadolu, Reuters, ReliefWeb, Dartmouth Flood Observatory, dam-release
    and death queries).
  - Estimated full 2010–2026 cost: ~45–50 h of agent time, plus ~20% for the second pass.
- **`merge.py` (Tasks 27, 27b):** rain is now measured at the flooded areas' own cells, over the flood day plus the day
  before. Measured that way, the drainage signal is **1 of 11 days** with < 20 mm locally (2023-04-27, Surulere, beside a
  canal). The first figure, 6 of 12 on the AOI mean, was an artefact of averaging over the rural fringe and of overnight rain.
  So in this sample, reported floods follow real local rain. Drainage decides *where* within a storm, not *whether* a light
  rain floods. Promotion: 3 days (2019-05-20 outlets; 2019-10-12 and 2023-09-16 deaths with a named source).
