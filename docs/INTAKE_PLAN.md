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

## Status (2026-10-18): full sweep under way (Task 28)
- **Done:** 2024 and 2025 (pass 1 + 2), plus pass 2 for 2019. The catalog has 25 flood days: 23 rain floods and 2 river
  floods, which are one riverine episode (Oyan Dam, Oct 2019, 6 dead).
- **Pass 2 slimmed.** The wire services, ReliefWeb, the Dartmouth archive and government sites added nothing in either test
  year. What pass 2 catches is river and dam floods, and deaths (the 2019 Oyan Dam flood; the 2025-05-20 Alakuko
  motorcyclist). The 2019 recall test was partly leaked: the prompt named the target article, so Task 28 now forbids
  searching for named articles.
- **Flood types (Task 28b).** Each day is now rain, river or lagoon, and river days within 21 days form one episode. The
  drainage signal counts rain floods only.
- **Merge rule tightened.** Only `approx` dates may join a neighbouring day; dates worked out from a weekday are reliable.
  This split 2019-10-11 (Agege) from 10-12 (Alimosho), and 2025-09-24 from 09-23 (rain on both days).
- **The drainage signal can't be read from IMERG alone.** 4 of 23 rain-flood days have < 20 mm locally (2023-04-27,
  2024-02-20, 2025-05-18, 2025-05-20). On every one of them, the sources describe heavy rain or a torrential downpour.
  The likelier reading is that IMERG (0.1°, satellite) misses short, intense, local storms, not that light rain floods
  Lagos. Next: cross-check those days against a rain gauge (GHCN-Daily stations at Ikeja and Lagos Marina, open NOAA data),
  if records exist for those dates.
- **Corrected:** r2025-013's cause_quote had TVC's Wahab quote copied in. It's replaced with Nairametrics' own sentence.
- **2026 (Jan–Sep) and 2022 done.** The catalog has 43 days (41 rain, 2 river), 16 promoted.
- **Deaths (Task 28c).** Each report now carries an explicit `deaths` field filled in by the reader. The word regex only
  feeds `deaths_review`; it never promotes. A day promotes on deaths when the source is named, or when at least 2
  outlets report the deaths (decision 3). Reviewer fix: r2022-003's death isn't attributed to Bamuya in the article.
- **Conflicting counts are kept as reported.** For 8–9 Jul 2022, Punch and Channels say NEMA counted 7 dead in Lagos;
  Vanguard says Farinloye split them 5 Lagos / 2 Ogun. Any total must use 5 for Lagos and must never sum across reports.
- **2021 done.** 9 days, among them a second riverine episode: 2 Sep–10 Oct 2021 (Owode-Onirin, Iba, Ajegunle, Itowolo;
  the Oyan release). The catalog has 52 days (46 rain, 6 river in 2 episodes), 18 promoted.
- **Reviewer fix: Tier A matching.** `tier_a_event` matched any day inside an event's ±1-week data window, which wrongly
  linked 2024-06-27 (Agungi) to `lagos-2024-07-03` and 2021-07-23 to `lagos-2021-07-16`. It now matches only the
  event's focus (the wettest ~48 h) or the folder's own date.
- **Watch:** Orile-Agege (2019-10-11) geocoded to two points ~3 km apart in two runs, which moved its local rain from 10 mm
  to 22 mm. Low-rain days near 20 mm are sensitive to geocoding; the gauge cross-check should use a margin.
- **2020 done.** 6 days. On 22 Jun, a teenager died in the Surulere canal (LASEMA; Punch prints her age as 19, Daily
  Trust as 17, and both are kept as printed). On 18 Jun, 6 outlets covered the flood and a 4-year-old was swept away at
  Orile-Agege; she's recorded as missing because no outlet confirms a death. The catalog has 58 days (52 rain, 6 river
  in 2 episodes), 21 promoted.
- **Reviewer fix: riverine trigger.** A bare "Ogun River" in the text is often a place ("Ogun River plains at Isheri"),
  and that made the 4 Jul 2020 weekend downpour a river flood. The river name now has to sit near overflow wording.
