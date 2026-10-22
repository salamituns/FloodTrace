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

## Run it daily

One cron line, run it as yourself, at whatever local time you like (this
example is 06:30 Lagos time every day):

```cron
30 6 * * * cd /path/to/FloodTrace && pipeline/.venv/bin/python pipeline/forecast.py >> events/forecast/cron.log 2>&1
```

Only the one line is needed: the script fetches, computes, validates and
archives by itself. It is deliberately not installed anywhere; if you want the
daily run, add the line with `crontab -e` and change the path.

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
