# Event dossier — Lagos Island flood, 16 July 2021

Status: **draft** · compiled 2026-10-17 · times WAT (UTC+1)

## 1. What happened

**Friday 16 July 2021:** roughly **12 h** of rain (IMERG 06:00–18:00), heaviest 10:00–17:00. Media often said **~4 h** — likely the peak period people noticed. Flooding concentrated on **Lagos Island / Marina car parks** (vehicles submerged), **Victoria Island / Ikoyi** (Alfred Rewane, Akin Adesola, Ozumba Mbadiwe, Law School–Bonny Camp), and the **Lekki–Ajah** axis (Jakande Estate, Lekki Phase 1, Awoyaya, Ajah), with mainland reports from Oshodi, Agege/Abule Egba, Ketu–Alapere, airport service lane.

LASTMA timed several island snarl-ups to **~14:00** and **18:03** (Alfred Rewane). Vanguard: 18 passengers rescued after a boat capsized in rain and high waves leaving Five Cowries Terminal, Ikoyi. No Lagos death toll in the named sources (Punch 24 Jul death figures are Europe/China/US — omitted).

NiMet (TheCable, 21 Jul) called the flood "highly unfortunate but expected" and quoted **125 mm at Oshodi / 66 mm at Ikeja**, **dated 15 Jul** in the statement. IMERG has **1–8 mm on 15 Jul** and **87–90 mm on 16 Jul** at those points — treat the statement date as a **probable slip**, not a fact (see §3).

The 16 Jul 2021 event was **#87** in the four-point rain scan and **#25** by population-weighted rain — easy to miss without exposure weighting.

## 2. Timeline

| When | What | Source |
|---|---|---|
| 15 Jul | IMERG **1–8 mm** (not the flood day) | IMERG |
| **16 Jul ~06:00** | Rain begins offshore/east | IMERG (approx.) |
| 16 Jul 09:00 | Offshore **high +0.59 m** | EOT20 |
| 16 Jul **12:00** | AOI mean peak **9.9 mm/h**, rain over the whole city; tide already falling (**+0.20 m**) | IMERG + EOT20 |
| 16 Jul ~14:00 | LASTMA: standstill Akin Adesola–Law School; slow on Ozumba Mbadiwe | Punch, 17 Jul |
| 16 Jul **15:00** | Offshore **low −0.39 m** | EOT20 |
| 16 Jul **16:00** | Core **40 mm/h** over Ikotun/Egbeda (west of Oshodi) | IMERG |
| 16 Jul ~16:00 | LASTMA: Oju-Odo almost overflowing the bridge; Ekoro heavy | Punch, 17 Jul |
| 16 Jul ~18:00 | Rain eases | IMERG (approx.) |
| 16 Jul 18:03 | LASTMA video: Alfred Rewane Road, Ikoyi, flooded | Punch, 17 Jul |
| 16 Jul (day) | Marina car parks submerged; Lekki/Jakande/Ajah | Channels, Punch, Nairametrics |
| 21 Jul | NiMet: rain "was expected"; 125 / 66 mm (dated 15 Jul) | TheCable |

## 3. Rainfall (GPM IMERG v07 Final, 30-min, 0.1°)

Calendar-day totals (IMERG, mm):

| | 15 Jul | 16 Jul |
|---|---|---|
| AOI mean | — | **74** |
| Lagos Island | — | **105** |
| Apapa | — | **106** |
| Oshodi | — | **90** |
| Ikeja | — | **87** |
| Points generally | **1–8** (task table; `event.json` uses **5–8** at Oshodi/Ikeja) | **~90–105** at every analysis point (cause text) |

`totals_mm.24h` in `rainfall_summary.json` is the 24 h *ending at each point's peak* (e.g. Lagos Island 88 mm, Ikeja 72 mm) — do not present those as calendar-day totals.

Intensity (IMERG):
- ~12 h, 06:00–18:00; heaviest **10:00–17:00**.
- AOI mean **9.9 mm/h at 12:00**.
- Grid core **40 mm/h at 16:00** over Ikotun/Egbeda, west of Oshodi.
- Point peaks: Apapa **32.2 mm/h** and Lagos Island **28.4 mm/h** at 16:00; Ikeja **31.7 mm/h** at 16:30; Oshodi **25.9 mm/h** at 15:30.

**NiMet vs IMERG (prob. date slip):** the statement dates 125 mm Oshodi / 66 mm Ikeja to **15 Jul**. IMERG has **1–8 mm that day** and **87–90 mm on the 16th**. If the totals belong to the 16th: Oshodi IMERG **90** vs gauge **125** (−28 %); Ikeja IMERG **87** vs **66** (+32 %). Present as a probable slip, not as two different storms.

Media "~4 h" vs IMERG ~12 h (~6 h heavy): likely the hours people noticed.

## 4. Tide (EOT20, offshore 6.4°N 3.52°E)

Astronomical tide only. Lagoon damping and ~1–3 h lag: see the 2024 dossier.

| Time | Offshore tide | Rain |
|---|---|---|
| 16 Jul 03:00 | −0.66 m (low) | before onset |
| 16 Jul 06:00 | +0.01 m, rising | rain begins |
| 16 Jul **09:00** | **+0.59 m (high)** | rain increasing |
| 16 Jul **12:00** | **+0.20 m, falling** | AOI mean peak 9.9 mm/h |
| 16 Jul **15:00** | **−0.39 m (low)** | still in heavy window |
| 16 Jul 16:00 | −0.38 m | Ikotun/Egbeda 40 mm/h |
| 16 Jul 21:00 | +0.37 m (evening high) | after rain |

