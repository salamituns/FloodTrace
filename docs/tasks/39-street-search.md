# Task 39: street search and "Your area" (flood risk, part 2)

Read `docs/design/WORDS.md` first. The audience is residents and journalists, and the first question here is **"what about my street?"**

## Why
Today a visitor has to know our 13 place names to find anything. Instead, they should be able to type their street, estate or landmark and get an answer about their area:
- has it flooded nearby, when, and what happened;
- which nearby spots flood;
- what is coming. This last part is a slot for now; Task 41 fills it from the forecast that Droid is building in parallel (Task 38).

## Files you own
- New: `pipeline/build_search_index.py`, and its output `events/search_index.json`.
- New: `pipeline/build_flood_spots.py`, and its output `events/flood_spots.json` (section B).
- New UI files:
  - `src/components/PlaceSearch.tsx`;
  - `src/components/AreaPanel.tsx`;
  - `src/lib/area.ts`;
  - `src/styles/area.css`.
- Light edits to `TopBar.tsx`, `App.tsx`, `state/store.ts` (a new selection state, and the URL hash `#area=<lon>,<lat>,<label>`) and `MapView.tsx` (the area pin, the radius ring and the flood-spot dots).
- Don't touch `pipeline/forecast.py` or `events/forecast/`; those belong to Droid.

## A. Search index (pipeline, runs offline)
Fetch named features inside the AOI bbox `[2.7, 6.38, 4.35, 6.75]` from OpenStreetMap through the public Overpass API, in one or a few polite queries cached under `pipeline/cache/osm/`. Fetch:
- named highways (streets);
- `place` = suburb, neighbourhood, quarter, village or town;
- landmarks: bus stations, markets, schools, hospitals and clinics, places of worship, malls, bridges, estates (`landuse=residential` with a name).

**Build** `events/search_index.json`, as small as possible:
- Merge street segments that share a name, keeping a centroid and a bbox.
- Store the name, any alt names, the kind, the containing area (nearest suburb or neighbourhood, to tell duplicates apart, e.g. "Allen Avenue, Ikeja"), and lon/lat.
- Report the size. The target is under 1.5 MB gzipped. If it is larger, drop the least useful kinds and say so.

**Also save** the school, clinic/hospital, market and bus-station points to `events/osm_facilities.geojson`. Task 41 will use them to list what's affected.

**Licence:** credit "© OpenStreetMap contributors (ODbL)" in `meta`.

**Privacy:** search runs entirely in the browser against this file. **No search text ever leaves the device.**

## B. Flood spots (pipeline)
`events/flood_days.json` already holds about 840 geocoded areas across 87 flood days. Turn them into `events/flood_spots.json`:
- **Cluster** mentions within about 300 m that share a name, or are near-identical.
- **Per spot:** the name, lon/lat, the geocode `confidence` (street / area / city), the list of dates, the count, the latest date, and the report URLs and publishers (from `events/intake/reports_*.json`, matched by date and area name).
- **Depth words.** Keep any depth wording found in those reports' `impacts` or `quote` text, e.g. "knee-deep", "waist-high", or a number in feet, inches or metres. Map it to a rough depth in metres, record the mapping table in `meta`, and keep the source phrase word for word.
- **Exclude** `city`-confidence mentions (e.g. just "Lagos" or "Ikeja" as a whole city); they can't place a spot. Report how many you dropped.

## C. UI
1. **Search box** in the top bar, visible in both modes. Its placeholder is "Search your street or area".
   - Matching is typo-tolerant, prefix-first and runs in the browser. Show at most 8 results, with the name, kind and containing area.
   - Keyboard: ↑, ↓, Enter, Esc. Screen-reader friendly: combobox/listbox roles.
   - On a phone, it opens full width.
2. **Choosing a result:**
   - drops a pin;
   - draws a 1.5 km ring, labelled "Your area (1.5 km)";
   - flies the map there;
   - opens `AreaPanel` in the side panel, as its own state: it is not a site page and not a mode;
   - updates the URL to `#area=…`, so the link can be shared.
   - Users can also tap or right-click the map and choose "Check this spot" to do the same.
3. **AreaPanel**, answer first:
   - **Heading:** the searched name, plus "within 1.5 km".
   - **Coming up** card: a placeholder that says "Forecast coming soon". Make it a clear slot, `<ForecastSlot lon lat />`, that renders nothing else for now.
   - **Has it flooded here?** If yes: "Yes: N flood days reported nearby since 2014; last <date>". Then the spots inside the ring, nearest first, each with its distance, dates, any depth phrase (quoted, with the source link), and a link to its news reports. If there are none: "No floods reported within 1.5 km since 2014. That isn't proof it's safe: news covers some areas far more than others."
   - **Places we track nearby:** our watch-list places within 3 km, with their priority badge. Clicking one opens the place page.
   - **Rain here:** one line from the IMERG history for the cell: "Heavy rain (40 mm or more in a day) hits this area about N times a year." Compute it from `rain_history_grid_daily.json` in a small precomputed file, or in `area.ts` if that stays fast.
   - **Back** returns to wherever the user came from.
4. **Map:** draw flood spots as small red dots, sized by count, when the area panel is open. Hovering or tapping a spot shows its name and dates. Keep them separate from the place markers, and add them to the map key.

## Check
- `npx tsc --noEmit`, `npm run build` and `npx tsx scripts/check-watchlist.ts` all pass.
- Report:
  - the index size and the feature counts by kind;
  - the flood-spot count, the clusters, and the dropped city-level mentions;
  - the number of spots that have depth phrases, listed with phrase → metres.
- Run these searches in a throwaway node or tsx script against the index, and report the top 3 results for each: "Agungi", "allen avenue", "lekki phase 1", "ojuelegba", "Yaba bus stop", "ikorodu road".
- **Do not start a dev server or open a browser.** I check the UI myself. (Last time a dev server was left running on port 5174, so don't repeat that.)

## Rules
- Foreground only.
- No `rm -rf`.
- Don't commit.
- No credentials are needed. Don't read `.env`.
