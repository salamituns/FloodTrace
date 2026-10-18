# Event dossier — Lagos flash flood, 3 July 2024

Status: **data inventory (draft)** · compiled 2026-10-16 · all times WAT (UTC+1) unless noted

## 1. What happened (documented)

| When | What | Source |
|---|---|---|
| 26–27 Jun 2024 | 48-hour rainfall floods Agungi / Lekki environs — catchment already wet going into July | Vanguard, 27 Jun 2024 |
| **3 Jul ~03:00** | Heavy rain begins ("around 3 am on Wednesday"), lasts many hours | ThisDay, 3 Jul 2024 |
| 3 Jul, morning | Flooding citywide: Third Mainland Bridge entrances, Iyana-Oworo/Alapomeji, Ketu-Alapere, Oshodi-Mafoluku, Aboru, Iyana Ipaja, Iyana Iba, Isheri/Idimu-LASU, Ijegun-Abaranje, Ikate, Egbeda-Akowonjo, Jakande Estate, Ogba, Okota, Lekki-Ajah axis | ThisDay |
| 3 Jul, morning | Ibeju-Lekki: Epe, Eredo, Bogije, Labora, Abijon, Sangotedo, Awoyaya, Ibeju-Lekki Expressway, Abraham Adesanya, Majek; homes submerged, residents displaced | Daily Trust, 3 Jul 13:05 |
| 3 Jul | Commissioner Tokunbo Wahab (on X): "flash flood… due to the high intensity of the rain", long duration, **high tidal level in the lagoon** stopping drainage; expected to clear in 1–2 h; EFAG team deployed to Alapomeji | ThisDay |
| ~7 Jul | "10-hour rainfall" — Lekki and Ikoyi residents flee homes | Punch, 7 Jul 2024 (not machine-readable; verify manually) |

**Date correction:** the Wikipedia article ("2024 Lekki flood") dates the event 4 July, but nearly all of its cited
sources are dated 3 July and describe rain starting early on Wednesday 3 July. Treat **3 July** as the primary event
date until contradicted.

No rainfall totals, water depths or casualty figures have been found in the sources reviewed so far.

## 2. Evidence available

| Dataset | Coverage for this event | Access | Notes |
|---|---|---|---|
| **Sentinel-1A SAR** (GRD, IW) | **3 Jul 05:30 UTC (06:30 WAT)**, track 95 — during the rain. Same-track baseline 21 Jun; follow-up 15 Jul. A second pass 3 Jul 17:53 UTC (track 103) only clips the far east of the AOI (lon ≥ 4.10°, Epe) | Copernicus Data Space or Planetary Computer | Lucky timing. Dense urban areas give double-bounce returns, so detection is reliable in open/low-rise areas and unreliable between buildings |
| Sentinel-2 optical | 3 Jul 10:00 UTC — **99.99 % cloud** (28 Jun 90 %, 8 Jul 100 %, 13 Jul 95 %) | Copernicus Data Space | Unusable for the event; useful for land cover |
| **GPM IMERG** rainfall | 30-min, ~10 km, final run available | NASA Earthdata, **free login needed** | Primary rainfall record |
| ERA5 (via Open-Meteo) | Hourly, ~25 km. Shows ~2–5 mm/h spread over 2–4 Jul (≈104 mm over 5 days) | Open, no key | Reanalysis smooths convective bursts — **underestimates intensity**; context only |
| Ocean tide (Open-Meteo marine) | Hourly. 3 Jul: high **+0.32 m at 02:00**, low −0.40 m at 08:00, high **+0.53 m at 14:00** | Open, no key | Offshore model point; lagoon tide is damped and lagged (to be quantified) |
| Terrain | Copernicus GLO-30 (open, AWS); FABDEM bare-earth (free, **non-commercial licence**) | Open | Vertical error ~1–3 m — same order as flood depths |
| Buildings | Google Open Buildings v3, Microsoft footprints, OSM | Open | Exposure + structure counts |
| Drainage | OSM waterways/canals; Lagos State drainage "systems" (e.g. System 156 cited by Wahab) | OSM open; state data **not public** | Key gap |
| Media / social | News photos & video (ThisDay, Daily Trust, TheCable, BBC Pidgin, Daily Post, Punch), X posts incl. @tokunbowahab | Manual collection | Main ground truth for a flash flood: geolocate + timestamp each item |

