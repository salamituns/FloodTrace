#!/usr/bin/env python3
"""Task 46 (docs/tasks/46-compare-models.md): is there a weather model that
sees Lagos storms better than ECMWF IFS 0.25 deg?

The live forecast uses the ECMWF IFS 0.25 deg ensemble. The hindcast of the
matching deterministic run gets the average right but flattens Lagos storms.
This script asks whether another Open-Meteo Previous Runs model, scored the
same way, would catch more of the 19 reported flood days at the same alarm
budget.

What it does:

  1. records every candidate that covers Lagos, has precipitation previous-day
     leads through at least day 3, is free, and has an open licence — and drops
     any whose Previous Runs archive does not cover April–November 2024–2026;
  2. fetches each usable model for the same 68 cells and the same months as
     pipeline/hindcast.py (cached under pipeline/cache/hindcast/<model>/;
     ECMWF IFS 0.25 stays at the original cache path);
  3. quantile-maps each model to IMERG, leave-one-season-out, the same way as
     pipeline/calibrate.py;
  4. compares at a FIXED alarm budget: the threshold that flags as many days
     as ECMWF IFS flags at its 15 mm rule, chosen on 2024+2025 only, then
     scored on all three seasons;
  5. scores two blends, members frozen on 2024+2025: the mean of the best two
     models, and the mean of every usable model.

Output: events/forecast/model_compare.json and docs/MODEL_COMPARE.md.

Usage:
    pipeline/.venv/bin/python pipeline/compare_models.py

Foreground only; no key needed. A second run is offline from the cache.
"""
from __future__ import annotations

import json
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np

import forecast as F  # noqa: E402
import hindcast as H  # noqa: E402
import calibrate as C  # noqa: E402

OUT = F.OUT_DIR / "model_compare.json"
DOC = F.ROOT / "docs" / "MODEL_COMPARE.md"
BASELINE = H.MODEL          # ecmwf_ifs025
RULE_MM = 15.0              # ECMWF IFS calibrated warning line
SOME = H.SOME               # 20 mm, Brier event
CITY_LEADS = C.CITY_LEADS   # (1, 3)
SEASONS = C.SEASONS
FIT_SEASONS = (2024, 2025)  # threshold and blend members frozen here
SLEEP_AFTER_FETCH_S = 15    # polite pause after a real network call

