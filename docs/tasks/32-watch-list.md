# Task 32: pre-season watch list (roadmap step 8)

Context:
- `docs/LAGOS_PLAN.md`, step 8: "Each March, rank sites with repeated flooding, named drainage failure and no visible fix."
- Inputs:
  - `events/sites.json`: `catalog_summary`, `catalog_floods`, `claims`, `verdict`, `change`;
  - `events/promises.json`, with the status from `promiseStatus(p, today)` in `src/lib/promises.ts`;
  - `events/site_rain_response.json`: rain-matched rates (Task 31).

## Principle: tiers and reasons, not a weighted score
A blended score (0.4 × floods + 0.3 × …) looks precise and hides its judgement. Instead, each site gets three yes/no tests.
- **The tier is the number passed.** The list orders by tier, then by the tie-breaks below.
- **Each test shows its reason** in words and links to its evidence.

## A. Slim rain summary (pipeline)
- `pipeline/storm_replay.py` also writes `events/site_rain_summary.json`. Per site it holds:
  - cell id;
  - for the 40 mm threshold, `all_years` and `well_searched_years` stats;
  - the replay headline per reference: ref mm, n_analogs, n_flooded, not_a_storm_here.
- Add meta with the caveats and the source file's sha256, and a schema.
- Re-run. `site_rain_response.json` must not change apart from generated_at.

## B. `src/lib/watchList.ts`: a pure function
`buildWatchList(sites, promises, rainSummary, asOf: Date): WatchRow[]`. Each row has site_id, name, `tests`, tier, the
tie-break values and `as_of`.
- **Test 1, repeated flooding:**
  - pass when the site has at least 2 strong pluvial catalog days in well-searched years, and at least 1 in the last
    3 seasons before `asOf`.
  - Reason, for example: "4 strong flood days in well-searched years; last 2026-06-28".
- **Test 2, named drainage failure:** pass when some claim names a drainage cause, and either:
  - it was attributed by an official or a journalist; or
  - its `evidence_status` is `supports` or `weak`.
  - A resident's claim with nothing checked doesn't pass on its own.
  - Reason: who blamed what, from the claim.
- **Test 3, no visible fix:** pass when no promise at the site is `delivered` as of `asOf` and the verdict doesn't say the
  problem is fixed.
  - A site with no promise passes: nothing was promised and nothing is visibly fixed.
  - Reason: the worst promise status, or "no promise on record".
- **Tie-breaks within a tier, in order:**
  1. strong days in the last 3 seasons;
  2. well-searched rate at ≥ 40 mm;
  3. name.
- Put the three rules in one place with a short comment each, so they can be changed without hunting.
- Add a small unit test file next to it. Use the repo's test runner if it has one; if not, say so and add a
  `scripts/check-watchlist.ts` run with `npx tsx`. Cover these cases:
  - a site with no promise;
  - a delivered promise, which fails test 3;
  - a flood only in a thin year, which doesn't count for test 1.

## C. UI: "Watch list" in Sites mode
- A card at the top of the site list (no site selected):
  - title "Pre-season watch list";
  - an `as of` date picker, defaulting to 1 March of the current year if today is past it, else 1 March of last year;
  - one row per site with its tier and three ticks or crosses, each with its reason on hover or on expand.
  - Clicking a row opens the site.
- Keep the existing site list below it, unchanged.
- **Footer:** "Ranks sites by evidence on record, not by forecast. A site with no reports can still flood."

## Check
- `npx tsc --noEmit`, `npm run build` and the unit checks pass.
- Print the watch list as of 2026-03-01 and as of 2027-03-01: tier, tests and reasons per site.
- Tell me any site whose tier surprises you, and why it lands there. Don't tune the rules to fix a surprise; report it.
- No browser tools. I'll check the UI myself.

## Rules
- Don't touch report files, flood_days.json, sites.json or promises.json.
- Foreground only. No `rm -rf`. Don't commit.
