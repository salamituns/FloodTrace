# Task 24 — do reported floods sit in terrain lows and flow paths more than comparable places? (roadmap step 5)

Context: `docs/LAGOS_PLAN.md` → "Roadmap: past → present → future", step 5. Before the app models the future it has to pass
one cheap, decisive test: does a bare-earth terrain model predict *where* floods get reported? If not, the app stays a
record-and-accountability tool. A clean negative result is as valuable as a positive one; do not tune the test to pass.

## Data
- **DEM, preferred: FABDEM V1-2** (Copernicus GLO-30 with buildings and trees removed; Hawker et al. 2022, CC BY-NC-SA 4.0),
  University of Bristol data.bris repository. It ships as 10°×10° zip archives of 1°×1° GeoTIFFs. Lagos needs tiles
  N06E002, N06E003, N06E004 (AOI `[2.6, 6.28, 4.45, 6.85]`). First try reading the inner tiles with GDAL
  `/vsizip//vsicurl/<zip url>/<inner path>`. If that fails and the zip must be downloaded, check its size with a HEAD request
  first; **stop and report if it is over 3 GB**. Keep only the three tiles (clipped to the AOI) under `pipeline/cache/dem/`.
- **DEM, comparison: Copernicus GLO-30 DSM** from the public AWS bucket `copernicus-dem-30m` (anonymous COGs,
  `https://copernicus-dem-30m.s3.amazonaws.com/Copernicus_DSM_COG_10_N06_00_E003_00_DEM/…`). It includes buildings, so run
  the test on it too and report both. If FABDEM is unreachable, run on GLO-30 only and say so prominently.
- **Water:** OSM lagoon/sea polygons (as Task 16 used, relations 2116202, 2116203) and OSM waterways (Task 21's extract) for
  burning in outlets and for distance-to-water.
- **Evidence points:** all `events/*/evidence.geojson` (216 points). Filtering as Task 16 (`events/builtup_evidence_test.json`
  meta): drop `location_confidence: lga`; drop duplicates within 200 m in the same event.
- **Matching layer:** GHSL built-up 2020 exactly as Task 16 (`pipeline/builtup_change.py`), because reports come from where
  people are.

## Hydrology (`pipeline/terrain_check.py`)
`pip install pysheds` into `pipeline/.venv` is approved. Install nothing else without asking (no whitebox: it downloads a
binary at runtime).
1. Reproject the DEM to UTM 31N (EPSG:32631), 30 m. Treat lagoon/sea as outlets (set to a low constant).
2. Depressions: `depth = filled − dem` (priority-flood fill). Keep the raw depth raster and a mask of depressions ≥ 0.5 m deep
   and ≥ 3 cells (FABDEM vertical error is ~2 m in cities; report sensitivity at 0.25 and 1.0 m).
3. Flow direction (D8) on the conditioned DEM, flow accumulation (cells), and **HAND** (height above nearest drainage),
   with drainage defined as accumulation ≥ 1 km² (sensitivity: 0.25 and 4 km²).
4. Also `tpi_500` = elevation − mean elevation within 500 m.

## Test
For every kept point, compute each metric **at the scale its location supports**. Street and point use a 150 m radius;
neighbourhood uses a 750 m radius. Per radius, compute:
- min HAND
- share of cells in a depression
- max log10 flow accumulation
- min tpi_500
- elevation (m)
Also record distance to lagoon/sea.

Controls: for each point, 20 random land points (not water, not within 1 km of any evidence point) with GHSL built-up 2020
within ±0.05 of the point's, evaluated with the **same radius as that point**. Compare points vs controls with a stratified
permutation test (10,000 shuffles, seed 20261018), per metric, reporting the effect size (median difference) and p-value.
Run it overall, then separately for street/point only (the precise subset) and for points more than 2 km from the lagoon
(where tide can't be the explanation).

Also report one secondary, honest check: the share of the AOI's land that is "low" (HAND < 2 m) versus the share of points
in low land, so a reader sees whether "most floods are in low land" is just "most of Lagos is low".

## Outputs
- `events/terrain_check.json`: `meta` (sources and licences, DEM versions, method, thresholds, seed, caveats) and
  `results` (per DEM × subset × metric: n, median point, median control, difference, p), plus a per-point table
  (event_id, evidence id, location_confidence, metrics).
- `events/drainage_sites_terrain.json`: the same metrics for each of the 13 sites in `events/drainage_sites.json`, at the
  site's geometry, and its percentile among the controls.
- PNGs in `events/terrain/`: HAND map of the AOI with points; depression map; one box/strip plot per metric (points vs
  controls), small (≤ 300 KB each).
- Print a summary table and a 3–5 sentence plain-language verdict: pass, fail or mixed, and which subset drives it.

## Rules
Keep caches under `pipeline/cache/dem/`. At the end, delete only the intermediate arrays with `find … -type f -delete`;
keep the clipped DEM tiles. No `rm -rf`. Run in the foreground, no background processes. Don't touch `src/`, `events/sites.json`
or any event folder. Don't commit. Don't use the Earthdata credentials (none of these sources need them).
