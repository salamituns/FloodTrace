# Event dossier — Alimosho flood, 8–9 July 2022

Status: **draft** · compiled 2026-10-17 · times WAT (UTC+1)

## 1. What happened

Friday 8 and Saturday 9 July 2022: two days of citywide rain on already wet ground. NEMA, via Channels TV (13 Jul) and Punch/NAN (13 Jul): **seven people died in Alimosho** — three siblings (Michael, 18; Elizabeth, 17; Timi, 14) swept while moving from a room in an uncompleted Mercy of Christ Apostolic Church building, and four adults. Eight people were saved. NEMA named flooded Alimosho communities as **Oke Isagun, Agbado Oke, Oko LCDA**.

Separately, Punch/NAN reported a NEMA update of **two dead and four rescued at Oyatoki, Orile Agege**. BBC Pidgin (9 Jul) reported **two people missing** after a flood carried their car at Oke Oba / Fatoki, Agege, and quoted a Bello statement that flash flooding on old Oko-Oba Road followed **over-10-hour rainfall** overflowing a canal under expansion. Evidence notes do **not** treat the Agege deaths/missing as the same people as the Alimosho seven, or Oyatoki as the same incident as Fatoki/Oke Oba.

No Sentinel-1 pass during the flood. Ranked **#2** by population-weighted rain in the catalog (see `docs/LAGOS_PLAN.md`).

## 2. Timeline

| When | What | Source |
|---|---|---|
| Prior 7 days | 70–98 mm at the analysis points (wet catchment) | IMERG v07 Final |
| **8 Jul ~06:30** | Citywide rain begins | IMERG (`key_events` rain-onset-1, approx.) |
| 8 Jul 07:00–19:00 | Day-1 rain; AOI calendar total **70 mm** | IMERG |
| 8 Jul **12:30** | Core **47 mm/h** over Lagos Lagoon (north); AOI mean **7.6 mm/h** | IMERG |
| 8 Jul ~19:30 | Rain eases | IMERG (approx.) |
| **9 Jul ~06:00–16:00** | Day-2 rain; AOI calendar total **41 mm** | IMERG |
| 9 Jul **13:00** | Day-2 core **26 mm/h**, Lagos Island | IMERG |
| 9 Jul ~08:00 (approx.) | BBC Pidgin: car carried at Oke Oba / Fatoki; old Oko-Oba Road | BBC Pidgin, 9 Jul |
| 9 Jul (day) | NEMA: Alimosho communities flooded; seven dead (reported 13 Jul) | Channels TV / Punch |
| 13 Jul | NEMA statement published (seven dead, three siblings, four adults) | Channels TV, Punch |

Exact hour of the Alimosho deaths is not reported — which day's rain is an open question.

## 3. Rainfall (GPM IMERG v07 Final, 30-min, 0.1°)

Calendar-day / window totals (IMERG, mm) — **not** `rainfall_summary.json` `totals_mm.24h`, which is the 24 h *ending at each point's peak*:

| | 8 Jul | 9 Jul |
|---|---|---|
| AOI mean | **70** | **41** |
| Alimosho | **85** | **71** |
| Ibeju-Lekki | **152** | — |
| Lekki | **99** | — |
| Apapa | — | **80** |

Prior 7 days: **70–98 mm** at the points (IMERG). Alimosho cell over the two days: **85 + 71 mm**.

Intensity (IMERG):
- Day 1: rain ~07:00–19:00; grid core **47 mm/h at 12:30** over the lagoon (north of the island). AOI mean peaks **7.6 mm/h** at the same time.
- Day 2: rain ~06:00–16:00; **26 mm/h at 13:00** at Lagos Island.
- Analysis-point peaks (`rainfall_summary.json`): Ibeju-Lekki **38.2 mm/h at 10:00 on 8 Jul**; Alimosho **18.4 mm/h at 12:30 on 8 Jul**; Lagos Island **26.0 mm/h at 13:00 on 9 Jul**. ~10 km cells smooth point intensities.

## 4. Tide (EOT20, offshore 6.4°N 3.52°E)

Astronomical tide only (no surge). Lagoon damping ≈ **0.34 × ocean at UNILAG**, **0.65 × at Ojo**; lag **~1–3 h (est.)** — see the 2024 dossier. Not lagoon water level.

| Time | Offshore tide | Rain |
|---|---|---|
| 8 Jul 05:00 | −0.45 m (low) | before onset |
| 8 Jul 07:00 | −0.20 m, rising | rain underway |
| 8 Jul **12:00** | **+0.52 m (high)** | core at **12:30** (47 mm/h) |
| 8 Jul 18:00 | −0.45 m (low) | rain easing |
| 9 Jul 06:00 | −0.43 m (low) | day-2 rain starts |
| 9 Jul **13:00** | **+0.56 m (high)** | day-2 core **26 mm/h** |
| 9 Jul 19:00 | −0.56 m (low) | after rain |

**Compound timing:** both days' cores fell **within an hour of high tide** (12:00 / 13:00). Rain–tide compounding is **plausible near the lagoon**. Alimosho (where the deaths were) is **~20 km inland**, so local drainage/canals are more likely there than tidal lock of lagoon outfalls.

