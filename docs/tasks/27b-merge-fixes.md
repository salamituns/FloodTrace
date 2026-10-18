# Task 27b: fixes to `pipeline/intake/merge.py` after review

Task 27's `build_event.py` is accepted. The reviewer found four problems in `merge.py` / `events/flood_days.json`:

1. **The drainage signal used the wrong rain.**
   - **The problem:** the AOI mean includes the rural fringe, and overnight rain lands on the previous calendar day.
   - **The evidence:** measured at the flooded areas' own cells, only 2 of 9 checkable days were under 20 mm, not 6 of 12.
   - **Fix:** per day, add a `local` block:
     - max and median `total_mm` over the cells of the geocoded areas, for the flood day and the day before;
     - `local_max_2d_mm` = max over those cells of (day + previous day);
     - the max 30-min rate over both days.
   - Base the printed drainage signal on `local_max_2d_mm < 20`. Keep the AOI mean as context.
   - Days with no geocoded area get `local: null` and are excluded from the signal. Print how many.
2. **Geocoding gaps.** Every area failed for 2019-09-19 ("Pen Cinema, Agege", …), 2023-04-24 ("Odo Iya-Alaro Bridge inward
   Ojota") and 2023-04-27 ("Babs Animashaun Road, Surulere").
   - **Fix:** when a full name fails, retry with the district part (the text after the last comma, or a known district name
     inside the string), with `confidence: "neighbourhood"` and `geocoded_from` recording the fallback.
   - Keep the LGA-level exclusion.
3. **Promotion: `official_named_structure` is too loose.**
   - **The problem:** it fired on LASEMA's "heavy rain and windstorm" (2019-05-20) and on LASTMA moving water into drains
     (2023-04-24).
   - **Fix:** require an official cause attribution with a human cause tag (not `heavy_rain`, `lagoon_tide` or `dam_release`)
     **and** a named physical structure in `cause_quote` or `cause_who`'s statement. A named structure is a canal, channel,
     collector, drain system number, bridge, culvert, outfall or named road project.
   - List each match with the matched text.
4. **Promotion: deaths missed.**
   - **The problem:** 2023-09-16 has NEMA (Ibrahim Farinloye) confirming a motorcyclist swept away at Papa Ashafa / Ile Epo
     canal, but it wasn't promoted.
   - **Fix:** the deaths rule should scan every report of the day, and treat "swept away", "drowned", "died", "dead", "killed"
     and "bodies" as death words.
   - When the attribution is to an official in **any** report of that day, use it. NEMA, LASEMA, police and named officials
     count, even if another report of the same day carries the description.
   - Record `deaths_note` with the source.

Then re-run on the pilot files, and print a before/after table: date, local_max_2d_mm, AOI mean, geocoded areas, promote,
and reasons.

Same rules as Task 27: don't touch `src/`, `events/sites.json` or event folders; run in the foreground; delete only with
`find … -type f -delete` (no `rm -rf`, including `__pycache__`; it's gitignored, so leave it); don't commit.
