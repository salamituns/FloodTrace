# Task 01 — open-data fetch script for an event package

Read `docs/LAGOS_PLAN.md` and `events/lagos-2024-07-03/event.json` first.

Write `pipeline/fetch_open_data.py`: `python3 pipeline/fetch_open_data.py events/lagos-2024-07-03`
reads `event.json` and writes these files into the same event folder. **Python 3 standard library only**
(urllib, json, datetime) — no pip installs. No API keys or logins are needed for any of these endpoints.

1. `tide.json` — Open-Meteo Marine API, hourly `sea_level_height_msl` at `aoi.points.offshore_tide`, over `window`,
   timezone from `event.json`. https://marine-api.open-meteo.com/v1/marine
2. `rainfall_reanalysis.json` — Open-Meteo Archive API, hourly `precipitation` at **each** `aoi.points` entry except
   `offshore_tide`, over `window`. https://archive-api.open-meteo.com/v1/archive
   Mark it clearly in the file: `"product": "ERA5 reanalysis via Open-Meteo", "note": "smooths convective bursts; context only, not event intensity"`.
3. `satellite_passes.json` — Copernicus Data Space OData catalogue
   (https://catalogue.dataspace.copernicus.eu/odata/v1/Products), products intersecting the AOI bbox polygon within
   `window` ± 14 days: Sentinel-1 `GRDH` (skip names ending `_COG.SAFE`) and Sentinel-2 `L2A` with `cloudCover`
   (use `$expand=Attributes`). Record name, acquisition start (UTC + local), platform, relative orbit/track if parseable,
   cloud cover for S2. Page through results with `$skip` if more than `$top`.
4. `drainage_osm.geojson` — Overpass API (https://overpass-api.de/api/interpreter), within AOI bbox:
   `way["waterway"~"canal|drain|ditch|stream|river"]` and `way["natural"="water"]["water"~"lagoon|canal"]`,
   output as GeoJSON LineStrings/Polygons with `waterway`, `name`, `osm_id` properties. Use `out geom;`, timeout 180.

Every output file gets a top-level `"meta"`: source URL (with query), retrieved_at (UTC ISO), units, licence
(Open-Meteo: CC BY 4.0; Copernicus: free/open; OSM: ODbL).

Also:
- Be polite to the APIs: one request at a time, a User-Agent `FloodTrace/0.1 (research)`, retry 3× with backoff on 429/5xx.
- Print a short summary at the end: files written, record counts, any failures.
- Run it once for `events/lagos-2024-07-03` and make sure it succeeds. Don't modify anything under `src/`. Don't commit.
- Finish by printing the summary output.
