#!/usr/bin/env python3
"""Task 38 (docs/tasks/38-forecast-pipeline.md): daily flood-risk forecast pipeline, part 1.

FloodTrace does not run a weather model: it takes published forecasts and
combines them with its own satellite-rain history. Per run it fetches, once:

  * the ECMWF IFS 0.25 deg ensemble (control + 50 members) for all 68 IMERG
    0.1 deg cells (one multi-coordinate call; GFS 0.25 deg as a second opinion,
    a second call) from the Open-Meteo Ensemble API;
  * the GloFAS river ensemble and its 1984-present daily-flow history for two
    river points from the Open-Meteo Flood API (4 calls);
and gets the EOT20 astronomical tide from the precomputed table
(events/forecast/tide_table.json) or, when the window is outside it, locally
with pyTMD (no network either way).

Since Task 44 the ensemble's rain is CALIBRATED to Lagos rain before any number
is computed: pipeline/calibrate.py fits a quantile mapping per lead day on the
2024-2026 hindcast (ECMWF IFS runs vs IMERG daily totals) and writes it to
events/forecast/calibration.json, which this script reads and applies to every
ensemble member's daily total (hourly values scaled by the same daily factor).
median_mm is calibrated; raw_median_mm keeps the uncalibrated median beside it.

Output, validated against pipeline/schemas/forecast.schema.json:
  events/forecast/<run-date>.json   (never overwritten: a same-day rerun gets a
                                    time suffix, e.g. 2026-10-21-0932.json)
  events/forecast/latest.json      (byte copy of the newest run)
  events/forecast/index.json       (the list of archived runs)

Usage:
    pipeline/.venv/bin/python pipeline/forecast.py

Run for today (Africa/Lagos). About 6 API calls on a fresh day; raw responses
are cached under pipeline/cache/forecast/<run-date>/ and reused on a same-day
rerun, so the archived numbers stay reproducible. Foreground only; no key
needed for any API. The daily wrapper is pipeline/run_daily.py (see docs/FORECAST.md).
"""
from __future__ import annotations

import json
import math
import os
import re
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import requests

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "pipeline"))
import pyTMD.compute  # noqa: E402
import jsonschema  # noqa: E402
from tide_eot20 import MODEL_DIR as TIDE_MODEL_DIR, EPOCH as TIDE_EPOCH  # noqa: E402

EVENTS = ROOT / "events"
OUT_DIR = EVENTS / "forecast"
# FLOODTRACE_TIDE_TABLE points at a different precomputed tide table (testing
# the live-computation fallback with FLOODTRACE_TIDE_MODEL_DIR beside it).
TIDE_TABLE_PATH = Path(
    os.environ.get("FLOODTRACE_TIDE_TABLE") or OUT_DIR / "tide_table.json"
)
CACHE_ROOT = ROOT / "pipeline" / "cache" / "forecast"
SCHEMA_PATH = ROOT / "pipeline" / "schemas" / "forecast.schema.json"

WAT = timezone(timedelta(hours=1))
ENSEMBLE_URL = "https://ensemble-api.open-meteo.com/v1/ensemble"
FLOOD_URL = "https://flood-api.open-meteo.com/v1/flood"
UA = {"User-Agent": "FloodTrace/1.0 (daily flood-risk pipeline)"}

FORECAST_DAYS = 7
RIVER_HISTORY_START = "1984-01-01"

# (id, plain name, requested [lon, lat]); the Flood API snaps each request to
# its GloFAS river cell and the snapped coordinates are recorded in the output.
RIVER_POINTS = [
    ("ogun-ishi", "Ogun near Isheri/Kara", [3.382, 6.617]),
    ("owo-ikorodu", "Osun/Owo outlet near Ikorodu", [3.68, 6.55]),
]

# ---- thresholds and rules (documented again in the output's meta) ----------
HOURLY_RATE_MM_H = 10.0     # hourly rain rate that makes an hour "at risk"
MEMBER_SHARE = 0.30         # or this share of members reaching that rate
DAILY_MM = (20, 40, 60)    # chance-of-at-least amounts in 24 h
HEAVY_MM = 40              # the history threshold used in storm_replay.py
ANALOGUE_TOL = 0.25        # analogue day within +/- 25% of the forecast median
ANALOGUE_MIN_MM = 20.0
MAX_ANALOGUES = 5
TIDE_OVERLAP_H = 2.0       # risk window counts as near_high_tide within +/- 2 h
AREA_MATCH_KM = 5.0        # a flood report matches a cell within this distance
LEVEL_MIN_DAYS = 5         # history can only nudge a level with >= 5 class days
LEVEL_UP_SHARE = 0.25      # >= this share of class days flooded -> step up
LEVELS = ["none", "low", "medium", "high"]
WINDOW_MONTHS = range(4, 12)  # April-November, as in storm_replay.py
CLASS_LABELS = {"10-20": "10-20 mm", "20-40": "20-40 mm", "ge-40": "40+ mm"}

STATS = {"api_calls": 0, "cache_hits": 0}


# ---- small helpers --------------------------------------------------------
def fetch_json(url: str, cache_path: Path):
    """GET url, or reuse the raw response cached for this run-date."""
    if cache_path.exists():
        STATS["cache_hits"] += 1
        return json.loads(cache_path.read_text())
    r = requests.get(url, headers=UA, timeout=240)
    r.raise_for_status()
    data = r.json()
    cache_path.write_text(json.dumps(data))
    STATS["api_calls"] += 1
    return data


