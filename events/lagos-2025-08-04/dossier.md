# Event dossier — Lagos flood, 3–4 August 2025

Status: **draft** · compiled 2026-10-17 · times WAT (UTC+1)

## 1. What happened

Overnight **Sunday 3 Aug ~19:30 → Monday 4 Aug ~08:30**: about **13 h** of rain on **dry** ground (only 7–13 mm in the prior week). Flooding reported especially in **Ijede / Agric / Oko Ope (Ikorodu)** — homes and vehicles submerged, families displaced — and named more widely (Lekki, Ajah, Jakande, Okota, Eti-Osa, Ajegunle, Agege, Surulere, Alimosho) in Guardian NG and Channels TV lists.

Commissioner Tokunbo Wahab (Punch, 4 Aug): **12 hours** of intense rainfall, more expected. A later Punch piece (12 Aug) called it a **14-hour** torrential downpour in Ikorodu and blamed a contractor damming a waterway downstream. Guardian NG (8 Aug): officials inspected Ijede, Gberigbe and environs after **over 13 hours** of rain.

**Casualties:** no Nigerian outlet in the event sources stated a death toll. **ClimaMeter's 191 deaths is not used** (unverified against Nigerian reporting).

Ranked **#21** by population-weighted rain in the catalog. No Sentinel-1 pass *during* the rain.

## 2. Timeline

| When | What | Source |
|---|---|---|
| Prior 7 days | **7–13 mm** at the points (dry catchment) | IMERG v07 Final |
| **3 Aug 06:30** | S1A track 95 — ~13 h **before** rain (dry 'before' only) | Copernicus |
| 3 Aug 18:53 | S1A track 103 — still before onset; historically clips far east of the AOI | Copernicus; cf. 2024 dossier |
| **3 Aug ~19:30** | Rain begins, east (Epe/Lekki) moving west | IMERG (approx.) |
| **4 Aug 01:30** | Peak: **31 mm/h** over Lekki; AOI mean **7.9 mm/h**; weak high tide **+0.10 m** | IMERG + EOT20 |
| 4 Aug **05:00** | Second core **30 mm/h**, east Lagos Lagoon | IMERG |
| 4 Aug ~08:30 | Rain eases below 3 mm/h AOI mean | IMERG (approx.) |
| 4 Aug (day) | Viral video / reports: Ijede, Agric, Oko Ope underwater | Vanguard X, OSU recap, Channels |
| 4 Aug (day) | Wahab: 12 hours of intense rainfall | Punch, 4 Aug |

## 3. Rainfall (GPM IMERG v07 Final, 30-min, 0.1°)