### Sentinel-1 results (`sar/`, `pipeline/sar_flood.py`)

- **Rain cells on the lagoon at 06:30 WAT, 3 Jul:** ~171 km² of permanent water brightened > 4 dB versus 21 Jun —
  surface roughening by heavy rain, concentrated over western Lagos Lagoon (central Lagos). Independent, timestamped
  evidence of intense rain ~3.5 h after the reported onset. (`rain_cells.geojson`)
- **Open-ground flooding is small:** ~7 km² (3 km² of it receded by 15 Jul), mostly wetland fringes of the eastern
  lagoons. None detected within 2 km of the Lekki, Lagos Island or Ibeju-Lekki points — consistent with a short-lived
  flash flood and with SAR's blindness in dense built-up areas, so **not** evidence that streets stayed dry. (`flood.geojson`)
- **Surface wetting** (~234 km², +3 dB on land) is wet soil/surfaces after rain; kept separately, not used as flood evidence. (`wetting.geojson`)
- **Limits:** 20 % of the AOI (west, toward Badagry) is outside the swath; the wind-roughened Atlantic doesn't classify
  as water at −16 dB, so rain cells over the sea are not detectable with this method.

### GPM IMERG v07 Final rainfall (`rainfall_imerg*.json`, `pipeline/imerg.py`)

30-min, 0.1° (~10 km) cells; times are interval starts, WAT. 624/624 steps from the Final run.

| | Lekki | Lagos Island | Ikeja | Ibeju-Lekki | AOI mean |
|---|---|---|---|---|---|
| Jul 2, 11:00–15:30 burst (peak) | **22.2 mm/h** at 11:30 | **22.0** at 12:00 | 5.1 | 12.0 | 4.4 |
| Jul 3 morning peak | 2.4 at 07:00 | 6.3 at 06:30 | **10.7 at 06:30** | — | 3.9 at 06:30 |
| 7-day antecedent before Jul 2 18:00 | 136 mm | 142 mm | 119 mm | 96 mm | 100 mm |

What it shows:
1. **Jul 3 rain onset ≈ 04:00 on the mainland** (Ikeja ≥ 1 mm/h from 04:00, peak 06:00–07:30), consistent with ThisDay's
   "around 3 am" given ~10 km / 30-min smoothing. TheCable's unverified "around 2am" is not supported.
2. **Independent cross-check:** IMERG's morning peak (06:00–07:00) coincides with the Sentinel-1 rain cells at 06:30 over
   western Lagos Lagoon, and with the 03:00–09:00 peak in media reports. Three independent sources agree on timing.
3. **An intense core over Apapa / Mile 2, then long duration everywhere.** The grid (not the four analysis points) peaks at
   **31 mm/h at 07:30** in the cell centred 6.45°N 3.35°E (Apapa–Mile 2–Ajegunle), with **19–31 mm/h sustained 06:00–08:30**
   (≈ 50 mm in ~2.5 h); a second core reached 28 mm/h at 08:00 around 6.35°N 3.15°E (Ojo / Badagry Expressway side).
   After the morning core, 3–5 mm/h persisted across the AOI until ~18:00 (cf. Punch "10-hour rainfall").
   *Correction (2026-10-17):* an earlier draft said no Jul 3 cell exceeded ~11 mm/h — that was true only at the four analysis
   points (Lekki, Lagos Island, Ikeja, Ibeju-Lekki), which all sit outside the core.
