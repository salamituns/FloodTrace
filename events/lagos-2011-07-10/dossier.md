# Event dossier — Lagos flood, 10 July 2011

Status: **draft** · compiled 2026-10-17 · times WAT (UTC+1)

## 1. Documented
- Sunday 10 July 2011, ~15–20 h of rain. NEMA: "not less than 20 people including children" killed (via AFP/Space Daily);
  Vanguard (12 Jul): 25 corpses recovered including 11 children; 28 families homeless in Ajegunle after four buildings collapsed.
- Areas named (Task 08 review): Dopemu, Aboru, Agbado-Oke Odo, Ogba, Agege, Orile-Agege, Iyana-Ipaja, Ikoyi, Victoria Island,
  Apapa, Lekki, Ajegunle, Jakande Estate (Oke-Afa, Isolo). Media evidence collection: Task 09 (in progress).
- Ranked **#1** of 287 candidates in the 2000–2026 IMERG rainfall scan (192 mm in a day at the Lagos Island cell).

## 2. Reconstruction
**Rain (GPM IMERG v07 Final, 30-min, 0.1°):** heavy rain ~07:00–23:00 (≈16 h — matches reports). Two cores:
- **Morning, 08:00–11:00:** 44 mm/h at 09:30 (Lagos Island / Apapa cells), 26–30 mm/h widely.
- **Evening, ~17:00:** 45.6 mm/h over the Ikeja / Oshodi cell (6.55°N 3.35°E), then 8–12 mm/h until ~21:00.
Peaks ~1.5× the 2024 event's, and about twice as long, citywide.

**Tide (EOT20, offshore point; validated against Open-Meteo for 2024: r = 0.966, RMSE 0.11 m, no lag):**

| Time | Offshore tide | Rain (Apapa cell) |
|---|---|---|
| 06:00 | −0.41 m (low) | 0.2 mm/h |
| 09:00 | +0.07 m, rising | 26.0 |
| 10:00 | +0.28 m, rising | 28.9 |
| 12:00 | **+0.53 m (high)** | 7.6 |
| 17:00 | −0.34 m, falling | 24.8 |
| 19:00 | −0.54 m (low) | 8.9 |

**Compound timing:** the morning core fell on a **rising tide into the 12:00 high**; with a lagoon lag of ~1–3 h (estimate —
see the 2024 dossier) lagoon levels would peak ~13:00–15:00, as runoff from the morning core was still draining. This is the
pattern a tidal-lock explanation needs, and it is **the opposite of 2024**, whose morning core fell on a falling tide.
The evening core fell on a falling tide (favourable outfall conditions). Caveats: offshore astronomical tide only (no surge),
lagoon damping ≈ 0.34–0.65 × and lag unmeasured.

## Cause (preliminary)

Heavy rain is the trigger; human drainage failures are the main amplifier of *where* it floods. Rain totals, peaks and tide
phase do not separate flood days from no-flood days (`events/flood_vs_noflood.json`); the causes sources name are almost all
drainage (Task 15). This day: ~16 h of rain (07:00–23:00) with two intense cores (44 mm/h at 09:30, 45.6 mm/h at 17:00); the
morning core fell on a rising tide into the 12:00 high — plausible rain–tide compounding (EOT20 + IMERG; agrees with
`event.json` `cause_prelim`). Ranked **#1** of 287 IMERG candidates (192 mm in a day at the Lagos Island cell).

Named human causes:

- **Heavy rain as a monthly total in one day** — expert (Dr Regina Folorunsho, NIOMR, Vanguard 15 Jul 2011), citywide. Status:
  `not checked` (rainfall claim, not a drain).
- **Channels locked by high tide in the Atlantic and lagoon** — official (Tunji Bello, Vanguard 15 Jul 2011), citywide.
  Status: `not checked` (no Task 17 street-level site for 2011).

2011 coverage barely names blocked or undersized drains; that is probably a reporting change rather than proof that drainage
was not involved. These are claims, not measured drainage capacity. No Task 17/18 chip exists for this event.

## 3. Gaps
- No Sentinel-1/2 (pre-2014/15). Landsat 7 / ENVISAT ASAR not yet checked.
- OSM drainage is today's network.
- Lagoon water levels unknown (as for 2024).
