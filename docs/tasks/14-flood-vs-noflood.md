# Task 14 — what separates Lagos flood days from heavy-rain days with no flood?

Context: `docs/LAGOS_PLAN.md` → "Exposure ranking". Of the top 25 candidates by population-weighted rain (`pwr_rank` in
`events/catalog_ranked.json`), 6 are floods and 18 had no flood report found (`events/catalog_review.json`). Rain totals alone
don't separate them. Measure what else might: intensity, duration, antecedent wetness, tide phase and time of day.

## Groups (top 25 by `pwr_rank`)
Match each candidate to `catalog_review.json` by overlapping dates (±1 day). Then:
- **flood**: verdict `confirmed_flood`, plus 2024-07-02/03 (`known_event_id`, the Lekki/Apapa flood). Expect 2011-07-10,
  2022-07-08, 2025-08-03/04, 2021-07-16, 2024-07-02/03. Print the list and stop if it isn't 5.
- **likely**: 2017-07-05/06 — report it separately, not in either group.
- **no_flood**: verdict `rain_no_flood_reported` (use the `recheck.verdict` where present). Expect 18.
Print the final membership.

## Data (all cached; no new downloads)
- 30-min IMERG per cell: `pipeline/cache/imerg_history/*.csv` (68 cells; reuse the parser in `pipeline/imerg_history_grid.py`).
  Check the time zone and whether stamps are interval starts; convert to WAT (UTC+1).
- Daily per cell: `events/rain_history_grid_daily.json`. Population per cell and epoch: `events/exposure_cells.json`.
- Tide: EOT20 via pyTMD exactly as `pipeline/tide_eot20.py` does (model files under `pipeline/cache/tide_models`), at the offshore
  point lon 3.52, lat 6.40, hourly or finer.

## Features per candidate (write `pipeline/compare_flood_days.py`)
Use population weights from the candidate's epoch. "pw" = population-weighted mean across the 68 cells. For each candidate's days
± 12 h:
1. `pwr_mm` (already in `catalog_ranked.json`) and `pw_peak_30min_mm_h`, `pw_max_1h_mm`, `pw_max_3h_mm` — the population-weighted
   series' peaks over rolling windows.
2. `urban_max_3h_mm` — max over the urban cells (`urban_cells` in `catalog_ranked.json`) of each cell's max 3-h total.
3. `heavy_hours` — hours with pw rate ≥ 2 mm/h. `peak_time_wat` — centre of the pw max-3h window. `peak_hour`, plus `night` if 20:00–06:00.
4. Antecedent: `pw_antecedent_3d_mm` and `pw_antecedent_7d_mm` (totals before the first day).
5. Tide at the pw max-3h window: `tide_at_peak_m`, `tide_max_in_window_m`, `tide_trend` (rising/falling), `hours_from_high`
   (signed: negative before high water), and `tidal_range_day_m` (high − low that day; spring vs neap).
6. `year` (for the reporting-bias question: online news coverage is thinner before ~2010).

## Output
- `events/flood_vs_noflood.json`: `meta` (method, sources, groups) plus one record per candidate with group, dates, `pwr_rank` and all features.
- Print a table sorted by group, then for each feature: flood median, no-flood median, and **how many no-flood events are ≥ the
  weakest flood** (a simple separability count). n = 5 vs 18, so no models and no p-values: description only. Say plainly which
  features separate the groups and which don't, and note any no-flood days that look like floods on every feature (possible
  under-reporting).

Don't touch `src/` or event folders. No stray background processes; run the script to completion. Don't commit.