4. **A heavier but shorter burst hit Lekki / Lagos Island the day before (Jul 2, 11:00–15:30, ~22 mm/h).** Not yet matched
   to any report — a gap to check (were there Jul 2 floods?), and it adds to the antecedent wetness.
5. **The catchment was already very wet:** ~100–140 mm in the preceding 7 days (incl. the 26–27 Jun rain).

**Tidal lock — revised assessment:** the offshore high tide (+0.32 m) was at ~02:00, *before* the rain; during the morning
peak (06:00–07:30) the offshore tide was **falling toward low water (−0.40 m at 08:00)**. A morning tidal lock therefore needs
the lagoon to lag the ocean by ~3–5 h, which is plausible for Lagos Lagoon but unmeasured. The afternoon is a stronger
candidate: sustained 3–7 mm/h rain coincided with the larger high tide (+0.53 m at 14:00). Status: **not supported for the
morning without lagoon levels; plausible for the afternoon.**

### Lagoon tide: what's known (literature search, 2026-10-17)

- **Damping is measured:** lagoon tide range ≈ **0.34 × ocean at the UNILAG gauge** (central Lagos Lagoon) and **0.65 × at
  Ojo** (west), from observed gauge ratios cited in a recent inundation study. So the +0.32 m offshore high at 02:00 was only
  ~+0.11 m in the central lagoon. Badejo's 12-gauge, 29-day survey (2014) exists but its full text (with any time lags) wasn't accessible.
- **Lag is not published in anything reachable.** A first-order estimate: a shallow-water tide wave (c = √(g·h), h ≈ 3 m →
  ~5 m/s) needs ~45 min to reach UNILAG (~15 km from the Commodore Channel) and ~1.5 h to Ikorodu; friction in a 2–4 m deep
  lagoon adds to that. **Order of 1–3 h**, not the 3–5 h a morning tidal lock would need. *Estimate, not measurement.*
- **The morning rain core was beside the harbour**, not deep in the lagoon: Apapa / Mile 2 drains to Badagry Creek and the
  harbour, where tide follows the ocean closely. During its 06:00–08:30 peak the harbour tide was **falling toward low water
  (08:00)**, i.e. the most favourable outfall conditions of the day.

**Assessment of hypothesis 1 (tidal lock):** for the *morning* flooding — the bulk of the reports — the evidence points to
**rain intensity on saturated ground and drainage capacity, not tidal lock**. Tidal lock remains plausible for (a) the
*afternoon* (rain continuing into the +0.53 m high at 14:00) and (b) the eastern lagoon shore, where the lag is longest.
Confidence: moderate; decisive evidence would be a lagoon water-level record for 3 Jul 2024 (NIOMR / NIWA gauges — not public).

Sources: Badejo et al., *Tidal characteristics and sounding datum variation in Lagos State* (ResearchGate 273699298);
Badejo & Akintoye, *High and low water prediction at Lagos Harbour*, Nigerian Journal of Technology (2017, AJOL 159326).

### 2 July check (Task 05, negative result)

No news, official or social report found of flooding at a named location on Tue 2 Jul 2024 (Punch, Vanguard, Guardian NG,
Premium Times, Channels TV, ThisDay, Nairametrics, Pulse, BusinessDay, Ripples, Investors King, LASEMA / Ministry of
Environment, public X search). The IMERG midday burst over Lekki / Lagos Island may have caused unreported nuisance flooding;
it certainly added to antecedent wetness. Relevant side-finding: ThisDay (4 Jul) reports the **lagoon had been rising "since
last week"** — a raised lagoon *baseline* from a week of rain (fluvial/runoff), distinct from the daily tide, which would make
outfalls sluggish regardless of tide phase. Worth testing with Sentinel-1 lagoon-edge comparisons across late June.

## 3. Hypotheses this event lets us test

