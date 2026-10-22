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

the EOT20 tide is read from the precomputed table
`events/forecast/tide_table.json` (no network, no model needed); only when the
forecast window falls outside the table's 2026-01-01 .. 2031-01-01 range is it
computed locally with pyTMD (which needs the 2.1 GB model). Raw responses are
cached under
`pipeline/cache/forecast/<run-date>/` and reused on a same-day rerun, so an
archived run stays reproducible.

## Run it every day

`pipeline/run_daily.py` is the one entry point for the daily maintenance. It
runs three steps in order, each as a subprocess of the pipeline's Python (the
venv's when present, otherwise the interpreter running the wrapper — e.g. the
GitHub Actions runner), with the repo root as its working directory:

1. `forecast.py` — every day: makes today's forecast (same as "Run it once").
2. `imerg_history_grid.py --update` — only when
   `events/rain_history_grid_daily.json` ends 5 or more days before today
   (Lagos time), and at most once a day. It reads the committed history,
   fetches only from its last day minus 7 days to now (to catch NASA's
   late-arriving data), and merges the fresh window in: new values replace
   old ones on overlapping days, every earlier day stays byte-identical, and
   the 2000-present history the scorer and the analogues depend on is never
   rewritten. It needs Earthdata credentials from the environment (the cloud
   run) or from `.env` (a laptop); the wrapper never touches credentials. The
   full rescan is still available by dropping `--update`, for when the grid
   itself must be rebuilt.

   NASA's research-grade Final run lags about 3.5 months, so recent days
   arrive from the near-real-time Late run. `--update` only looks back a
   week, so it never swaps those Late values for Final ones. Run the full
   rescan (without `--update`, on a machine with the IMERG cache) about once a
   season to upgrade them; the scores and analogues then use Final rain.
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

### The cloud run (the primary way)

`.github/workflows/daily.yml` runs `pipeline/run_daily.py` on GitHub Actions
every day at 06:30 Lagos time (05:30 UTC — Lagos is UTC+1 with no daylight
saving), and on any manual trigger. It installs the pipeline's Python
dependencies from `pipeline/requirements.txt`, runs the three steps with the
Earthdata credentials in the environment, then commits whatever changed under
`events/forecast/` and `events/rain_history_grid_daily.json` as
`github-actions[bot]` ("Daily forecast 2026-10-23") and pushes; the push is
what rebuilds the site on Cloudflare Pages. A push that races a human one is
rebased and retried once. The job commits only those two paths, holds only
`contents: write` permission, is serialized as `daily-forecast`, and times out
after 30 minutes.

What the cloud run does not need on the runner: the 2.1 GB EOT20 tide model
(the tide comes from the committed `events/forecast/tide_table.json`, built
by `pipeline/tide_table.py` — regenerate it before its 2031-01-01 end), the
IMERG fetch cache (`--update` fetches only the last week), the venv (the
steps run under the runner's Python) or the logs directory (run logs go to
the job output; `events/forecast/logs/` is never committed).

Secrets the owner must add (Settings → Secrets and variables → Actions;
names only): `EARTHDATA_USERNAME` and `EARTHDATA_PASSWORD`. They are exposed
only to the pipeline step's environment and are never printed, logged or
written anywhere.

Manual run: Actions → daily-forecast → Run workflow — for testing after a
pipeline change, or to catch up after a missed run. A manual run that lands
while another is running waits its turn (the workflow is serialized, and
`run_daily.py` itself holds a lock file).

Reading a failed run: GitHub emails the owner when the job fails, and the
run is red in the Actions tab with each step's full output. As long as the
forecast step itself succeeded, `status.json` is still committed and pushed:
it records per step `ok` / `skipped` / `failed` with times and, for skips,
the reason. A failed IMERG refresh never costs the day's forecast — the
wrapper runs the independent steps anyway and exits non-zero at the end,
which is what fails the job.

### Repository growth

Each run file is about 0.5 MB, about 200 MB a year uncompressed. Measured
(Task 47): git delta-compresses consecutive daily runs extremely well —
three committed runs, 1.9 MB of working files, pack to 25 KB in a bare clone,
about 1% — because each day's file and the rewritten `latest.json` differ
from the previous day's only in their numbers. The archive therefore costs on
the order of a few MB of git history per year, and no mitigation (pruning
old runs, LFS, a separate data repo) is worth its complexity now. Revisit
only if a fresh clone's `git count-objects -v` starts growing by tens of MB
per month.

### The Mac LaunchAgent (optional)

The cloud run replaced the laptop as the primary way to keep the forecast
current; the agent below is still there for owners who want the pipeline on
their own machine too. A launchd LaunchAgent, deliberately not cron: launchd
runs a missed job once when a sleeping Mac wakes up, cron just skips it, and
a forecast that silently did not run while the lid was closed is exactly what
this project must avoid. The agent runs `run_daily.py` at 06:30 local time
every day, and finds the Earthdata credentials in `.env` (the cloud run gets
them from the environment instead).

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