Overnight window **3 Aug 09:00 → 4 Aug 09:00** (IMERG, mm) — use these, **not** `totals_mm.24h` (that field is the 24 h *ending at each point's peak*, so it cuts off most of the night after 01:30):

| Lekki | Lagos Island | Ikorodu | Ikeja |
|---|---|---|---|
| **146** | **123** | **103** | **77** |

Cause text: **120–160 mm** over Lekki / Lagos Island / Ikorodu. Prior 7 days: **7–13 mm**.

Intensity (IMERG):
- Onset ~19:30 on 3 Aug in the east, then west.
- **01:30 on 4 Aug:** Lekki cell **31 mm/h**; AOI mean **7.9 mm/h**. Analysis-point max at Lekki **31.5 mm/h** (`rainfall_summary.json`).
- **05:00:** second core **30 mm/h** over east Lagos Lagoon; Ikeja/Ikorodu point peaks **12.1 / 21.3 mm/h** around 05:00–05:30.
- Rain eases ~08:30. Duration ~13 h matches Wahab's "12 hours" (IMERG). Later "14-hour" wording (Punch 12 Aug) is the same night, rounded differently.

## 4. Tide (EOT20, offshore 6.4°N 3.52°E)

Astronomical tide only. Lagoon damping and ~1–3 h lag: see the 2024 dossier.

| Time | Offshore tide | Rain |
|---|---|---|
| 3 Aug 19:00 | −0.37 m (low) | onset ~19:30 |
| 4 Aug **01:00** | **+0.10 m (weak high)** | peak **01:30**, 31 mm/h |
| 4 Aug 05:00 | −0.17 m, falling | second core 30 mm/h |
| 4 Aug 06:00 | −0.22 m (low) | still raining |
| 4 Aug 13:00 | +0.32 m (afternoon high) | after rain had eased |

The 01:30 peak coincided with a **weak** high (**0.10 m**) — **little tidal contribution**. The second core fell on a **falling** tide toward the 06:00 low. Ijede/Ikorodu on the **north shore of Lagos Lagoon** could still see lagoon backwater; that is not modelled (open question).

## 5. Satellite imagery

No Sentinel-1 pass **during** the flood. The pass the catalogue and `event.json` flag is **S1A 3 Aug 06:30 WAT**, track 95 — **~13 h before** rain onset, usable only as a dry 'before' image. A second S1A at **18:53 WAT** (track 103) is still before 19:30 onset and, as in 2024, that track typically only clips the far east of the AOI.

Sentinel-2 **2 Aug 11:00 WAT** (day before): cloud **22 %** (T31NDH), **48 %** (NEH), **91 %** (NFH) — a possible land-cover / dry-before optical, not a flood image. **7 Aug** and **9 Aug**: ~99–100 % cloud.

## 6. Evidence (`evidence.geojson`, Task 12 + review)

22 features. Quote check: **6 verified** (OSU, Vanguard X, Punch 12 Aug, Vanguard 30 Aug); **16 unverifiable** (Guardian NG and Channels TV block automated checks). All `observed_at` are 4 Aug (day confidence).

By area:
- **Ikorodu north shore (Ijede, Agric, Oko Ope, Gberigbe):** strongest cluster. Verified: OSU ("floodwaters swallowed the Agric and Ijede communities"); Vanguard X (heavy flooding; resident in Oko Ope); Punch 12 Aug (14-hour downpour; blocked waterway); Vanguard 30 Aug (displaced families, 4 Aug). Unverified but consistent: Channels (houses and vehicles submerged in Ijede); Guardian inspection of Ijede / Gberigbe.
- **Peninsula / mainland lists:** Guardian (Ijede, Ikorodu, Jakande, Ajah, Okota, Lekki) and Channels (Lekki, Eti-Osa, Ajegunle, Agege, Surulere, Alimosho) — unverifiable quotes; Punch 4 Aug names **no streets**. Guardian Ajegunle was left off the map (Ikorodu vs Ajeromi ambiguity).

No death toll in these items. Punch 12 Aug Agboyi/Agiliti/Itowolo/Ajegunle are relocation advice, not mapped as flooded that night.

## 7. Cause (preliminary)

Heavy rain is the trigger; human drainage failures are the main amplifier of *where* it floods. Rain totals, peaks and tide phase do not separate flood days from no-flood days (`events/flood_vs_noflood.json`); the causes sources name are almost all drainage (Task 15). This event: ~13 h of overnight rain (19:30 3 Aug → ~08:30 4 Aug) on dry ground (7–13 mm prior week); AOI mean peak 7.9 mm/h at 01:30, cells to 31 mm/h; 120–160 mm over Lekki/Lagos Island/Ikorodu. The 01:30 peak coincided with a weak high tide (0.10 m) — little tidal contribution. Duration matches Wahab's "12 hours". (IMERG + EOT20; agrees with `event.json` `cause_prelim`.)

Named human causes:

- **Contractor dammed the downstream of an Ikorodu waterway for construction** — official (Tokunbo Wahab, Punch 12 Aug 2025), Gberigbe–Ijede outfall corridor. Status: `no imagery after event` (Wayback newest chip Nov 2024, before the ~Feb 2025 start).
- **Bridge construction at Agric, Ikorodu** — journalist / recap (Ohio State OIA 29 Sep 2025; National Daily 5 Aug 2025 names AFA Bridge / HiTech), Agric–Isawo Road. Status: `imagery supports` (2020-01 → 2025-04: corridor and earthworks in place before the flood; no post-flood image yet).
- **Abandoned unfinished drainage at Ijede** — resident (Punch 6 Aug 2025, Oko Ope to Abule Eko); official (Guardian 8 Aug) says the 12-month job was not abandoned. Status: `no imagery after event` (same Nov 2024 chip, before the works).

These are claims plus visible change, not measured drainage capacity. A cofferdam can vanish within days; imagery after the rain may miss it.

## 8. Open questions

- ClimaMeter's 191 deaths is unverified against Nigerian reporting — not used.
- Only Sentinel-1 pass highlighted (S1A, 3 Aug 06:30) is ~13 h before the rain — usable only as a dry 'before' image.
- Ijede/Ikorodu flooding may involve lagoon backwater from the Lagos Lagoon's north shore — not modelled.
- Media evidence: 16 of 22 quotes unverifiable (Guardian NG / Channels TV block automated checks).

## 9. Sources

- Punch, 4 Aug 2025 — Wahab, 12 hours: https://punchng.com/lagos-urges-calm-as-heavy-rainfall-persists/
- Punch, 12 Aug 2025 — Ikorodu blocked waterway: https://punchng.com/lasg-blames-blocked-waterway-for-ikorodu-flooding/
- Vanguard X, 4 Aug 2025: https://x.com/vanguardngrnews/status/1952406403252924608
- Vanguard, 30 Aug 2025 — Ijede/Ikorodu relief: https://www.vanguardngr.com/2025/08/ijede-ikorodu-flood-victims-get-relief-materials/
- Guardian NG, 5 Aug 2025: https://guardian.ng/news/nigeria/metro/ajah-ijede-lekki-others-submerged-after-downpour-in-lagos/
- Guardian NG, 8 Aug 2025 — inspection: https://guardian.ng/news/nigeria/metro/lasg-officials-inspect-ikorodu-drainage-project-allay-residents-fear-on-flash-flooding/
- Channels TV, 4 Aug 2025: https://www.channelstv.com/2025/08/04/lagos-communities-flooded-vehicles-submerged-after-marathon-rainfall/
- Ohio State OIA, 29 Sep 2025: https://oia.osu.edu/news/2025/09/29/documenting-floods-and-building-resilience-lagos
- Rain: GPM IMERG v07 Final · Tide: EOT20 · Passes: Copernicus catalogue
