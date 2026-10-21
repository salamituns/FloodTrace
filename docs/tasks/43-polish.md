# Task 43: polish for the area panel, search and week strip

Review of Tasks 39, 39b and 41. All of these work. These are the rough edges I found in the browser.

## 1. News links in the area panel (`AreaPanel.tsx`)
- **One link per report.** Surulere currently shows 16 links, with Punch and Premium Times repeated.
  - Dedupe by URL.
  - Show each link as "Publisher, date", e.g. "Punch, 13 Jul 2026", newest first.
  - Show at most 4, then a "+N more" toggle.
- **Normalise publisher names.** One name per outlet:
  - "The Guardian Nigeria" and "Guardian NG" → **Guardian NG**;
  - "Channels Television" and "Channels TV" → **Channels TV**.

  Do it in the pipeline (`build_flood_spots.py`), so the data is clean too.
- **Link style.** The links currently use the browser's default blue underline. Use the app's existing link style: look for `.link` / `var(--accent)` in the styles. The quoted depth phrase ("Knee-deep") should look like a quote with a source, not a bare link.

## 2. Depth matching on word boundaries (`build_flood_spots.py`)
"Knee-deep flooding in parts of Gbagada, Ipaja and Surulere" also put the depth on the **Iyana Ipaja** spot. Iyana Ipaja is a separate place.
- Match the area name as a whole phrase.
- A spot whose name is *longer* than what the sentence says doesn't match. The reverse is fine: "Ipaja" may match a sentence that says "Iyana Ipaja".

Rerun, and list the placed depths again.

## 3. Duplicate search results (`build_search_index.py` / `PlaceSearch.tsx`)
For example, "Ojuelegba Road bridge" appears twice. Collapse entries with the same normalised name and kind that lie within 300 m of each other. Keep the one with the most detail.

## 4. WeekStrip at panel width (`WeekStrip.tsx`, `forecast.css`)
In the 360 px panel, each tile wraps "40 mm+: 2% chance" onto 4 lines.
- Show just "2%" in the tile.
- Add one caption under the strip: "% = chance of 40 mm or more that day".
- Keep the text level label next to the shape.
- Check that it fits at 320 px.

## 5. Licence footnote (`ForecastCard.tsx` footnote only)
"CC BY 4.0 (attribution required)" is repeated. Collapse the licences into one tidy line per source, e.g.:

> "ECMWF IFS © ECMWF, GFS © NOAA, GloFAS © Copernicus CEMS, all CC BY 4.0 via Open-Meteo; NASA IMERG open data; news reports compiled by FloodTrace."

Droid will add one sentence under this footnote in Task 42, so touch only the licence line.

## Check
- `npx tsc --noEmit`, `npm run build` and `npx tsx scripts/check-watchlist.ts` all pass.
- `npx tsx scripts/probe-search.ts` shows no duplicates for "ojuelegba".
- Report the counts before and after for: search entries, links per spot (max and median), and placed depths.

## Rules
- Foreground only.
- No `rm -rf`.
- Don't commit.
- Don't read `.env`.
- Don't start a dev server or open a browser.
- Droid is working on Tasks 40b and 42 in `MapView.tsx`, `Map3DWater.tsx`, `LayersPanel.tsx`, `store.ts`, `impacts.ts` and the `ForecastCard.tsx` hindcast line. Don't touch those, except the footnote licence line.
