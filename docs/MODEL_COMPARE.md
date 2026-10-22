# Did another weather model see Lagos storms better?

The live forecast uses ECMWF IFS at 0.25° (~28 km). Its deterministic hindcast gets the average right but flattens Lagos storms: the heaviest days are about half as heavy as IMERG, and at the 15 mm warning line it caught 11 of 19 flood days the day before, with about 94% of warnings on days with no flood reported. This page asks whether a finer or differently built model, scored the same way, would do better.

It does **not** change the live forecast. Task 46 only measures.

## Who was in, who was out

Checked against the [Previous Runs API](https://open-meteo.com/en/docs/previous-runs-api) and each model's Open-Meteo page, then probed at Lagos (6.55 N, 3.35 E) for `precipitation_previous_day1`–`day7`. Free, no key, open licence, and history covering April–November 2024–2026, or it is out.

| Model | Resolution | Leads | History | In? |
|---|---|---|---|---|
| ECMWF IFS 0.25° (`ecmwf_ifs025`) | 0.25° (~28 km) | previous_day1–7 | 2024-01 (Previous Runs; open-data IFS from 2024-02-03) | yes |
| ECMWF IFS HRES 9 km (`ecmwf_ifs`) | 9 km (O1280) | previous_day1–7 on the live Forecast API | Previous Runs at Lagos is empty through 2025; a 2026-04-01 probe had day 1 only | no |
| ECMWF AIFS 0.25° Single (`ecmwf_aifs025_single`) | 0.25° (~28 km) | previous_day1–7 | 2025-02-20 | no |
| ECMWF AIFS 0.25° (superseded) (`ecmwf_aifs025`) | 0.25° (~28 km) | previous_day1–7 while it ran | 2024-04 through early 2025; empty by 2025-04 | no |
| DWD ICON global (`icon_global`) | 0.1° (~11 km) | previous_day1–6 (7.5-day horizon; day 7 empty) | 2024-01 (open-data ICON from 2023-12-15) | yes |
| UKMO global 10 km (`ukmo_global_deterministic_10km`) | 0.09° (~10 km) | previous_day1–7 when the archive has the run | Historical Forecast from 2022-03-01; Previous Runs at Lagos is gappy | no |
| Météo-France ARPEGE world (`arpege_world`) | 0.25° (~25 km) | previous_day1–3 (4-day horizon) | 2024-01-02 | yes |
| NCEP GFS 0.11° (`gfs013`) | 0.11° (~13 km) | previous_day1–7 | 2024-01 (GFS precipitation on Previous Runs from 2024; GFS 2 m T from 2021-03) | yes |
| NCEP GFS 0.25° (`gfs025`) | 0.25° (~25 km) | not populated on Previous Runs for precipitation at Lagos | n/a on Previous Runs precipitation | no |
| CMC GEM global (`gem_global`) | 0.15° (~15 km) | previous_day1–7 | 2024-01 (open-data GEM from 2023-12-15) | yes |
| JMA GSM (`jma_gsm`) | 0.5° (~55 km) | previous_day1–7 | 2018 on Previous Runs (JMA); 2023-12-15 in the AWS open-data table | yes |
| CMA GRAPES global (`cma_grapes_global`) | 0.125° (~13 km) | previous_day1–7 | 2024-01-01 | yes |
| BOM ACCESS-G (`bom_access_global`) | 0.175°/0.117° (~15 km) | previous_day1–7 when the archive has the run | Present at Lagos on 2024-04 and 2025-04; empty by 2025-11 | no |

Dropped, and why:

- **ECMWF IFS HRES 9 km** (`ecmwf_ifs`): Previous Runs has no precipitation_previous_day1–3 at Lagos for 2024 or 2025, so the archive cannot cover 2024–2026 April–November. The 9 km HRES series lives on the Single Runs / Historical Weather APIs, which are not previous-day leads.
- **ECMWF AIFS 0.25° Single** (`ecmwf_aifs025_single`): Previous Runs at Lagos starts 2025-02-20, so the 2024 season and the start of 2025 are missing.
- **ECMWF AIFS 0.25° (superseded)** (`ecmwf_aifs025`): Replaced by ecmwf_aifs025_single. Lagos previous-day precipitation is present in 2024 but gone by April 2025, so 2025–2026 is a hole.
- **UKMO global 10 km** (`ukmo_global_deterministic_10km`): Previous Runs at Lagos is not continuous: April 2024 is empty, and 2025 months are missing day 1 or day 3. That is too short and too holey to cover 2024–2026 April–November.
- **NCEP GFS 0.25°** (`gfs025`): precipitation_previous_day1–7 is all-null at Lagos on every probed date. The 0.11° GFS (gfs013) carries the previous-day rain instead.
- **BOM ACCESS-G** (`bom_access_global`): Previous Runs at Lagos is empty for every probed 2026 date (April–October) and for 2025-11-01, so the archive cannot cover 2024–2026 April–November.

## How the comparison is fair

Different models sit on different millimetre scales, so a shared 15 mm or 40 mm line would be unfair. Each model is quantile-mapped to IMERG the same way as `pipeline/calibrate.py`, out of sample. Then, on 2024+2025 only, ECMWF IFS at 15 mm flags a fixed number of days; every other model (and each blend) is given the threshold that flags as close as possible to that many days. That threshold is frozen before 2026 is scored. The table below is the three-season total at that frozen line.

ECMWF's 2024+2025 budget is **138 days** the day before and **148 days** at day 3.

Blends are the mean of the calibrated daily totals. The best two were ecmwf_ifs025, gem_global, chosen on 2024+2025 day-1 flood days caught, before 2026 was looked at.

## Day before (lead 1)

| Model | Warning line | Flood days caught (of 19) | Days flagged | False-alarm share | Calibrated p99 vs IMERG 54 mm | Brier skill ≥ 20 mm | vs ECMWF |
|---|---|---|---|---|---|---|---|
| ECMWF IFS 0.25° (`ecmwf_ifs025`) | 15.0 mm | 11/19 | 211 | 0.938 | 54.4 mm (IMERG 53.9) | -0.557 | baseline. |
| DWD ICON global (`icon_global`) | 16.74 mm | 8/19 | 190 | 0.958 | 54.9 mm (IMERG 54.0) | -0.618 | gained 1 flood days on ECMWF IFS, lost 4 (exact McNemar p = 0.38); with 19 flood days this difference is within noise. |
| Météo-France ARPEGE world (`arpege_world`) | 17.963 mm | 8/19 | 208 | 0.947 | 54.3 mm (IMERG 54.0) | -0.77 | gained 1 flood days on ECMWF IFS, lost 4 (exact McNemar p = 0.38); with 19 flood days this difference is within noise. |
| NCEP GFS 0.11° (`gfs013`) | 15.709 mm | 7/19 | 213 | 0.948 | 54.5 mm (IMERG 53.9) | -0.62 | gained 1 flood days on ECMWF IFS, lost 5 (exact McNemar p = 0.22); with 19 flood days this difference is within noise. |
| CMC GEM global (`gem_global`) | 16.94 mm | 8/19 | 206 | 0.927 | 54.6 mm (IMERG 53.9) | -0.616 | gained 1 flood days on ECMWF IFS, lost 4 (exact McNemar p = 0.38); with 19 flood days this difference is within noise. |
| JMA GSM (`jma_gsm`) | 11.875 mm | 7/19 | 220 | 0.945 | 55.0 mm (IMERG 53.9) | -0.722 | gained 2 flood days on ECMWF IFS, lost 6 (exact McNemar p = 0.29); with 19 flood days this difference is within noise. |
| CMA GRAPES global (`cma_grapes_global`) | 15.369 mm | 8/19 | 230 | 0.948 | 54.8 mm (IMERG 53.5) | -0.651 | gained 2 flood days on ECMWF IFS, lost 2 (exact McNemar p = 1.00); with 19 flood days this difference is within noise. |
| Mean of the best two (frozen on 2024+2025) | 15.143 mm | 10/19 | 209 | 0.938 | 39.8 mm (IMERG 53.9) | -0.495 | gained 0 flood days on ECMWF IFS, lost 1 (exact McNemar p = 1.00); with 19 flood days this difference is within noise. |
| Mean of every usable model | 9.616 mm | 9/19 | 221 | 0.95 | 35.4 mm (IMERG 53.6) | -0.383 | gained 2 flood days on ECMWF IFS, lost 1 (exact McNemar p = 1.00); with 19 flood days this difference is within noise. |

## Three days before (lead 3)

| Model | Warning line | Flood days caught (of 19) | Days flagged | False-alarm share | Calibrated p99 vs IMERG 54 mm | Brier skill ≥ 20 mm | vs ECMWF |
|---|---|---|---|---|---|---|---|
| ECMWF IFS 0.25° (`ecmwf_ifs025`) | 15.0 mm | 7/19 | 213 | 0.948 | 54.1 mm (IMERG 53.9) | -0.659 | baseline. |
| DWD ICON global (`icon_global`) | 15.889 mm | 8/19 | 212 | 0.939 | 53.5 mm (IMERG 53.9) | -0.594 | gained 3 flood days on ECMWF IFS, lost 2 (exact McNemar p = 1.00); with 19 flood days this difference is within noise. |
| Météo-France ARPEGE world (`arpege_world`) | 15.879 mm | 8/19 | 217 | 0.949 | 53.6 mm (IMERG 54.0) | -0.831 | gained 3 flood days on ECMWF IFS, lost 2 (exact McNemar p = 1.00); with 19 flood days this difference is within noise. |
| NCEP GFS 0.11° (`gfs013`) | 14.79 mm | 8/19 | 223 | 0.942 | 54.6 mm (IMERG 53.9) | -0.758 | gained 2 flood days on ECMWF IFS, lost 1 (exact McNemar p = 1.00); with 19 flood days this difference is within noise. |
| CMC GEM global (`gem_global`) | 14.885 mm | 5/19 | 211 | 0.967 | 52.8 mm (IMERG 53.1) | -0.668 | gained 1 flood days on ECMWF IFS, lost 3 (exact McNemar p = 0.62); with 19 flood days this difference is within noise. |
| JMA GSM (`jma_gsm`) | 9.929 mm | 7/19 | 218 | 0.959 | 54.2 mm (IMERG 53.9) | -0.743 | gained 2 flood days on ECMWF IFS, lost 2 (exact McNemar p = 1.00); with 19 flood days this difference is within noise. |
| CMA GRAPES global (`cma_grapes_global`) | 10.519 mm | 9/19 | 254 | 0.957 | 53.7 mm (IMERG 53.6) | -0.692 | gained 3 flood days on ECMWF IFS, lost 0 (exact McNemar p = 0.25); with 19 flood days this difference is within noise. |
| Mean of the best two (frozen on 2024+2025) | 14.026 mm | 8/19 | 212 | 0.953 | 39.3 mm (IMERG 53.1) | -0.495 | gained 1 flood days on ECMWF IFS, lost 0 (exact McNemar p = 1.00); with 19 flood days this difference is within noise. |
| Mean of every usable model | 9.979 mm | 8/19 | 222 | 0.959 | 34.8 mm (IMERG 52.6) | -0.359 | gained 2 flood days on ECMWF IFS, lost 0 (exact McNemar p = 0.50); with 19 flood days this difference is within noise. |

## Recommendation

**keep ECMWF.** No usable model caught more of the 19 flood days than ECMWF IFS (11) at the same alarm budget. The best-two blend (ecmwf_ifs025+gem_global) caught 10 (p = 1.0). Stay on the ECMWF 51-member ensemble; a deterministic other model is not earning its extra API call.

### What that would cost

- Live today: The live run makes 1 Open-Meteo Ensemble call for ECMWF IFS 0.25 (51 members) and 1 for GFS 0.25 as an uncalibrated second opinion, plus 4 Flood API calls. Weather-model cost is 2 forecast calls/day.
- Keep ECMWF: 0 extra weather-model calls/day.
- Add a second opinion: 1 extra Ensemble or Forecast API call/day per added model. A deterministic second opinion can raise or lower a cell's level when it disagrees with the ECMWF ensemble median, but it cannot replace the 51-member chances.
- Switch the headline: Still 1 headline ensemble call/day if that model has an ensemble on the Ensemble API (ICON and GFS do; ARPEGE/GEM/JMA/CMA/BOM deterministic would replace the 51-member chance ladder with a single run). Recalibrate first. Do not do this from this file alone.
- Blend: 1 Forecast/Ensemble call/day per member of the blend. A mean of deterministic totals is not an ensemble: it can be a second opinion on the daily total, not a replacement for P(≥ 40 mm).

A deterministic Previous Runs series is not the live product. The live product's chances come from 51 ECMWF members. Another deterministic model can only nudge a level or sit beside the card as a second opinion; it cannot honestly replace P(≥ 40 mm) unless that model also has an ensemble and we calibrate it.

## Caveats

- This comparison scores one deterministic Previous Runs series per model, not the 51-member ECMWF ensemble the live product uses. A deterministic model can only adjust those chances or act as a second opinion.
- Quantile mapping restores the size of rain a model already saw; it cannot invent a storm the model never placed on Lagos.
- The reported-flood catalog undercounts real floods, so a flagged day with no report is not proof no flood happened.
- With 19 flood days, McNemar will usually call a difference noise. The vs_ecmwf.plain field on each row says so when it is.

Built by `pipeline/compare_models.py` on 2026-10-22T19:23:48+00:00. Numbers: `events/forecast/model_compare.json`.

