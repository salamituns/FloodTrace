# Task 12 — media evidence for three more Lagos floods

FloodTrace is a forensic tool for Lagos flood events (`docs/LAGOS_PLAN.md`). Each event lives in `events/<id>/` with an
`event.json` (dates, sources). We need geolocated, timestamped media evidence for three newly built events.

**Read first:** `docs/tasks/03-media-evidence.md` (the schema and rules — they apply unchanged) and
`docs/tasks/09-evidence-2011.md` (archive links, keeping casualty figures honest). Existing examples:
`events/lagos-2024-07-03/evidence.geojson`, `events/lagos-2011-07-10/evidence.geojson`.

Do the three events **one at a time**, writing `events/<id>/evidence.geojson` (ids `ev-001`…) for each:

| event id | flood | start from (`event.json` sources + `events/catalog_review.json`) |
|---|---|---|
| `lagos-2021-07-16` | Fri 16 Jul 2021, ~4 h rain: Marina / Lagos Island car parks, Lekki, Jakande, Ajah, Awoyaya | Channels TV, Punch, TheCable (NiMet), FloodList |
| `lagos-2022-07-08` | 8–9 Jul 2022: Alimosho (Oke Isagun, Agbado Oke) — NEMA: seven dead | Channels TV, Vanguard |
| `lagos-2025-08-04` | night of 3–4 Aug 2025, ~12 h rain: Ijede / Agric, Ikorodu and elsewhere | Punch (Wahab), Vanguard on X, OSU recap |

Then search for more coverage of each (Punch, Vanguard, Guardian NG, Premium Times, ThisDay, Daily Trust, BBC Pidgin, Nairametrics,
Pulse, TVC, Arise, LASEMA / Lagos Ministry of Environment / NEMA / NiMet statements, X posts by officials or news outlets).

## Lessons from earlier reviews (please apply)
- Nominatim free text matches **street names before places** ("Majek" → Phillip Majek *Street*). Use `pipeline/geocode.py` (it filters
  to place types, takes an area hint, and maps "Lekki" to the peninsula); spot-check each result's district.
- Same-named places exist in different LGAs (Ajegunle in Ajeromi vs Ajegunle in Ikorodu) — keep them distinct.
- Never put a citywide death toll on a single street; only attach casualty numbers where the source does.
- **ClimaMeter's "191 deaths" (Aug 2025) is not corroborated by Nigerian reporting — don't use it** unless a named Nigerian
  authority or outlet states a toll.
- Quotes ≤ 25 words, verbatim. `read_status`: `read` or `headline_only`. Use the Wayback Machine for dead links (`original_url`).
- Run any script to completion before reporting; confirm files aren't modified afterwards; no background processes. Don't touch `src/`
  or other event folders' files except `evidence.geojson` and (adding new sources only) `event.json` `sources`. Don't commit.

Finish with, per event: features, sources (read / headline_only / archive), locations by confidence, anything unresolved.
