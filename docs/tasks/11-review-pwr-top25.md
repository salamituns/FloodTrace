# Task 11 — review the rest of the top 25 (population-weighted rain), and re-check two "no flood" verdicts

Context: `events/catalog_ranked.json` is now sorted by `pwr_rank` (population-weighted rain — the average rain a Lagos resident
got). Your Task 08 review (`events/catalog_review.json`) covered the old point-scan top 20. Same method, schema and rules as
Task 08 (`docs/tasks/08-confirm-candidates.md`) — accuracy beats coverage; no invented numbers, dates or quotes.

## A. Review these 10 unreviewed candidates (pwr rank · dates · pop-weighted rain mm · wettest cell)
| 9 | 2012-09-26 → 2012-09-27 | 116.1 | Festac Town |
| 10 | 2018-05-03 → 2018-05-05 | 115.5 | Seme border |
| 11 | 2018-06-30 → 2018-07-01 | 106.1 | Alimosho / Ipaja |
| 14 | 2009-07-10 → 2009-07-12 | 104.3 | Agbowa-Ikosi |
| 17 | 2014-05-05 → 2014-05-06 | 99.4 | Epe |
| 18 | 2002-09-18 → 2002-09-19 | 97.6 | Epe |
| 19 | 2008-06-06 → 2008-06-08 | 95.6 | Kosofe |
| 23 | 2018-09-06 → 2018-09-07 | 88.7 | Mushin |
| 24 | 2023-07-22 → 2023-07-23 | 88.3 | Epe |
| 25 | 2021-07-16 → 2021-07-16 | 87.3 | Apapa |

## B. Deeper re-check of two earlier `rain_no_flood_reported` verdicts
These fall in well-covered years, so "no flood reported" is surprising. Search harder (±2 days, Pidgin/Yoruba-language coverage,
X/Twitter, YouTube news clips, LASEMA/NEMA/NiHSA bulletins, Nairaland threads as leads only — a Nairaland post alone is not evidence):
- **2016-10-07 → 2016-10-09** (pwr rank 3, 142.5 mm)
- **2023-06-06 → 2023-06-08** (pwr rank 5, 131.5 mm)

## Output
- **Append** records for part A to `events/catalog_review.json` (same record schema; add `"pwr_rank"`). Don't renumber or rewrite
  existing records.
- For part B, **don't overwrite** the original records: add a `recheck` object to each (`checked_at`, `verdict`, `summary`,
  `sources`, `searched` — list of what you tried). If the verdict changes, say why.
- Read the file fresh immediately before writing, write once, no background process writing afterwards.
- Finish with a table: pwr rank, dates, verdict (and for B: old → new), one-line summary. Don't touch `src/` or event folders. Don't commit.
