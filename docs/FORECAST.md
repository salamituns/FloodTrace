# Daily forecast (flood risk)

The 7-day flood-risk forecast behind "when will it flood, where and what will it
affect". Built by `pipeline/forecast.py` (Task 38,
[docs/tasks/38-forecast-pipeline.md](tasks/38-forecast-pipeline.md)); the UI
comes later (Task 41), and Task 42 will score old runs against what actually
fell.

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
