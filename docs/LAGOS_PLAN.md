# FloodTrace for Lagos — multi-event plan

Goal: a forensic tool for **any** Lagos flood event, not one hand-built scenario. Each event is a data package;
the app is a viewer and analysis surface over a catalog of them.

## Event catalog

```
events/
  catalog.json                 # index: id, dates, areas, severity, data availability flags
  lagos-2024-07-03/
    dossier.md                 # human write-up: timeline, sources, hypotheses, gaps
    event.json                 # machine-readable: window, AOI, key events, cited sources
    rainfall.json              # IMERG 30-min series (AOI mean + grid)
    tide.json                  # tide series (+ lagoon estimate)
    sar/                       # pre/during/post flood masks (COG / GeoJSON)
    evidence.geojson           # geolocated, timestamped reports (photo/video/news/official)
```

Every number carries its **source and uncertainty**; "est." and "prob." labels are first-class, as in the FireTrace reference.

## Finding events (to scale beyond one)

1. **Rainfall trigger scan:** IMERG daily/30-min history (2000→present) over the Lagos AOI → candidate days above an intensity/total threshold.
2. **Cross-reference:** news + X + NiHSA/LASEMA statements + Dartmouth Flood Observatory + EM-DAT for each candidate.
3. **Satellite luck check:** list Sentinel-1 passes within ±12 h of each candidate (Copernicus catalogue query — already scripted ad hoc).
4. Confirmed events get a dossier; scoring = evidence richness, so the best-documented events come first.

### Status (2026-10-17): first scan done — `events/catalog_candidates.json`

- IMERG v07 half-hourly at the 4 analysis points, Jun 2000 → present (Final to 2025-09-30, Late after), via GES DISC
  Giovanni-in-the-Cloud time series (Data Rods was retired in 2025). `pipeline/imerg_history.py`.
- **287 candidates** (any point ≥ 50 mm/day or ≥ 30 mm/h in 30 min). Seasonality matches Lagos's two wet seasons (Apr–Jul, Sep–Oct).
- **Validation against known disasters:** 10 Jul 2011 ranks **#1** (192 mm, Lagos Island); 6–8 Jun 2023 **#3**;
  4 Aug 2025 **#8**; 2–3 Jul 2024 **#26** (point-based, see below).
- `antecedent_7d_mean_mm` is the **mean daily** rain over the 7 days before the start (×7 for a total).
- **Known blind spot:** four points miss rain cores between them — the 3 Jul 2024 core (31 mm/h over Apapa / Mile 2) is
  invisible to this scan. Next: scan the IMERG grid max over the AOI (or add points: Apapa, Ikorodu, Badagry, Epe, Ojo, Oshodi).
- **Top-20 review (`events/catalog_review.json`, Task 08):** 3 confirmed floods (2011-07-10, 2022-07-08, 2025-08-04),
  1 likely (2017-07-05/08), **16 heavy-rain events with no flood report found**. Either rain totals alone are a weak flood
  predictor in Lagos (location/intensity/tide/drainage matter), or older floods are under-reported online — likely both.
  Telling these apart is a core question for the tool. Casualty figures were taken only from named, readable sources.
- **Grid scan (Task 07, `catalog_candidates_grid.json`):** 68 IMERG cells (land + lagoon shore), 2000 → present → **641
  candidates** (356 not found by the 4-point scan). 2011-07-10 stays **#1** (213 mm at Apapa, all 68 cells); 2024-07-02/03 is #30.
  - Ranking by the single wettest cell is **dominated by the rural fringe** (top 100: Epe 22, Sangotedo 11, Lekki Free Zone 11,
    Ibeju 8, Seme border 5) — big totals where few people live.
  - **Spatial extent discriminates the deadly floods:** cells over threshold — 2011: 68/68, 2022: 65, Aug 2025: 52 (all ≥ 97th
    percentile; median candidate = 6). Jul 2024 (31, 88th pct) is a more local event driven by an intense core on saturated ground.
  - Next: an **exposure-weighted ranking** — rain over built-up cells (Google Open Buildings / WorldPop density) and extent — and
    review candidates in that order. Treat single-cell peaks > 70 mm/h (e.g. 109 mm/h on 2014-05-13) with suspicion until checked.
