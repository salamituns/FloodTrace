# Task 28: full news sweep, one year per run, with a recall pass

Context: read `docs/INTAKE_PLAN.md` first (decisions and pilot status) and `docs/tasks/26-news-sweep-pilot.md` (method and
schema). The pilot worked but missed floods: Anadolu reported 6 dead in Lagos on 23 Oct 2019 after an Oyan Dam release, and
the pilot has nothing for it. This task runs the same sweep plus a second, recall-focused pass.

## Scope of one run
**Do one year per run, then stop and report.** The reviewer briefs the next year. The order is:
1. 2024, 2025, 2026 (through September);
2. then 2022 back to 2010;
3. then pass 2 only for 2019 and 2023 (pass 1 is already done).

The year for this run is given in the prompt. If none is given, do 2024.

## Pass 1: as in Task 26
For each wet-season month (Apr–Nov), use the same outlets, queries, qualifying rule and per-report fields as Task 26.

## Pass 2: recall, per month (slimmed 2026-10-18 after the 2024 and 2019 tests)
Run these after pass 1 for the same month. The wire services, ReliefWeb, the Dartmouth archive and the government sites found
nothing usable in either test year, so they're dropped. What pass 2 catches is river, dam and lagoon flooding, and deaths.
- **Death queries**, across all outlets with no `site:` filter: "Lagos flood" with each of dead, died, drowned,
  "swept away", bodies, killed.
- **River, dam and lagoon queries:**
  - "Oyan Dam" Lagos;
  - "Ogun River" overflow Lagos;
  - "Lagos lagoon" overflow;
  - "release of water" Lagos;
  - "Isheri" OR "Ajegunle" OR "Owode Onirin" OR "Agboyi" flood.
- **Anadolu** (`site:aa.com.tr` Lagos flood): one query per year, not per month.
- **Out-of-season check, once per year:** "flood Lagos" for Jan–Mar and Dec. Keep any qualifying report.
- **Never search for a specific article the reviewer names.** Recall tests must use only these generic queries.

## Deduplication
- A pass-2 report on a day already found in pass 1 is still kept: more outlets helps promotion. Give it its own `id`.
- Don't re-add the same URL.

## Output
- Append to `events/intake/reports_<year>.json`, creating it if needed, in the same schema as the pilot files. Add
  `"pass": 1` or `"pass": 2` and the `deaths` field (schema in `docs/tasks/28c-deaths-field.md`) to every report you add.
- Append one entry per year-month to `events/intake/search_log.json`, as in Task 26, plus a `pass2` object holding the same
  fields: queries, outlets, hits_screened, kept, excluded, minutes.
- For 2019 and 2023, add only the `pass2` object to the existing entries. Don't duplicate them.
- Don't run `merge.py` while Task 28b is open. The reviewer runs it.

## Report at the end of the run
A table per month with these columns:
- pass 1 kept;
- pass 2 kept;
- distinct flood days;
- days found **only** by pass 2;
- outlets blocked;
- minutes.

Also list every report that has deaths, with its source, and the total time. If pass 2 found fewer than 1 new day per 3
months, say so; the reviewer may then drop pass 2 for older years.

## Rules
- Task 03 and Task 26 rules apply.
- Never invent dates, numbers or quotes. Quotes are verbatim and at most 25 words, and **every `quote` and `cause_quote`
  must appear in that report's own URL**. Don't copy a quote from another outlet's article, even about the same statement.
- **`date_confidence: "period"`** is for a roundup that names no flood day or week ("over the last few weeks", "this
  rainy season", "in the past month"). Set `date` to the publication date. merge.py lists these reports apart and never
  makes them flood days. Use `approx` only when the article lets you place the flood within a few days ("last week's
  downpour").
- **The date is the flood day, not the publication day.** When an article says "on Saturday", work out the date and set
  `date_confidence: "day"`.
- A month with nothing found is a valid result. Log it.
- Nairaland, YouTube and X posts are leads only. Confirm them in a news or official source.
- Don't geocode, create event folders, or touch `src/`, `events/sites.json`, `events/flood_days.json` (merge.py writes it)
  or event folders.
- No background processes. No `rm -rf`. Don't commit.
