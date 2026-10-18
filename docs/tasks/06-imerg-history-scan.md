# Task 06 — find candidate Lagos flood days in the IMERG record (2000 → present)

Goal: the first list of candidate events for the multi-event catalog (`docs/LAGOS_PLAN.md`, "Finding events").
Credentials: reuse the `.env` loader in `pipeline/imerg.py` (never print or copy the values).

## Data
Prefer the cheapest route that gives **daily totals and the max 30-min intensity** at the Lagos points:
1. **GES DISC Hydrology Data Rods** (point time series of IMERG half-hourly precipitation, whole record in one request per point) — try this first.
2. Fallback: daily IMERG (`GPM_3IMERGDF` Final; `GPM_3IMERGDL` Late for the most recent months not yet in Final) subset to the AOI via
   OPeNDAP — never keep global files. Note: daily files don't give 30-min peaks; say so if you use them.

Points: `aoi.points` from `events/lagos-2024-07-03/event.json` (lekki, lagos_island, ikeja, ibeju_lekki). Period: 2000-06-01 → latest available.

## Write `pipeline/imerg_history.py` → outputs in `events/`
- `events/rain_history_daily.json` — per day (WAT calendar day): total mm per point, max 30-min intensity per point (if available), `meta` (product, version, run per period, URLs, retrieved_at, licence, method).
- `events/catalog_candidates.json` — days where **any** point has a daily total ≥ 50 mm **or** a 30-min intensity ≥ 30 mm/h (keep thresholds as named constants, recorded in meta). Merge consecutive qualifying days into one candidate (start/end). For each candidate: dates, per-point totals and peaks, 7-day antecedent mean, a severity rank (by max point total), and `known_event_id` if it overlaps a folder in `events/` (e.g. `lagos-2024-07-03`).
- Print: period covered, number of days, number of candidates, top 25 by severity, whether 2024-07-02/03 appears and where it ranks, and the distribution by month.

## Rules
- Be polite to NASA services (sequential requests, retries with backoff). Cache raw responses under `pipeline/cache/imerg_history/` so re-runs are cheap.
- This is a long job: run it in the foreground or wait for it to finish before reporting; make sure no stray background process keeps running afterwards.
- Don't touch `src/` or `events/lagos-2024-07-03/`. Don't commit.
