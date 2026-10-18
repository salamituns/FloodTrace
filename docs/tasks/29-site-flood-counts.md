# Task 29: repeat-flood record per site, from the flood-day catalog

Context:
- `docs/INTAKE_PLAN.md`: the Tier B catalog.
- `docs/SITES_PLAN.md`: the sites.
- `events/flood_days.json`: 69 days for 2018–2026, built by `pipeline/intake/merge.py`. Each day has `areas[]` with
  lon/lat/confidence, a flood type, episode_id, `reports[]` with URLs and quotes, and `promote`.
- `events/sites.json`: 13 sites, built by `pipeline/build_sites.py`. Each site's `floods[]` holds only Tier A event
  evidence.

Goal: for each site, the dated, sourced list of catalog flood days that hit it, and a count that's honest about how hard
each year was searched.

## A. Matching, in `pipeline/build_sites.py` (a new function; keep it in one place)
A catalog day matches a site if any of these hold. Record the strongest:
1. **`name`**: a site name or alias token appears in one of the day's area names. Use the place token, not the structure
   word: "Agungi", "Alapere", "Olopo Meji", "Oko Oba", "Ijede", "Labora", "Sangotedo", "Marina", "Alpha Beach", "Agric".
   - Normalise case, hyphens and spaces.
   - Add a hand-checked `place_tokens` list per site in a small dict in the script, with a comment. Don't derive it
     automatically from the structure names; they contain generic words.
2. **`near`**: an area with confidence `exact` or `street` lies within the site's `flood_radius_m` + 200 m of the site
   geometry. Use the existing distance helpers.
3. **`area`**: an area with confidence `neighbourhood` or `area` lies within 1,500 m of the site geometry.
   - `city`, `lga` and unknown confidence never match.
   - The fallback geocodes (`geocoded_from` set) count as `area` at best.

## B. Output: new fields per site (don't change existing fields)
- **`catalog_floods[]`**, one entry per matching day, newest first:
  - date, flood_type, episode_id, strength (`name` | `near` | `area`), matched area name(s), distance_m;
  - n_outlets, promote, tier_a_event_id;
  - `sources`: up to 3 of `{url, publisher, quote}`, taken from the day's reports that name the matched area if any,
    otherwise the first ones.
- **`catalog_summary`**:
  - `n_days` and `n_days_strong` (name + near);
  - `years_with_flood`;
  - `years_searched`: years with at least one April–November entry in `flood_days.json` → `meta.search_coverage`. Use
    that, not the live search_log, so a year Cursor hasn't finished yet doesn't count;
  - `per_searched_year`: n_days_strong / len(years_searched), 2 decimals;
  - `riverine_days`;
  - `note`: "counts reported floods; a year with no report is not proof of no flood".
- **`meta`**: method text, the catalog's sha256 and the matching rules.

## C. Check
- Re-run `build_sites.py`. Diff `events/sites.json` before and after: only the new fields may change. Reviewer fields
  (verdicts, change.summary) must carry over.
- Expect:
  - agungi-collector to include 2024-06-27 (`name`);
  - olopomeji and alapere-ogudu to include 2024-07-03;
  - oko-oba-canal to include 2022-10-21 if New Oko Oba geocodes nearby.
  If any doesn't match, report why instead of loosening the rules.
- Print a table: site, n_days, n_days_strong, years_with_flood, per_searched_year, riverine, and the 3 newest dates.
- List every `area`-strength match with its distance, so the reviewer can check them on the map.

## Rules
- Don't touch `src/`, the report files, `flood_days.json` or event folders.
- Cursor is appending `reports_2017.json` and the search log at the same time. Read them; don't write them. Don't run
  merge.py; use flood_days.json as it is.
- Foreground only. No `rm -rf`. Don't commit.
