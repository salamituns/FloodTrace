# Task 22 — official drainage promises for each site, and what happened since

Context: `docs/SITES_PLAN.md` (read it first, especially the `events/promises.json` schema and the seed list). The app will
judge each promise **from imagery only**: officials' claims are recorded but never decide the status. Your job is the
research: what was promised, by whom, when, by when, and every later piece of evidence.

## Scope
All 13 sites in `events/drainage_sites.json`. For each, search official sources (Lagos MoE / Drainage Services / LASBCA / LASEPA /
Ministry of Works, Governor, Commissioner X accounts, state press releases) and news, **from 6 months before the site's flood to
today**, for commitments about that site's structure: build, expand, excavate, dredge, demolish, enforce, maintain. Start
with the seed list in `SITES_PLAN.md` and verify each one; find more. Several promises per site is normal (e.g. System 156:
excavation + dredging + enforcement).

## Per promise
Fill every field of the schema. Rules:
- `quote`: ≤ 25 words, verbatim from `url`, with `read_status` noted in `meta.sources`. Task 03 rules (Wayback for dead links).
- `kind`: pick the closest. Dredging, desilting and routine cleaning are `dredge` or `maintain`.
- `due`: `stated` only if the source gives a date or duration ("within 14 days", "12-month completion"); `contract` if from a
  contract or award notice; otherwise `none` (the app applies a 12-month grace). Never invent a due date.
- `updates`: every later news or official item about delivery, oldest first, each with `kind` (`news` | `official`),
  `ref` (url) and `finding` (`claimed_done` | `claimed_ongoing` | `done` only if a journalist **reports seeing** it completed |
  `no_change` if a report says nothing happened). **Don't add `imagery` updates**: I add those after checking imagery.
- Leave `status`, `status_reason` and `last_checked` as `null`: they're computed.

## Output
`events/promises.json` with `meta` (method, sources list, searched_until date) and `promises[]`. IDs: `<site_id>-<kind>-<yyyymm>`.
Don't touch other files. No background processes. Don't commit.
Finish with a table: site, promise, made (date, who), due (basis), n updates, latest update finding.
