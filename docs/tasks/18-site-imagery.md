# Task 18 — dated before/after imagery and OSM context for the blamed drainage sites

Context: `docs/LAGOS_PLAN.md`, `docs/tasks/17-drainage-sites.md`. Cursor is writing `events/drainage_sites.json` (one entry per
site: geometry, image_windows) in parallel. Build the tool now; test it on the provisional sites below. When
`drainage_sites.json` appears and has a `sites` array, run on it too. You produce imagery and measurements; **don't interpret what
changed** (I'll do that).

Provisional sites (lon, lat): alpha-beach-156 3.515 6.430 · agungi-collector 3.518 6.447 · olopomeji 3.399 6.548 ·
oko-oba-canal 3.322 6.637 · alapere-ogudu 3.392 6.592 · ikorodu 3.504 6.619 · ijede 3.592 6.566 · sangotedo 3.636 6.471.

## Imagery: Esri World Imagery Wayback (public, no login)
- Releases list: `https://s3-us-west-2.amazonaws.com/config.maptiles.arcgis.com/waybackconfig.json`. Tiles: the WMTS
  `.../World_Imagery/WMTS/1.0.0/default028mm/MapServer/tile/{releaseNum}/{z}/{y}/{x}`.
- **Release date ≠ acquisition date.** For each release, query that release's metadata layer at the site point to get the
  real **acquisition date**, source and resolution. Many releases reuse the same local image: dedupe by acquisition date.
- Per site, write a chip around the geometry (point: 500 × 500 m; line: its bbox + 150 m), zoom 18 (or 17 if 18 is missing),
  mosaicked from tiles, as JPEG q85, for **every distinct acquisition date** (cap at 10 per site, spread across the years,
  always including the closest dates either side of the event and of each `image_windows` bound).
  Path: `events/drainage_sites/<site_id>/<acq-date>.jpg`. Draw the site geometry as a thin outline on a copy
  `<acq-date>_marked.jpg`. Also one `contact_sheet.jpg` per site (all dates, labelled with acquisition date, ≤ 2500 px wide).
- Throttle (≤ 4 req/s), cache tiles under `pipeline/cache/wayback/` and delete the tile cache at the end. Disk is tight (~11 GB):
  keep the total under ~60 MB.
- Attribution in meta: "Esri World Imagery Wayback; imagery © Esri, Maxar, Earthstar Geographics and the GIS User Community".

## OSM context (per site, current data via Overpass, one query per site)
Within 300 m of the geometry: waterways and drains (`waterway=drain|canal|stream|river|ditch`, `culvert`), and buildings.
Report: drain length, number of buildings and their footprint area **within 5, 10 and 20 m of a mapped drain/canal** (setback
proxy; say clearly this is not the legal setback), and any `bridge`/`construction` ways. Save `events/drainage_sites/<site_id>/osm.geojson`.

## Output
`pipeline/site_imagery.py` (args: sites file or the built-in provisional list), and `events/drainage_sites_imagery.json`:
per site → list of `{acq_date, release, source, resolution_m, file, marked_file}`, the OSM measurements, and gaps (no imagery
near the event, cloud, etc.). Print a table: site, n dates, nearest dates before/after the event, drains m, buildings ≤ 10 m.
Don't touch `src/` or event folders other than `events/drainage_sites/`. No stray background processes. Don't commit.
