# Task 08 — confirm the top rainfall candidates against flood reports

Input: `events/catalog_candidates.json` (Task 06 point scan). Take the **top 20 by `rank`**. (A grid-based list is being built in
parallel; we'll merge later — don't wait for it.)

For each candidate, search for evidence that **flooding** happened in Lagos on those dates (± 1 day): Nigerian news archives
(Punch, Vanguard, Guardian NG, ThisDay, Premium Times, Channels TV, Daily Trust, BBC, Reuters, AFP), LASEMA / Lagos State Ministry
of Environment, NEMA, the **Dartmouth Flood Observatory** archive (floodobservatory.colorado.edu), EM-DAT, ReliefWeb, Wikipedia.
Older events (2000–2012) are mostly in newspapers' online archives, BBC/Reuters, Wikipedia and ReliefWeb.

## Output: `events/catalog_review.json`
`meta` (compiled_at, method, notes) and one record per candidate:
- `start`, `end`, `rank` (from the input), `verdict`: `confirmed_flood` · `likely_flood` · `rain_no_flood_reported` · `not_checked`
- `summary` (≤ 40 words: what happened, where), `areas` (list of named Lagos areas), `impacts` (deaths, displaced, damage — only as reported, with numbers verbatim),
  `official_statements` (who, what, ≤ 25-word quote), `sources` (list of {title, url, publisher, published_at, read_status})
- `suggested_event_id` for confirmed ones: `lagos-YYYY-MM-DD` (main flood day)

## Rules
- Accuracy beats coverage. Never invent casualty numbers, dates or quotes. Quotes ≤ 25 words, verbatim. `read_status`: `read` or `headline_only`.
- A candidate with heavy rain but no flood report is a valid and useful result (`rain_no_flood_reported`).
- Note any date mismatch (e.g. flood reported a day after the rain candidate).
- Don't create event folders, don't touch `src/` or existing `events/<event-id>/` folders. Don't commit.
- Finish with a table: rank, dates, verdict, one-line summary.
