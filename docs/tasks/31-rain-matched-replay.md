# Task 31: rain-matched storm replay per site (roadmap steps 6 and 7)

Context:
- `docs/LAGOS_PLAN.md`, steps 5–7. Step 5 found no usable terrain signal at 30 m, so we don't simulate water. We replay
  storms against history instead: "of the days since 2014 when rain at least this heavy hit this site, how many flooded
  it, and did that change after a fix?"
- `events/rain_history_grid_daily.json`: IMERG per 0.1° cell, per WAT day, 2000-06-01 → 2026-10-17. `meta.cells` gives
  cell centres; `series[cell]` holds parallel arrays (read the file to see the field names) of daily total mm and max
  30-min intensity, aligned with `dates`.
- `events/flood_days.json`: the catalog. Each day has `flood_type`, `episode_id`, and `meta.search_coverage`.
- `events/sites.json`: `catalog_floods[]` per site with `strength`; use only `name` and `near` (the strong matches).
- `events/promises.json`: dated official commitments per site, with updates.

## A. `pipeline/storm_replay.py` → `events/site_rain_response.json`
1. **Site cell:** the IMERG cell whose 0.1° box contains the site geometry's centroid. Also record the max over the 3×3
   neighbourhood as a sensitivity value; the main numbers use the site's own cell.
2. **Storm days:** the rain on day *d* is the 2-day total (*d*−1 + *d*), the same measure as `local_max_2d_mm` in
   flood_days.json. Also keep the max 30-min intensity over the 2 days.
   - **Window:** April–November of the searched years (from `meta.search_coverage`). Dec–Mar was only searched once a
     year, so floods there are listed separately and stay out of the rates.
   - **Declustering:** consecutive days at or above a threshold form one storm. Its rain is the max over its days. It
     counts as flooded if a strong match falls on any of its days or the day after the last one.
3. **Floods counted:** only `pluvial` strong matches. Riverine, lagoon and coastal days are listed per site but stay out of
   the rates: local rain doesn't drive them.
4. **City-wide sanity check first.** Take every Apr–Nov day of the searched years and the max 2-day rain over all land
   cells. Report the share of days that are catalog flood days in bins 0–10, 10–20, 20–40, 40–60, 60–80 and ≥80 mm.
   - If the share doesn't rise with rain, stop and report it. The method has nothing to stand on, as with step 5.
   - Print the bins either way.
5. **Per site, per threshold** (20, 40, 60, 80 mm): the number of storms, how many flooded, and the rate. Add a Wilson
   95% interval; the counts are small and the interval says so.
6. **Replay of reference storms:**
   - The references are the five Tier A events: 2011-07-10, 2021-07-16, 2022-07-08, 2024-07-03 and 2025-08-04.
   - For each site, take the reference storm's 2-day rain at the site cell. Its analogs are the searched-window storms
     with at least that much rain at the site cell. Exclude the reference storm itself.
   - Output, per site and reference: the reference rain, the analogs (date, mm, flooded yes/no, sources from
     `catalog_floods` when flooded), the count and the rate.
   - A reference with under 10 mm at a site gets `"not_a_storm_here": true` and no analogs.
7. **Before/after:** for each site with a promise:
   - Split the storms ≥ 40 mm at the earliest of three dates: the promise date, the first `claimed_done` update, and the
     first `claimed_ongoing` update. Record which date was used and why.
   - Report the counts and rates on each side.
   - No significance test. Give a plain-language `reading` instead, such as "3 of 4 before, 2 of 2 after: too few storms
     after to tell".
   - Call a difference only if each side has at least 5 storms. Otherwise say there are too few.
8. **Reporting bias:**
   - Compute catalog flood days per searched year. Mark a year **thin** if it has fewer than 5.
   - Give every rate twice: all searched years, and well-searched years only.
   - Put a `caveats[]` list in `meta`:
     - unreported ≠ dry;
     - IMERG cells are ~10 km and smooth storm cores;
     - thin early years;
     - a strong match means the news named the place or a point near it, not a measured depth.
9. **meta:** method, input file sha256s, thresholds and generated_at.
   - Deterministic: two runs give identical output apart from generated_at.
   - Add `pipeline/schemas/site_rain_response.schema.json` and validate against it, as `build_sites.py` does.
   - Run with `pipeline/.venv/bin/python`.

## Check and report
- The city-wide bins table (point 4).
- A table with one row per site:
  - storms ≥ 40 mm, flooded, rate (all years / well-searched years);
  - the 2024-07-03 replay: reference mm, number of analogs, how many flooded.
- Spot check:
  - agungi-collector against 2024-07-03. List every analog with its date, mm and flooded flag. Confirm by hand that 2 of
    them match `catalog_floods`.
  - For the city-wide check, give 3 of the bins' days with their catalog status.
- Before/after for every site with a promise, with the split date and the `reading`.
- Say plainly if any result looks too good, such as a rate near 100%, and why.

## Rules
- Read-only on `events/` except the new output file. Don't touch `src/`, the report files, flood_days.json, sites.json or
  promises.json.
- No new downloads. If a date is missing from the rain file, treat it as missing, not zero, and count such days.
- Foreground only. No `rm -rf`. Don't commit. No browser tools; this task has no UI.
