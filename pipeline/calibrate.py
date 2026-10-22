#!/usr/bin/env python3
"""Task 44 (docs/tasks/44-calibrate-forecast.md): calibrate the forecast's
rain to Lagos rain, then say how good it is — plainly, noise included.

The hindcast (pipeline/hindcast.py, events/forecast/hindcast.json) showed the
problem: the model's mean is right but it flattens the extremes, so a 40 mm
threshold on raw model values almost never fires. This script fixes the values,
not the thresholds: quantile mapping (QM) per lead day, fitted on the hindcast
cache (ECMWF IFS 0.25 deg deterministic runs, Africa/Lagos calendar days)
against IMERG daily totals, pooling all 68 cells. The model's p-th percentile
is mapped to the IMERG p-th percentile of the same fit sample.

What it does, in order:

  1. fits the per-lead mapping and tests whether a PER-CELL adjustment is
     stable across seasons (it must be, or it is not added);
  2. validates OUT OF SAMPLE, leave-one-season-out (LOSO): fit 2024-2025 /
     test 2026, fit 2024+2026 / test 2025, fit 2025+2026 / test 2024. Before
     (raw) vs after (calibrated), per lead day: hits, misses and false alarms
     at IMERG-equivalent 40 mm, and the Brier skill of the hard yes/no
     forecast against per-cell climatology;
  3. chooses the level rule's calibrated threshold from the 2024 and 2025
     seasons ONLY (each calibrated by a mapping fitted on the other season),
     by the highest true skill statistic TSS = POD - POFD at day 1 — the rule
     is FIXED before the 2026 test season is looked at, and the 2026 numbers
     at the frozen threshold are then reported;
  4. says plainly whether the gain is noise (exact McNemar test on the 19
     flood days);
  5. writes events/forecast/calibration.json: the mapping (deployed version
     refit on all three seasons) plus the method, the fit period and the
     validation in meta. pipeline/forecast.py reads that file and applies the
     mapping to every ensemble member before computing chances and levels.

Usage:
    pipeline/.venv/bin/python pipeline/calibrate.py

Nothing is fetched: the hindcast cache under pipeline/cache/hindcast/ must
already exist (run pipeline/hindcast.py first if it does not). Foreground
only; no key needed.
"""
from __future__ import annotations

import json
import math
from datetime import datetime, timedelta, timezone

import numpy as np

import forecast as F  # noqa: E402  (same directory; runs under pipeline/.venv)
import hindcast as H  # noqa: E402

OUT = F.OUT_DIR / "calibration.json"
LEAD_DAYS = H.LEAD_DAYS
HEAVY = 40.0            # mm/day, IMERG-equivalent, the headline threshold
PCT_STEP = 0.25         # percentile grid step: 0.25% -> 401 points per lead
P_GRID = np.round(np.arange(0.0, 100.0 + PCT_STEP / 2, PCT_STEP), 2)
SEASONS = (2024, 2025, 2026)
SWEEP = (15.0, 20.0, 25.0, 30.0, 35.0, 40.0)   # candidate calibrated thresholds
STABLE_FACTOR = 1.25    # a per-cell adjustment is "stable" when its largest and
                        # smallest season values differ by less than this factor
MIN_HEAVY_DAYS = 5      # cell-seasons need this many IMERG >= 40 mm days to be
                        # testable at all in the per-cell stability test
MIN_MODEL_P99 = 10.0    # and a model p99 at least this, so the ratio means tail

CITY_LEADS = (1, 3)     # the flood-day metrics are reported at these lead days


# ---- quantile mapping ------------------------------------------------------
def fit_qm(mod: np.ndarray, obsv: np.ndarray):
    """Empirical QM: quantiles of the model sample mapped to the same
    quantiles of the paired IMERG sample. Rounded to 0.001 mm so the JSON
    file that ships the mapping IS the mapping that was validated."""
    mq = np.round(np.quantile(mod, P_GRID / 100.0), 3)
    oq = np.round(np.quantile(obsv, P_GRID / 100.0), 3)
    return mq, oq


