# Task 38: daily forecast pipeline (flood risk, part 1)

## Why
FloodTrace is becoming a flood-risk tool. People want to know **when** flooding will hit their area, **where**, and **what it will affect**, so they can plan. This task builds the data behind that: a 7-day forecast, fetched once a day, archived, and turned into risk windows for each 0.1° cell. A later task (41) builds the UI on top of it, and another (42) scores old forecasts against what actually fell. Read `docs/design/WORDS.md` for the plain words.

We do **not** run a weather model. We take published forecasts and combine them with our own history.

## Files you own
- New: `pipeline/forecast.py`.
- New: `pipeline/schemas/forecast.schema.json`.
- New output directory: `events/forecast/`.
- You may import helpers from `pipeline/tide_eot20.py` and `pipeline/storm_replay.py`. Don't change their behaviour.
- Don't touch `src/`. Cursor is working there in parallel.

## Inputs
**Cells.** Use the IMERG 0.1° cell ids and centres from `events/rain_history_grid_daily.json`. There are 68 cells (`series` keys such as `c6.45N3.35E`).

**Rain forecast.** Open-Meteo Ensemble API (free, no key, CC BY 4.0):
- endpoint: `https://ensemble-api.open-meteo.com/v1/ensemble`;
- parameters: `hourly=precipitation`, `models=ecmwf_ifs025`, `forecast_days=7`, `timezone=Africa/Lagos`;
- this returns a control run plus 50 members per point.
- Use the multi-coordinate form (comma-separated `latitude`/`longitude`) if it works; otherwise make one call per cell.
- Also fetch `models=gfs025` as a second opinion. Store it, but base the headline numbers on ECMWF.
- Stay far under the free limit: no more than a few hundred calls per run.
- Cache raw responses under `pipeline/cache/forecast/<run-date>/`.

**Tide.** Run the EOT20 astronomical tide forward over the same 7 days at the offshore tide point used by the events (`aoi.points.offshore_tide` in any `events/lagos-*/event.json`). List the high tides with their times and heights.

**Rivers.** Use the Open-Meteo Flood API (GloFAS): `https://flood-api.open-meteo.com/v1/flood`.
- Fetch `daily=river_discharge` with `ensemble=true` for the Ogun near Isheri/Kara (about 6.62N 3.38E) and the Osun/Owo outlet near Ikorodu. Choose the points so they snap to the real river cells, and record the snapped coordinates.
- Also fetch the historical record from the same API (it goes back to 1984). From that, compute what flow counts as unusual: the 90th and 99th percentiles of daily flow.

**History** (all in `events/`):
- `rain_history_grid_daily.json`;
- `flood_days.json` (days, with geocoded `areas`);
- `site_rain_summary.json`;
- `sites.json`.

## What to compute
For each cell and each day of the forecast (Lagos time):
1. **Rain amounts:**
   - the ensemble median for the 24 hours;
   - the 90th percentile;
   - the chance of at least 20, 40 and 60 mm in 24 hours, as the share of members.
   - **40 mm is the history threshold used in `storm_replay.py`. Keep it.**
   - For each day, the peak 3-hour window: the start hour, and the median and 90th-percentile mm.
2. **Risk window** for each cell and day. It is the hours when:
   - the member-median rain rate is high, **or**
   - at least 30% of members exceed the hourly threshold you choose. Document the threshold and justify it from the IMERG history: what hourly rate preceded the reported flood days?

   Flag `near_high_tide` if the window overlaps ±2 h of a high tide.
3. **Plain risk level** per cell and day: `high | medium | low | none`. Use a rule you write down in the script and the output's `meta`, based on the chance of heavy rain and on how often this cell's past storms of that size were followed by reported floods. Keep it simple and explainable in one sentence for the UI.
4. **Past storms like this (analogues).** For each cell-day at medium or above:
   - find up to 5 past days (IMERG, 2014 onwards, when news was searched) whose 24-hour total at that cell is within ±25% of the forecast median, and ≥ 20 mm;
   - prefer days that are in `flood_days.json`. For each one, record the date, the IMERG mm, whether it is a reported flood day, and the reported flood `areas` within 5 km of the cell centre (name, lon, lat);
   - also record: of all qualifying analogue days, how many were reported flood days.
5. **Rivers:** daily median and 90th-percentile flow per point, and a flag for days whose median is at or above the historical 90th or 99th percentile.

## Output
**`events/forecast/<run-date>.json`.** Validate it against the schema. It contains:
- `meta`: run time; sources with URLs and licences; model names; the thresholds and rules; and the caveats in plain words. One caveat must say that reported floods undercount real floods.
- `tides`;
- `rivers`;
- `cells`: per cell id, the centre and the per-day blocks above;
- `citywide`: per day, the most-at-risk cells and the overall level.

**Also write:**
- `events/forecast/latest.json`, a copy of the newest run;
- `events/forecast/index.json`, the list of archived runs.

**Archive rule:** never overwrite an earlier run-date file. If you rerun on the same day, append a time suffix.

## Daily run
- Add a usage block at the top of the script.
- Add a short `docs/FORECAST.md` saying how to run it daily, e.g. one cron line the user can choose to install. **Do not install a cron job or any background process yourself.**

## Check
- Run it once for today. Report:
  - the number of cells;
  - the 3 riskiest cell-days, with their analogues;
  - the next 4 high tides;
  - the river flags.
- Validate the output against the schema.
- Spot-check one cell by hand: refetch it with curl and recompute its chance of ≥ 40 mm. It should match.
- Python only. Use the existing `pipeline/.venv`, and don't add a package unless it is truly needed. If you do add one, say which and why.

## Rules
- Foreground only. No background processes.
- No `rm -rf`; delete with `find … -type f -delete`.
- Don't commit.
- These APIs need no credentials. **Don't** read `.env`.
