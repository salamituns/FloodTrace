# Task 40: 3D view: evidence water, rough-model water, what's hit (flood risk, part 3)

Read `docs/design/WORDS.md` first. Tasks 38 (forecast pipeline) and 39 (street search, flood spots) have landed, so read their outputs before starting. **Note:** Cursor is fixing depth attribution in `events/flood_spots.json` in parallel (Task 39b): depths will gain a `placed_by` field, and some will be removed. Do sections A and C first, read the depths for B last, and draw only depths that have `placed_by`. Cursor owns `build_flood_spots.py` and `AreaPanel.tsx`.

## Why
People plan better when they can **see** what a flood would look like on their street.

The user chose **"evidence first, plus a clearly labelled simulation layer"**. Two kinds of water must therefore never be confused:
- **Evidence water** comes from what was reported or seen.
- **Rough-model water** comes from terrain plus rain.

Our own test (`events/terrain/verdict.txt`) found that 30 m terrain only weakly predicts which spot floods. Flooded spots are about 2 cm lower than their surroundings, while the terrain data's error is about 2 m. The model layer must say so in plain words, wherever it is switched on.

## Files you own
- New: `pipeline/rough_model.py`, outputs under `events/rough_model/`, `src/components/Map3D*.ts(x)` if you split layers out, and `src/styles/map3d.css`.
- Edit: `MapView.tsx` (the 3D layers), `LayersPanel.tsx` / `store.ts` (layer toggles) and the map key.
- Don't touch the forecast pipeline (Task 38), `AreaPanel.tsx`, or the search files (Task 39), except to read their data.

## A. Buildings in 3D
- When 3D is on, extrude buildings from the basemap's own vector `building` layer (OpenFreeMap / OpenMapTiles schema, `render_height` / `render_min_height`; a default of 6 m where missing). Use a MapLibre `fill-extrusion` layer.
- Use a neutral light grey so water and red stand out.
- Fade buildings in from zoom 14 so the city view stays light.
- Report how much of Lagos has building outlines in these tiles. OSM coverage is patchy, so name two areas with good coverage and two with poor coverage.

## B. Evidence water (always the primary layer)
- From `events/flood_spots.json` (Task 39): for each spot with a depth phrase, draw a translucent water body:
  - radius by geocode confidence: about 120 m for a street, about 400 m for an area;
  - the surface raised by the reported depth × the same vertical exaggeration as the map. Use deck.gl `PolygonLayer` or `SolidPolygonLayer`, extruded, blue, about 50% opacity.
- Spots without a depth phrase: a flat blue disc with a dashed edge, meaning "flooded, depth not reported".
- Show the 2024 radar flood map (`events/lagos-2024-07-03/sar/flood.geojson`) the same blue, labelled "Seen by radar satellite, 3 Jul 2024".
- **Hover or tap:** the spot name, dates, the depth phrase quoted word for word with its source, e.g. "'knee-deep' (Punch, 8 Jul 2022)".

## C. Rough-model water (secondary, off by default)
**Pipeline: `pipeline/rough_model.py`**
- Use FABDEM (`pipeline/cache/dem/fabdem_aoi.tif`), which is bare earth. Don't use GLO-30, which includes buildings.
- Use a simple, documented approach that fills low ground: height above nearest drainage (HAND) against the waterways and lagoon in `pipeline/cache/osm/`, plus local depression filling.
- For **excess rain** scenarios of 20, 40, 60, 80, 100 and 150 mm, estimate where water stands and roughly how deep. Excess rain means rain minus what drains away. Make drain capacity a stated parameter, e.g. 10 mm/h, so the reader can see the assumption.
- Clip to the built-up area, and keep only depths ≥ 10 cm.

**Output**
- For each scenario, a PNG overlay (depth-coloured, transparent where dry) plus its bounds, under `events/rough_model/`.
- `events/rough_model/meta.json`, containing:
  - the method, the parameters and the terrain verdict;
  - **a validation step**: score each scenario against the flood spots and the 2024 radar map. Of the evidence spots, how many fall in model-wet cells, compared with a random baseline of the same wet area? Report this honestly, even if it's poor.
- Keep the total under 15 MB. Crop to the urban core if needed, and say so.

**UI**
- A layer toggle "Rough model (low ground)", plus a scenario slider ("If 40 mm more rain falls than the drains can take").
- A visible banner while it is on: "Rough model: shows low ground where water could collect. It is not a measurement, and our tests found it only weakly matches real floods." Link it to the validation numbers.
- Different styling from evidence water: a cooler, lighter blue with a fine hatch or stipple, so a screenshot can never pass it off as a real flood.

## D. What's hit
- When evidence or model water is shown inside the user's area ring (Task 39) or in a place's view, highlight:
  - roads that pass through water (basemap `transportation` features where available; otherwise OSM highways from Task 39's cache);
  - facilities from `events/osm_facilities.geojson` inside the water;
  - buildings inside the water (count them, and tint them blue at the base).
- Expose a small function `impactsAt(lon, lat, radiusM, source: 'evidence' | 'model', scenario?)` in `src/lib/impacts.ts`. It returns:
  - roads: name, and length under water;
  - facilities: name, kind;
  - the building count.

  Task 41 will show these in plain words.

## E. Demo camera
Add a "Show me in 3D" button wherever water is shown:
- in AreaPanel, next to the Has-it-flooded card;
- on the place page.

It tilts to 3D, flies close, and slowly orbits once. Respect `prefers-reduced-motion`: no orbit, just tilt.

## Check
- `npx tsc --noEmit`, `npm run build` and `npx tsx scripts/check-watchlist.ts` all pass.
- Report:
  - the building coverage;
  - the rough-model validation table (scenario → hit rate compared with the random baseline);
  - the sizes of the files in `events/rough_model/`;
  - `impactsAt` results for Agungi, Ojuelegba and Ikorodu Road at Maryland.
- **Don't start a dev server or open a browser.** I check the UI.

## Rules
- Foreground only.
- No `rm -rf`.
- Don't commit.
- Don't read `.env`.
