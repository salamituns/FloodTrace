# Task 44: calibrate the forecast to Lagos rain, then say how good it is

This follows Task 42. Your hindcast was the right thing to build, and it found the most important problem we have.

## What the hindcast shows (I checked it from your cache)
- **The model gets the average right but flattens the extremes.** Over every cell-day, the mean is 5.5 mm forecast against 5.5 mm by IMERG. But the 99th percentile is **28.9 mm forecast against 54.0 mm** by IMERG.
  - Example: on 3 Jul 2024, the day-1 forecast for c6.45N2.75E was 14.2 mm, and IMERG measured 53.9 mm.
  - Global models at 0.25° smear West African convective storms, so a "≥ 40 mm" threshold almost never fires. The day-1 forecast flagged 1 of 19 flood days at 40 mm.
- **But the forecast does carry signal at lower model values.** Day-1, citywide (any cell near a reported area), 2024–2026, Apr–Nov, 692 days:

  | model ≥ T | flood days flagged | days flagged | of which a flood was reported |
  |---|---|---|---|
  | 10 mm | 11/19 | 269 | 14 (5%) |
  | 15 mm | 8/19 | 155 | 12 (8%) |
  | 20 mm | 6/19 | 84 | 11 (13%) |
  | 30 mm | 3/19 | 25 | 4 (16%) |

  The base rate is 19/692 = 2.7% of days with a flood reported, so a model value of 20 mm or more raises the odds about fivefold.

So the live levels, which read the raw ensemble against 20/40 mm, are close to always "none". A quiet week is therefore weaker evidence than the card implied. I have already hedged the quiet-week wording in `src/lib/forecast.ts`; don't change those strings.

## Do
1. **Calibrate with quantile mapping.** In a new `pipeline/calibrate.py`:
   - From the hindcast cache, build a mapping from model daily totals to IMERG daily totals, per lead day (1–7). Pool all cells, then add a per-cell adjustment only if it is stable. Show that it is stable, or don't add it.
   - **Validate out of sample.** Fit on 2024–2025 and test on 2026. Then fit on 2024 + 2026 and test on 2025, and so on (leave one season out).
   - **Report**, before and after calibration:
     - hits, misses and false alarms at IMERG-equivalent 40 mm;
     - flood days flagged and the false-alarm share at day 1 and day 3;
     - the Brier skill against climatology.
   - **Say plainly if the gain is noise.** With 19 flood days, it may be.
   - Write the mapping to `events/forecast/calibration.json`, with the method, the fit period and the validation in `meta`.
2. **Apply it in `forecast.py`.**
   - Map each ensemble member's daily (and hourly, scaled by the same daily factor) totals through the calibration **before** computing the chances, the levels and the hourly export.
   - Record `calibration` in the output `meta`, and keep the raw median beside the calibrated one, as `raw_median_mm`.
   - Rerun, and update the schema.
3. **Level thresholds.** If the out-of-sample results support it, you may also choose the level rule from the hindcast, e.g. the calibrated threshold that best balances flood days caught against false alarms.
   - Fix the rule before you look at the 2026 test season.
   - Write the rule and its numbers into `meta`.
4. **Then do Task 42 part C** (it was not done): the one plain sentence in `ForecastCard.tsx` under the footnote, plus `<details>`, built from the **calibrated** out-of-sample numbers. Show it on quiet weeks too; that is when people most need to know how much a quiet forecast is worth.

   Example shape (use the real numbers):
   > "How much to trust this: in past seasons, the day-before forecast flagged 8 of 19 days when floods were reported, and most of its warnings passed without a reported flood."
5. **Rerun `score_forecasts.py`** so it also reads the calibrated fields.

## Check
- `npx tsc --noEmit`, `npm run build`, `npx tsx scripts/check-watchlist.ts` and `npx tsx scripts/check-forecast.ts` all pass.
- The forecast output validates against the schema.
- **Report:**
  - the before/after table, out of sample;
  - this week's levels after calibration (are they still all "none"?);
  - the exact sentence the app now shows.

## Rules
- Foreground only.
- No `rm -rf`.
- Don't commit.
- Don't read `.env`.
- Don't start a dev server or open a browser.
- Don't change the quiet-week strings or the `whatToDo` lines in `src/lib/forecast.ts`.
