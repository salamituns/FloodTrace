# Task 20 — Sentinel-2 monthly timelines to date the change at each drainage site

Context: `docs/LAGOS_PLAN.md` → "Street-level drainage check". Wayback imagery (Task 18) is sparse in time: Alpha Beach has nothing
between 2020-04 and 2024-11, and there's nothing after the 2025-08-04 flood for Ikorodu/Ijede/Agric. Sentinel-2 (10 m, ~5-day
revisit) can't show a drain, but it can date **vegetation clearing, sand-filling, earthworks and new roofs** at site scale.

## Data (open, no login)
Sentinel-2 L2A COGs via the Element84 Earth Search STAC (`https://earth-search.aws.element84.com/v1`, collection
`sentinel-2-l2a`). Use ranged COG reads (windowed, only the site bbox): bands B02, B03, B04, B08, B11 and SCL. Don't download
whole tiles. Cache only small per-site arrays under `pipeline/cache/s2_sites/` and delete them at the end. Disk is tight (~11 GB).

## Do (`pipeline/site_s2_timeline.py`, sites from `events/drainage_sites.json`)
1. **Area of interest per site**: point → 300 m buffer; line → 100 m buffer. For **alpha-beach-156**, also a separate polygon over
   the south-end cleared area: take the geometry's southern 600 m with a 250 m buffer, and say what you used.
2. **2018-01 → today**, all scenes with < 60% cloud over the tile. Mask with SCL (keep classes 4, 5, 6 and 7; drop clouds, shadow,
   cirrus and snow). Keep a scene for a site only if ≥ 70% of its AOI pixels are clear.
3. Per kept scene: median NDVI, median bare-soil index (BSI = ((B11+B04)−(B08+B02))/((B11+B04)+(B08+B02))), NDWI, and the
   fraction of pixels with NDVI > 0.4 (vegetated). Then aggregate to **monthly medians** (n scenes per month recorded).
4. **Change dating**: per site, find the largest sustained step in vegetated fraction or BSI (e.g. a simple two-segment fit or
   a CUSUM on the monthly series) and report the month, step size and how many clear months support each side. Report the step
   relative to that site's flood date: before or after the event. Don't over-claim: if no step stands out, say "no clear change".
5. **Image chips**: per site, true-colour chips (B04/B03/B02, 2–98% stretch, 10 m, AOI + 200 m) for the clearest scene closest to:
   1 Jan of each year, 1 month before the flood, 1 month after the flood, and the step month ±2 months.
   Save as `events/drainage_sites/<site_id>/s2_<date>.jpg`, plus `s2_timeline.png` (monthly vegetated fraction and BSI with the
   flood date and step marked). Keep the total under ~25 MB.

## Output
`events/drainage_sites_s2.json`: `meta` (source, licence "Copernicus Sentinel data <years>", method, thresholds) plus, per site,
the monthly series, step result and chip list. Print a table: site, clear months, step month, step direction/size, before/after
flood. Don't touch `src/` or event folders other than `events/drainage_sites/`. Run in the foreground (chunk per site if long).
No `rm -rf`: delete cache files individually or with `find <dir> -type f -delete`. No background processes. Don't commit.
