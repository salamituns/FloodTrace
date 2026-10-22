# FloodTrace

A map of floods in Lagos: which places keep flooding, what was blamed, and
whether a promised fix happened. It also shows rain risk for the week ahead.

**Site (TODO until live):** https://floodtrace.pages.dev

This is an independent tool, not a government warning. Follow NiMet and Lagos
State (LASEMA) advice.

## Run the app

```bash
npm install
npm run dev        # http://localhost:5173
npm run build      # typecheck + production bundle
```

Checks: `npx tsc --noEmit`, `npx tsx scripts/check-watchlist.ts`,
`npx tsx scripts/check-forecast.ts`.

## Pipeline

Python scripts in `pipeline/` build the forecast, flood catalog, and maps.
The daily flood-risk forecast is documented in [`docs/FORECAST.md`](docs/FORECAST.md).
How that forecast compares with other weather models is in
[`docs/MODEL_COMPARE.md`](docs/MODEL_COMPARE.md).

```bash
pipeline/.venv/bin/python pipeline/forecast.py
```

## Data

Code is MIT (`LICENSE`). FloodTrace's own derived data is CC BY 4.0. Upstream
sources (ECMWF and GloFAS via Open-Meteo, NASA IMERG, EOT20, OpenStreetMap,
Copernicus Sentinel, and others) keep their own licences — see
[`DATA_LICENSE.md`](DATA_LICENSE.md). OSM-derived files are listed there.