# Every global (or Lagos-covering) Previous Runs model we checked against the
# Open-Meteo Previous Runs API page, each model's page, and a Lagos probe
# (6.55 N, 3.35 E) of precipitation_previous_day1..7. Regional models that
# never reach Lagos (HRRR, NAM, NBM, ICON-EU/D2, AROME, JMA MSM, GEM RDPS,
# UKV, …) are omitted.
CANDIDATES = [
    {
        "id": "ecmwf_ifs025",
        "name": "ECMWF IFS 0.25°",
        "resolution": "0.25° (~28 km)",
        "leads": "previous_day1–7",
        "history_start": "2024-01 (Previous Runs; open-data IFS from 2024-02-03)",
        "licence": "CC BY 4.0 (Open-Meteo); ECMWF IFS open data CC BY 4.0",
        "usable": True,
        "drop_reason": None,
        "docs": "https://open-meteo.com/en/docs/ecmwf-api",
    },
    {
        "id": "ecmwf_ifs",
        "name": "ECMWF IFS HRES 9 km",
        "resolution": "9 km (O1280)",
        "leads": "previous_day1–7 on the live Forecast API",
        "history_start": "Previous Runs at Lagos is empty through 2025; a 2026-04-01 probe had day 1 only",
        "licence": "CC BY 4.0 (Open-Meteo); ECMWF IFS open data CC BY 4.0",
        "usable": False,
        "drop_reason": (
            "Previous Runs has no precipitation_previous_day1–3 at Lagos for "
            "2024 or 2025, so the archive cannot cover 2024–2026 April–November. "
            "The 9 km HRES series lives on the Single Runs / Historical Weather "
            "APIs, which are not previous-day leads."
        ),
        "docs": "https://open-meteo.com/en/docs/ecmwf-api",
    },
    {
        "id": "ecmwf_aifs025_single",
        "name": "ECMWF AIFS 0.25° Single",
        "resolution": "0.25° (~28 km)",
        "leads": "previous_day1–7",
        "history_start": "2025-02-20",
        "licence": "CC BY 4.0 (Open-Meteo); ECMWF AIFS open data CC BY 4.0",
        "usable": False,
        "drop_reason": (
            "Previous Runs at Lagos starts 2025-02-20, so the 2024 season and "
            "the start of 2025 are missing."
        ),
        "docs": "https://open-meteo.com/en/docs/ecmwf-api",
    },
    {
        "id": "ecmwf_aifs025",
        "name": "ECMWF AIFS 0.25° (superseded)",
        "resolution": "0.25° (~28 km)",
        "leads": "previous_day1–7 while it ran",
        "history_start": "2024-04 through early 2025; empty by 2025-04",
        "licence": "CC BY 4.0 (Open-Meteo); ECMWF AIFS open data CC BY 4.0",
        "usable": False,
        "drop_reason": (
            "Replaced by ecmwf_aifs025_single. Lagos previous-day precipitation "
            "is present in 2024 but gone by April 2025, so 2025–2026 is a hole."
        ),
        "docs": "https://open-meteo.com/en/docs/ecmwf-api",
    },
    {
        "id": "icon_global",
        "name": "DWD ICON global",
        "resolution": "0.1° (~11 km)",
        "leads": "previous_day1–6 (7.5-day horizon; day 7 empty)",
        "history_start": "2024-01 (open-data ICON from 2023-12-15)",
        "licence": "CC BY 4.0 (Open-Meteo); DWD ICON open data (GeoNutzV)",
        "usable": True,
        "drop_reason": None,
        "docs": "https://open-meteo.com/en/docs/dwd-api",
    },
    {
        "id": "ukmo_global_deterministic_10km",
        "name": "UKMO global 10 km",
        "resolution": "0.09° (~10 km)",
        "leads": "previous_day1–7 when the archive has the run",
        "history_start": "Historical Forecast from 2022-03-01; Previous Runs at Lagos is gappy",
        "licence": "CC BY-SA 4.0 (UKMO via Open-Meteo)",
        "usable": False,
        "drop_reason": (
            "Previous Runs at Lagos is not continuous: April 2024 is empty, "
            "and 2025 months are missing day 1 or day 3. That is too short "
            "and too holey to cover 2024–2026 April–November."
        ),
        "docs": "https://open-meteo.com/en/docs/ukmo-api",
    },
    {
        "id": "arpege_world",
        "name": "Météo-France ARPEGE world",
        "resolution": "0.25° (~25 km)",
        "leads": "previous_day1–3 (4-day horizon)",
        "history_start": "2024-01-02",
        "licence": "CC BY 4.0 (Open-Meteo); Météo-France open data (Etalab)",
        "usable": True,
        "drop_reason": None,
        "docs": "https://open-meteo.com/en/docs/meteofrance-api",
    },
    {
        "id": "gfs013",
        "name": "NCEP GFS 0.11°",
        "resolution": "0.11° (~13 km)",
        "leads": "previous_day1–7",
        "history_start": "2024-01 (GFS precipitation on Previous Runs from 2024; GFS 2 m T from 2021-03)",
        "licence": "CC BY 4.0 (Open-Meteo); NOAA GFS public domain",
        "usable": True,
        "drop_reason": None,
        "docs": "https://open-meteo.com/en/docs/gfs-api",
    },
    {
        "id": "gfs025",
        "name": "NCEP GFS 0.25°",
        "resolution": "0.25° (~25 km)",
        "leads": "not populated on Previous Runs for precipitation at Lagos",
        "history_start": "n/a on Previous Runs precipitation",
        "licence": "CC BY 4.0 (Open-Meteo); NOAA GFS public domain",
        "usable": False,
        "drop_reason": (
            "precipitation_previous_day1–7 is all-null at Lagos on every probed "
            "date. The 0.11° GFS (gfs013) carries the previous-day rain instead."
        ),
        "docs": "https://open-meteo.com/en/docs/gfs-api",
    },
    {
        "id": "gem_global",
        "name": "CMC GEM global",
        "resolution": "0.15° (~15 km)",
        "leads": "previous_day1–7",
        "history_start": "2024-01 (open-data GEM from 2023-12-15)",
        "licence": "CC BY 4.0 (Open-Meteo); ECCC Open Government Licence",
        "usable": True,
        "drop_reason": None,
        "docs": "https://open-meteo.com/en/docs/gem-api",
    },
    {
        "id": "jma_gsm",
        "name": "JMA GSM",
        "resolution": "0.5° (~55 km)",
        "leads": "previous_day1–7",
        "history_start": "2018 on Previous Runs (JMA); 2023-12-15 in the AWS open-data table",
        "licence": "CC BY 4.0 (Open-Meteo); JMA GSM redistributed as open data",
        "usable": True,
        "drop_reason": None,
        "docs": "https://open-meteo.com/en/docs/jma-api",
    },
    {
        "id": "cma_grapes_global",
        "name": "CMA GRAPES global",
        "resolution": "0.125° (~13 km)",
        "leads": "previous_day1–7",
        "history_start": "2024-01-01",
        "licence": "CC BY 4.0 (Open-Meteo); CMA GRAPES open data as served by Open-Meteo",
        "usable": True,
        "drop_reason": None,
        "docs": "https://open-meteo.com/en/docs/cma-api",
    },
    {
        "id": "bom_access_global",
        "name": "BOM ACCESS-G",
        "resolution": "0.175°/0.117° (~15 km)",
        "leads": "previous_day1–7 when the archive has the run",
        "history_start": "Present at Lagos on 2024-04 and 2025-04; empty by 2025-11",
        "licence": "CC BY 4.0 (Open-Meteo); BoM ACCESS open data",
        "usable": False,
        "drop_reason": (
            "Previous Runs at Lagos is empty for every probed 2026 date "
            "(April–October) and for 2025-11-01, so the archive cannot cover "
            "2024–2026 April–November."
        ),
        "docs": "https://open-meteo.com/en/docs",
    },
]


def months_for(today):
    yesterday = today - timedelta(days=1)
    months = []
    for y in range(H.ARCHIVE_START.year, today.year + 1):
        for m in range(4, 12):
            first, last = H.month_days(y, m, yesterday)
            if first <= last:
                months.append((y, m, first, last))
    return months


def load_raw(cells, months, model: str):
    """Daily totals for one model: dict day -> [per-cell [lead1..7] or None]."""
    totals: dict[str, list] = {}
    for y, m, first, last in months:
        cached = H.cache_file(y, m, model).exists()
        print(f"  {model} {y}-{m:02d} ({'cache' if cached else 'fetch'}) ...",
              flush=True)
        data = H.fetch_month(cells, y, m, first, last, model=model)
        if not cached:
            time.sleep(SLEEP_AFTER_FETCH_S)
        if not isinstance(data, list) or len(data) != len(cells):
            raise SystemExit(f"{model} {y}-{m:02d}: expected {len(cells)} locations, got {len(data) if isinstance(data, list) else type(data)}")
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
                totals[day][ci] = [per_lead[n][j] for n in range(1, H.LEAD_DAYS + 1)]
    return totals


