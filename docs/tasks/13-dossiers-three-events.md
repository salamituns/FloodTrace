# Task 13 — dossiers for three events

FloodTrace (`docs/LAGOS_PLAN.md`) keeps a human write-up, `dossier.md`, in each event folder. Write one for each of:
`events/lagos-2022-07-08/`, `events/lagos-2025-08-04/`, `events/lagos-2021-07-16/`.

**Follow the structure and tone of** `events/lagos-2011-07-10/dossier.md` (and, for depth, `events/lagos-2024-07-03/dossier.md`):
what happened, timeline, rainfall, tide, satellite imagery, evidence, cause (preliminary), open questions, sources.

## Inputs (all already in each folder — don't download or recompute anything)
- `event.json` — `cause_prelim`, `key_events`, `open_questions`, `sources`. **These are the reviewed analysis; the dossier must agree
  with them.** Don't introduce new numbers.
- `rainfall_summary.json`, `rainfall_imerg.json` — IMERG v07 Final, 30-min. Note: `totals_mm.24h` is the 24 h *ending at each
  point's peak*, NOT a calendar day — don't present it as a daily total. Calendar-day totals you may quote:

  | event | day totals (IMERG, mm) |
  |---|---|
  | 2022 | 8 Jul: AOI 70, Alimosho 85, Ibeju-Lekki 152, Lekki 99 · 9 Jul: AOI 41, Alimosho 71, Apapa 80 · prior 7 days 70–98 at the points |
  | 2025 | 3 Aug 09:00 → 4 Aug 09:00: Lekki 146, Lagos Island 123, Ikorodu 103, Ikeja 77 · prior 7 days 7–13 |
  | 2021 | 16 Jul: AOI 74, Lagos Island 105, Apapa 106, Oshodi 90, Ikeja 87 · 15 Jul: 1–8 |

- `tide_eot20.json` — EOT20 astronomical tide offshore (not lagoon level). Lagoon damping and lag: see the 2024 dossier.
- `satellite_passes.json` — no Sentinel-1 pass during any of the three floods (2025: S1A 3 Aug 06:30 WAT, ~13 h before the rain).
- `evidence.geojson` — your Task 12 output, with my `quote_check` flags and `meta.review` counts. Summarise by area and time;
  cite the strongest items. Say how many quotes are verified versus unverifiable.

## Rules
- Times in WAT (UTC+1). Label every number with its source (IMERG / EOT20 / NiMet / outlet), and "est."/"prob." where inferred.
- Casualties only as stated by named sources (2022: NEMA via Channels TV: seven dead). Not ClimaMeter's 191 for 2025.
- 2021 NiMet: the statement dates its 125 mm Oshodi / 66 mm Ikeja totals 15 Jul, but IMERG has 1–8 mm that day and 87–90 mm on
  the 16th. Present this as a probable date slip, not a fact.
- Write only the three `dossier.md` files. Don't touch `src/`, `event.json`, `evidence.geojson` or other folders. Don't commit.

Finish with: per event, the word count, the sections, and anything you couldn't reconcile between the inputs.
