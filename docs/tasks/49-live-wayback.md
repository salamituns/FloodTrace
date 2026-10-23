# Task 49: show Esri imagery live, and stop storing copies

## Why
The drainage-site before/after slider and the timeline show JPG crops of **Esri World Imagery Wayback**, saved in `events/drainage_sites/<site>/`. The files are:
- `YYYY-MM-DD.jpg` and `_marked.jpg`;
- `_detailN.jpg` and `_detailN_marked.jpg`;
- `contact_sheet.jpg`.

That imagery belongs to Esri and its providers (Maxar and others). The repo and the site are going public, and redistributing stored copies isn't allowed. A web page loading Esri's tiles directly, with Esri's credit line, is the normal permitted use. So:
- **in the app**, keep the same pictures, but fetch the tiles live from Esri in the visitor's browser;
- **in the repo**, store no Esri pixels at all.

Sentinel-2 (`s2_*`) and Open Buildings (`ob_*`) images are open data. Leave them alone.

## Do
1. **Pipeline (`pipeline/site_imagery.py`, and `pipeline/build_sites.py` if needed).** For every Wayback image and detail chip, record what a browser needs to draw it:
   - the Wayback `release` number;
   - the tile `zoom`;
   - the chip's lon/lat bounds (or its corners, if the chip is rotated or not north-up; check how `build_chip` works and keep the same framing);
   - the tile URL template (`release["tile_url"]` or equivalent);
   - `acq_date` and `resolution_m`, as today.

   **Storage:**
   - Keep that data in the same site records the app reads today (see `src/sites/types.ts`, `WaybackImage`). Add fields; don't move the data.
   - The site outline drawn on `_marked` chips must be available as geometry, so the app can draw it as an SVG overlay. It probably already is (`osm.geojson`, or the site geometry in `events/sites.json`); check.
   - Stop writing any Wayback-derived JPG into `events/`. If the pipeline itself needs chips for analysis (look at `channel_encroachment.py` and anything else that reads them), write them under `pipeline/cache/wayback/chips/` (gitignored) instead.
   - Use the cached identify responses (`pipeline/cache/wayback/meta/`) and `waybackconfig.json`. Fetching the public Wayback config is fine.
   - Regenerate the records.
   - Add a test that the pipeline output references no JPG under `events/drainage_sites/` except `s2_*` and `ob_*`.
2. **App.** Rebuild the before/after slider (`BeforeAfter` in `SitePanel.tsx`), the detail chips and anything in `SiteTimeline.tsx` that shows Wayback chips:
   - draw each image from live Wayback tiles;
   - a small grid of `<img>` tiles cropped to the chip bounds is the simplest choice;
   - a second map instance is also fine, if it stays light.

   **Requirements:**
   - The site outline is an SVG overlay, matching today's `_marked` look, with a toggle if one exists today.
   - Credit line under every Wayback image, exactly: "Imagery: Esri World Imagery Wayback (Esri, Maxar, Earthstar Geographics, and the GIS User Community)". Also add it to the map attribution when Wayback is shown.
   - **Loading and failure:** while tiles load, show a neutral placeholder. If they fail (offline, or Esri down), say "Imagery couldn't load" with a retry. Never show a broken image icon.
   - **Phones:** the tiles must load lazily, only when the slider is visible, and the slider must work by touch at 360 px.
3. **Delete the stored copies from the working tree.** Delete exactly the JPGs matching the patterns above under `events/drainage_sites/`, with `find … -type f -delete`. Then add a `.gitignore` rule so those patterns can't be committed again, keeping `s2_*` and `ob_*` allowed. Report the count and the bytes removed.
4. **Docs.** Add a line to `DATA_LICENSE.md` that Esri imagery is displayed live from Esri's service and not stored or redistributed.
   Also fix the FABDEM row: FABDEM is **CC BY-NC-SA 4.0**. List the files derived from it (the terrain maps under `events/terrain/` and anything else built from FABDEM), and say they carry that licence, not CC BY.

## Check
- `npx tsc --noEmit`, `npm run build`, `npx tsx scripts/check-watchlist.ts` and `npx tsx scripts/check-forecast.ts` all pass. So do the pipeline tests.
- `git ls-files events/drainage_sites | grep -E '\.jpg$' | grep -vE '/(s2_|ob_)'` prints nothing, once deletions are staged with `git add -A events/drainage_sites`. **Don't commit.**
- **Report:**
  - the new record fields, with one example;
  - which components changed;
  - how the tile URL is built.

  I will check it in a browser.

## Rules
- Foreground only.
- No `rm -rf`.
- Don't commit or push.
- Don't read `.env`.
- Don't start a dev server or open a browser.
- Don't touch `.github/`, `pipeline/forecast.py`, `pipeline/run_daily.py` or the IMERG scripts.
