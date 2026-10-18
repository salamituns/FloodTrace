# Task 28c: deaths come from an explicit field, not keywords

**The problem:** the death-word regex in `pipeline/intake/merge.py` (Task 27b fix 4) fires on text that isn't a flood death.
- 2026-06-28 matched "traders said for Iyaloja's death, not the flood".
- 2026-06-30 matched "a man swept away inside a wooden kiosk (outcome not stated)".
- Negations such as "no life lost" are also at risk.

Promotion on deaths must come from a reader's judgement, recorded in the report.

## Schema addition (every report)
```json
"deaths": null | {
  "count": 6,               // integer as reported; null if "some"/"several" with no number
  "who_reported": "Benjamin Hundeyin, Lagos State Police PRO",  // official or named person; null if journalist only
  "quote": "≤25 words, verbatim, from this report's own URL"
}
```
- `null` means the article reports no flood death.
- Rescues, injuries, outcome-unknown cases, collapses with no flood link, and deaths outside Lagos State are `null`. Put
  them in `impacts` instead.

## Cursor: backfill and onward
- Add `deaths` to every report in `events/intake/reports_2019.json`, `_2023`, `_2024`, `_2025` and `_2026`. Re-read the
  article when the impacts mention a death, a drowning or someone swept away. Otherwise set `null`.
- Use `null` for the Magodo building collapse (2019) unless the article ties it to the flood.
- From now on, Task 28 runs fill `deaths` for every report.

## Droid: `merge.py`
- **The deaths rule** fires only when some report of the day (or of the episode) has `deaths` with a non-null `count`,
  or `count: null` and a non-null `who_reported`.
- `deaths_note` becomes `"<count> dead per <who_reported or publisher> (<url>)"`, built from those reports.
- **Keep the regex only as a review aid.** A regex hit on a report whose `deaths` is `null` or missing adds that report's id
  and the matched text to a day-level `deaths_review[]`. It never promotes.
- When a report has no `deaths` key at all (an old file), treat it as missing: review only, never promote.
- **Check:** run merge.
  - 2026-06-28 and 2026-06-30 lose the deaths reason and keep the outlet reason.
  - 2019-10-12, the 2019 Oyan episode, 2023-09-16 and 2025-05-20 keep deaths, **once Cursor's backfill is in**.
  - Before the backfill they show under `deaths_review`. That's expected; say so.

## Rules
- Droid reads the report files and never writes them. Cursor writes them.
- Foreground only. No `rm -rf`. Don't commit.
