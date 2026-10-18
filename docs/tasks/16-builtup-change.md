# Task 16 — how much has Lagos been built over since 2000, and do flooded places stand out?

Context: `docs/LAGOS_PLAN.md`. Rain doesn't explain which days flood. One hypothesis is that land paved or built over
(wetlands, floodplains, canal setbacks) floods more. Measure built-up change and test it against the evidence locations.

## Data (open, no login)
**GHSL GHS-BUILT-S R2023A** (JRC, CC BY 4.0): built-up surface per cell, epochs **1975, 1990, 2000, 2010, 2020** (plus 2025 if
it's in the release; say whether it's observed or projected). Use the **100 m, Mollweide (ESRI:54009)** product if feasible, otherwise
the 3 arc-second WGS84 one. Download only the tile(s) over the AOI, clip to bbox `[2.6, 6.28, 4.45, 6.85]`, and keep only clipped
rasters under `pipeline/cache/ghsl/`. **Disk is tight (~12 GB free): delete zips and full tiles after clipping.** The existing
GHS-POP clips are in the same folder; follow `pipeline/exposure_rank.py` for how they were fetched.

## Do (`pipeline/builtup_change.py`)
1. **Grid layer for the app:** aggregate to a **~1 km grid** (0.01°) over the AOI, keeping cells with any land. For each cell,
   record `built_frac` per epoch (built-up m² / cell m², 0–1). Write `events/builtup_grid.geojson` as polygons with properties
   `b1975`, `b1990`, `b2000`, `b2010`, `b2020` (`b2025` if present), `d2000_2020` (change in fraction), plus `meta` (source,
   licence, epochs, method). Round to 3 decimals and keep the file under ~8 MB (drop cells that are 0 in every epoch).
2. **Evidence test.** Take every evidence point from the five events (`events/*/evidence.geojson`). Exclude
   `location_confidence: "lga"` and duplicates within 200 m of each other in the same event. For each point, get the 1 km cell's
   `built_frac` in 2000 and 2020 and the change.
   **The catch:** flood reports come from where people are, so reported points will look more built-up whatever the cause.
   Compare against a **background sample matched on 2020 built-up level**: for each evidence point, draw 20 random land cells
   from the AOI with `b2020` within ±0.05 of it. Then ask whether flooded places **gained more** built-up since 2000 than equally
   built places that weren't reported. Report medians, the share of evidence points above their matched-background median,
   and a simple permutation test on the median difference (10,000 shuffles, fixed seed).
   Also report the same test restricted to points within 2 km of the Lagos Lagoon / Lekki Lagoon shore (Natural Earth or the
   OSM water you already have), where reclamation is most likely.
3. Write `events/builtup_evidence_test.json` (per-point values, background stats, results) and print a short summary.
   Interpret cautiously: the sample is small, 1 km cells are coarse, and GHSL misses informal settlements. Also say what a
   null result would and wouldn't mean.

Don't touch `src/` or event folders. No stray background processes. Run to completion. Don't commit.
