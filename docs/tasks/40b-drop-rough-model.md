# Task 40b: drop the rough model from the app

Review of Task 40. The 3D buildings, the evidence water and "Show me in 3D" work well, and they stay.

## Why
Your own validation in `events/rough_model/meta.json` shows the rough model matches reported floods **no better than chance**:
- 20–80 mm: 2.2% of the spots are hit, against a 4–5% random baseline.
- 100 and 150 mm: 45–48%, against 44–45%.

The jump at 100 mm happens because nearly all low ground near the lagoon turns wet at once. The user has decided to drop the layer, so 3D shows reported floods only.

## Do
1. **Remove the layer from the app:**
   - the "Rough model (low ground)" toggle, the scenario slider, the banner and its key entry;
   - the `waterModel` layer in `store.ts`;
   - the PNG overlay code in `Map3DWater.tsx` / `MapView.tsx`.
2. **`impactsAt`:** remove the `'model'` source, keeping `'evidence'` only. Its callers (`ForecastCard.tsx`, `AreaPanel.tsx`) already pass `'evidence'`; check that, and change only the call if it doesn't.
3. **Data:**
   - Delete the scenario PNGs and any file that only the model used, with `find events/rough_model -name 'scenario_*.png' -type f -delete` (and likewise for others).
   - Keep the files the evidence impacts still need, such as `roads.json` and `building_counts.json`. If they live under `rough_model/`, that's fine.
   - Keep `meta.json` as the record of the negative result.
4. **Keep `pipeline/rough_model.py`.** Add a header comment saying the layer was dropped on 21 Oct 2026 because its validation was no better than chance, and pointing to `meta.json`.
5. **Write the result down.** Add a short paragraph to `docs/FORECAST.md` (or a new `docs/ROUGH_MODEL.md`) with the validation table, in plain words.

## Check
- `npx tsc --noEmit`, `npm run build` and `npx tsx scripts/check-watchlist.ts` all pass.
- `grep -rn "waterModel\|Rough model\|scenario_" src` returns nothing.
- Report the files removed and the new size of `events/rough_model/`.

## Rules
- Foreground only.
- No `rm -rf`.
- Don't commit.
- Don't read `.env`.
- Don't start a dev server or open a browser.
- Cursor is working on Task 43 in `AreaPanel.tsx`, `PlaceSearch.tsx`, `WeekStrip.tsx` and the search/flood-spot builders, so don't touch those beyond step 2.

When this is done, go straight on to `docs/tasks/42-forecast-scoring.md`.
