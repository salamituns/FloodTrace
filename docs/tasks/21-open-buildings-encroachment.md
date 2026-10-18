# Task 21 — when did buildings appear beside the blamed drainage channels? (Google Open Buildings 2.5D Temporal)

Context: `docs/LAGOS_PLAN.md` → "Street-level drainage check", "External tools". Officials blamed buildings on drainage channels
(System 156 at Alpha Beach; Sangotedo contravention notices; the Oko-Oba canal widening). OSM gives only today's buildings, and
Wayback dates are sparse. Google's Open Buildings 2.5D Temporal gives **annual building presence 2016–2023** (Sentinel-2 based,
4 m effective resolution, 0.5 m pixels). Measure how building cover beside each channel changed year by year, against a
city-wide baseline.

## Access (verified 2026-10-17: public, anonymous, no Earth Engine)
- Bucket `open-buildings-temporal-data`. Manifests: `https://storage.googleapis.com/open-buildings-temporal-data/v1/manifests/<s2token>_EPSG_32631_<YYYY>_06_30.json`
  (Lagos is UTM 31N; tokens `11` and `13` exist for 32631; Alpha Beach is in token `11`). Each manifest has `uriPrefix`
  and `tilesets[].sources[]` with `uris`, `affineTransform` (0.5 m, translateX/Y = UL corner in EPSG:32631) and 25000×25000 dims.
- **URL gotcha:** concatenate `uriPrefix` and the uri **without** a slash: prefix `gs://…/v1/geotiffs/1` + `03bc_2023_06_30/tile_q4BO4L-hR04.tif`
  → `https://storage.googleapis.com/open-buildings-temporal-data/v1/geotiffs/103bc_2023_06_30/tile_q4BO4L-hR04.tif`.
- Tiles are ~520 MB tiled COGs (512 blocks, overviews), so **never download a tile**. Read windows with rasterio `/vsicurl/` and
  `GDAL_DISABLE_READDIR_ON_OPEN=EMPTY_DIR`. A 500 m window takes ~1.3 s.
- Bands: `building_fractional_count`, `building_height` (m), `building_presence` (0–1, **uncalibrated** model confidence, so
  use a threshold, not a probability). Licence CC BY 4.0 or ODbL 1.0; cite Sirko et al. 2023 (arXiv 2310.11622).

## Do (`pipeline/channel_encroachment.py`)
1. **Channels.** Use mapped channel lines, not road lines: OSM `waterway=drain|canal|stream|ditch|river` within each site's
   300 m radius (Task 18's `events/drainage_sites/<site>/osm.geojson` or a fresh Overpass query), plus the `geometry` in
   `events/drainage_sites.json` **only if** that site's `structure_name` is a channel and `location_confidence` isn't `not_found`
   (Cursor is re-locating oko-oba-canal, sangotedo and labora in Task 19; use the updated file). Sites with no channel line: skip
   them and list them.
2. **Bands** in UTM 31N: 0–10 m, 10–20 m and 20–50 m from the channel centreline, clipped to the site's 300 m radius.
3. **Per year 2016–2023**, per band: built fraction = share of pixels with `building_presence` ≥ 0.5 (also report 0.4 and 0.6 as a
   sensitivity check), resampled to 4 m effective before thresholding (block-mean of 8×8 at 0.5 m, then threshold). To suppress
   flicker, count a 4 m cell as **newly built in year t** only if it's built in t and t+1 and not built in t−1 and t−2.
4. **City-wide baseline.** All OSM waterways in the AOI `[2.6, 6.28, 4.45, 6.85]` (the Overpass extract you have or one query),
   sampled as 200 random 300 m segments **not** within 1 km of any named site. Compute the same band series. This is the
   control: is building beside the blamed channels faster than beside channels in general?
5. **Validation (required before interpreting).** For 3 sites, compare the 2023 ≥ 0.5 mask with OSM building footprints
   (precision/recall at 4 m), and visually with the latest Wayback chip in `events/drainage_sites/<site>/`. Save the overlay PNGs.
6. **Outputs:** `events/drainage_sites_buildings.json` (meta: source, licence, thresholds, method; per site and baseline: per band, per
   year built fraction and newly built area m²; validation scores), `events/drainage_sites/<site>/ob_timeline.png` (built
   fraction by year per band, flood dates marked, baseline median and IQR shaded) and `ob_<year>.png` presence masks over the
   site (2016, 2019, 2023; small). Print a table: site, 0–10 m built 2016 → 2023, newly built m² by year, baseline comparison.

Keep caches under `pipeline/cache/open_buildings/` (small arrays only) and delete them at the end with `find … -type f -delete`.
No `rm -rf`. Run in the foreground. No background processes. Don't touch `src/` or event folders other than `events/drainage_sites/`.
Don't commit. Interpret cautiously: 4 m effective resolution means the 0–10 m band is 2–3 cells wide, so read trends, not exact
counts.