The midday peak fell on a **falling tide** (high 09:00, low 15:00) — **like 2024**, rain-driven rather than tide-locked. Harbour / Marina outfalls would have been improving through the afternoon, not locking.

## 5. Satellite imagery

No Sentinel-1 pass **during** the flood. Nearest S1A:
- **12 Jul 19:02 WAT**, track 1 — four days before.
- **19 Jul 06:30 WAT**, track 95 — three days after.

Sentinel-2 **14 Jul 11:00 WAT**: 72–93 % cloud. **19 Jul 11:00**: 80–99 % cloud. No usable optical flood map.

## 6. Evidence (`evidence.geojson`, Task 12 + review)

51 features. Quote check: **43 verified**; **3 unverifiable** (Channels TV article + TheCable NiMet; publishers block automated access); **5 headline-only** (Channels YouTube; Punch X) with no quote to check. Open-questions line: "43 of 51 quotes verified."

By area and time:
- **Lagos Island / Marina / Apongbon / Adeniji-Adele:** Channels (unverified quote) and Punch/Nairametrics/Daily Trust (verified): vehicles submerged in car parks. Same-day coverage (16 Jul).
- **VI / Ikoyi (timed):** LASTMA ~14:00 Akin Adesola and Ozumba Mbadiwe; **18:03** Alfred Rewane (time_confidence `exact`). Strongest timing in the set.
- **Lekki–Ajah / Jakande / Awoyaya:** Punch 24 Jul (verified): households displaced; water "gushing out from the floor" at Oba Elegushi New Market; worst-hit island list.
- **Mainland:** LASTMA ~16:00 Oju-Odo / Ekoro / Oluwaga; airport service lane; Alapere–Ogudu; Nairametrics list (Agege, Iju Road, Oshodi, Ilupeju, Ogudu, Ketu).
- **Five Cowries Terminal:** Vanguard (verified): boat capsize, 18 rescued — rain and waves, not a street-flood depth.
- **NiMet gauges:** TheCable (unverified quotes), dated 15 Jul — rainfall, not a street.

Jakande is Eti-Osa/Lekki, not Isolo. Magboro (Ogun) and out-of-state floods omitted.

## 7. Cause (preliminary)

Heavy rain is the trigger; human drainage failures are the main amplifier of *where* it floods. Rain totals, peaks and tide phase do not separate flood days from no-flood days (`events/flood_vs_noflood.json`); the causes sources name are almost all drainage (Task 15). This day: ~12 h of rain (06:00–18:00 Fri 16 Jul), heaviest 10:00–17:00 (AOI mean to 9.9 mm/h at 12:00; 40 mm/h cell over Ikotun/Egbeda at 16:00); ~90–105 mm at every analysis point. The midday peak fell on a falling tide (high 09:00, low 15:00) — like 2024, rain-driven rather than tide-locked. (IMERG + EOT20; agrees with `event.json` `cause_prelim`.)

Named human causes:

- **Road construction at Alapere inwards Ogudu Car Wash** — official (LASTMA, Punch/ThisDay 17 Jul 2021), Lagos–Ibadan / Ogudu Road. Status: `imagery inconclusive` (road-works claim; no named canal).
- **Marina has no drainage system** — resident (Okechukwu Chuckwu, Punch 17 Jul 2021), Marina Road from Kakawa. Status: `imagery inconclusive` (covered/kerbside drains; absence of drainage is not a surface change).

These are claims plus visible change, not measured drainage capacity. 2021 coverage names few human causes; that is as likely a reporting pattern as a different flood.

## 8. Open questions

- Media say '~4 h' of rain; IMERG shows ~12 h, with ~6 h of heavy rain — likely the peak period people noticed.
- NiMet totals (125 mm Oshodi, 66 mm Ikeja) are dated 15 Jul, but IMERG has only 5–8 mm on 15 Jul and 87–90 mm on 16 Jul — the statement's date likely means the 16th. If so: Oshodi IMERG 90 vs gauge 125 (−28 %), Ikeja 87 vs 66 (+32 %).
- No Sentinel-1 pass during the flood.
- Media evidence: 43 of 51 quotes verified.

## 9. Sources

- Channels TV, 16 Jul 2021: https://www.channelstv.com/2021/07/16/vehicles-submerged-on-lagos-island-amid-heavy-downpour/
- Channels TV YouTube (headline only): https://www.youtube.com/watch?v=7ZCqbpTTtk0
- Punch, 17 Jul 2021 — LASTMA / gridlock: https://punchng.com/flood-fallen-trucks-cause-lagos-gridlock-commuters-stranded/
- Punch, 24 Jul 2021 — Jakande / Lekki: https://punchng.com/rains-pound-europe-us-china-houses-submerged-cars-washed-away-over-200-killed/
- Punch X, 16 Jul 2021: https://x.com/MobilePunch/status/1416140356941455360
- TheCable, 21 Jul 2021 — NiMet: https://www.thecable.ng/nimet-lagos-flood-highly-unfortunate-but-expected/
- Nairametrics, 16 Jul 2021: https://nairametrics.com/2021/07/16/flood-hits-parts-of-lagos-ogun/
- Vanguard, 16 Jul 2021 — boat: https://www.vanguardngr.com/2021/07/18-passengers-escape-death-as-boat-capsizes-amid-heavy-rainfall-in-lagos/
- FloodList, 20 Jul 2021: https://floodlist.com/africa/nigeria-floods-taraba-july-2021
- Daily Trust, 21 Aug 2021: https://dailytrust.com/flood-wreaks-havoc-in-5-states-9-dead-hundreds-rendered-homeless/
- Rain: GPM IMERG v07 Final · Tide: EOT20 · Passes: Copernicus catalogue
