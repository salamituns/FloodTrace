# Task 26: news-first flood sweep, pilot years 2019 and 2023

Context: `docs/INTAKE_PLAN.md` (read it first). Rain-first discovery found only 5 floods in the top 25 rain days. This sweep
finds Lagos floods from the news side, so that floods on moderate-rain days are captured and every month gets a recorded
search effort.

## Do, for each wet-season month (Apr–Nov) of 2019 and 2023
1. **Search.** Use at least these:
   - Google News-style queries, run per outlet with `site:`, for "flood" plus "Lagos". Use "flood" plus district names for
     the 15 biggest districts (list them in `meta`).
   - Outlets: Punch, Vanguard, Guardian NG, Premium Times, Channels TV, TVC, Daily Trust, BBC Pidgin, Nairametrics.
   - The X accounts of LASEMA, Lagos MoE and NEMA, if you can reach them.
   - Nairaland and YouTube are **leads only**. Confirm them in a news or official source.
2. **Qualifying reports.** Keep a report only if it's a readable source that names a place in Lagos State and a date, and
   describes water on streets or in homes. Warnings, forecasts and "residents fear" pieces don't qualify. Record them in
   the log as `excluded` with the reason.
3. **Per report:**
   - `date` (the flood day, not the publication day) and `date_confidence` (`exact` | `day` | `approx`);
   - `areas[]`, as named;
   - `impacts`, as reported, with numbers verbatim;
   - `quote`: at most 25 words, verbatim;
   - `causes`, `cause_quote`, `cause_attributed_by`, `cause_who` (Task 15 tags and rules);
   - `url`, `publisher`, `published_at`, `read_status`.
4. **Search log, per month:** the queries run, outlets reached or blocked, number of hits screened, and number kept.

## Output
- `events/intake/reports_2019.json` and `events/intake/reports_2023.json`.
- `events/intake/search_log.json`, appending: one entry per year-month.
- Finish with a table per month: reports kept, distinct flood days, outlets that returned nothing, and time spent. Then
  estimate the time for all of 2010–2026.

## Rules
Task 03 rules apply. Never invent dates, numbers or quotes. A month with no flood found is a valid, useful result. Don't
geocode (merge.py does that). Don't create event folders or touch `src/`, `events/sites.json` or existing event folders.
No background processes. Don't commit.