def to_arrays(totals: dict, cells, date_idx, series):
    days = sorted(totals)
    nD, nC = len(days), len(cells)
    years = np.array([int(x[:4]) for x in days])
    raw = np.full((H.LEAD_DAYS, nD, nC), np.nan)
    obs = np.full((nD, nC), np.nan)
    for di, day in enumerate(days):
        i = date_idx.get(day)
        for ci, c in enumerate(cells):
            v = totals[day][ci]
            if v is not None:
                for n in range(1, H.LEAD_DAYS + 1):
                    if v[n - 1] is not None:
                        raw[n - 1, di, ci] = v[n - 1]
            if i is not None:
                o = series[c["id"]]["total_mm"][i]
                if o is not None:
                    obs[di, ci] = o
    return days, years, raw, obs


def trust_cal(raw, obs, years, n):
    """Calibrated field for lead n, using calibrate.py's trust folds:
    2024 fit on 2025, 2025 fit on 2024, 2026 fit on 2024+2025."""
    cal = raw[n - 1].copy()
    maps = {}
    for test, fit in ((2024, (2025,)), (2025, (2024,)), (2026, (2024, 2025))):
        fit_rows = np.isin(years, fit)
        test_rows = years == test
        r = raw[n - 1]
        keep = fit_rows[:, None] & ~np.isnan(r) & ~np.isnan(obs)
        if keep.sum() < 50:
            continue
        mq, oq = C.fit_qm(r[keep], obs[keep])
        maps[test] = (mq, oq)
        cal[test_rows, :] = C.apply_qm(r[test_rows, :], mq, oq)
    return cal, maps


def loso_cal_concat(raw, obs, years, n):
    """LOSO calibrated values on the test seasons only, for p99 / Brier."""
    parts_c, parts_r, parts_o = [], [], []
    for test in SEASONS:
        fit = tuple(y for y in SEASONS if y != test)
        fit_rows = np.isin(years, fit)
        test_rows = years == test
        r = raw[n - 1]
        keep_fit = fit_rows[:, None] & ~np.isnan(r) & ~np.isnan(obs)
        if keep_fit.sum() < 50:
            continue
        mq, oq = C.fit_qm(r[keep_fit], obs[keep_fit])
        c = C.apply_qm(r[test_rows, :], mq, oq)
        o = obs[test_rows, :]
        keep = ~np.isnan(c) & ~np.isnan(o)
        parts_c.append(c[keep])
        parts_r.append(r[test_rows, :][keep])
        parts_o.append(o[keep])
    if not parts_c:
        return None, None, None
    return np.concatenate(parts_c), np.concatenate(parts_r), np.concatenate(parts_o)


def brier_skill_ge(vals_by_fold: dict, obs, years, event_mm: float):
    """Hard yes/no Brier skill vs per-cell climatology of IMERG >= event_mm,
    pooled across LOSO folds. vals_by_fold[test] is the calibrated field."""
    n_scored = hits = misses = fa = 0
    brier_num = bclim_num = 0.0
    for test in SEASONS:
        if test not in vals_by_fold:
            continue
        fit = tuple(y for y in SEASONS if y != test)
        clim = np.zeros(obs.shape[1])
        for ci in range(obs.shape[1]):
            o = obs[np.isin(years, fit), ci]
            o = o[~np.isnan(o)]
            clim[ci] = (float((o >= event_mm).sum()) / len(o)) if len(o) else 0.0
        vals = vals_by_fold[test]
        m = (years == test)[:, None] & ~np.isnan(vals) & ~np.isnan(obs)
        v = vals[m] >= event_mm
        o = obs[m] >= event_mm
        n = int(m.sum())
        if n == 0:
            continue
        n_scored += n
        hits += int((v & o).sum())
        misses += int((~v & o).sum())
        fa += int((v & ~o).sum())
        p, ob = v.astype(float), o.astype(float)
        clim_m = np.broadcast_to(clim, vals.shape)[m]
        brier_num += float(np.sum((p - ob) ** 2))
        bclim_num += float(np.sum((clim_m - ob) ** 2))
    if n_scored == 0 or bclim_num == 0:
        return {"n_scored": n_scored, "hits": hits, "misses": misses,
                "false_alarms": fa, "brier": None, "brier_clim": None, "skill": None}
    brier = brier_num / n_scored
    bclim = bclim_num / n_scored
    return {
        "n_scored": n_scored, "hits": hits, "misses": misses, "false_alarms": fa,
        "brier": round(brier, 4), "brier_clim": round(bclim, 4),
        "skill": round(1 - brier / bclim, 3),
    }


def loso_fields(raw, obs, years, n):
    out = {}
    for test in SEASONS:
        fit = tuple(y for y in SEASONS if y != test)
        r = raw[n - 1]
        keep = np.isin(years, fit)[:, None] & ~np.isnan(r) & ~np.isnan(obs)
        if keep.sum() < 50:
            continue
        mq, oq = C.fit_qm(r[keep], obs[keep])
        c = r.copy()
        c[years == test, :] = C.apply_qm(r[years == test, :], mq, oq)
        out[test] = c
    return out


def city_max(vals, di):
    row = vals[di]
    if np.isnan(row).all():
        return np.nan
    return float(np.nanmax(row))


def near_max(vals, di, ncs):
    if not ncs or any(np.isnan(vals[di, ci]) for ci in ncs):
        return np.nan
    return float(max(vals[di, ci] for ci in ncs))


