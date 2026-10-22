# Daily forecast (flood risk)

The 7-day flood-risk forecast behind "when will it flood, where and what will it
affect". Built by `pipeline/forecast.py` (Task 38,
[docs/tasks/38-forecast-pipeline.md](tasks/38-forecast-pipeline.md)); the UI
comes later (Task 41), Task 42 scores old runs against what actually fell, and
Task 44 calibrates the ensemble's rain to Lagos rain.

## Calibrate first (once per season, or when IMERG is refreshed)

The ECMWF ensemble flattens Lagos's heaviest rain: its day-1 99th percentile is
about 29 mm where IMERG measures 54 mm. `pipeline/calibrate.py` fixes that with
a quantile mapping per lead day, fitted on the 2024-2026 hindcast
(`pipeline/hindcast.py`, cached under `pipeline/cache/hindcast/`) against the
IMERG grid, and validated leave-one-season-out. It also fixes the level rule's
warning threshold from the 2024+2025 seasons only, then tests it on 2026.

```sh
pipeline/.venv/bin/python pipeline/hindcast.py    # fetches once, then cached
pipeline/.venv/bin/python pipeline/calibrate.py   # offline: reads the cache
```

Order matters: refresh IMERG first (`pipeline/imerg_history_grid.py`, needs
Earthdata credentials), then `hindcast.py`, then `calibrate.py`, then
`forecast.py`, which refuses to run without
`events/forecast/calibration.json`. Everything the calibration found — the
mapping, the validation tables, the level rule and its numbers, and whether
the gain is noise — is written into that file's `meta`, and the day-before
warning numbers it stands behind are copied into each run's
`meta.calibration.trust`, which the Coming-up card shows as one plain
sentence under the footnote (also on quiet weeks).

## Run it once

```sh
pipeline/.venv/bin/python pipeline/forecast.py
```

Foreground only, no keys needed. On a fresh day it makes 6 API calls:

- 1 call to the Open-Meteo Ensemble API for the ECMWF ensemble at all 68 cells
  (plus 1 for the GFS second opinion);
- 4 calls to the Open-Meteo Flood API (ensemble forecast + 1984-present flow
  history for the Ogun near Isheri/Kara and the Osun/Owo outlet);

the EOT20 tide is computed locally (no network). Raw responses are cached under
`pipeline/cache/forecast/<run-date>/` and reused on a same-day rerun, so an
archived run stays reproducible.

## Run it every day

`pipeline/run_daily.py` is the one entry point for the daily maintenance. It
runs three steps in order, each as a subprocess of the venv's Python:

1. `forecast.py` — every day: makes today's forecast (same as "Run it once").
2. `imerg_history_grid.py` — only when `events/rain_history_grid_daily.json`
   ends 5 or more days before today (Lagos time), and at most once a day. It
   reads the Earthdata login from `.env` by itself; the wrapper never touches
   credentials. The script takes `--start/--end`, but it rewrites
   `rain_history_grid_daily.json` to cover only the requested window, so a
   narrow range would throw away the 2000-present history the scorer and the
   analogues depend on. The default full range is the narrowest safe range,
   and it is cheap: responses are cached per 2-year chunk, so only the newest
   chunk hits the API.
3. `score_forecasts.py` — after a successful IMERG refresh, and on its own
   when `scores.json` is missing.

A failing step is logged and the run carries on to the next independent step
(IMERG failing must not cost anyone today's forecast); the run exits non-zero
if any step failed. Two runs never overlap: the lock file
`events/forecast/.run_daily.lock` makes a second concurrent run exit
immediately with "already running".

Every run writes `events/forecast/status.json` (validated against
`pipeline/schemas/run_daily_status.schema.json`): when the run happened, what
happened per step (`ok`, `skipped` or `failed`, with a time and, for skips, a
reason), the last day the IMERG history covers (`imerg_through`), and how many
forecast cell-days have been scored (`n_scored`, from `scores.json`). Logs go
to `events/forecast/logs/run_daily-YYYY-MM.log`, one file per month; each step
gets a timestamp, its duration and its exit code, plus the last 20 lines of
its output on failure.

Check the last run:

```sh
cat events/forecast/status.json                                   # what ran, what skipped
tail -20 events/forecast/logs/run_daily-$(date +%Y-%m).log         # this month's log
```

Debug flags: `--skip-imerg` never runs the IMERG step (use it when the
Earthdata refresh should not happen, e.g. in tests), and
`--fail-step <forecast|imerg|score_forecasts>` forces one step to run and
fail, to exercise the failure path (the real command for that step is not
executed).

### Install the daily schedule (macOS)

A launchd LaunchAgent, deliberately not cron: launchd runs a missed job once
when a sleeping Mac wakes up, cron just skips it, and a forecast that silently
did not run while the lid was closed is exactly what this project must avoid.
The agent runs `run_daily.py` at 06:30 local time every day.

```sh
ops/install_daily.sh      # fills __REPO__ in the template, installs and loads the agent
ops/uninstall_daily.sh    # unloads it and removes that one plist file
```

### What the 36-hour "out of date" line in the app means

The app marks a forecast whose `meta.run.generated_at` is more than 36 hours
old as out of date (`forecastFreshness` in `src/lib/forecast.ts`) and says so
plainly ("This forecast is out of date (made 21 Oct 2026)") instead of
pretending it is current. So a missed daily run shows up honestly in the UI on
its own; nothing else needs to notice. The archive still keeps every run, and
the next successful `run_daily.py` brings the app current again.

## What comes out

Everything lands in `events/forecast/`:

- `<run-date>.json` — the run itself: per cell and day the rain forecast
  (median, 90th percentile, chances of 20/40/60 mm, peak 3-hour window), the
  hours at risk and the near-high-tide flag, a plain level
  (`high | medium | low | none`) with a one-sentence reason, analogues (past
  storms like this one) at medium and above, plus citywide headlines, the high
  tides, and the two river points with their high-flow flags. Validated
  against `pipeline/schemas/forecast.schema.json` before it is written.
- `latest.json` — a byte copy of the newest run, for the UI.
- `index.json` — the list of archived runs.

Earlier runs are never overwritten: rerun on the same day and the new file gets
a time suffix (`2026-10-21-0932.json`). `latest.json` always mirrors the
newest.

## Reading it

The rules and thresholds (hourly rain rate, level rule, analogue match, tide
overlap) and their justification are written into each run's `meta.rules`, and
the caveats into `meta.caveats`. The big one: reported floods undercount real
floods, so every "how often it flooded here" number is a floor, not the truth.
