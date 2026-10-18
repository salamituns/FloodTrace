# Task 07 — rescan the IMERG record over every Lagos cell, not just 4 points

Context: `docs/LAGOS_PLAN.md` ("Status" → known blind spot). Task 06's scan used 4 points and missed the 3 Jul 2024 core
(31 mm/h at the cell centred 6.45°N 3.35°E, Apapa / Mile 2), so that event ranked only #26.

## Do
1. Extend `pipeline/imerg_history.py` (or add `pipeline/imerg_history_grid.py` reusing its fetch/cache/credential code) to scan
   **every IMERG 0.1° cell centre inside the AOI bbox** `[2.70, 6.38, 4.35, 6.75]` that is **land or lagoon shore** — drop cells that
   are entirely Atlantic Ocean (you can use a simple coastline test, e.g. cell centre north of the shoreline polygon from OSM /
   Natural Earth, or a hand-listed exclusion; explain what you did).
2. Same service, same period (Jun 2000 → present), same Final/Late split, cache per cell under `pipeline/cache/imerg_history/`.
   The 4 existing points are already cached — reuse, don't refetch. Be polite: sequential requests with backoff.
3. Outputs in `events/`:
   - `rain_history_grid_daily.json` — per day: per-cell daily total + max 30-min intensity (compact arrays; cell list in meta).
   - `catalog_candidates_grid.json` — same schema as `catalog_candidates.json`, but criteria apply to **any cell**, with
     `max_cell` (lon, lat, nearest place name if you can — e.g. from a small hand list of Lagos districts), number of cells over
     threshold (spatial extent proxy), and `rank`. Rename the ambiguous field: `antecedent_7d_mean_daily_mm`.
   - `catalog_scan_compare.json` — candidates found only by the grid scan, only by the point scan, and rank changes for the overlap.
4. Print: cells scanned, candidates, top 25, the new rank of 2024-07-02/03 and of 2011-07-10, and the 10 biggest rank changes.

Don't touch `src/` or any `events/<event-id>/` folder. Leave `catalog_candidates.json` as is. No stray background processes. Don't commit.