def match_threshold(vals, years, target_n, seasons=FIT_SEASONS):
    """Smallest T (mm) whose citywide flag count on `seasons` is as close as
    possible to target_n. Ties keep the count from going over the budget."""
    maxes = []
    for di in range(len(years)):
        if years[di] not in seasons:
            continue
        mx = city_max(vals, di)
        if not np.isnan(mx):
            maxes.append(mx)
    if not maxes or target_n <= 0:
        return 0.0, 0
    maxes = np.asarray(maxes)
    # Candidate T's are the unique daily maxima: flag count changes only there.
    cands = np.unique(maxes)
    best_t, best_n, best_err = float(cands[0]), int((maxes >= cands[0]).sum()), 10**9
    for t in cands:
        n = int((maxes >= t).sum())
        err = abs(n - target_n)
        # prefer not exceeding the budget when errors tie
        over = n > target_n
        key = (err, over, -t)
        if key < (best_err, best_n > target_n, -best_t):
            best_t, best_n, best_err = float(t), n, err
    return round(best_t, 3), best_n


def score_at(vals, years, days, flood_days, near_cells, t, seasons=SEASONS):
    fd = [x for x in flood_days if int(x[:4]) in seasons]
    flagged_fd = 0
    fd_flags = {}
    day_idx = {x: i for i, x in enumerate(days)}
    flood_set = set(fd)
    for day in fd:
        di = day_idx.get(day)
        if di is None:
            continue
        mx = near_max(vals, di, near_cells[day])
        if np.isnan(mx):
            continue
        hit = mx >= t
        fd_flags[day] = hit
        if hit:
            flagged_fd += 1
    n_flagged = n_with_flood = n_scored_days = 0
    for di, day in enumerate(days):
        if years[di] not in seasons:
            continue
        if np.isnan(vals[di]).all():
            continue
        n_scored_days += 1
        if np.nanmax(vals[di]) >= t:
            n_flagged += 1
            if day in flood_set or day in set(flood_days):
                if day in set(flood_days):
                    n_with_flood += 1
    fa_share = (round((n_flagged - n_with_flood) / n_flagged, 3)
                if n_flagged else None)
    return {
        "threshold_mm": t,
        "flood_days_in_period": len(fd),
        "flood_days_flagged": flagged_fd,
        "days_scored": n_scored_days,
        "days_flagged": n_flagged,
        "days_flagged_with_flood_reported": n_with_flood,
        "false_alarm_share": fa_share,
        "flood_flags": fd_flags,
    }


def mcnemar_vs(base_flags: dict, other_flags: dict) -> dict:
    common = set(base_flags) & set(other_flags)
    b = sum(1 for x in common if other_flags[x] and not base_flags[x])
    c = sum(1 for x in common if base_flags[x] and not other_flags[x])
    p = C.mcnemar_p(b, c)
    plain = (
        f"gained {b} flood days on ECMWF IFS, lost {c} (exact McNemar p = {p:.2f}); "
        + ("this is unlikely to be pure noise."
           if p < 0.05 else
           "with 19 flood days this difference is within noise.")
    )
    return {"gained": b, "lost": c, "n_common": len(common),
            "mcnemar_p": round(p, 3), "plain": plain}


def pct(x):
    return None if x is None or (isinstance(x, float) and np.isnan(x)) else round(float(x), 1)


