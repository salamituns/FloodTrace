# Task 10 — exposure-weighted ranking of the rainfall candidates

Context: `docs/LAGOS_PLAN.md` → "Grid scan" bullets. Ranking by the single wettest IMERG cell is dominated by the rural fringe
(Epe, Sangotedo, Seme border…). We want to rank by **rain where people are**, and by spatial extent.

## Exposure data (open, no login)
Use **GHSL GHS-POP R2023A** (JRC, CC BY 4.0) population grids at 30 arc-second (~1 km), WGS84, for the epochs
**2000, 2005, 2010, 2015, 2020, 2025**, so a 2007 event is weighted by 2005 population and a 2024 event by 2025, since
Lagos grew a lot. Download only the tile(s) covering the AOI, clip to the AOI bbox (padded 0.1°), keep only the clipped
rasters under `pipeline/cache/ghsl/` (disk is tight: ~12 GB free — delete zips/full tiles after clipping). If GHS-POP is unreachable,
fall back to WorldPop 2000–2020 (constrained or unconstrained, 1 km) and say so.

## Do (`pipeline/exposure_rank.py`)
1. Aggregate population to the **68 IMERG cells** used by Task 07 (same cell list/order as `rain_history_grid_daily.json`), per epoch
   → `events/exposure_cells.json` (`meta`: source, epochs, licence; per cell: lon, lat, place, population per epoch).
2. For every candidate in `events/catalog_candidates_grid.json`, using the epoch nearest the event year and the per-cell daily
   totals / peaks over the candidate's days:
   - `pop_exposed_50mm` — people in cells whose candidate total ≥ 50 mm
   - `pop_exposed_30mmh` — people in cells with any 30-min intensity ≥ 30 mm/h
   - `pop_weighted_rain_mm` — Σ(cell total × cell pop) / Σ(cell pop)
   - `urban_cells_over_threshold` — cells over threshold among the cells holding the top 80 % of population
   - keep `cells_over_threshold`, `max_cell`, `max_peak_mm_h`, `known_event_id`; flag `suspect_peak: true` if any cell peak > 70 mm/h
3. `exposure_rank` = rank by `pop_exposed_50mm` (ties → `pop_weighted_rain_mm`). Write `events/catalog_ranked.json`
   (same records + the new fields, sorted by `exposure_rank`).
4. Print: total Lagos population per epoch (sanity check against ~8–9 M in 2000 → ~15–17 M in 2025 for this AOI; explain any big gap),
   top 25 by `exposure_rank` (dates, people exposed, pop-weighted rain, extent, suspect flag), and where these land:
   2011-07-10, 2022-07-08, 2025-08-03/04, 2024-07-02/03, 2017-07-05 (confirmed/likely floods). Also the count of suspect peaks.

Reuse existing caches; no new IMERG downloads. Don't touch `src/` or `events/<event-id>/`. No stray background processes. Don't commit.
