# Task 27: one-command event builder, and the flood-day merger

Context: `docs/INTAKE_PLAN.md` (read it first). The last three event folders were built by hand. Steps: write `event.json`,
then run `fetch_open_data.py`, `imerg.py`, `tide_eot20.py` and, when there was a radar pass, `sar_flood.py`. Make both
steps repeatable.

## A. `pipeline/build_event.py <event_id> --start YYYY-MM-DD --end YYYY-MM-DD [--focus-start ISO --focus-end ISO] [--out DIR]`
1. Write `event.json` from a template derived from `events/lagos-2025-08-04/event.json`:
   - `window` = start − 6 d → end + 7 d;
   - `focus` defaults to the wettest 48 h in IMERG;
   - the same AOI and points;
   - `cause_prelim`, `key_events` and `open_questions` empty, plus `"status": "draft"`.
2. Run the existing scripts in order, each with the event folder:
   - `fetch_open_data.py` (it lists Sentinel-1 passes);
   - `imerg.py`;
   - `tide_eot20.py`;
   - `sar_flood.py`, only if a pass falls inside `focus`.
   Stop at the first failure, with a clear message. Credentials only through the existing `.env` loader in `imerg.py`;
   never print them.
3. Add or update the `catalog.json` entry: `built: true`, `status: "draft"`.
4. Make it idempotent. Each step is skipped if its output exists, unless `--force`.
5. **Test:** rebuild `lagos-2021-07-16` with `--out pipeline/cache/rebuild_test/lagos-2021-07-16`.
   - Diff every machine output against the reviewed folder: numbers equal within float noise, same files.
   - Report the differences. Don't touch the real folder.
   - Delete the test folder afterwards with `find … -type f -delete`.

## B. `pipeline/intake/merge.py`
- **Input:** `events/intake/reports_*.json` (schema in `docs/tasks/26-news-sweep-pilot.md`; use the pilot files when they exist,
  otherwise a 3-report fixture you write under `pipeline/intake/fixtures/`).
- **Group** reports into flood days: same date, or date ±1 when `date_confidence` isn't `exact` and areas overlap.
- **Geocode areas** with `pipeline/geocode.py`. Respect Nominatim's 1 request/s, and cache.
- **Attach the rain signature** from `events/rain_history_grid_daily.json`:
  - the AOI mean;
  - the wettest cell, with mm and place;
  - the number of cells ≥ 50 mm;
  - population-weighted rain, computed as in `catalog_ranked.json`;
  - the rain at the cell containing each geocoded area.
- **Match** to `catalog_ranked.json` candidates (`candidate_rank` or `null`).
- **Output** `events/flood_days.json`, with:
  - `meta`: method, sources, and search coverage per year-month from `events/intake/search_log.json`;
  - `days[]`: `date`, `areas[]` (with lon/lat/confidence), `n_sources`, `n_outlets`, `impacts`, `causes`, `rain`,
    `candidate_rank`, `tier_a_event_id` if a folder exists, and `promote` (true/false by the rule in
    `docs/INTAKE_PLAN.md` decision 3).
- **Print** flood days per year, and the share of flood days with AOI rain below 20 mm. That share is the drainage signal.

## Rules
Don't touch `src/`, `events/sites.json` or any existing event folder. Run in the foreground, with no background processes.
No `rm -rf`. Don't commit.
