# Task 46: is there a weather model that sees Lagos storms better?

Read these first:
- `docs/FORECAST.md`;
- `pipeline/hindcast.py`;
- `pipeline/calibrate.py`;
- the `meta` blocks of `events/forecast/hindcast.json` and `events/forecast/calibration.json`.

## Why
The live forecast uses ECMWF IFS at 0.25° (about 28 km). The hindcast showed it gets the average right but cannot see Lagos storms. Its heaviest days are about half as heavy as the satellite measures. The day before, at a warning line that flags about 211 days a season-set, it caught 11 of 19 flood days, and about 94% of its warnings had no flood reported.

Finer or differently built models might do better. Test this with data, not datasheets.

## Do
1. **Find the candidates.** Using the Open-Meteo docs (the Previous Runs API page and each model's page), list every model that:
   - covers Lagos (6.4–6.7 N, 3.0–3.7 E);
   - has `precipitation` with previous-day leads (`precipitation_previous_day1` … at least `day3`) back to April 2024;
   - is free, needs no key, and has an open licence.

   Likely candidates, to check rather than assume:
   - ECMWF IFS HRES 9 km (`ecmwf_ifs`, if offered);
   - ECMWF AIFS;
   - ICON global;
   - UKMO global 10 km;
   - Météo-France ARPEGE;
   - GFS;
   - GEM;
   - JMA;
   - CMA.

   For each one, write the resolution, the leads offered, the date the history starts and the licence into the output `meta`. Drop any model whose history is too short to cover 2024–2026 April–November, and say why.
2. **`pipeline/compare_models.py`** fetches each candidate for the same 68 cells and the same period as `hindcast.py`.
   - Import its helpers; don't copy them. If a helper needs a `model` parameter, add it to `hindcast.py` with the current model as the default, so that `hindcast.py` behaves exactly as before.
   - Cache under `pipeline/cache/hindcast/<model>/`.
   - Be polite to the API: one request per model per lead set, and sleep on 429.
3. **Score every model the same way, out of sample.** Reuse `calibrate.py`'s quantile mapping and its leave-one-season-out split.
   - **The fair comparison is at a fixed alarm budget.** For each model and lead (day 1, day 3), choose the threshold that flags the *same number of days* ECMWF IFS flags at its 15 mm rule. Then compare:
     - flood days caught (of 19 at day 1);
     - the false-alarm share.

     Different models put their thresholds in different places, so comparing at a fixed number of mm would be unfair.
   - Also report, per model:
     - the calibrated p99 against IMERG's 54 mm;
     - the Brier skill for ≥ 20 mm against climatology.
   - **Blends.** Score the best two models, and all usable models together, with a rule chosen in advance: the mean of the calibrated totals. Fix the blend before you look at the 2026 test season.
   - **Noise check.** Use McNemar against ECMWF IFS on flood days caught, as `calibrate.py` does. With 19 flood days, say plainly when a difference is noise.
4. **Output.**
   - `events/forecast/model_compare.json`: `meta` (sources, method, caveats), plus one row per model and per blend.
   - `docs/MODEL_COMPARE.md`: the table in plain words and a recommendation. Possible recommendations:
     - keep ECMWF;
     - switch;
     - add a model as a second opinion;
     - blend.

     Say what each would cost in API calls per day. Remember that the live product uses the 51-member ensemble for its chances. A deterministic model can only adjust those chances or act as a second opinion, so say how you would use it.

## Check
- The comparison runs from cache offline on a second run.
- `hindcast.py` still reproduces `events/forecast/hindcast.json` exactly. Diff the file before and after.
- **Report:** the comparison table at day 1 and day 3, and your recommendation with its noise caveat.

## Rules
- Foreground only.
- No `rm -rf`.
- Don't commit.
- Don't read `.env`.
- Don't start a dev server or open a browser.
- Don't change `forecast.py`, `calibrate.py`'s outputs or anything in `src/`. This task only measures; I will decide what to switch.
- Droid is working on Task 45 in `pipeline/run_daily.py`, `ops/` and `docs/FORECAST.md`. Don't touch those.
