# Task 28b: flood type and episodes in `pipeline/intake/merge.py`

Context: `docs/INTAKE_PLAN.md`; Task 27 / 27b (merge.py). The recall pass for 2019 (Task 28) found the Oyan Dam flood of
October 2019: the Ogun River over its banks for weeks (Isheri, Ajegunle, Owode Elede, Kio-Kio, Irawo), 6 dead. merge.py
treats it like a rain flood. It splits the flood into one-day records (4 Oct, 20 Oct) and puts the local rain on them in the
drainage signal. River and dam floods come from rain far upstream, so local rain says nothing about them.

## Do
1. **Flood type per report**, derived (don't edit the report files):
   - `riverine`: causes include `dam_release`, or the text (quote, impacts, cause_quote) names the Ogun River, Oyan Dam, Owena
     or "release of water". `canal_overflow` alone is **not** riverine.
   - `lagoon`: `lagoon_tide` is the **only** non-rain cause, and the text says the lagoon or tide overflowed into an area.
     Lagoon backflow that slows drainage during rain stays pluvial.
   - `pluvial`: everything else.
   Keep the rule in one function, with a short docstring listing the triggers.
2. **Flood type per day:** `riverine` if any report of the day is riverine; else `lagoon` if any is; else `pluvial`. Also
   record `flood_type_reports: {pluvial: n, riverine: n, lagoon: n}`.
3. **Episodes:**
   - Riverine days less than 21 days apart join one `episode_id` (`ep-<first date>-riverine`), and the reports keep their own
     dates.
   - Add `episodes[]` to `flood_days.json`: id, type, first and last date, days, areas (union), deaths_note (the first that
     exists), n_outlets (distinct over the episode), and `promote` by the same rule applied over the episode.
   - Pluvial days are not grouped.
4. **Drainage signal:** compute it only over `pluvial` days. Print it as "pluvial days with local_max_2d_mm < 20: k/n".
   Print counts per type, and list riverine and lagoon days with their episode.
5. **Check:**
   - Run on `events/intake/reports_*.json`.
   - Expect 2019-10-04 and 2019-10-20 in one riverine episode, with deaths.
   - Expect 2024-07-03 to stay pluvial: Wahab's lagoon remark is backflow during rain.
   - Print a before/after table: date, type, episode, local_max_2d_mm, promote.

## Rules
- Don't touch the report files, `src/`, `events/sites.json` or event folders.
- Cursor is appending to `events/intake/reports_2025.json` at the same time. Read the report files; never write them.
- Foreground only. No `rm -rf`. Don't commit.
