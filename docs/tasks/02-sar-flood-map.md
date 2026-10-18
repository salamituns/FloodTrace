# Task 02 — Sentinel-1 flood map (before / during / after)

Context: `docs/LAGOS_PLAN.md`, `events/lagos-2024-07-03/dossier.md` (§2), `events/lagos-2024-07-03/event.json`.
Sentinel-1A track 95 imaged Lagos at 3 Jul 2024 05:30 UTC, during the flood. Analysis-ready, terrain-corrected (RTC)
scenes exist on Microsoft Planetary Computer — **no account needed** (anonymous signing via the `planetary-computer` package):

| role | STAC item id (collection `sentinel-1-rtc`) |
|---|---|
| pre (baseline) | `S1A_IW_GRDH_1SDV_20240621T053018_20240621T053047_054417_069F0A_rtc` |
| during | `S1A_IW_GRDH_1SDV_20240703T053017_20240703T053046_054592_06A521_rtc` |
| post | `S1A_IW_GRDH_1SDV_20240715T053017_20240715T053046_054767_06AB2E_rtc` |

STAC API: https://planetarycomputer.microsoft.com/api/stac/v1

## Setup
- Create a venv at `pipeline/.venv` (add `pipeline/.venv` to `.gitignore`) and install only what you need:
  `pystac-client planetary-computer rasterio numpy scipy shapely` (+ `matplotlib` for previews). Pin versions in `pipeline/requirements.txt`.

## Write `pipeline/sar_flood.py`
`pipeline/.venv/bin/python pipeline/sar_flood.py events/lagos-2024-07-03`

1. Read the three item ids above from a new `"sar"` block you add to `event.json`
   (`{"collection": "sentinel-1-rtc", "pre": "...", "during": "...", "post": "..."}`) so the script works for future events.
2. For each scene read the **VV** and **VH** assets windowed to the AOI bbox, resampled to a common **20 m** grid
   (UTM zone 31N, EPSG:32631). Use the same grid for all three. Convert linear → dB (guard zeros/nodata). Apply a 5×5 median filter for speckle.
3. Classify per pixel (VV unless noted):
   - `open_flood` — during < −16 dB **and** (during − pre) < −3 dB **and** pre ≥ −16 dB (was not water before).
   - `permanent_water` — pre < −16 dB **and** post < −16 dB (lagoon, sea, canals) — exclude from flooding.
   - `receded` — `open_flood` pixels where post ≥ −16 dB again.
   - `urban_flood_possible` — (during − pre) > +3 dB in VV where pre VV > −8 dB (bright built-up double-bounce increase). **Low confidence**; label it that way.
   Keep the thresholds as named constants at the top of the file and record them in the output metadata.
4. Outputs in `events/lagos-2024-07-03/sar/`:
   - `classes.tif` — uint8 Cloud-Optimized GeoTIFF (0 none, 1 permanent water, 2 open flood, 3 open flood receded by post, 4 urban flood possible) in EPSG:4326 or 32631 (say which).
   - `flood.geojson` — polygons for classes 2–4 (EPSG:4326), dissolved per class, simplified ~20 m, drop polygons < 0.5 ha; property `class`, `confidence` (`moderate` for 2/3, `low` for 4), `area_ha`.
   - `stats.json` — area (km²) per class for the whole AOI and within 2 km of each `aoi.points` entry; thresholds; item ids; acquisition times; `"meta"` with source + licence (Copernicus Sentinel data, free/open; processed by Planetary Computer RTC).
   - `preview_pre.png`, `preview_during.png`, `preview_classes.png` — quick-look images (VV dB greyscale; classes colour-coded with legend), ≤ 2000 px wide, AOI bbox.
5. Print a summary: areas per class, output paths, anything skipped.

## Rules
- Don't touch `src/`. Don't commit. Run it once end-to-end and make sure all outputs exist.
- If a read is slow, window reads to the bbox — never download whole scenes.
- If something in this spec turns out to be wrong (asset names, CRS, thresholds giving obviously nonsense results), say so in your summary rather than silently changing the method.