1. **Tidal lock:** rain onset (~03:00) coincided with high tide (~02:00–03:00 offshore); peak rain fell while the lagoon was
   still high, so outfalls couldn't discharge. → Needs the lagoon tide lag + IMERG intensity timing.
2. **Antecedent saturation:** the 26–27 Jun rain left drains/soils full. → IMERG 7-day antecedent totals.
3. **Drainage obstruction:** Ibeju-Lekki flooding tied to blocked drains and construction (residents, Daily Trust); Lekki
   tied to building over a drainage channel (Wahab). → Map flooded reports against OSM drains + new construction (Sentinel-2 change).
4. **Low-lying exposure:** reported locations sit in depressions / reclaimed land. → Reported points vs. FABDEM height-above-drainage.

## Cause (preliminary)

Heavy rain is the trigger; human drainage failures are the main amplifier of *where* it floods. Rain totals, peaks and tide phase do not separate flood days from no-flood days (`events/flood_vs_noflood.json`); the causes sources name are almost all drainage (Task 15). This morning: intense rain on saturated ground (IMERG core 19–31 mm/h over Apapa/Mile 2, 06:00–08:30); tidal lock unlikely for the morning, possible for the afternoon (`event.json` `cause_prelim`).

Named human causes:

- **Buildings / developers blocked System 156** — official (Tokunbo Wahab, Vanguard / MoE 27 Jun 2024), Alpha Beach Road corridor. Status: `imagery supports` (2020-04 → 2024-11: wetland/settlement along the line cleared and sand-filled, new building and estate grid). Sentinel-2 dates it: wet-season vegetated fraction at the south end fell 0.38 (2018) → 0.28 (2020) → 0.17 (2022) → 0.12 (2024) → 0.08 (2025), steepest 2021–22. Most of the clearance therefore **predates** the flood and the state's June 2024 excavation; the decline continued afterwards (`events/drainage_sites_s2.json`). Google Open Buildings shows the same years: built cover within 10 m of the mapped System 156 drains rose from 3.6% (2016) to 9.4% (2023), mostly 2019–22, higher than 88% of comparable urban channel stretches (`events/drainage_sites_buildings.json`). So the land beside the channel was cleared and built on before the flood.
- **Agungi collector too small; road development outgrew the drain** — official (Wahab, Vanguard / Arise / MoE Jun–Jul 2024), Agungi–Ajiran Road. Status: `imagery inconclusive` (weak support: infill and a new estate at the lagoon end; collector itself not visible).
- **Refuse blocked water paths at Olopomeji** — official / emergency responders (Punch 7 Jul 2024; EFAG), Iyana Oworo approach to Third Mainland. Status: `imagery inconclusive` (refuse in an open path).
- **Buildings on drainage channels in Sangotedo** — official (Wahab, 23 Jun 2024 notices; Independent 24 Jun: "Sangotedo by Lagos Business School"; later named System 63b). Status: `imagery inconclusive` (channel centreline not in OSM; point moved from the town centroid to LBS).
- **Road rehabilitation at Sangotedo, Awoyaya, Majek, Abraham Adesanya** — journalist (Daily Trust / NAN 3 Jul 2024). Status: `imagery inconclusive` (road-works claim).
- **New site with no drainage at Labora** — resident (Rasheed Ayobami / Bola Fadugba, Daily Trust 3 Jul 2024), now Abijo GRA not the forest point. Status: `not checked` (Task 18 chip was the wrong geocode).
- **Blocked drains on the Ibeju-Lekki Expressway** — resident (Seyi Arowosaye, Daily Trust 3 Jul 2024). Status: `imagery inconclusive` (covered roadside drains).

These are claims plus visible change, not measured drainage capacity.

## 4. Open gaps

- IMERG download needs a NASA Earthdata account.
- Exact flood start/end times per neighbourhood — needs timestamped media.
- Lagoon (not ocean) water levels — no open gauge found yet.
- Lagos State drainage network — not public.