def apply_qm(vals: np.ndarray, mq: np.ndarray, oq: np.ndarray) -> np.ndarray:
    """Map model mm to IMERG-equivalent mm (NaNs stay NaN; values above the
    fit maximum clip to the IMERG fit maximum)."""
    p = np.interp(vals, mq, P_GRID)
    return np.interp(p, P_GRID, oq)


def mcnemar_p(b: int, c: int) -> float:
    """Exact two-sided McNemar test on the discordant counts b and c."""
    n = b + c
    if n == 0:
        return 1.0
    k = min(b, c)
    tail = sum(math.comb(n, i) for i in range(k + 1)) / (2.0 ** n)
    return min(1.0, 2.0 * tail)


def main() -> None:
    generated_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    today = datetime.now(F.WAT).date()
    yesterday = today - timedelta(days=1)

    # ---- inputs: IMERG grid, flood days, hindcast cache --------------------
    grid = json.loads((F.EVENTS / "rain_history_grid_daily.json").read_text())
    cells = grid["meta"]["cells"]
    date_idx = {x: i for i, x in enumerate(grid["dates"])}
    series = grid["series"]
    fd_doc = json.loads((F.EVENTS / "flood_days.json").read_text())
    areas_by_date = {
        day["date"]: [(a["lon"], a["lat"]) for a in day.get("areas", [])
                      if a.get("lon") is not None and a.get("lat") is not None]
        for day in fd_doc["days"]
    }

    months = []
    for y in range(H.ARCHIVE_START.year, today.year + 1):
        for m in range(4, 12):
            first, last = H.month_days(y, m, yesterday)
            if first <= last:
                months.append((y, m, first, last))
    assert {y for y, *_ in months} == set(SEASONS), "hindcast cache must cover all seasons"

    print(f"loading hindcast cache: {len(months)} months ...")
    totals: dict[str, list] = {}   # day -> [per-cell [lead1..7] or None]
    for y, m, first, last in months:
        data = H.fetch_month(cells, y, m, first, last)   # cached; no network
        assert len(data) == len(cells)
        n_days = len(data[0]["hourly"]["time"]) // 24
        if n_days == 0:
            continue
        for j in range(n_days):
            day = data[0]["hourly"]["time"][j * 24][:10]
            totals.setdefault(day, [None] * len(cells))
        for ci, loc in enumerate(data):
            per_lead = H.daily_totals(loc, n_days)
            for j in range(n_days):
                day = loc["hourly"]["time"][j * 24][:10]
                totals[day][ci] = [per_lead[n][j] for n in range(1, LEAD_DAYS + 1)]

    days = sorted(totals)
    day_idx = {x: i for i, x in enumerate(days)}
    nD, nC = len(days), len(cells)
    years = np.array([int(x[:4]) for x in days])
    raw = np.full((LEAD_DAYS, nD, nC), np.nan)     # model mm per lead/day/cell
    obs = np.full((nD, nC), np.nan)                # IMERG mm per day/cell
    for di, day in enumerate(days):
        i = date_idx.get(day)
        for ci, c in enumerate(cells):
            v = totals[day][ci]
            if v is not None:
                for n in range(1, LEAD_DAYS + 1):
                    if v[n - 1] is not None:
                        raw[n - 1, di, ci] = v[n - 1]
            if i is not None:
                o = series[c["id"]]["total_mm"][i]
                if o is not None:
                    obs[di, ci] = o
    print(f"days {days[0]} .. {days[-1]} ({nD}), cells {nC}, "
          f"IMERG pairs {int((~np.isnan(obs[years == 2026])).sum())} in 2026")

    # flood-day structures (the same 5 km rule as forecast.py / hindcast.py)
    flood_days_in_period = [x for x in sorted(areas_by_date)
                            if areas_by_date[x] and x in day_idx
                            and F.d(x).month in F.WINDOW_MONTHS]
    flood_day_set = set(flood_days_in_period)
    near_cells = {day: [ci for ci, c in enumerate(cells)
                        if any(F.haversine_km(c["lon"], c["lat"], lon, lat) <= F.AREA_MATCH_KM
                               for lon, lat in areas_by_date[day])]
                  for day in flood_days_in_period}
    print(f"flood days in the hindcast window: {len(flood_days_in_period)}")

    # ---- helpers -----------------------------------------------------------
    def fold_cal(test: int, fit: tuple[int, ...]):
        """Calibrated values for the test season, mapping fitted on `fit`
        seasons only. Returns (cal per lead, fitted maps per lead, pairs used)."""
        fit_rows = np.isin(years, fit)                   # 1-D over days
        test_rows = years == test
        cal, maps, n_pairs = {}, {}, {}
        for n in range(1, LEAD_DAYS + 1):
            r = raw[n - 1]
            keep = fit_rows[:, None] & ~np.isnan(r) & ~np.isnan(obs)
            mq, oq = fit_qm(r[keep], obs[keep])
            maps[n], n_pairs[n] = (mq, oq), int(keep.sum())
            c = r.copy()
            c[test_rows, :] = apply_qm(r[test_rows, :], mq, oq)
            cal[n] = c
        return cal, maps, n_pairs

    def climatology(fit: tuple[int, ...]) -> np.ndarray:
        """Per cell-day: that cell's frequency of IMERG >= 40 mm over the fit
        seasons (the Brier climatology baseline)."""
        fit_mask = np.isin(years, fit)
        out = np.zeros((nD, nC))
        for ci in range(nC):
            o = obs[fit_mask, ci]
            o = o[~np.isnan(o)]
            out[:, ci] = (float((o >= HEAVY).sum()) / len(o)) if len(o) else 0.0
        return out

    def cell_metrics(vals: np.ndarray, test: int, clim: np.ndarray) -> dict:
        """Hits/misses/FA at 40 mm + hard-forecast Brier and skill vs clim."""
        m = (years == test)[:, None] & ~np.isnan(vals) & ~np.isnan(obs)
        v = vals[m] >= HEAVY
        o = obs[m] >= HEAVY
        p, ob = v.astype(float), o.astype(float)
        brier = float(np.mean((p - ob) ** 2))
        bclim = float(np.mean((clim[m] - ob) ** 2))
        return {
            "n_scored": int(m.sum()),
            "hits": int((v & o).sum()),
            "misses": int((~v & o).sum()),
            "false_alarms": int((v & ~o).sum()),
            "brier_ge_40mm": round(brier, 4),
            "brier_clim_ge_40mm": round(bclim, 4),
            "skill_ge_40mm": round(1 - brier / bclim, 3) if bclim > 0 else None,
        }

    def day_metrics(vals: np.ndarray, season: int, t: float) -> dict:
        """Flood days flagged (near a reported area) and citywide flagged days
        at threshold t, for one season. Same rules as the hindcast tables."""
        fd = [x for x in flood_days_in_period if int(x[:4]) == season]
        flagged_fd = 0
        for day in fd:
            di = day_idx[day]
            ncs = near_cells[day]
            if not ncs or any(np.isnan(vals[di, ci]) for ci in ncs):
                continue
            if max(vals[di, ci] for ci in ncs) >= t:
                flagged_fd += 1
        n_flagged = n_with_flood = 0
        for di in range(nD):
            if years[di] != season or np.isnan(vals[di]).all():
                continue
            if np.nanmax(vals[di]) >= t:
                n_flagged += 1
                if days[di] in flood_day_set:
                    n_with_flood += 1
        return {
            "flood_days_in_season": len(fd),
            "flood_days_flagged": flagged_fd,
            "days_flagged": n_flagged,
            "days_flagged_with_flood_reported": n_with_flood,
        }

    def add_dicts(*ds: dict) -> dict:
        out = {}
        for d in ds:
            for k, v in d.items():
                out[k] = out.get(k, 0) + v
        return out

    # ---- 1. per-cell adjustment: stable or not? -----------------------------
    qualified = stable = 0
    worst = []
    for ci in range(nC):
        for n in range(1, LEAD_DAYS + 1):
            r = raw[n - 1][:, ci]
            per_season = []
            ok = True
            for y in SEASONS:
                m = years == y
                mm, oo = r[m], obs[m, ci]
                keep = ~(np.isnan(mm) | np.isnan(oo))
                mm, oo = mm[keep], oo[keep]
                if len(oo) == 0 or (oo >= HEAVY).sum() < MIN_HEAVY_DAYS:
                    ok = False
                    break
                q99m = float(np.quantile(mm, 0.99))
                if q99m < MIN_MODEL_P99:
                    ok = False
                    break
                per_season.append((float(np.quantile(oo, 0.99)) + 1.0) / (q99m + 1.0))
            if not ok:
                continue
            qualified += 1
            lo, hi = min(per_season), max(per_season)
            worst.append(hi / lo)
            if hi / lo <= STABLE_FACTOR:
                stable += 1
    if worst:
        print(f"per-cell stability: {stable} of {qualified} testable cell-leads "
              f"stable across seasons (worst max/min {max(worst):.1f}x)")
    else:
        print("per-cell stability: no cell-lead testable")
    per_cell = {
        "test": (
            "A per-cell adjustment would multiply the pooled mapping by this "
            "cell's own tail correction: (cell IMERG p99 + 1) / (cell model "
            "p99 + 1), computed separately for each season. It counts as "
            f"stable only when a cell-lead has at least {MIN_HEAVY_DAYS} IMERG "
            f">= 40 mm days and a model p99 of at least {MIN_MODEL_P99:g} mm in "
            "every season, and its largest and smallest season values differ by "
            f"less than a factor {STABLE_FACTOR}."
        ),
        "n_cell_leads_testable": qualified,
        "n_stable": stable,
        "conclusion": (
            ("No per-cell adjustment is used: no cell-lead had enough 40 mm days in "
             "every season for the test to run at all. The deployed mapping pools "
             "all cells, per lead day.")
            if qualified == 0 else
            (f"No per-cell adjustment is used: only {stable} of {qualified} testable "
             "cell-leads met the stability limit, because each cell-season holds "
             "only a handful of 40 mm days and the per-cell tail correction swings "
             "widely between seasons. The deployed mapping pools all cells, per "
             "lead day.")
        ),
    }

    # ---- 2. LOSO validation at 40 mm (before = raw, after = calibrated) ------
    print("leave-one-season-out validation at 40 mm ...")
    loso = {test: fold_cal(test, tuple(y for y in SEASONS if y != test)) for test in SEASONS}
    clim_cache = {t: climatology(tuple(y for y in SEASONS if y != t)) for t in SEASONS}

    def agg_metrics(per_fold: list[dict]) -> dict:
        """Sum integer fields over folds; Brier fields are fold means, so pool
        them weighted by the fold sizes before turning them into skill."""
        agg = {k: sum(f[k] for f in per_fold)
               for k in ("n_scored", "hits", "misses", "false_alarms")}
        n_tot = agg["n_scored"]
        for k in ("brier_ge_40mm", "brier_clim_ge_40mm"):
            agg[k] = (round(sum(f[k] * f["n_scored"] for f in per_fold) / n_tot, 4)
                      if n_tot else None)
        b, bc = agg["brier_ge_40mm"], agg["brier_clim_ge_40mm"]
        agg["skill_ge_40mm"] = round(1 - b / bc, 3) if bc else None
        return agg

    before_after = []
    for n in range(1, LEAD_DAYS + 1):
        row = {"lead_day": n}
        for tag in ("before", "after"):
            per_fold = [cell_metrics(raw[n - 1] if tag == "before" else loso[t][0][n],
                                     t, clim_cache[t])
                        for t in SEASONS]
            row[tag] = agg_metrics(per_fold)
        before_after.append(row)

    flood_40 = {}
    for n in CITY_LEADS:
        flood_40[n] = {
            "before": add_dicts(*[day_metrics(raw[n - 1], t, HEAVY) for t in SEASONS]),
            "after": add_dicts(*[day_metrics(loso[t][0][n], t, HEAVY) for t in SEASONS]),
        }

    # distribution check: does calibration restore the extremes? (LOSO, day 1-7)
    dist_check = []
    for n in range(1, LEAD_DAYS + 1):
        keep_all = ~np.isnan(obs)
        r_all = raw[n - 1][keep_all]
        c_all = np.concatenate([loso[t][0][n][years == t][~np.isnan(obs[years == t])] for t in SEASONS])
        o_all = obs[keep_all]
        dist_check.append({
            "lead_day": n,
            "model_p99_mm": round(float(np.nanpercentile(r_all, 99)), 1),
            "calibrated_p99_mm": round(float(np.nanpercentile(c_all, 99)), 1),
            "imerg_p99_mm": round(float(np.percentile(o_all, 99)), 1),
        })

    # ---- 3. the level rule: threshold fixed on 2024+2025, then 2026 test ----
    print("choosing the level rule from 2024+2025 (2026 not touched) ...")
    sweep_folds = {2024: fold_cal(2024, (2025,)), 2025: fold_cal(2025, (2024,))}
    sweep_rows = []
    for t in SWEEP:
        agg = add_dicts(*[day_metrics(sweep_folds[y][0][1], y, t) for y in (2024, 2025)])
        n_nonflood = sum(1 for di in range(nD)
                         if years[di] in (2024, 2025) and days[di] not in flood_day_set
                         and not np.isnan(sweep_folds[years[di]][0][1][di]).all())
        flagged_nonflood = agg["days_flagged"] - agg["days_flagged_with_flood_reported"]
        pod = agg["flood_days_flagged"] / agg["flood_days_in_season"]
        pofd = flagged_nonflood / n_nonflood
        sweep_rows.append({**agg, "threshold_mm": t, "pod": round(pod, 3),
                           "pofd": round(pofd, 3), "tss": round(pod - pofd, 3),
                           "false_alarm_share": round(flagged_nonflood / agg["days_flagged"], 3)
                           if agg["days_flagged"] else None})
    best = max(sweep_rows, key=lambda r: (r["tss"], -r["days_flagged"], -r["threshold_mm"]))
    t_star = float(best["threshold_mm"])
    print("  day-1 sweep on 2024+2025 (calibrated, out of sample within those seasons):")
    for r in sweep_rows:
        mark = " <- chosen" if r["threshold_mm"] == t_star else ""
        print(f"    >={r['threshold_mm']:>4.0f} mm: flood days {r['flood_days_flagged']}"
              f"/{r['flood_days_in_season']}, days flagged {r['days_flagged']} "
              f"(FA share {r['false_alarm_share']}), TSS {r['tss']}{mark}")

    # the 2026 test season at the frozen threshold (mapping fit on 2024+2025)
    test_2026 = {n: day_metrics(loso[2026][0][n], 2026, t_star) for n in CITY_LEADS}
    test_2026_40 = {n: day_metrics(loso[2026][0][n], 2026, HEAVY) for n in CITY_LEADS}
    print(f"  2026 test season at the frozen {t_star:g} mm, day 1: "
          f"flood days {test_2026[1]['flood_days_flagged']}/{test_2026[1]['flood_days_in_season']}, "
          f"days flagged {test_2026[1]['days_flagged']}")

    # trust numbers for the app: all three LOSO folds at the frozen threshold,
    # day 1. 2024/2025 use the sweep mappings (fit on the other of the two), so
    # no fold's calibration ever saw that season.
    trust_fold_vals = {2024: sweep_folds[2024][0][1], 2025: sweep_folds[2025][0][1],
                       2026: loso[2026][0][1]}
    trust_agg = add_dicts(*[day_metrics(trust_fold_vals[y], y, t_star) for y in SEASONS])
    fa_share = round((trust_agg["days_flagged"] - trust_agg["days_flagged_with_flood_reported"])
                     / trust_agg["days_flagged"], 3) if trust_agg["days_flagged"] else None

    # ---- 4. is the gain noise? ---------------------------------------------
    def flags_by_day(vals_by_season: dict, t: float) -> dict:
        out = {}
        for y, vals in vals_by_season.items():
            for day in [x for x in flood_days_in_period if int(x[:4]) == y]:
                di = day_idx[day]
                ncs = near_cells[day]
                if not ncs or any(np.isnan(vals[di, ci]) for ci in ncs):
                    continue
                out[day] = max(vals[di, ci] for ci in ncs) >= t
        return out

    noise_parts = []
    for label, before_flags, after_flags in (
        ("40 mm", flags_by_day({y: raw[0] for y in SEASONS}, HEAVY),
         flags_by_day({y: loso[y][0][1] for y in SEASONS}, HEAVY)),
        (f"{t_star:g} mm (the warning threshold)", flags_by_day({y: raw[0] for y in SEASONS}, t_star),
         flags_by_day(trust_fold_vals, t_star)),
    ):
        common = set(before_flags) & set(after_flags)
        b = sum(1 for x in common if after_flags[x] and not before_flags[x])
        c = sum(1 for x in common if before_flags[x] and not after_flags[x])
        p = mcnemar_p(b, c)
        noise_parts.append({
            "threshold": label,
            "gained": b, "lost": c,
            "mcnemar_p": round(p, 3),
            "plain": (
                f"at {label}: the calibration newly flagged {b} flood days and lost {c} "
                f"(exact McNemar p = {p:.2f}); "
                + ("this is unlikely to be pure noise."
                   if p < 0.05 else
                   "with so few flood days this difference is within noise — treat the "
                   "improvement as suggestive, not proven.")
            ),
        })
    for part in noise_parts:
        print(f"noise check {part['plain']}")

    # ---- 5. deployed mapping: refit on all three seasons --------------------
    print("fitting the deployed mapping on all seasons ...")
    deploy = {}
    for n in range(1, LEAD_DAYS + 1):
        r = raw[n - 1]
        keep = ~np.isnan(r) & ~np.isnan(obs)
        mq, oq = fit_qm(r[keep], obs[keep])
        deploy[n] = {"model_mm": mq, "observed_mm": oq, "n_pairs": int(keep.sum())}

    # ---- write calibration.json --------------------------------------------
    fit_start, fit_end = days[0], days[-1]
    meta = {
        "built_by": "pipeline/calibrate.py",
        "task": "44-calibrate-forecast (docs/tasks/44-calibrate-forecast.md)",
        "generated_at": generated_at,
        "method": (
            "Quantile mapping per lead day (1-7), fitted on the hindcast cache "
            "(pipeline/cache/hindcast/: ECMWF IFS 0.25 deg DETERMINISTIC runs from the "
            "Open-Meteo Previous Runs API, hourly mm summed to Africa/Lagos calendar "
            "days) against IMERG daily totals (events/rain_history_grid_daily.json), "
            "pooling all 68 cells: the model's p-th percentile is mapped to the IMERG "
            f"p-th percentile of the same fit sample ({len(P_GRID)} percentile points, "
            "0 to 100 by 0.25), and any model value is placed by interpolation. Values "
            "above the fit maximum clip to the IMERG fit maximum. In "
            "pipeline/forecast.py the mapping is applied to every ensemble member's "
            "daily total BEFORE chances, levels, risk windows and the hourly export are "
            "computed; each member's hourly values are scaled by that member's same "
            "daily factor. The deployed mapping below is refit on all three seasons; "
            "every number in validation is leave-one-season-out and therefore out of "
            "sample."
        ),
        "fit_period": {
            "start": fit_start, "end": fit_end,
            "seasons": list(SEASONS),
            "months": "April-November of each season (the hindcast window)",
            "n_pairs_per_lead_day": {str(n): deploy[n]["n_pairs"] for n in range(1, LEAD_DAYS + 1)},
        },
        "per_cell_adjustment": per_cell,
        "validation": {
            "design": (
                "Leave-one-season-out over 2024-2026: each held-out season is scored "
                "with a mapping fitted only on the other seasons. 'Before' is the raw "
                "model value, 'after' the calibrated one, both against the same "
                "thresholds, so the difference is the calibration alone."
            ),
            "at_40mm_by_lead_day": [
                {
                    "lead_day": r["lead_day"],
                    "before": r["before"],
                    "after": r["after"],
                }
                for r in before_after
            ],
            "flood_days_at_40mm": {
                f"day{n}": {
                    "before": {k: flood_40[n]["before"][k] for k in
                               ("flood_days_in_season", "flood_days_flagged", "days_flagged",
                                "days_flagged_with_flood_reported")},
                    "after": {k: flood_40[n]["after"][k] for k in
                              ("flood_days_in_season", "flood_days_flagged", "days_flagged",
                               "days_flagged_with_flood_reported")},
                }
                for n in CITY_LEADS
            },
            "distribution_check": dist_check,
            "noise": noise_parts,
        },
        "level_rule": {
            "applied": t_star < HEAVY,
            "threshold_mm": t_star,
            "rule": (
                f"A cell-day whose CALIBRATED member-median reaches {t_star:g} mm is "
                "raised to at least 'medium', whatever the ensemble chances say. "
                f"The threshold was fixed on the 2024 and 2025 seasons only (each "
                "calibrated by a mapping fitted on the other season), as the day-1 "
                "threshold with the best true skill statistic TSS = POD - POFD over "
                "the candidates 15/20/25/30/35/40 mm; it was frozen before the 2026 "
                "test season was looked at. It is 'applied' only when it differs "
                "from the 40 mm the chance ladder already uses."
            ) if t_star < HEAVY else (
                f"The best-balanced day-1 threshold on 2024+2025 was {t_star:g} mm, "
                "the same 40 mm the chance ladder already uses, so no extra rule was "
                "added: calibration alone moves the levels."
            ),
            "criterion": "max TSS = POD - POFD at day 1, citywide day-level flags",
            "candidates_2024_2025": sweep_rows,
            "test_2026_at_threshold": test_2026,
            "test_2026_at_40mm": test_2026_40,
        },
        "trust": {
            "lead_day": 1,
            "threshold_mm": t_star,
            "flood_days_in_period": trust_agg["flood_days_in_season"],
            "flood_days_flagged": trust_agg["flood_days_flagged"],
            "days_flagged": trust_agg["days_flagged"],
            "days_flagged_with_flood_reported": trust_agg["days_flagged_with_flood_reported"],
            "false_alarm_share": fa_share,
            "design": (
                "Out of sample, leave-one-season-out over 2024-2026: each season's "
                "numbers come from a mapping fitted without it (2024 and 2025 from a "
                "mapping fitted on the other of the two, 2026 from one fitted on "
                "2024+2025). The threshold itself was fixed on 2024+2025 before the "
                "2026 numbers were computed."
            ),
        },
        "caveats": [
            "The calibration is fitted on one deterministic ECMWF IFS run per lead "
            "day (the hindcast), while the live forecast calibrates each of the 51 "
            "ensemble members; a single run is noisier than an ensemble median.",
            "Quantile mapping fixes the size of the rain the model does see; it "
            "cannot create a storm the model never saw at all.",
            "The reported-flood catalog undercounts real floods, so 'no flood "
            "reported' on a flagged day is not proof no flood happened.",
            "With only 19 flood days in the window, every flood-day number here has "
            "wide uncertainty; the noise field says plainly when a difference is "
            "within it.",
        ],
    }
    out = {
        "meta": meta,
        "percentiles": [float(x) for x in P_GRID],
        "mapping": {
            str(n): {
                "n_pairs": deploy[n]["n_pairs"],
                "model_mm": [float(x) for x in deploy[n]["model_mm"]],
                "observed_mm": [float(x) for x in deploy[n]["observed_mm"]],
            }
            for n in range(1, LEAD_DAYS + 1)
        },
    }
    OUT.write_text(json.dumps(out, indent=1) + "\n")
    print(f"wrote {OUT.relative_to(F.ROOT)}")

    # ---- console summary ----------------------------------------------------
    print()
    print("LOSO before/after at 40 mm (all cell-days, all folds pooled):")
    for r in before_after:
        b, a = r["before"], r["after"]
        print(f"  day {r['lead_day']}: hits {b['hits']}->{a['hits']}, "
              f"misses {b['misses']}->{a['misses']}, FA {b['false_alarms']}->{a['false_alarms']}, "
              f"brier skill {b['skill_ge_40mm']}->{a['skill_ge_40mm']}")
    for n in CITY_LEADS:
        b, a = flood_40[n]["before"], flood_40[n]["after"]
        print(f"  day-{n} flood days flagged {b['flood_days_flagged']}->{a['flood_days_flagged']} "
              f"of {a['flood_days_in_season']}; days flagged {b['days_flagged']}->{a['days_flagged']} "
              f"(with flood {b['days_flagged_with_flood_reported']}->{a['days_flagged_with_flood_reported']})")
    print()
    print(f"trust (day 1, >= {t_star:g} mm calibrated, out of sample): flagged "
          f"{trust_agg['flood_days_flagged']} of {trust_agg['flood_days_in_season']} flood days; "
          f"{trust_agg['days_flagged']} days flagged, FA share {fa_share}")


if __name__ == "__main__":
    main()
