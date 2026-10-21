# Task 41: the forecast on screen: when, where, what to do (flood risk, part 4)

Read `docs/design/WORDS.md` first. Tasks 38 (forecast pipeline), 39/39b (search, flood spots) and 40 (3D, `impactsAt`) have landed, so read their outputs first:
- `events/forecast/latest.json`, and the rules in its `meta`;
- `events/flood_spots.json`;
- `src/lib/impacts.ts`.

## Why
A resident should be able to open FloodTrace, find their street, and learn in 10 seconds:
- **when** heavy rain is coming;
- whether storms like it flooded **near them** before;
- **what** got hit last time;
- **what to do**.

A journalist should see this week's citywide picture at a glance.

## Files you own
- New: `src/components/ForecastCard.tsx`, `src/components/WeekStrip.tsx`, `src/lib/forecast.ts` and `src/styles/forecast.css`.
- Edit:
  - `AreaPanel.tsx`: replace the `ForecastSlot` placeholder;
  - `WatchList.tsx`: add a "This week" card at the top;
  - `MapView.tsx`: a forecast layer;
  - `store.ts`: forecast state;
  - `pipeline/forecast.py` and its schema, for the hourly export in section E only.

## A. Load and freshness
- `src/lib/forecast.ts` loads `events/forecast/latest.json` once and finds the cell containing a lon/lat. IMERG cells are 0.1° and are centred at x.x5.
- Always show "Forecast made <day, time> (Lagos time)". If the run is more than 36 hours old, show an amber note instead: "This forecast is out of date (made <date>)". Then show levels in grey, not colour.
- If `latest.json` is missing, show nothing forecast-related, with no error banner. History still works.

## B. "Coming up" card in AreaPanel (replaces the placeholder)
1. **Headline** in one plain sentence, from the worst day in the next 7:
   - "Heavy rain likely **Thursday afternoon (14:00–19:00)**, close to high tide." or
   - "No heavy rain expected in the next 7 days."

   Build it from `level`, the risk `hours`, `near_high_tide` and `peak_3h`. Never print a number the data doesn't have.
2. **WeekStrip:** 7 small day tiles, each showing the day name, a level badge (same shapes and colours as the priority badges, with a text label too), and "40 mm+: N% chance". Tapping a tile selects that day.
3. **For a medium or high day:**
   - **Past storms like this here:** "Of 41 past days with similar rain here, 7 had floods reported within 5 km." Use `n_qualifying_flood_days` (local), **not** the citywide count. Then up to 3 analogue days: the date, the mm, and the area names reported.
   - **"Show me last time"** button on the top analogue. It highlights that day's flood spots on the map and opens 3D via Task 40's "Show me in 3D" camera. If the analogue day is a mapped flood (`events/lagos-*`), also offer "Replay this flood →".
   - **What got hit last time**, from `impactsAt(lon, lat, 1500, 'evidence')`: the roads, facilities and building count, in words. For example: "Roads under water last time: Ikorodu Road, Fashoro Street. Near a school: …".
4. **What to do.** A short checklist that changes with the level. Use widely accepted safety advice only:
   - **high:** move valuables and documents off the floor before <window start>; avoid <roads hit last time> during the window; don't walk or drive through flood water ("you can't see how deep it is or what is under it"); check on neighbours who may need help;
   - **medium:** a shorter version;
   - **low / none:** a single line: "No action needed. Check again before the weekend."

   Add Lagos emergency contacts **only** if you can confirm them from an official Lagos State or LASEMA page. Cite the page in a code comment and in your report. If you can't confirm them, leave them out.
5. **Footnote:** "Rain forecast: ECMWF ensemble via Open-Meteo. Tides: EOT20. Reported floods undercount real floods, so 'no floods reported' is not proof it's safe." Include licences as `meta` says.

## C. "This week" card at the top of the Places list
- **Headline:** the citywide level for the worst day, plus the areas most at risk. Use `citywide.days[].most_at_risk[].place` names, deduplicated.
- **The WeekStrip** for the city: the worst level per day.
- **"Check your street →"** focuses the search box.
- On a quiet week, keep it to one line: "No heavy rain expected in Lagos in the next 7 days (forecast made …)". Don't take space from the list.

## D. Map: forecast layer (Places mode)
- When a day is selected in either WeekStrip, colour the 68 cells by that day's level:
  - translucent fill, using the same palette as the badges, with `none` drawn transparent;
  - a key entry "Forecast: <day>".
- Hovering or tapping a cell shows the median mm, the chance of 40 mm or more, and the risk hours.
- Off by default. It is on while a day is selected, and "Clear" turns it off.

## E. Pipeline: hourly export (small)
- In `pipeline/forecast.py`, add to each cell an `hourly` block: the member-median mm/h for each of the 168 hours, plus the 90th percentile, rounded to 0.1. Keep the output under 600 KB.
- Update the schema, then rerun.
- Use it in the UI for a **"Play the next 48 hours"** control in the selected-day view. It animates the cell colours hour by hour (median), with a time label and the high-tide marks. Respect `prefers-reduced-motion`.

## Check
- `npx tsc --noEmit`, `npm run build` and `npx tsx scripts/check-watchlist.ts` all pass.
- The forecast output validates against the schema after the rerun.
- **This week is quiet**: every cell-day is `none`. To test the medium/high paths, write a throwaway fixture `events/forecast/_fixture_storm.json`:
  - copy `latest.json`;
  - set a few cells around Ojuelegba (c6.55N3.35E) and Agungi to `high`, with plausible numbers and analogues produced by calling `find_analogues` from the pipeline;
  - load it with `?forecast=fixture` (dev builds only; guard it with `import.meta.env.DEV`).

  Report what the card says for Ojuelegba and Agungi under the fixture. **Delete the fixture** with `find … -type f -delete` before finishing, and confirm that `?forecast=fixture` is a no-op in production builds.
- Report every new user-facing string.
- **Don't start a dev server or open a browser.** I check the UI.

## Rules
- Foreground only.
- No `rm -rf`.
- Don't commit.
- Don't read `.env`.