def main() -> None:
    generated_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    today = datetime.now(F.WAT).date()
    months = months_for(today)
    usable = [c for c in CANDIDATES if c["usable"]]
    dropped = [c for c in CANDIDATES if not c["usable"]]
    print(f"usable models: {', '.join(c['id'] for c in usable)}")
    print(f"dropped: {', '.join(c['id'] for c in dropped)}")

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

    packed = {}
    for cand in usable:
        mid = cand["id"]
        print(f"loading {mid} ...", flush=True)
        totals = load_raw(cells, months, mid)
        days, years, raw, obs = to_arrays(totals, cells, date_idx, series)
        packed[mid] = {"days": days, "years": years, "raw": raw, "obs": obs,
                       "cand": cand}
        n_ok = int((~np.isnan(raw[0])).sum())
        print(f"  {mid}: days {days[0]}..{days[-1]} ({len(days)}), "
              f"day-1 values {n_ok}", flush=True)

    # Align every model onto the baseline day axis (ECMWF's hindcast days).
    base = packed[BASELINE]
    days, years, obs = base["days"], base["years"], base["obs"]
    nD, nC = len(days), obs.shape[1]
    day_pos = {d: i for i, d in enumerate(days)}

    def aligned_raw(mid):
        src = packed[mid]
        src_pos = {d: i for i, d in enumerate(src["days"])}
        out = np.full_like(base["raw"], np.nan)
        for d, di in day_pos.items():
            sj = src_pos.get(d)
            if sj is None:
                continue
            out[:, di, :] = src["raw"][:, sj, :]
        return out

    raws = {mid: aligned_raw(mid) for mid in packed}

    flood_days = [x for x in sorted(areas_by_date)
                  if areas_by_date[x] and x in day_pos
                  and F.d(x).month in F.WINDOW_MONTHS]
    near_cells = {day: [ci for ci, c in enumerate(cells)
                        if any(F.haversine_km(c["lon"], c["lat"], lon, lat) <= F.AREA_MATCH_KM
                               for lon, lat in areas_by_date[day])]
                  for day in flood_days}
    print(f"flood days in window: {len(flood_days)}")

    # Calibrate each model (trust folds for flags; LOSO for p99/Brier).
    trust = {mid: {} for mid in raws}
    loso = {mid: {} for mid in raws}
    for mid, raw in raws.items():
        print(f"calibrating {mid} ...", flush=True)
        for n in CITY_LEADS:
            trust[mid][n] = trust_cal(raw, obs, years, n)[0]
            loso[mid][n] = loso_fields(raw, obs, years, n)

    # ECMWF alarm budget at 15 mm, frozen on 2024+2025.
    budget = {}
    ecmwf_fit_scores = {}
    for n in CITY_LEADS:
        ecmwf_fit_scores[n] = score_at(
            trust[BASELINE][n], years, days, flood_days, near_cells, RULE_MM,
            seasons=FIT_SEASONS)
        budget[n] = ecmwf_fit_scores[n]["days_flagged"]
        print(f"  ECMWF day-{n} 15 mm on 2024+2025 flags {budget[n]} days")

    def loso_stack(mid, n):
        """Calibrated values with each test season filled from its LOSO fold."""
        stacked = np.full((nD, nC), np.nan)
        for test, field in loso[mid][n].items():
            stacked[years == test, :] = field[years == test, :]
        return stacked

    rows = []
    flags_store = {}  # (mid, lead) -> flood_flags on all seasons
    fit_caught = {}   # mid -> day-1 flood days flagged on 2024+2025 (for blend pick)

    for cand in usable:
        mid = cand["id"]
        row = {
            "id": mid,
            "name": cand["name"],
            "kind": "model",
            "resolution": cand["resolution"],
            "leads": cand["leads"],
            "history_start": cand["history_start"],
            "licence": cand["licence"],
        }
        for n in CITY_LEADS:
            vals = trust[mid][n]
            if mid == BASELINE:
                t = RULE_MM
            else:
                t, _ = match_threshold(vals, years, budget[n], seasons=FIT_SEASONS)
            fit = score_at(vals, years, days, flood_days, near_cells, t,
                           seasons=FIT_SEASONS)
            alls = score_at(vals, years, days, flood_days, near_cells, t,
                            seasons=SEASONS)
            y2026 = score_at(vals, years, days, flood_days, near_cells, t,
                             seasons=(2026,))
            flags_store[(mid, n)] = alls["flood_flags"]
            cal_c, cal_r, cal_o = loso_cal_concat(raws[mid], obs, years, n)
            brier = brier_skill_ge(loso[mid][n], obs, years, SOME)
            lead = {
                "threshold_mm": t,
                "threshold_source": (
                    f"ECMWF IFS 15 mm rule (the live warning line)"
                    if mid == BASELINE else
                    f"matched to ECMWF's {budget[n]} flagged days on 2024+2025"
                ),
                "fit_2024_2025": {k: fit[k] for k in (
                    "flood_days_in_period", "flood_days_flagged", "days_flagged",
                    "days_flagged_with_flood_reported", "false_alarm_share")},
                "all_seasons": {k: alls[k] for k in (
                    "flood_days_in_period", "flood_days_flagged", "days_flagged",
                    "days_flagged_with_flood_reported", "false_alarm_share")},
                "test_2026": {k: y2026[k] for k in (
                    "flood_days_in_period", "flood_days_flagged", "days_flagged",
                    "days_flagged_with_flood_reported", "false_alarm_share")},
                "calibrated_p99_mm": pct(None if cal_c is None else np.nanpercentile(cal_c, 99)),
                "raw_p99_mm": pct(None if cal_r is None else np.nanpercentile(cal_r, 99)),
                "imerg_p99_mm": pct(None if cal_o is None else np.nanpercentile(cal_o, 99)),
                "brier_ge_20mm": brier,
            }
            if mid != BASELINE:
                lead["vs_ecmwf"] = mcnemar_vs(flags_store[(BASELINE, n)],
                                              alls["flood_flags"])
            else:
                lead["vs_ecmwf"] = {
                    "gained": 0, "lost": 0,
                    "n_common": len(alls["flood_flags"]),
                    "mcnemar_p": 1.0,
                    "plain": "baseline.",
                }
            row[f"day{n}"] = lead
            if n == 1:
                fit_caught[mid] = fit["flood_days_flagged"]
        rows.append(row)
        d1 = row["day1"]["all_seasons"]
        print(f"  {mid} day1 T={row['day1']['threshold_mm']} mm: "
              f"flood days {d1['flood_days_flagged']}/{d1['flood_days_in_period']}, "
              f"days flagged {d1['days_flagged']}, FA {d1['false_alarm_share']}")

    # Blends: freeze members on 2024+2025 before looking at 2026.
    ranked = sorted(fit_caught, key=lambda m: (-fit_caught[m], m))
    best_two = ranked[:2]
    all_ids = [c["id"] for c in usable]
    print(f"best two on 2024+2025 day-1 flood days caught: {best_two} "
          f"({ {m: fit_caught[m] for m in best_two} })")

    def blend_field(members, n):
        stack = np.stack([trust[m][n] for m in members], axis=0)
        # Mean only where every member has a value, so a hole cannot inflate skill.
        return np.mean(stack, axis=0)

    blends = [
        {"id": "blend_best_two", "name": "Mean of the best two (frozen on 2024+2025)",
         "members": best_two},
        {"id": "blend_all", "name": "Mean of every usable model",
         "members": all_ids},
    ]
    blend_rows = []
    for b in blends:
        row = {
            "id": b["id"], "name": b["name"], "kind": "blend",
            "members": b["members"],
            "rule": "mean of the calibrated daily totals, members fixed on 2024+2025",
        }
        for n in CITY_LEADS:
            vals = blend_field(b["members"], n)
            t, _ = match_threshold(vals, years, budget[n], seasons=FIT_SEASONS)
            fit = score_at(vals, years, days, flood_days, near_cells, t,
                           seasons=FIT_SEASONS)
            alls = score_at(vals, years, days, flood_days, near_cells, t,
                            seasons=SEASONS)
            y2026 = score_at(vals, years, days, flood_days, near_cells, t,
                             seasons=(2026,))
            loso_b = {}
            for test in SEASONS:
                fields = [loso[m][n].get(test) for m in b["members"]]
                if any(f is None for f in fields):
                    continue
                loso_b[test] = np.mean(np.stack(fields, axis=0), axis=0)
            stacked = np.full((nD, nC), np.nan)
            for test, field in loso_b.items():
                stacked[years == test, :] = field[years == test, :]
            keep = ~np.isnan(stacked) & ~np.isnan(obs)
            brier = brier_skill_ge(loso_b, obs, years, SOME)
            row[f"day{n}"] = {
                "threshold_mm": t,
                "threshold_source": f"matched to ECMWF's {budget[n]} flagged days on 2024+2025",
                "fit_2024_2025": {k: fit[k] for k in (
                    "flood_days_in_period", "flood_days_flagged", "days_flagged",
                    "days_flagged_with_flood_reported", "false_alarm_share")},
                "all_seasons": {k: alls[k] for k in (
                    "flood_days_in_period", "flood_days_flagged", "days_flagged",
                    "days_flagged_with_flood_reported", "false_alarm_share")},
                "test_2026": {k: y2026[k] for k in (
                    "flood_days_in_period", "flood_days_flagged", "days_flagged",
                    "days_flagged_with_flood_reported", "false_alarm_share")},
                "calibrated_p99_mm": pct(np.nanpercentile(stacked[keep], 99) if keep.any() else np.nan),
                "imerg_p99_mm": pct(np.nanpercentile(obs[keep], 99) if keep.any() else np.nan),
                "brier_ge_20mm": brier,
                "vs_ecmwf": mcnemar_vs(flags_store[(BASELINE, n)], alls["flood_flags"]),
            }
        blend_rows.append(row)
        d1 = row["day1"]["all_seasons"]
        print(f"  {b['id']} day1 T={row['day1']['threshold_mm']} mm: "
              f"flood days {d1['flood_days_flagged']}/{d1['flood_days_in_period']}, "
              f"days flagged {d1['days_flagged']}")

    rec, rec_why = recommend(rows, blend_rows, best_two)

    meta = {
        "built_by": "pipeline/compare_models.py",
        "task": "46-compare-models (docs/tasks/46-compare-models.md)",
        "generated_at": generated_at,
        "endpoint": H.PREVIOUS_RUNS_URL,
        "period": {"start": days[0], "end": days[-1],
                   "months": "April–November of 2024, 2025 and 2026 so far",
                   "years": list(SEASONS)},
        "cells": f"{len(cells)} IMERG 0.1 deg cell centres, same as the live forecast",
        "observations": "events/rain_history_grid_daily.json (NASA GPM IMERG daily totals per cell)",
        "flood_days": "events/flood_days.json; a cell matches a flood day when a reported area lies within 5 km",
        "cache": "pipeline/cache/hindcast/<model>/ (ECMWF IFS 0.25 stays at pipeline/cache/hindcast/)",
        "licence": "CC BY 4.0 (Open-Meteo); each model's upstream licence is in its row; NASA IMERG open data",
        "candidates": CANDIDATES,
        "usable": [c["id"] for c in usable],
        "dropped": [{"id": c["id"], "reason": c["drop_reason"]} for c in dropped],
        "method": (
            "Each usable model is fetched from the Open-Meteo Previous Runs API "
            "for the same 68 cells and April–November 2024–2026 window as "
            "pipeline/hindcast.py, one multi-coordinate call per model per month "
            "(all previous-day leads in that one call). Hourly precipitation is "
            "summed to Africa/Lagos calendar days. Each model is then quantile-"
            "mapped to IMERG per lead day, pooling cells, with the same trust "
            "folds as pipeline/calibrate.py (2024 fit on 2025, 2025 fit on 2024, "
            "2026 fit on 2024+2025) so every flood-day number is out of sample. "
            "The fair comparison is at a fixed alarm budget: on 2024+2025, ECMWF "
            f"IFS at its {RULE_MM:g} mm calibrated rule flags a known number of "
            "days; every other model (and each blend) gets the threshold that "
            "flags as close as possible to that many days on 2024+2025. That "
            "threshold is frozen before 2026 is scored. Brier skill for ≥ 20 mm "
            "and the calibrated p99 use full leave-one-season-out. Blends are "
            "the mean of the calibrated totals; the best two models are the two "
            "with the most 2024+2025 day-1 flood days caught at the matched "
            "budget, frozen before 2026 is looked at."
        ),
        "alarm_budget": {
            "baseline": BASELINE,
            "rule_mm": RULE_MM,
            "fit_seasons": list(FIT_SEASONS),
            "day1_days_flagged_2024_2025": budget[1],
            "day3_days_flagged_2024_2025": budget[3],
        },
        "blend": {
            "rule": "mean of calibrated daily totals (all members must be present)",
            "best_two": best_two,
            "best_two_chosen_by": (
                "most 2024+2025 day-1 flood days flagged at the matched budget; "
                "2026 was not used to pick the members"
            ),
        },
        "recommendation": {"choice": rec, "why": rec_why},
        "api_cost": api_cost_notes(),
        "caveats": [
            "This comparison scores one deterministic Previous Runs series per "
            "model, not the 51-member ECMWF ensemble the live product uses. A "
            "deterministic model can only adjust those chances or act as a "
            "second opinion.",
            "Quantile mapping restores the size of rain a model already saw; it "
            "cannot invent a storm the model never placed on Lagos.",
            "The reported-flood catalog undercounts real floods, so a flagged "
            "day with no report is not proof no flood happened.",
            "With 19 flood days, McNemar will usually call a difference noise. "
            "The vs_ecmwf.plain field on each row says so when it is.",
        ],
        "sources": [
            "https://open-meteo.com/en/docs/previous-runs-api",
            "https://open-meteo.com/en/docs",
            "https://github.com/open-meteo/open-data/blob/main/README.md",
        ],
    }
    out = {"meta": meta, "models": rows, "blends": blend_rows}
    OUT.write_text(json.dumps(out, indent=1) + "\n")
    print(f"wrote {OUT.relative_to(F.ROOT)}")
    DOC.write_text(render_doc(out))
    print(f"wrote {DOC.relative_to(F.ROOT)}")


