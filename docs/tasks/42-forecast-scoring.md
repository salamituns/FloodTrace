# Task 42: how good is the forecast? (flood risk, part 5)

Read `docs/design/WORDS.md`, `docs/FORECAST.md` and the `meta` block of `events/forecast/latest.json` first.

## Why
A warning people can't check is a warning they stop trusting. FloodTrace has to be able to say plainly how often its warnings came true, and to keep score as time goes on.

## A. Score the archived forecasts: `pipeline/score_forecasts.py`
- **Inputs:**
  - every archived run in `events/forecast/` (the dated files, not `latest.json` or `index.json`);
  - the IMERG daily grid in `events/rain_history_grid_daily.json`;
  - local flood days from `events/flood_days.json`, using the same 5 km rule as `forecast.py`. Import its helpers; don't copy them.
- **What gets scored.** For each run, each cell and each forecast day that IMERG now covers, compare against the observed IMERG total:
  - **Brier score** for P(≥20 mm) and P(≥40 mm). Compare it with a **climatology baseline**, meaning that cell's own frequency of ≥20 / ≥40 mm days in the April–November window. Report skill = 1 − Brier / Brier_climatology.
  - **Levels against what happened.** Treat a medium or high level as a "warning". Count hits, misses and false alarms against two kinds of event: (a) IMERG ≥ 40 mm in that cell, and (b) a flood reported within 5 km.
  - Group the scores by lead time (day 1 … day 7).
- **Output:** `events/forecast/scores.json`, holding the totals, the scores per lead day, and `n_scored`.
  - Be honest about small samples. Below 30 scored cell-days for a lead day, set `"enough_data": false`.
  - Today nothing can be scored yet: the archive starts 21 Oct 2026, and IMERG ends 16 Oct. The script must handle that cleanly.
- **IMERG freshness.** The IMERG updater needs Earthdata credentials, so **you don't run it**, and you don't read `.env`. In `docs/FORECAST.md`, document the order: the user (or I) refreshes IMERG first, then runs `score_forecasts.py`.

## B. Hindcast: an early estimate of skill
The archive is empty, so estimate skill from past forecasts that are public:
- Use the Open-Meteo **Previous Runs API** (`previous-runs-api.open-meteo.com`), or the **Historical Forecast API**.
  - Check in the docs which ECMWF model and lead days are available, and since when. Write the exact endpoints, variables and dates into `meta`.
  - No keys. Cache the raw responses under `pipeline/cache/hindcast/`.
- **Period:** April–November of every year available, for the 68 cell centres.
- **Score**, in the same way as A, but this is a **deterministic** forecast (single run, not the ensemble). So report:
  - hits, misses and false alarms of forecast ≥ 40 mm against IMERG ≥ 40 mm, by lead day;
  - **the 87 flood days**: on how many of them did the day-1 forecast reach ≥ 40 mm (or ≥ 20 mm) in a cell within 5 km of a reported area? Then the same for day 3;
  - the false-alarm rate: days forecast ≥ 40 mm with no flood reported within 5 km.
- **Output:** `events/forecast/hindcast.json`. Its `meta` must say plainly that this was a single-run forecast, not the 51-member ensemble the live product uses, so it is a rough guide only.

## C. One line in the app
In `src/components/ForecastCard.tsx`, under the footnote, add one plain sentence from `hindcast.json` (and later from `scores.json`, once `enough_data` is true). For example:

> "How often this kind of forecast was right: in 2024–2026, the day-before forecast flagged heavy rain on 31 of the 52 days floods were reported, and 1 in 3 of its heavy-rain warnings came with no flood reported nearby."

- Use the real numbers. Never print a number the file doesn't have.
- Link it to a short explanation: a `<details>` element with the method and the caveat.
- If neither file exists, show nothing.

## Check
- `npx tsc --noEmit`, `npm run build` and `npx tsx scripts/check-watchlist.ts` all pass.
- `score_forecasts.py` runs today and reports "nothing to score yet" without errors.
- **Report:**
  - the hindcast table (by lead day: hits, misses, false alarms);
  - the flood-day result for day 1 and day 3;
  - the exact sentence the app now shows.

## Rules
- Foreground only.
- No `rm -rf`.
- Don't commit.
- Don't read `.env`.
- Don't start a dev server or open a browser.
- Cursor owns `AreaPanel.tsx`, `PlaceSearch.tsx`, `WeekStrip.tsx` and the search/flood-spot builders (Task 43). Don't edit those.