## 5. Satellite imagery

No Sentinel-1 GRD pass **during** the flood (`satellite_passes.json`). Nearest S1A:
- **7 Jul 19:02 WAT**, track 1 — evening before day-1 rain (not during).
- **14 Jul 06:30 WAT**, track 95 — five days after.

Sentinel-2 on **9 Jul 11:00 WAT**: ~99–100 % cloud (tiles T31NDH/NEH/NFH). 4 Jul 72–84 % cloud; 14 Jul 79–98 %. Optical is unusable for flood extent.

## 6. Evidence (`evidence.geojson`, Task 12 + review)

14 features. Quote check (`meta.review` / `quote_check`): **9 verified** (verbatim match, Punch and BBC Pidgin spot-checked); **5 unverifiable** (Channels TV blocked automated access). Times are mostly `day` (9 Jul) except BBC Pidgin Agege items (`approx`, ~08:00).

By area:
- **Alimosho (Oke Isagun, Agbado Oke, Oko LCDA; church building):** NEMA via Channels (unverified quotes) and Punch (verified): seven dead; three siblings named; communities listed.
- **Oyatoki, Orile Agege:** Punch/NAN (verified): two died, four rescued — kept separate from the Alimosho seven.
- **Oke Oba / Fatoki / old Oko-Oba Road, Agege:** BBC Pidgin (verified): two missing in a car; canal overflow after >10 h rain.

Strongest items: Punch ev-006 / ev-007 (NEMA seven dead + church); Punch ev-011 (Oyatoki two dead); BBC Pidgin ev-012–014 (same-day Agege canal). Unresolved in the file: which of Oke Isagun / Agbado Oke / Oko LCDA contains the church; Oyatoki vs Fatoki possibly the same Agege canal incident (not merged).

## 7. Cause (preliminary)

Heavy rain is the trigger; human drainage failures are the main amplifier of *where* it floods. Rain totals, peaks and tide phase do not separate flood days from no-flood days (`events/flood_vs_noflood.json`); the causes sources name are almost all drainage (Task 15). This weekend: two days of citywide rain on wet ground (70–98 mm in the prior 7 days): 8 Jul 07:00–19:00 (AOI 70 mm, cores to 47 mm/h over the lagoon), 9 Jul 06:00–16:00 (AOI 41 mm). Both days' cores fell within an hour of high tide (12:00, 13:00) — rain–tide compounding plausible near the lagoon; Alimosho (where the deaths were) is ~20 km inland, so local drainage/canals more likely there. Alimosho cell: 85 + 71 mm. (IMERG + EOT20; agrees with `event.json` `cause_prelim`.)

Named human causes:

- **Oko-Oba Canal Channel under expansion overflowed** — official (Tunji Bello, via BBC Pidgin 9 Jul 2022), old Oko-Oba Road / Agege. Status: `weak support`. The canal, traced on imagery, is a narrow, overgrown open channel. Google Open Buildings shows ~13% of the land within 10 m already built by 2016 and unchanged through 2023, so encroachment predates the record (matching the state's Oct 2022 "infringed channel" notices). No widened section is visible by May 2025. Imagery can't show the overflow itself.
- **Canal construction described as slow** — resident / eyewitness (BBC Pidgin 9 Jul 2022), Fatoki / Agege. Status: `not checked` (same unmapped channel).

These are claims plus (for later events) visible change, not measured drainage capacity. The Oko-Oba alignment is now the open channel traced on imagery, running north from the Agric Road bridge behind Abimbola Awoniyi Estate, not the road.

## 8. Open questions

- Exact timing of the deaths in Oke Isagun / Agbado Oke is not reported — which day's rain?
- Alimosho is inland: was the killer flood a canal/stream overflow (local drainage) rather than tide-locked lagoon outflow?
- No Sentinel-1 pass during the flood (none within the window).
- Media evidence: 9 of 14 quotes verified; 5 behind blocked sites (see evidence `meta.review`).

## 9. Sources

- Channels TV, 13 Jul 2022 — NEMA: seven dead (three siblings, four adults): https://www.channelstv.com/2022/07/13/lagos-flood-killed-three-siblings-four-adults-nema/
- Punch, 13 Jul 2022 — same NEMA briefing (NAN): https://punchng.com/lagos-flood-killed-three-siblings-four-adults-nema/
- BBC Pidgin, 9 Jul 2022 — Agege missing / Oko-Oba Road: https://www.bbc.com/pidgin/articles/crgw8vrgjdeo
- Vanguard, 15 Jul 2022 — citywide rain, no named Lagos streets (omitted from the evidence map): https://www.vanguardngr.com/2022/07/jandors-comical-ignorance-on-lagos-floods/
- Rain: GPM IMERG v07 Final (`rainfall_imerg.json`, `rainfall_summary.json`)
- Tide: EOT20 offshore (`tide_eot20.json`)
- Passes: Copernicus catalogue (`satellite_passes.json`)