def api_cost_notes():
    return {
        "live_today": (
            "The live run makes 1 Open-Meteo Ensemble call for ECMWF IFS 0.25 "
            "(51 members) and 1 for GFS 0.25 as an uncalibrated second opinion, "
            "plus 4 Flood API calls. Weather-model cost is 2 forecast calls/day."
        ),
        "keep_ecmwf": "0 extra weather-model calls/day.",
        "switch_headline_to_other_ensemble": (
            "Still 1 headline ensemble call/day if that model has an ensemble "
            "on the Ensemble API (ICON and GFS do; ARPEGE/GEM/JMA/CMA/BOM "
            "deterministic would replace the 51-member chance ladder with a "
            "single run). Recalibrate first. Do not do this from this file alone."
        ),
        "add_second_opinion": (
            "1 extra Ensemble or Forecast API call/day per added model. A "
            "deterministic second opinion can raise or lower a cell's level "
            "when it disagrees with the ECMWF ensemble median, but it cannot "
            "replace the 51-member chances."
        ),
        "blend": (
            "1 Forecast/Ensemble call/day per member of the blend. A mean of "
            "deterministic totals is not an ensemble: it can be a second "
            "opinion on the daily total, not a replacement for P(≥ 40 mm)."
        ),
    }


def recommend(rows, blend_rows, best_two):
    """Keep ECMWF unless another model beats it on day-1 flood days caught
    AND McNemar says that is not noise. Otherwise offer a second opinion
    when the gain is suggestive, or keep ECMWF."""
    ecmwf = next(r for r in rows if r["id"] == BASELINE)
    e_n = ecmwf["day1"]["all_seasons"]["flood_days_flagged"]
    better = []
    for r in rows:
        if r["id"] == BASELINE:
            continue
        n = r["day1"]["all_seasons"]["flood_days_flagged"]
        p = r["day1"]["vs_ecmwf"]["mcnemar_p"]
        better.append((n - e_n, p, r))
    better.sort(key=lambda x: (-x[0], x[1]))
    if not better:
        return "keep ECMWF", "No other usable model."
    gain, p, top = better[0]
    top_n = top["day1"]["all_seasons"]["flood_days_flagged"]
    blend_best = blend_rows[0]["day1"]["all_seasons"]["flood_days_flagged"]
    blend_p = blend_rows[0]["day1"]["vs_ecmwf"]["mcnemar_p"]
    if gain > 0 and p < 0.05:
        return (
            "switch",
            f"{top['name']} caught {top_n} of 19 flood days the day before "
            f"against ECMWF's {e_n}, at the same alarm budget, and McNemar "
            f"p = {p} is below 0.05. That is the only case this comparison "
            "would switch the headline. The live product still needs that "
            "model's ensemble (or it can only be a second opinion)."
        )
    if gain > 0:
        return (
            "add a model as a second opinion",
            f"{top['name']} caught {top_n} of 19 flood days the day before "
            f"against ECMWF's {e_n} at the same alarm budget, but McNemar "
            f"p = {p} — with 19 flood days that is within noise. Do not switch "
            "the 51-member headline. If you add anyone, add this model as a "
            "calibrated second opinion (one extra API call/day) and keep ECMWF "
            "for the chances. The best-two blend "
            f"({'+'.join(best_two)}) caught {blend_best} of 19 (p = {blend_p}), "
            "which is also within noise unless p < 0.05."
        )
    return (
        "keep ECMWF",
        f"No usable model caught more of the 19 flood days than ECMWF IFS "
        f"({e_n}) at the same alarm budget. The best-two blend "
        f"({'+'.join(best_two)}) caught {blend_best} (p = {blend_p}). Stay "
        "on the ECMWF 51-member ensemble; a deterministic other model is not "
        "earning its extra API call."
    )