def haversine_km(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    r = 6371.0088
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def d(s: str) -> date:
    return date.fromisoformat(s)


# ---- ensemble rain --------------------------------------------------------
def ensemble_url(cells: list, model: str) -> str:
    lats = ",".join(str(c["lat"]) for c in cells)
    lons = ",".join(str(c["lon"]) for c in cells)
    return (f"{ENSEMBLE_URL}?latitude={lats}&longitude={lons}&hourly=precipitation"
            f"&models={model}&forecast_days={FORECAST_DAYS}&timezone=Africa%2FLagos")


def member_keys(hourly: dict) -> list:
    keys = [k for k in hourly if re.fullmatch(r"precipitation_member\d+", k)]
    keys.sort(key=lambda k: int(k.split("member")[1]))
    return ["precipitation"] + keys


def parse_ensemble(data, cells: list, run_day: str):
    """Return {cell_id: (n_series, n_hours) ndarray} and the shared local times."""
    if not isinstance(data, list) or len(data) != len(cells):
        raise SystemExit(f"ensemble response has {len(data)} locations, want {len(cells)}")
    times = data[0]["hourly"]["time"]
    if len(times) != FORECAST_DAYS * 24 or times[0] != f"{run_day}T00:00":
        raise SystemExit(f"unexpected ensemble time axis: {len(times)} hours from {times[0]}")
    out = {}
    for rec, cell in zip(data, cells):
        hourly = rec["hourly"]
        if hourly["time"] != times:
            raise SystemExit(f"time axis mismatch at cell {cell['id']}")
        rows = []
        for k in member_keys(hourly):
            col = hourly[k]
            if any(v is None for v in col):
                raise SystemExit(f"nulls in ensemble series {k} at cell {cell['id']}")
            rows.append(col)
        out[cell["id"]] = np.array(rows, dtype=float)
    return out, times


def day_totals_and_chances(sub: np.ndarray):
    totals = sub.sum(axis=1)
    return totals, float(np.median(totals)), float(np.percentile(totals, 90)), \
        {t: float(np.mean(totals >= t)) for t in DAILY_MM}


# ---- calibration (Task 44) -------------------------------------------------
CAL_PATH = OUT_DIR / "calibration.json"


def load_calibration() -> dict:
    """Read the quantile mapping fitted by pipeline/calibrate.py, plus the
    level rule and trust numbers from its meta."""
    if not CAL_PATH.exists():
        raise SystemExit(
            "events/forecast/calibration.json is missing: run pipeline/calibrate.py "
            "first (it needs the hindcast cache built by pipeline/hindcast.py)")
    doc = json.loads(CAL_PATH.read_text())
    pct = np.array(doc["percentiles"], dtype=float)
    maps = {int(k): (np.array(v["model_mm"], dtype=float),
                     np.array(v["observed_mm"], dtype=float))
            for k, v in doc["mapping"].items()}
    meta = doc.get("meta", {})
    rule = meta.get("level_rule") or {}
    return {
        "pct": pct,
        "maps": maps,
        # the hindcast-derived floor on the calibrated median (None: not applied)
        "rule_mm": float(rule["threshold_mm"]) if rule.get("applied") else None,
        "meta": meta,
        "fit_period": (meta.get("fit_period") or {}),
    }


def calibrate_mm(values: np.ndarray, pct: np.ndarray, mq: np.ndarray, oq: np.ndarray) -> np.ndarray:
    """Map model mm to IMERG-equivalent mm through the fitted quantile mapping:
    the value's percentile in the fit model sample becomes the same percentile
    of the fit IMERG sample. NaN stays NaN; values above the fit maximum clip
    to the fit IMERG maximum."""
    p = np.interp(values, mq, pct)
    return np.interp(p, pct, oq)


def risk_ranges(sub: np.ndarray, times: list) -> list:
    """Consecutive-hours ranges where the median rate is high or many members are."""
    hour_med = np.median(sub, axis=0)
    share = np.mean(sub >= HOURLY_RATE_MM_H, axis=0)
    flag = (hour_med >= HOURLY_RATE_MM_H) | (share >= MEMBER_SHARE)
    ranges = []
    h = 0
    while h < len(flag):
        if not flag[h]:
            h += 1
            continue
        h0 = h
        while h + 1 < len(flag) and flag[h + 1]:
            h += 1
        end = datetime.fromisoformat(times[h]) + timedelta(hours=1)
        ranges.append({"start": times[h0], "end": end.isoformat(timespec="minutes")})
        h += 1
    return ranges, flag


# ---- tide -----------------------------------------------------------------
def tide_hour_times(run_day: date) -> list:
    """The forecast's hour grid: run day 00:00 WAT, hourly, FORECAST_DAYS long."""
    start = datetime(run_day.year, run_day.month, run_day.day, tzinfo=WAT)
    end = start + timedelta(days=FORECAST_DAYS)
    times, t = [], start
    while t < end:
        times.append(t)
        t += timedelta(hours=1)
    return times


def tide_values_from_table(times: list, lon: float, lat: float) -> list | None:
    """Hourly tide heights from the precomputed table, or None when the table
    does not cover the forecast window or this point."""
    if not TIDE_TABLE_PATH.is_file():
        return None
    table = json.loads(TIDE_TABLE_PATH.read_text(encoding="utf-8"))
    meta = table["meta"]
    if meta.get("interval_hours") != 1:
        return None
    start = datetime.fromisoformat(meta["start"])
    if start.utcoffset() != times[0].utcoffset():
        return None  # the table is on a different hour grid
    index0 = int((times[0] - start).total_seconds() // 3600)
    values = None
    for point in table["points"]:
        if point["lon"] == lon and point["lat"] == lat:
            values = point["values"]
            break
    if values is None:
        return None
    if index0 < 0 or index0 + len(times) > len(values):
        return None  # window not inside the table
    return values[index0:index0 + len(times)]


def tide_values_from_model(times: list, lon: float, lat: float) -> list:
    """Hourly tide heights computed live with pyTMD (needs the 2.1 GB model)."""
    if not (TIDE_MODEL_DIR / "EOT20").is_dir():
        try:
            table_ref = str(TIDE_TABLE_PATH.relative_to(ROOT))
        except ValueError:
            table_ref = str(TIDE_TABLE_PATH)
        raise SystemExit(
            "tide unavailable: the forecast window is not covered by "
            f"{table_ref} and the EOT20 model is not present under "
            f"{TIDE_MODEL_DIR}. Regenerate the table with "
            "pipeline/tide_table.py on a machine that has the model, or see "
            "docs/FORECAST.md for the model itself."
        )
    delta = np.array([(x.astimezone(timezone.utc) - TIDE_EPOCH).total_seconds()
                      for x in times])
    tide = pyTMD.compute.tide_elevations(
        np.array([lon]), np.array([lat]), delta,
        directory=TIDE_MODEL_DIR, model="EOT20", crs=4326,
        epoch=(2000, 1, 1, 0, 0, 0), type="time series", standard="UTC",
        extrapolate=True, cutoff=20.0)
    values = np.ma.filled(np.ma.asarray(tide, dtype=float), np.nan).reshape(-1)
    if np.isnan(values).any():
        raise SystemExit("EOT20 returned NaN hours at the offshore point")
    return [round(float(v), 2) for v in values]  # centimetre, as in the table


def compute_tides(run_day: date, event_dirs: list):
    """High tides over the forecast window, from the precomputed table when it
    covers the window (the daily cloud run needs no 2.1 GB model), else
    computed live with pyTMD. Heights are rounded to the centimetre on both
    paths, so the two agree exactly."""
    ev = json.loads((event_dirs[-1] / "event.json").read_text())
    lon, lat = ev["aoi"]["points"]["offshore_tide"]
    times = tide_hour_times(run_day)
    values = tide_values_from_table(times, lon, lat)
    if values is not None:
        source = "the precomputed tide table (events/forecast/tide_table.json)"
    else:
        values = tide_values_from_model(times, lon, lat)
        source = "a local pyTMD computation (EOT20 model files)"
    high = []
    for i in range(1, len(values) - 1):
        if values[i] >= values[i - 1] and values[i] > values[i + 1]:
            high.append({
                "time": times[i].replace(tzinfo=None).isoformat(timespec="minutes"),
                "height_m": round(float(values[i]), 2),
            })
    return ({"point": {"lon": lon, "lat": lat,
                      "source": f"events/{event_dirs[-1].name}/event.json aoi.points.offshore_tide"},
             "high_tides": high},
            [datetime.fromisoformat(h["time"]) for h in high],
            source)


# ---- rivers ---------------------------------------------------------------
def river_forecast(rid: str, req: list, cache_dir: Path, forecast_days: list):
    url = (f"{FLOOD_URL}?latitude={req[1]}&longitude={req[0]}&daily=river_discharge"
           f"&ensemble=true&forecast_days={FORECAST_DAYS}&timezone=Africa%2FLagos")
    data = fetch_json(url, cache_dir / f"flood_{rid}_ensemble.json")
    daily = data["daily"]
    if daily["time"] != forecast_days:
        raise SystemExit(f"river {rid} forecast days {daily['time']} != {forecast_days}")
    keys = [k for k in daily if re.fullmatch(r"river_discharge_member\d+", k)]
    keys.sort(key=lambda k: int(k.split("member")[1]))
    rows = [daily["river_discharge"]] + [daily[k] for k in keys]
    return np.array(rows, dtype=float), [data["longitude"], data["latitude"]]


def river_history(rid: str, req: list, cache_dir: Path, run_day: date):
    url = (f"{FLOOD_URL}?latitude={req[1]}&longitude={req[0]}&daily=river_discharge"
           f"&start_date={RIVER_HISTORY_START}&end_date={(run_day - timedelta(days=1)).isoformat()}")
    data = fetch_json(url, cache_dir / f"flood_{rid}_history.json")
    daily = data["daily"]
    pairs = [(t, v) for t, v in zip(daily["time"], daily["river_discharge"])
             if v is not None]
    if not pairs:
        raise SystemExit(f"river {rid}: no historical discharge values")
    vals = np.array([v for _, v in pairs])
    return {
        "start": pairs[0][0],
        "end": pairs[-1][0],
        "n_days": len(vals),
        "p90_m3s": round(float(np.percentile(vals, 90)), 1),
        "p99_m3s": round(float(np.percentile(vals, 99)), 1),
        "max_m3s": round(float(vals.max()), 1),
    }


# ---- risk level -----------------------------------------------------------
def base_level(p20: float, p40: float) -> str:
    if p40 >= 0.30:
        return "high"
    if p40 >= 0.10:
        return "medium"
    if p20 >= 0.20:
        return "low"
    return "none"


def level_for(median_mm: float, p20: float, p40: float, cls_stats: dict):
    base = base_level(p20, p40)
    if median_mm >= 40:
        cls = "ge-40"
    elif median_mm >= 20:
        cls = "20-40"
    elif median_mm >= 10:
        cls = "10-20"
    else:
        cls = None
    hist = None
    nudge = None
    if cls:
        n, k = cls_stats[cls]
        hist = {
            "class_mm": CLASS_LABELS[cls],
            "n_days": n,
            "n_flood_days": k,
            "share": round(k / n, 3) if n else None,
            "nudge": None,
        }
        if n >= LEVEL_MIN_DAYS:
            if k / n >= LEVEL_UP_SHARE and base in ("low", "medium"):
                nudge = "up"
            elif k == 0 and base in ("medium", "high"):
                nudge = "down"
    final = base
    if nudge == "up":
        final = LEVELS[LEVELS.index(base) + 1]
    elif nudge == "down":
        final = LEVELS[LEVELS.index(base) - 1]
    if hist is not None:
        hist["nudge"] = nudge

    if base == "none":
        reason = f"Little rain expected ({p20:.0%} chance of even 20 mm in 24 hours)."
    elif base == "low":
        reason = (f"Rain is likely ({p20:.0%} chance of 20 mm) but heavy rain is not "
                  f"({p40:.0%} chance of 40 mm).")
    elif base == "medium":
        reason = f"Heavy rain is possible ({p40:.0%} chance of 40 mm or more in 24 hours)."
    else:
        reason = f"Heavy rain is likely ({p40:.0%} chance of 40 mm or more in 24 hours)."
    if hist is not None:
        label = hist["class_mm"]
        if hist["n_days"] < LEVEL_MIN_DAYS:
            reason += (f" This cell's history has only {hist['n_days']} past "
                       f"{label} days, too few to shift the level.")
        else:
            reason += (f" Past {label} days here: {hist['n_flood_days']} of "
                      f"{hist['n_days']} were reported floods")
            if nudge == "up":
                reason += f", so the level moves up from {base} to {final}."
            elif nudge == "down":
                reason += f", so the level moves down from {base} to {final}."
            else:
                reason += "."
    return base, final, hist, reason


# ---- analogues ------------------------------------------------------------
def find_analogues(cell_id: str, median_mm: float, window_days: list,
                   totals_by_cell: dict, flood_by_date: dict, areas_by_date: dict,
                   centre: dict, local_flood_days: set):
    """Up to MAX_ANALOGUES past days whose 24-h total is within +/- ANALOGUE_TOL
    of the forecast median and >= ANALOGUE_MIN_MM. Days with a flood reported
    within AREA_MATCH_KM of the cell come first: a flood elsewhere in Lagos
    that day says nothing about this area."""
    qualifying = []
    tot = totals_by_cell[cell_id]
    for day in window_days:
        t = tot.get(day)
        if t is None:
            continue
        if t >= ANALOGUE_MIN_MM and abs(t - median_mm) <= ANALOGUE_TOL * median_mm:
            qualifying.append((day, t))
    n_local = sum(1 for day, _ in qualifying if day in local_flood_days)
    n_city = sum(1 for day, _ in qualifying if day in flood_by_date)
    qualifying.sort(key=lambda x: (0 if x[0] in local_flood_days else 1,
                                   abs(x[1] - median_mm), x[0]))
    out_days = []
    for day, t in qualifying[:MAX_ANALOGUES]:
        areas = []
        for name, lon, lat in areas_by_date.get(day, []):
            if haversine_km(centre["lon"], centre["lat"], lon, lat) <= AREA_MATCH_KM:
                areas.append({"name": name, "lon": lon, "lat": lat})
        out_days.append({
            "date": day,
            "imerg_mm": round(t, 1),
            "flood_day": day in local_flood_days,
            "citywide_flood_day": day in flood_by_date,
            "areas_within_5km": areas,
        })
    return {"n_qualifying": len(qualifying), "n_qualifying_flood_days": n_local,
            "n_qualifying_citywide_flood_days": n_city, "days": out_days}


def main() -> None:
    run_day = datetime.now(WAT).date()
    run_date = run_day.isoformat()
    generated_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    cache_dir = CACHE_ROOT / run_date
    cache_dir.mkdir(parents=True, exist_ok=True)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    print(f"run date (Lagos): {run_date}")

    # ---- inputs -----------------------------------------------------------
    print("loading events/rain_history_grid_daily.json ...")
    grid = json.loads((EVENTS / "rain_history_grid_daily.json").read_text())
    cells = grid["meta"]["cells"]
    grid_dates = grid["dates"]
    date_idx = {x: i for i, x in enumerate(grid_dates)}
    series = grid["series"]
    print("loading events/flood_days.json ...")
    fd_doc = json.loads((EVENTS / "flood_days.json").read_text())
    fd_days = fd_doc["days"]
    flood_by_date = {x["date"]: x for x in fd_days}
    areas_by_date = {}
    for day in fd_days:
        areas_by_date[day["date"]] = [
            (a["name"], a["lon"], a["lat"]) for a in day.get("areas", [])
            if a.get("lon") is not None and a.get("lat") is not None
        ]

    # searched window for history-based numbers: April-November of the
    # year-months the catalog actually searched, 2014 onward.
    searched_ym = {e["year_month"] for e in fd_doc["meta"]["search_coverage"]}

    def in_window(day: str) -> bool:
        return day[:7] in searched_ym and d(day).month in WINDOW_MONTHS and day >= "2014-01-01"

    window_days = [x for x in grid_dates if in_window(x)]
    print(f"searched window days (2014+, Apr-Nov): {len(window_days)}")

    print("loading calibration (events/forecast/calibration.json) ...")
    cal = load_calibration()
    cal_rule_mm = cal["rule_mm"]
    cal_trust = cal["meta"].get("trust") or {}
    cal_fit = cal["fit_period"]
    print(f"  quantile mapping for lead days {sorted(cal['maps'])}, fitted "
          f"{cal_fit.get('start')}..{cal_fit.get('end')}; "
          + (f"level floor at {cal_rule_mm:g} mm calibrated median"
             if cal_rule_mm is not None else "no level floor"))

    # per-cell totals over the window; per-cell flood dates within AREA_MATCH_KM
    totals_by_cell, class_stats, local_flood = {}, {}, {}
    for c in cells:
        cid = c["id"]
        raw = series[cid]["total_mm"]
        totals_by_cell[cid] = {day: raw[date_idx[day]] for day in window_days}
        local_flood[cid] = {
            day for day in flood_by_date
            if any(haversine_km(c["lon"], c["lat"], lon, lat) <= AREA_MATCH_KM
                   for _, lon, lat in areas_by_date.get(day, []))
        }
        st = {"10-20": [0, 0], "20-40": [0, 0], "ge-40": [0, 0]}
        for day in window_days:
            t = totals_by_cell[cid][day]
            if t is None:
                continue
            cls = "ge-40" if t >= 40 else "20-40" if t >= 20 else "10-20" if t >= 10 else None
            if cls:
                st[cls][0] += 1
                if day in local_flood[cid]:
                    st[cls][1] += 1
        class_stats[cid] = st

    # ---- justify the hourly rate threshold from the IMERG history ---------
    max30 = {c["id"]: series[c["id"]]["max_30min_mm_h"] for c in cells}
    flood_day_rates = []
    for day in flood_by_date:
        best = None
        for dd in (day, (d(day) - timedelta(days=1)).isoformat()):
            i = date_idx.get(dd)
            if i is None:
                continue
            for cid in max30:
                v = max30[cid][i]
                if v is not None and (best is None or v > best):
                    best = v
        if best is not None:
            flood_day_rates.append(best)
    rates = np.array(flood_day_rates)
    p10 = float(np.percentile(rates, 10))
    p50 = float(np.percentile(rates, 50))
    n_ge = int((rates >= HOURLY_RATE_MM_H).sum())
    justification = (
        f"{HOURLY_RATE_MM_H:g} mm/h is the low end of what preceded reported flood "
        f"days in the satellite record: on each of the {len(rates)} reported flood "
        f"days, the highest 30-min IMERG rain rate over all {len(cells)} cells on "
        f"the day itself or the day before has a 10th percentile of {p10:.1f} mm/h "
        f"and a median of {p50:.1f} mm/h, and {n_ge} of {len(rates)} days reached "
        f"{HOURLY_RATE_MM_H:g} mm/h somewhere in the city. Hourly ensemble "
        f"precipitation (mm per hour) is compared against that rate directly."
    )

    # ---- fetch forecasts (cached per run-date) ----------------------------
    print("fetching ECMWF ensemble (68 cells, 51 series x 168 h) ...")
    ecmwf_raw = fetch_json(ensemble_url(cells, "ecmwf_ifs025"),
                           cache_dir / "ecmwf_ifs025.json")
    print("fetching GFS ensemble (second opinion) ...")
    gfs_raw = fetch_json(ensemble_url(cells, "gfs025"), cache_dir / "gfs025.json")
    ecmwf, times = parse_ensemble(ecmwf_raw, cells, run_date)
    gfs, _ = parse_ensemble(gfs_raw, cells, run_date)
    n_series = ecmwf[cells[0]["id"]].shape[0]
    n_gfs = gfs[cells[0]["id"]].shape[0]
    forecast_days = sorted({t[:10] for t in times})
    if forecast_days[0] != run_date or len(forecast_days) != FORECAST_DAYS:
        raise SystemExit(f"forecast days {forecast_days} do not start at {run_date}")

    print("fetching GloFAS river forecasts and history ...")
    rivers_out = {}
    for rid, name, req in RIVER_POINTS:
        fm, snapped = river_forecast(rid, req, cache_dir, forecast_days)
        hist = river_history(rid, req, cache_dir, run_day)
        days = []
        for j, day in enumerate(forecast_days):
            col = [v for v in fm[:, j] if v is not None]
            med = float(np.median(col))
            flags = []
            if med >= hist["p90_m3s"]:
                flags.append("at_or_above_p90_hist")
            if med >= hist["p99_m3s"]:
                flags.append("at_or_above_p99_hist")
            days.append({"date": day, "median_m3s": round(med, 1),
                         "p90_m3s": round(float(np.percentile(col, 90)), 1),
                         "flags": flags})
        rivers_out[rid] = {"name": name, "requested": req, "snapped": snapped,
                           "history": hist, "days": days}
        print(f"  {name}: snapped to {snapped}, history {hist['n_days']} days, "
              f"p90 {hist['p90_m3s']} / p99 {hist['p99_m3s']} m3/s")

    print("getting the tide at the offshore point ...")
    event_dirs = sorted([p for p in EVENTS.iterdir()
                         if p.is_dir() and p.name.startswith("lagos-")])
    tides, tide_times, tide_source = compute_tides(run_day, event_dirs)
    print(f"  from {tide_source}")
    print(f"  {len(tides['high_tides'])} high tides over {FORECAST_DAYS} days")

    # ---- per cell, per day -------------------------------------------------
    print("computing per-cell risk ...")
    cells_out = {}
    all_blocks = []  # (level_idx, p40, median, cell_id, day, block)
    for c in cells:
        cid = c["id"]
        centre = {"lon": c["lon"], "lat": c["lat"], "place": c.get("place")}
        M, G = ecmwf[cid], gfs[cid]
        # Calibrate each member's daily total through the quantile mapping
        # (Task 44), then scale that member's hourly values by the same daily
        # factor, so chances, levels, risk windows and the hourly export are
        # all computed on IMERG-equivalent rain. A member-day the model keeps
        # fully dry keeps zero hourly rates; its mapped daily total can still
        # carry a little IMERG-equivalent drizzle.
        n_m = M.shape[0]
        raw_day = M.reshape(n_m, FORECAST_DAYS, 24).sum(axis=2)
        cal_day = np.empty_like(raw_day)
        for di in range(FORECAST_DAYS):
            mq, oq = cal["maps"][di + 1]
            cal_day[:, di] = calibrate_mm(raw_day[:, di], cal["pct"], mq, oq)
        factors = np.where(raw_day > 0, cal_day / np.maximum(raw_day, 1e-12), 1.0)
        Mcal = (M.reshape(n_m, FORECAST_DAYS, 24) * factors[:, :, None]).reshape(
            n_m, FORECAST_DAYS * 24)
        day_blocks = []
        for di, day in enumerate(forecast_days):
            sub = Mcal[:, di * 24:(di + 1) * 24]   # calibrated hourly rates
            totals = cal_day[:, di]                # calibrated daily totals
            med = float(np.median(totals))
            p90 = float(np.percentile(totals, 90))
            chances = {t: float(np.mean(totals >= t)) for t in DAILY_MM}
            raw_med = float(np.median(raw_day[:, di]))
            gsub = G[:, di * 24:(di + 1) * 24]     # GFS stays uncalibrated
            _, gmed, gp90, gchances = day_totals_and_chances(gsub)
            # peak 3-hour window: highest member-median 3-h total in the day
            best_w, best_med = 0, -1.0
            for w in range(22):
                mw = float(np.median(sub[:, w:w + 3].sum(axis=1)))
                if mw > best_med:
                    best_med, best_w = mw, w
            tw = sub[:, best_w:best_w + 3].sum(axis=1)
            # risk window
            ranges, flag = risk_ranges(sub, times[di * 24:(di + 1) * 24])
            near_high = False
            if flag.any():
                hours = [datetime.fromisoformat(times[di * 24 + h])
                        for h in range(24) if flag[h]]
                for ht in hours:
                    if any(abs((ht - t).total_seconds()) <= TIDE_OVERLAP_H * 3600
                           for t in tide_times):
                        near_high = True
                        break
            _, final, hist, reason = level_for(med, chances[20], chances[40],
                                               class_stats[cid])
            # Hindcast-derived floor (Task 44, part 3): a calibrated median at
            # or above the threshold fixed on 2024+2025 raises the day to at
            # least medium, whatever the ensemble chances say.
            if cal_rule_mm is not None and med >= cal_rule_mm and final in ("none", "low"):
                final = "medium"
                reason = (
                    f"The calibrated forecast's middle scenario reaches {med:.0f} mm, and "
                    f"in past seasons the day-before forecast at this level or above "
                    f"flagged {cal_trust.get('flood_days_flagged')} of the "
                    f"{cal_trust.get('flood_days_in_period')} days floods were reported "
                    f"on, so this counts as a risk day even though the chance of 40 mm "
                    f"is low ({chances[40]:.0%})."
                )
            block = {
                "date": day,
                "rain": {
                    "median_mm": round(med, 1),
                    "raw_median_mm": round(raw_med, 1),
                    "p90_mm": round(p90, 1),
                    "chance_ge_20mm": round(chances[20], 3),
                    "chance_ge_40mm": round(chances[40], 3),
                    "chance_ge_60mm": round(chances[60], 3),
                    "peak_3h": {
                        "start_hour_local": times[di * 24 + best_w][11:16],
                        "median_mm": round(best_med, 1),
                        "p90_mm": round(float(np.percentile(tw, 90)), 1),
                    },
                    "second_opinion_gfs": {
                        "median_mm": round(gmed, 1),
                        "p90_mm": round(gp90, 1),
                        "chance_ge_40mm": round(gchances[40], 3),
                    },
                },
                "risk": {"hours": ranges, "near_high_tide": near_high},
                "level": final,
                "level_reason": reason,
            }
            if hist is not None:
                block["level_history"] = hist
            if final in ("medium", "high"):
                block["analogues"] = find_analogues(
                    cid, med, window_days, totals_by_cell, flood_by_date,
                    areas_by_date, centre, local_flood[cid])
            day_blocks.append(block)
            all_blocks.append((LEVELS.index(final), chances[40], med, cid, day, block))
        # Member-median and 90th-percentile mm/h for each of the 168 hours
        # (Task 41), on the CALIBRATED hourly rates (Task 44). Rounded to 0.1
        # so the whole file stays under 600 KB.
        cells_out[cid] = {
            "centre": centre,
            "days": day_blocks,
            "hourly": {
                "median": [round(float(x), 1) for x in np.median(Mcal, axis=0)],
                "p90": [round(float(x), 1) for x in np.percentile(Mcal, 90, axis=0)],
            },
        }

    # ---- citywide -----------------------------------------------------------
    city_days = []
    for di, day in enumerate(forecast_days):
        by_level = {"high": 0, "medium": 0, "low": 0, "none": 0}
        day_cells = []
        for li, p40, med, cid, dname, block in all_blocks:
            if dname != day:
                continue
            by_level[block["level"]] += 1
            day_cells.append((li, p40, med, cid, block))
        day_cells.sort(key=lambda x: (-x[0], -x[1], -x[2], x[3]))
        overall = "none"
        for lv in ("high", "medium", "low"):
            if by_level[lv]:
                overall = lv
                break
        top = [{
            "cell": cid,
            "place": cells_out[cid]["centre"]["place"],
            "level": block["level"],
            "median_mm": block["rain"]["median_mm"],
            "chance_ge_40mm": block["rain"]["chance_ge_40mm"],
        } for _, _, _, cid, block in day_cells[:3]]
        city_days.append({"date": day, "overall_level": overall,
                          "cells_by_level": by_level, "most_at_risk": top})

    # ---- meta ---------------------------------------------------------------
    cache_files = sorted(p.name for p in cache_dir.glob("*.json"))
    meta = {
        "built_by": "pipeline/forecast.py",
        "task": "38-forecast-pipeline (docs/tasks/38-forecast-pipeline.md)",
        "schema": "pipeline/schemas/forecast.schema.json",
        "method": (
            "Daily 7-day flood-risk forecast. No weather model is run here: "
            "published forecasts are combined with FloodTrace's own satellite-rain "
            "history. The ECMWF IFS 0.25 deg ensemble (control + 50 members) is "
            "fetched once for all 68 IMERG 0.1 deg cells (one multi-coordinate "
            "call; the model grid is coarser than the cells, so several cells "
            "share one model point) and drives the headline rain numbers; the "
            "GFS 0.25 deg ensemble is stored as a second opinion. Since Task 44 "
            "every ECMWF member's daily total is first calibrated to Lagos rain "
            "by a quantile mapping fitted per lead day on the 2024-2026 "
            "hindcast (events/forecast/calibration.json, built by "
            "pipeline/calibrate.py), and each member's hourly values are scaled "
            "by the same daily factor, so the medians, percentiles, chances, "
            "risk windows and the hourly export are IMERG-equivalent; "
            "raw_median_mm keeps the uncalibrated median beside the calibrated "
            "one, and the GFS second opinion stays uncalibrated. Per cell and "
            "Lagos day the pipeline records the ensemble-median and 90th-percentile "
            "24-h rain, the chance of at least 20/40/60 mm (share of the 51 "
            "series), the peak 3-hour window, the hours at risk (member-median "
            "rate at least 10 mm/h, or at least 30% of members at it), whether "
            "those hours come within 2 h of an EOT20 high tide, a plain risk "
            "level (chance of heavy rain, nudged by this cell's own reported-flood "
            "record), and, at medium or above, past days whose rain matched the "
            "forecast (analogues). Each cell also carries the 168-hour "
            "member-median and 90th-percentile rain rate in mm/h for the UI. "
            "GloFAS river ensembles and their 1984-present "
            "daily-flow history are fetched for two river points, and each "
            "forecast day is flagged when the member-median flow reaches the "
            "point's historical 90th/99th percentile. Raw API responses are "
            f"cached under pipeline/cache/forecast/{run_date}/ ({', '.join(cache_files)}) "
            "and reused on same-day reruns, so an archived run stays reproducible."
        ),
        "run": {
            "run_date": run_date,
            "generated_at": generated_at,
            "forecast_days": forecast_days,
            "cache_dir": f"pipeline/cache/forecast/{run_date}",
            "api_calls": STATS["api_calls"],
            "cache_reused": STATS["cache_hits"] > 0,
        },
        "sources": [
            {
                "name": "Open-Meteo Ensemble API, ECMWF IFS 0.25 deg ensemble",
                "url": "https://ensemble-api.open-meteo.com/v1/ensemble?hourly=precipitation&models=ecmwf_ifs025&forecast_days=7&timezone=Africa/Lagos",
                "licence": "CC BY 4.0 (attribution required); ECMWF IFS data (c) ECMWF",
                "note": "one multi-coordinate call for all 68 cell centres; "
                        "control run plus 50 perturbed members per point; the "
                        "headline rain numbers come from this model",
            },
            {
                "name": "Open-Meteo Ensemble API, GFS 0.25 deg ensemble",
                "url": "https://ensemble-api.open-meteo.com/v1/ensemble?hourly=precipitation&models=gfs025&forecast_days=7&timezone=Africa/Lagos",
                "licence": "CC BY 4.0 (attribution required); GFS data (c) NOAA",
                "note": "second opinion only; stored per cell-day as median, "
                        "90th percentile and chance of 40 mm",
            },
            {
                "name": "Open-Meteo Flood API (GloFAS global flood awareness system)",
                "url": "https://flood-api.open-meteo.com/v1/flood?daily=river_discharge&ensemble=true&forecast_days=7",
                "licence": "CC BY 4.0 (Open-Meteo); GloFAS data by the Copernicus "
                           "Emergency Management Service (CEMS)",
                "note": "river ensemble (control + 50 members) for the 7 forecast "
                        "days, and the daily-flow reanalysis history back to 1984 "
                        "used for the 90th/99th percentile flags",
            },
            {
                "name": "EOT20 global ocean tide model",
                "url": "https://doi.org/10.17882/79489",
                "licence": "CC BY 4.0",
                "note": "Hart-Davis et al. (2021), EOT20, SEANOE, DGFI-TUM; "
                        f"astronomical tide from {tide_source} at the "
                        "events' offshore point",
            },
            {
                "name": "NASA GPM IMERG half-hourly rain V07 (our history file)",
                "url": "https://gpm.nasa.gov/data/imerg",
                "licence": "NASA open data",
                "note": "events/rain_history_grid_daily.json: WAT daily totals and "
                        "max 30-min rates per 0.1 deg cell, 2000-06-01 onward; "
                        "the source of analogues, class counts and the hourly-rate "
                        "justification",
            },
            {
                "name": "FloodTrace flood-day catalog (reported floods)",
                "url": "events/flood_days.json",
                "licence": "our own compilation from news reports",
                "note": f"{len(fd_days)} reported flood days with geocoded areas; "
                        "a day matches a cell when one of its areas lies within "
                        "5 km of the cell centre",
            },
            {
                "name": "Forecast calibration (quantile mapping)",
                "url": "https://previous-runs-api.open-meteo.com/v1/forecast",
                "licence": "CC BY 4.0 (Open-Meteo); ECMWF IFS data (c) ECMWF; NASA IMERG open data",
                "note": "events/forecast/calibration.json, built by pipeline/calibrate.py "
                        "from the 2024-2026 hindcast of ECMWF IFS deterministic runs "
                        "vs IMERG daily totals; the mapping applied to every member here",
            },
        ],
        "calibration": {
            "applied": True,
            "method": (
                "Quantile mapping per lead day (1-7), fitted by pipeline/calibrate.py on "
                "the 2024-2026 hindcast (ECMWF IFS 0.25 deg deterministic runs vs IMERG "
                "daily totals), pooling all 68 cells; no per-cell adjustment (tested "
                "and unstable across seasons). Every ECMWF member's daily total is "
                "mapped to IMERG-equivalent mm BEFORE chances, levels, risk windows and "
                "the hourly export are computed; each member's hourly values are scaled "
                "by that member's same daily factor. median_mm is calibrated; "
                "raw_median_mm keeps the uncalibrated median beside it. The GFS second "
                "opinion is NOT calibrated (the mapping was fitted on ECMWF IFS runs). "
                "Validated leave-one-season-out: the calibrated day-1 p99 matches "
                "IMERG's (54.4 vs 53.9 mm, model raw 28.9), and flood days flagged at "
                "40 mm went from 1 of 19 (raw) to 6 of 19 (calibrated) — but most "
                "flagged days still pass without a reported flood, and with 19 flood "
                "days the gain may be noise."
            ),
            "fit_period": (
                f"{cal_fit.get('start')} to {cal_fit.get('end')} "
                f"({', '.join(str(y) for y in cal_fit.get('seasons', []))}), "
                "April-November; deployed mapping refit on all seasons, validation "
                "leave-one-season-out"
            ),
            "mapping_file": "events/forecast/calibration.json",
            "level_rule": (
                {
                    "threshold_mm": cal_rule_mm,
                    "rule": cal["meta"]["level_rule"]["rule"],
                    "criterion": cal["meta"]["level_rule"]["criterion"],
                    "fit_numbers": next(
                        (r for r in cal["meta"]["level_rule"]["candidates_2024_2025"]
                         if r["threshold_mm"] == cal_rule_mm), None),
                    "test_2026": cal["meta"]["level_rule"]["test_2026_at_threshold"],
                }
                if cal_rule_mm is not None else None
            ),
            "trust": cal_trust,
        },
        "models": {
            "rain_headline": f"ecmwf_ifs025 (control + {n_series - 1} perturbed members)",
            "rain_second_opinion": f"gfs025 (control + {n_gfs - 1} perturbed members)",
            "rivers": "GloFAS via the Open-Meteo Flood API (control + 50 perturbed members)",
            "tide": f"EOT20 (17 constituents), from {tide_source}",
        },
        "thresholds": {
            "hourly_rate_mm_h": HOURLY_RATE_MM_H,
            "member_share_for_hourly_rate": MEMBER_SHARE,
            "daily_mm": list(DAILY_MM),
            "heavy_rain_mm": HEAVY_MM,
            "analogue_tolerance": ANALOGUE_TOL,
            "analogue_min_mm": ANALOGUE_MIN_MM,
            "max_analogues": MAX_ANALOGUES,
            "high_tide_overlap_hours": TIDE_OVERLAP_H,
            "area_match_km": AREA_MATCH_KM,
        },
        "rules": {
            "risk_window": (
                "An hour is inside the risk window when the member-median rain "
                f"rate is at least {HOURLY_RATE_MM_H:g} mm/h, or at least "
                f"{MEMBER_SHARE:.0%} of the {n_series} ensemble series reach "
                f"{HOURLY_RATE_MM_H:g} mm/h in that hour; consecutive hours are "
                "joined into ranges in Lagos time. A day's window is flagged "
                "near_high_tide when any of its hours falls within +/- "
                f"{TIDE_OVERLAP_H:g} h of a high tide."
            ),
            "hourly_rate_justification": justification,
            "risk_level": (
                "The level starts from the chance of heavy rain (high: at least "
                "30% chance of 40 mm in 24 h; medium: at least 10%; low: at least "
                "20% chance of 20 mm; none below that), then moves one step by "
                "this cell's own record when it has at least 5 past days of the "
                "forecast's size class (10-20 / 20-40 / 40+ mm, April-November "
                "of the searched months, 2014 onward): one step up if at least "
                "a quarter of those days were reported floods within 5 km of the "
                "cell centre, one step down if none of them were. In one "
                "sentence: heavy rain likely or possible, checked against how "
                "often rain of that size here actually flooded."
            ),
            "calibration": (
                "Every ECMWF member's daily rain total is mapped to IMERG-equivalent mm "
                "through the quantile mapping in events/forecast/calibration.json "
                "(fitted per lead day on the 2024-2026 hindcast, pooled over all "
                "cells; a per-cell adjustment was tested and rejected as unstable "
                "across seasons). Each member's hourly values are scaled by that "
                "member's same daily factor, and everything downstream — chances, "
                "levels, risk windows, the hourly export — is computed on the "
                "calibrated rain; raw_median_mm keeps the uncalibrated median beside "
                "the calibrated one. The GFS second opinion is not calibrated. "
                + (
                    f"Level floor: a calibrated member-median of at least {cal_rule_mm:g} mm "
                    "raises a cell-day to at least medium, whatever the ensemble "
                    "chances say — the day-1 threshold fixed on the 2024 and 2025 "
                    "seasons as the best balance of flood days caught against false "
                    "alarms (TSS, out of sample within those seasons) and kept frozen "
                    "before the 2026 test season, where it flagged "
                    f"{(cal['meta']['level_rule'].get('test_2026_at_threshold') or {}).get('1', {}).get('flood_days_flagged')} "
                    "of "
                    f"{(cal['meta']['level_rule'].get('test_2026_at_threshold') or {}).get('1', {}).get('flood_days_in_season')} "
                    "flood days against "
                    f"{(cal['meta']['level_rule'].get('test_2026_at_40mm') or {}).get('1', {}).get('flood_days_flagged')} "
                    "of "
                    f"{(cal['meta']['level_rule'].get('test_2026_at_40mm') or {}).get('1', {}).get('flood_days_in_season')} "
                    "at 40 mm."
                    if cal_rule_mm is not None else
                    "No level floor beyond the chance ladder."
                )
            ),
            "analogues": (
                "For medium and high cell-days: past days (April-November of the "
                "searched months, 2014 onward) whose IMERG 24-h total at the cell "
                f"is within +/- {ANALOGUE_TOL:.0%} of the forecast median and at "
                f"least {ANALOGUE_MIN_MM:g} mm. Days with a flood reported within "
                f"{AREA_MATCH_KM:g} km of the cell centre come first (flood_day), "
                "then the closest to the forecast; up to "
                f"{MAX_ANALOGUES} are kept, each with the reported flood areas "
                f"within {AREA_MATCH_KM:g} km of the cell centre. Counts: "
                "n_qualifying_flood_days = qualifying days with a flood reported "
                f"within {AREA_MATCH_KM:g} km; n_qualifying_citywide_flood_days = "
                "qualifying days with a flood reported anywhere in Lagos."
            ),
            "rivers": (
                "Per river point: the daily ensemble median and 90th-percentile "
                "flow over the forecast days, flagged at_or_above_p90_hist / "
                "at_or_above_p99_hist when the median reaches the historical "
                "90th/99th percentile of daily flow at that point "
                f"({RIVER_HISTORY_START} onward, GloFAS reanalysis)."
            ),
            "tides": (
                "The EOT20 astronomical tide is read hourly at the offshore "
                "point over the 7 forecast days from the precomputed tide "
                "table (events/forecast/tide_table.json, built by "
                "pipeline/tide_table.py) when the window is inside it, and "
                "computed locally with pyTMD otherwise; every local maximum "
                "is listed as a high tide (times to the nearest hour, heights "
                "in metres above sea level, rounded to the centimetre). No "
                "storm surge, no lagoon damping or phase lag is included."
            ),
        },
        "caveats": [
            "A reported flood undercounts real floods: the catalog is news "
            "coverage, not a gauge, so floods no outlet reported are missing "
            "and every 'how often it flooded' number here is a floor, not the "
            "truth.",
            "The calibration corrects how much rain the model forecasts, not "
            "where it puts it: out of sample it flagged 6 of 19 flood days at "
            "day 1 against 1 of 19 raw, but most flagged days still pass "
            "without a reported flood, and with only 19 flood days that gain "
            "may be noise (see meta.calibration.trust).",
            "The forecast model is coarser than our history cells: the ECMWF "
            "ensemble is 0.25 deg (about 25 km), so several 0.1 deg cells share "
            "one model point and neighbourhood rain is smoothed.",
            "The chances are the spread of the model's own ensemble, not true "
            "probabilities.",
            "The tide is astronomical only: no storm surge, and the lagoon "
            "drains slower than the open sea, so the real high water inside "
            "Lagos can be different.",
            "River flow is modelled (GloFAS), not measured; there is no public "
            "gauge for the Ogun at Kara or the Osun/Owo outlet.",
            "Forecasts get less reliable further out; by day 7 this is a hint, "
            "not a plan.",
            "Satellite rain (IMERG) smooths storm cores, so the heaviest burst "
            "in a cell can be heavier than the cell number shows.",
        ],
        "counts": {
            "cells": len(cells),
            "ensemble_series_per_cell": n_series,
            "gfs_series_per_cell": n_gfs,
            "reported_flood_days_in_catalog": len(fd_days),
        },
    }

    out = {"meta": meta, "tides": tides, "rivers": rivers_out,
           "cells": cells_out, "citywide": {"days": city_days}}

    # ---- validate and write -------------------------------------------------
    schema = json.loads(SCHEMA_PATH.read_text())
    jsonschema.Draft202012Validator(schema).validate(out)

    run_path = OUT_DIR / f"{run_date}.json"
    if run_path.exists():  # archive rule: never overwrite, add a time suffix
        suffix = datetime.now(WAT).strftime("%H%M")
        run_path = OUT_DIR / f"{run_date}-{suffix}.json"
    text_out = json.dumps(out, indent=1, ensure_ascii=False) + "\n"
    run_path.write_text(text_out, encoding="utf-8")
    (OUT_DIR / "latest.json").write_text(text_out, encoding="utf-8")
    size = run_path.stat().st_size
    if size >= 600_000:
        raise SystemExit(f"forecast file is {size} bytes; keep it under 600 KB")

    runs = []
    for p in sorted(OUT_DIR.glob("*.json")):
        # only dated run files; the directory also holds latest.json, index.json,
        # calibration.json, scores.json and hindcast.json (Task 42/44)
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}(-\d{4})?\.json", p.name):
            continue
        m = json.loads(p.read_text())["meta"]["run"]
        runs.append({"file": p.name, "run_date": m["run_date"],
                     "generated_at": m["generated_at"]})
    runs.sort(key=lambda x: (x["run_date"], x["generated_at"]))
    (OUT_DIR / "index.json").write_text(
        json.dumps({"runs": runs}, indent=1) + "\n", encoding="utf-8")

    # ---- console summary ----------------------------------------------------
    print()
    print(f"cells: {len(cells)}   ensemble series per cell: {n_series} "
          f"(GFS second opinion: {n_gfs})")
    print(f"api calls this run: {STATS['api_calls']} "
          f"(cache reuses: {STATS['cache_hits']})")
    print()
    print("3 riskiest cell-days:")
    ranked = sorted(all_blocks, key=lambda x: (-x[0], -x[1], -x[2], x[4], x[3]))[:3]
    for li, p40, med, cid, day, block in ranked:
        c_place = cells_out[cid]["centre"]["place"] or ""
        print(f"  {day} {cid} ({c_place}) level {block['level']}, "
              f"median {block['rain']['median_mm']} mm "
              f"(raw {block['rain']['raw_median_mm']} mm), "
              f"chance>=40mm {block['rain']['chance_ge_40mm']}")
        print(f"    {block['level_reason']}")
        for a in block.get("analogues", {}).get("days", []):
            note = "flood day" if a["flood_day"] else "no report"
            areas = "; ".join(x["name"] for x in a["areas_within_5km"]) or "-"
            print(f"    analogue {a['date']}: {a['imerg_mm']} mm IMERG ({note}; "
                  f"nearby areas: {areas})")
    print()
    print("next 4 high tides (offshore, Lagos time):")
    for h in tides["high_tides"][:4]:
        print(f"  {h['time']}  {h['height_m']:+.2f} m")
    print()
    print("river flags:")
    any_flag = False
    for rid, riv in rivers_out.items():
        for day in riv["days"]:
            if day["flags"]:
                any_flag = True
                print(f"  {rid} {day['date']}: median {day['median_m3s']} m3/s "
                      f"({', '.join(day['flags'])}; p90 hist "
                      f"{riv['history']['p90_m3s']}, p99 hist {riv['history']['p99_m3s']})")
    if not any_flag:
        print("  none: no forecast day reaches the historical 90th percentile "
              "at either point")
    print()
    print(f"wrote {run_path.relative_to(ROOT)} ({run_path.stat().st_size} bytes)")
    print(f"wrote events/forecast/latest.json and events/forecast/index.json "
          f"({len(runs)} runs archived)")


if __name__ == "__main__":
    main()