- **Exposure ranking (Task 10 + review, `catalog_ranked.json`):** GHSL GHS-POP R2023A per epoch (AOI 9.4 M in 2000 → 15.8 M
  in 2025). Primary order = `pwr_rank` (population-weighted rain); "people exposed ≥ 50 mm" saturates (56 candidates expose
  > 90 % of the AOI) and mostly encodes the population epoch, so it's kept as a secondary field.
  **Top 25 by pwr, all reviewed (Tasks 08 + 11):** 5 confirmed floods (2022-07-08 #2, 2011-07-10 #6, 2025-08-03 #21,
  2021-07-16 #25, plus the known 2024-07-02/03 #20), 1 likely (2017 #22), 18 with no flood report found — including
  2016-10 (#3) and 2023-06 (#5) after a deeper ±2-day re-check. The 16 Jul 2021 Marina/Lekki flood was #87 in the point scan
  and invisible to the first review; pwr surfaced it.
  Ground truth found along the way: NiMet station totals for 15 Jul 2021 — 125 mm Oshodi, 66 mm Ikeja (use to validate IMERG).
- **Three more events built (2026-10-17):** 2022-07-08, 2025-08-04, 2021-07-16 now have IMERG, EOT20 tide, OSM drainage and
  reviewed evidence, and are selectable in the app. Tide phase at the rain peak: 2022 cores within 1 h of high tide (compounding
  plausible near the lagoon, but the Alimosho deaths were ~20 km inland); 2025 peak on a weak high (0.10 m); 2021 peak on a
  falling tide (like 2024). No Sentinel-1 pass during any of the three.
  Gauge check (if NiMet's "15 Jul" means the 16th): Oshodi IMERG 90 vs gauge 125 mm, Ikeja 87 vs 66 mm.
  Note: `rainfall_summary.json` `totals_mm.24h` is the 24 h *ending at each point's peak*, not a calendar-day total.
- **Flood vs no-flood (Task 14, `events/flood_vs_noflood.json`):** pwr top 25 = 5 floods, 19 no-flood, 1 likely (2017).
  Nothing separates the groups cleanly. Rain totals, 30-min/1-h/3-h peaks, duration and 7-day antecedent overlap almost
  completely; urban 3-h intensity (8/19 no-flood ≥ weakest flood) and 3-day antecedent (10/19) are weak signals at best.
  **Tide phase adds nothing:** 4 of 5 floods peaked on a falling tide (median 2 h after high water) — tidal lock is not what
  made these days flood. **The loudest pattern is year:** all 5 floods are 2011+, no-flood days median 2012 (span 2002–2023).
  So "no flood report" before ~2014 likely often means under-reporting: 2010-09-23 and 2008-06-06 match or beat the weakest
  flood on every rain/tide feature. 2016-10-07 and 2023-06-06 (well-covered years, rechecked) are the real puzzles.
  The 2017 "likely" event has weak rain (pw max-3h 13 mm), fitting its flooding being two days later.
- **Reported causes (Task 15):** every evidence feature carries `causes`/`cause_quote`/`cause_attributed_by`; citywide claims
  sit in `meta.citywide_cause_statements`. These are *attribution claims*, not verdicts. Heavy rain is named in every event;
  human causes are almost all drainage (blocked by refuse, too small, abandoned, built over, dammed by a contractor) and
  cluster in 2024–2025. 2011 coverage barely names any, which is probably a reporting change rather than a new cause.
  App: cause chips per report, "Reported causes" bars in Event Overview (brown = human).
- **Built-up change (Task 16, `pipeline/builtup_change.py`):** GHSL GHS-BUILT-S R2023A, 100 m → 0.01° grid
  (`events/builtup_grid.geojson`, app layer "Built over since 2000"). Built-up in AOI 477 km² (2000) → 781 km² (2020), +64%;
  2020 is interpolated and 2025 projected. Evidence test (`events/builtup_evidence_test.json`, 126 points after dropping LGA-level
  and <200 m duplicates, each matched to 20 cells with similar 2020 built-up): reported places gained **less** than matched
  controls (median Δ +0.007 vs +0.020, p≈0.03–0.045; lagoon-shore n=26: +0.015 vs +0.099, p≈0.001–0.002; I re-ran it independently).
  This reflects saturation: reports cluster in the old core, already built out by 2000. The Lekki axis built up most but
  is not reported more. 1 km cells can't test reclamation or setback encroachment, which happen at parcel scale.
  Next: per-parcel change along canals and the lagoon edge for the specific streets named in cause claims.
- **Street-level drainage check (Tasks 17–18):** `events/drainage_sites.json` (13 sites, structure, dates, quotes; 5 key
  quotes verified) and `events/drainage_sites/<site>/` (Esri Wayback chips by acquisition date, OSM context;
  `events/drainage_sites_imagery.json`). My reading of the before/after pairs:
  - *alpha-beach-156* (2020-04 → 2024-11): south end changed most. A vegetated wetland and informal settlement along the line
    were cleared and sand-filled, with a walled plot, a large new building and a new estate grid to the south. The open
    channel at the expressway and in the estates is intact. Consistent with "developers" on the corridor, but the Nov 2024
    image comes after the June–July 2024 excavation and enforcement, so the clearance could be either.
  - *agungi-collector* (2020-04 → 2024-11): steady infill, and a new terrace estate on open land at the lagoon end (more
    runoff into the same outfall). The collector itself isn't visible (roadside or underground). Weak support.
  - *agric-bridge* (2020-01 → 2025-04): road widened to a construction corridor, with large earthworks beside the green
    river wetland at the south end. Confirms major works were under way before the flood. No post-flood image exists yet.
  - *oko-oba-canal*: the line follows Oko Oba Road (unpaved 2021 → paved 2025), not the canal, which OSM doesn't map.
    Re-locate the canal before judging.
  - *sangotedo*, *olopomeji*, *marina*, *alapere*, *ibeju-lekki-expy*: inconclusive (channel not located, refuse not
    visible, covered drains, or a road-works claim). *labora*: the point falls in forest, so the geocode is wrong.
  - *ikorodu-dammed*, *ijede-drain*: newest imagery is Nov 2024, before the Feb 2025 start. Re-run when Wayback adds
    late-2025 imagery.
  - **Sentinel-2 timelines (Task 20, `events/drainage_sites_s2.json`).** Only Alpha Beach south changes. Its wet-season (May–Oct)
    vegetated fraction fell 0.38 (2018) → 0.28 (2020) → 0.17 (2022) → 0.12 (2024) → 0.08 (2025), so most of the clearing predates
    the flood and the June 2024 excavation. Droid's step detector reported "2022-10", but the series has a strong dry-season dip
    to ~0 every year, so read same-season medians, not raw monthly steps. Every other site is flat; at 10 m most are already
    built out (Agric 0.02, Marina 0.00), or the works are too narrow to register.
  - **Open Buildings encroachment (Task 21, `events/drainage_sites_buildings.json`).** Built fraction 0–10 m from each
    channel, 2016–2023 (Google Open Buildings 2.5D Temporal, presence ≥ 0.5, 4 m effective). Droid's percentiles (97–99%) were
    against all OSM waterways, mostly rural, with a median of 0 built within 10 m, so they're inflated. I re-ranked against
    channel segments with similar 2016 built-up at 20–50 m (n ≈ 13–20):
    - *Alpha Beach / System 156:* 0.036 → 0.094, surge 2019–22, 88th pct vs matched. Same years as the Sentinel-2 clearing, so
      the land beside the channel was cleared **and built on** before the 2024 flood. The most consistent case we have.
    - *Oko-Oba canal* (traced channel): ~0.13 built within 10 m already in 2016, unchanged since (21st pct). Encroachment
      predates the satellite record, consistent with the "infringed channel" notices of Oct 2022.
    - *Agungi* (71st) and *Olopomeji* (73rd): ordinary. *Alapere*: decline (road works). *Agric*: flat.
    - *Ikorodu/Ijede* (93–100th): **discard**. Their lines are rough town-to-town corridors, not channels, so they measure
      roadside growth. *Sangotedo*: no centreline. *Marina, Labora, Ibeju-Lekki Expy*: no channel line, skipped.
    Validation of the 2023 mask vs OSM footprints: precision 0.42–0.56 / recall 0.52–0.79 near channels. Usable for trends,
    not counts.
  - **Task 19 relocations.** Labora → Abijo GRA (3.666, 6.450). Sangotedo notices → Lagos Business School (3.604, 6.471),
    System 63b, no OSM centreline. Oko-Oba canal: I traced the open channel on current Esri imagery (S→N from the Agric Road
    bridge 3.3147, 6.6494); Cursor's line veered onto streets in the north (kept as `geometry_prev_task19`).
- Next after that: cross-reference the top candidates with news/LASEMA/Dartmouth Flood Observatory and promote confirmed ones to event folders.

## App changes from the Phase-1 prototype

- **Keep:** single clock, timeline, key events, charts, layers panel, cards, overall layout.
- **Replace:** procedural valley + levee model → **MapLibre GL + deck.gl** over real basemap, terrain and building footprints.
- **Hydrology card →** rain intensity / 24-h total / antecedent 7-day, ocean + lagoon tide, Ogun River / Oyan Dam status, reported-flooding count.
- **Evidence tab (central):** media items on the map and timeline, each with location confidence and time confidence.
- **Event switcher:** the "Cedar Fork Flood ▾" selector becomes the catalog.

## Pipeline

Python scripts under `pipeline/` produce the event packages (IMERG, tide, Sentinel-1 flood masks, buildings, OSM drains);
the web app only reads static files. No backend needed until collaboration/editing of evidence.

## Cause position (agreed with the user, 2026-10-17)

Heavy rain is the **trigger**; human drainage failures are the **main amplifier** of where Lagos floods: refuse-blocked drains,
drains too small or never built, buildings on channels and setbacks, wetland fill, and works that obstruct flow. The evidence
lines up: rain and tide don't separate flood days from no-flood days, the causes sources name are almost all drainage, and
imagery shows visible human change at named sites (Alpha Beach, Agric). This is strong agreement across lines of evidence, not
measured drainage capacity. The app therefore stops asking *whether* causes are human and asks **which action, where, by whom,
when, and was it fixed**. Dossiers state this framing; each named cause carries an evidence status.

## Roadmap: past → present → future

The geoscience principle "the present is the key to the past", with a Lagos twist. Physics is constant, but the urban drainage
system that routes the water is rebuilt every year (fill, encroachment, new roads and outfalls). So the same storm hits a
different city each year, which is why rain alone didn't explain flood days. Read the past through present-day processes
**plus** a record of how the system changed (actualism rather than strict uniformitarianism). Each stage builds on the one before.

**Past: reconstruct (done for 5 events; scale it).**
1. *Automated event intake.* IMERG candidate days → news scan → event package → agent evidence and cause tagging → my
   verification. Toward "as many events as exist". Treat the thin record before ~2014 as a preservation bias, like the fossil
   record: "no report" ≠ "no flood".

**Present: sites and accountability.**
2. *Sites as the main unit.* A persistent page per place (Agungi, Alpha Beach/System 156, Oko-Oba, Ikorodu/Ijede, Lekki…): every
   report across events, causes blamed and by whom, the structure involved, Wayback before/after pairs and the Sentinel-2
   timeline (`events/drainage_sites*`). Events become a filter.
3. *Promise tracker.* Dated official commitments (Agungi collector, Jun 2024; System 156 excavation, Jun–Jul 2024; Oko-Oba 8 m
   expansion, Oct 2022; Ijede 12-month job, due ~Feb 2026). Status = delivered / in progress / no visible work, evidenced by
   imagery and re-checked every rainy season.
4. *Cause chain per claim.* Who claimed it → which structure → dated change → flood → evidence status. Cause chips link into it.
   **Done 2026-10-18.**
   - In Incident mode, a report that belongs to a site shows "Part of site: … →", and its map tooltip names the site.
   - A cause chip that became a site claim is a button with an evidence-status dot. It opens the site page, scrolled to
     that claim and highlighted.
   - The links come from `sites.json` (flood radius + claims) via `src/sites/links.ts`. Sites now load at startup.

**Future: scenarios, not forecasts.**
5. *Terrain check first (cheap, decisive).* Copernicus GLO-30 / FABDEM (bare-earth) → depressions, fill-and-spill, flow
   accumulation. Test whether the ~200 evidence points fall in modelled sinks and paths more than matched random points. Passing
   this is what earns the app the right to look forward. Lagos is flat and DEM vertical error is ~2 m, so rank sites
   relatively; never predict depths.
   **Result (Tasks 24/24b, 2026-10-18): no usable terrain signal at 30 m.** On FABDEM (bare earth, from the Hugging Face
   mirror `links-ads/fabdem-v12` because data.bris refused every request; CC BY-NC-SA) with neighbourhood controls
   (1–3 km, equally built-up), the pre-set rule technically passes: min HAND (Holm p = 0.002) and TPI (p = 0.035). But the
   effects are 0.02 m and 0.21 m, which is 1% and 11% of the ~2 m DEM error. Min HAND sits at ~0 for 78% of windows, so it
   barely discriminates: 59% of flooded spots sit below their neighbours' median, where chance alone gives 50%. GLO-30
   fails the same test, and depression share and flow accumulation show nothing. The 17 m elevation gap in the first run
   was geography: the coastal city against the Ogun/Epe hinterland. My mistake was a rule with no minimum effect size.
   Reading: at 30 m, terrain can't say which spot in a neighbourhood floods. That fits the cause position (drainage
   decides where), so a site-level forecast shouldn't rest on these DEMs. Revisit only with better elevation data
   (LiDAR or a city DTM, none public) or a much larger event set (step 1). Outputs: `events/terrain_check.json`,
   `events/drainage_sites_terrain.json`, `events/terrain/`.
6. *Storm replay.* Run past IMERG storms over present conditions (the 2011 storm on 2025 Lagos) and over hypothetical fixes
   (the 2024 storm with the Agungi collector built). This is the most direct use of the principle.
7. *Per-site flood odds.* P(flood | rain intensity, site drainage state: blocked / built-over / fixed). It needs many more
   events than 5, so it depends on step 1.
8. *Pre-season watch list.* Each March, rank sites with repeated flooding, named drainage failure and no visible fix.
   Sea and lagoon level rise and projected rain intensification enter later as boundary conditions; drainage dominates on the
   app's timescales.
Limits to state everywhere: no public gauges, few events, reporting bias, coarse DEM. Outputs are comparative ("worse than",
"this fix helps more than that one"), which is exactly the comparison a drainage agency needs to prioritise.

Order: 2 → 3 (build on current site data) → 5 → 4 → 1 → 6 → 7 → 8. `tidalLock()` (`src/lib/tidalLock.ts`, user TODO) is now
low priority: drop it or scope it to lagoon-edge sites where backwater may still slow drainage.

## External tools to consider

From the curated list https://github.com/sparkgeo/geo-mcp-servers (MIT, 107 servers, checked 2026-10-17):
- **Data worth using regardless of MCP:** Overture Maps buildings (via the *Overture Maps MCP* / *PlaceRoot*). They include Google
  Open Buildings, which covers Lagos far better than OSM. Google's *Open Buildings 2.5D Temporal* (annual 2016–2023) could date
  building on drainage channels per parcel. Best fit for the setback test and site timelines.
- **MapSmith** (Whitebox hydrology + provenance manifest): candidate for prototyping roadmap step 5.
- **earthdata-mcp** (NASA, official), **stac-mcp** / **planetary-computer-mcp**: dataset discovery. Our pipeline already calls
  these APIs directly, so they add little.
- Policy: MCP servers are third-party code. Read the source before installing, install only with the user's OK, and never pass
  the Earthdata credentials to one. The pipeline stays as reproducible scripts; MCP is for exploration, not production.