def cell(v):
    return "—" if v is None else v


def render_doc(doc: dict) -> str:
    m = doc["meta"]
    lines = []
    lines.append("# Did another weather model see Lagos storms better?")
    lines.append("")
    lines.append(
        "The live forecast uses ECMWF IFS at 0.25° (~28 km). Its deterministic "
        "hindcast gets the average right but flattens Lagos storms: the heaviest "
        "days are about half as heavy as IMERG, and at the 15 mm warning line "
        "it caught 11 of 19 flood days the day before, with about 94% of "
        "warnings on days with no flood reported. This page asks whether a "
        "finer or differently built model, scored the same way, would do better."
    )
    lines.append("")
    lines.append("It does **not** change the live forecast. Task 46 only measures.")
    lines.append("")
    lines.append("## Who was in, who was out")
    lines.append("")
    lines.append(
        "Checked against the [Previous Runs API](https://open-meteo.com/en/docs/previous-runs-api) "
        "and each model's Open-Meteo page, then probed at Lagos (6.55 N, 3.35 E) "
        "for `precipitation_previous_day1`–`day7`. Free, no key, open licence, "
        "and history covering April–November 2024–2026, or it is out."
    )
    lines.append("")
    lines.append("| Model | Resolution | Leads | History | In? |")
    lines.append("|---|---|---|---|---|")
    for c in m["candidates"]:
        mark = "yes" if c["usable"] else "no"
        lines.append(f"| {c['name']} (`{c['id']}`) | {c['resolution']} | {c['leads']} | {c['history_start']} | {mark} |")
    lines.append("")
    lines.append("Dropped, and why:")
    lines.append("")
    for d in m["dropped"]:
        name = next(c["name"] for c in m["candidates"] if c["id"] == d["id"])
        lines.append(f"- **{name}** (`{d['id']}`): {d['reason']}")
    lines.append("")
    lines.append("## How the comparison is fair")
    lines.append("")
    lines.append(
        "Different models sit on different millimetre scales, so a shared 15 mm "
        "or 40 mm line would be unfair. Each model is quantile-mapped to IMERG "
        "the same way as `pipeline/calibrate.py`, out of sample. Then, on "
        "2024+2025 only, ECMWF IFS at 15 mm flags a fixed number of days; every "
        "other model (and each blend) is given the threshold that flags as close "
        "as possible to that many days. That threshold is frozen before 2026 is "
        "scored. The table below is the three-season total at that frozen line."
    )
    lines.append("")
    lines.append(
        f"ECMWF's 2024+2025 budget is **{m['alarm_budget']['day1_days_flagged_2024_2025']} days** "
        f"the day before and **{m['alarm_budget']['day3_days_flagged_2024_2025']} days** "
        "at day 3."
    )
    lines.append("")
    lines.append(
        "Blends are the mean of the calibrated daily totals. The best two "
        f"were {', '.join(m['blend']['best_two'])}, chosen on 2024+2025 day-1 "
        "flood days caught, before 2026 was looked at."
    )
    lines.append("")
    lines.append("## Day before (lead 1)")
    lines.append("")
    lines.append(
        "| Model | Warning line | Flood days caught (of 19) | Days flagged | False-alarm share | Calibrated p99 vs IMERG 54 mm | Brier skill ≥ 20 mm | vs ECMWF |"
    )
    lines.append("|---|---|---|---|---|---|---|---|")
    for r in doc["models"] + doc["blends"]:
        d = r["day1"]
        a = d["all_seasons"]
        p99 = d.get("calibrated_p99_mm")
        im = d.get("imerg_p99_mm")
        p99s = f"{p99} mm" if p99 is not None else "—"
        if im is not None:
            p99s += f" (IMERG {im})"
        brier = d.get("brier_ge_20mm") or {}
        skill = brier.get("skill") if isinstance(brier, dict) else None
        vs = d["vs_ecmwf"]["plain"]
        name = r["name"] if r.get("kind") == "blend" else f"{r['name']} (`{r['id']}`)"
        lines.append(
            f"| {name} | {d['threshold_mm']} mm | "
            f"{a['flood_days_flagged']}/{a['flood_days_in_period']} | "
            f"{a['days_flagged']} | {cell(a['false_alarm_share'])} | "
            f"{p99s} | {cell(skill)} | {vs} |"
        )
    lines.append("")
    lines.append("## Three days before (lead 3)")
    lines.append("")
    lines.append(
        "| Model | Warning line | Flood days caught (of 19) | Days flagged | False-alarm share | Calibrated p99 vs IMERG 54 mm | Brier skill ≥ 20 mm | vs ECMWF |"
    )
    lines.append("|---|---|---|---|---|---|---|---|")
    for r in doc["models"] + doc["blends"]:
        d = r["day3"]
        a = d["all_seasons"]
        p99 = d.get("calibrated_p99_mm")
        im = d.get("imerg_p99_mm")
        p99s = f"{p99} mm" if p99 is not None else "—"
        if im is not None:
            p99s += f" (IMERG {im})"
        brier = d.get("brier_ge_20mm") or {}
        skill = brier.get("skill") if isinstance(brier, dict) else None
        vs = d["vs_ecmwf"]["plain"]
        name = r["name"] if r.get("kind") == "blend" else f"{r['name']} (`{r['id']}`)"
        lines.append(
            f"| {name} | {d['threshold_mm']} mm | "
            f"{a['flood_days_flagged']}/{a['flood_days_in_period']} | "
            f"{a['days_flagged']} | {cell(a['false_alarm_share'])} | "
            f"{p99s} | {cell(skill)} | {vs} |"
        )
    lines.append("")
    lines.append("## Recommendation")
    lines.append("")
    lines.append(f"**{m['recommendation']['choice']}.** {m['recommendation']['why']}")
    lines.append("")
    lines.append("### What that would cost")
    lines.append("")
    cost = m["api_cost"]
    lines.append(f"- Live today: {cost['live_today']}")
    lines.append(f"- Keep ECMWF: {cost['keep_ecmwf']}")
    lines.append(f"- Add a second opinion: {cost['add_second_opinion']}")
    lines.append(f"- Switch the headline: {cost['switch_headline_to_other_ensemble']}")
    lines.append(f"- Blend: {cost['blend']}")
    lines.append("")
    lines.append(
        "A deterministic Previous Runs series is not the live product. The live "
        "product's chances come from 51 ECMWF members. Another deterministic "
        "model can only nudge a level or sit beside the card as a second "
        "opinion; it cannot honestly replace P(≥ 40 mm) unless that model also "
        "has an ensemble and we calibrate it."
    )
    lines.append("")
    lines.append("## Caveats")
    lines.append("")
    for c in m["caveats"]:
        lines.append(f"- {c}")
    lines.append("")
    lines.append(
        f"Built by `{m['built_by']}` on {m['generated_at']}. Numbers: "
        "`events/forecast/model_compare.json`."
    )
    lines.append("")
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    main()
