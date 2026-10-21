#!/usr/bin/env python3
"""Task 42, part B (docs/tasks/42-forecast-scoring.md): an early estimate of
how good the forecast is, from past forecasts that are public.

The live archive (score_forecasts.py) is empty for now, so skill is estimated
from the Open-Meteo Previous Runs API, which serves past model runs aligned to
fixed lead times: precipitation_previous_day1 is the rain forecast 24 hours
before valid time, _day2 48 hours before, and so on to day 7. The ECMWF IFS
0.25 deg runs are archived there from January 2024, so the hindcast covers
April-November of 2024, 2025 and 2026 so far.

This is a DETERMINISTIC forecast: one ECMWF IFS 0.25 deg run per lead time,
not the 51-member ensemble the live product uses, so every number here is a
rough guide only. A single run is noisier than an ensemble median: it can
miss rain the ensemble would have flagged and it can place a storm one cell
off, which counts as a miss here.

What is scored, for every day of April-November in the covered years and all
68 cell centres (the same IMERG cells and the same 5 km flood-match rule as
pipeline/forecast.py, whose helpers are imported, not copied):

  * hits, misses and false alarms of forecast >= 40 mm against the IMERG
    observed total >= 40 mm, grouped by lead day;
  * the reported flood days: on how many did the day-1 (and day-3) forecast
    reach >= 40 mm (or >= 20 mm) in a cell within 5 km of a reported area;
  * the false-alarm rate: the share of forecast->= 40 mm cell-days with no
    flood reported within 5 km.

Output: events/forecast/hindcast.json. No key needed; raw API responses are
cached under pipeline/cache/hindcast/ and reused, so the run is reproducible.

Usage:
    pipeline/.venv/bin/python pipeline/hindcast.py
"""
from __future__ import annotations

import json
import time
from datetime import date, datetime, timedelta, timezone

import numpy as np

import forecast as F  # noqa: E402  (same directory; runs under pipeline/.venv)

OUT = F.OUT_DIR / "hindcast.json"
CACHE = F.ROOT / "pipeline" / "cache" / "hindcast"
PREVIOUS_RUNS_URL = "https://previous-runs-api.open-meteo.com/v1/forecast"
MODEL = "ecmwf_ifs025"
LEAD_DAYS = 7
HEAVY = 40.0      # mm in a day, the "heavy rain" threshold of the live product
SOME = 20.0       # mm in a day, the lower warning threshold
ARCHIVE_START = date(2024, 1, 1)   # Previous Runs API archive for IFS 0.25 deg
VAR = {n: f"precipitation_previous_day{n}" for n in range(1, LEAD_DAYS + 1)}


def month_days(y: int, m: int, last_day: date):
    first = max(date(y, m, 1), ARCHIVE_START)
    last = min(date(y + (m == 12), m % 12 + 1, 1) - timedelta(days=1), last_day)
    return first, last


def fetch_month(cells, y: int, m: int, first: date, last: date):
    """One multi-coordinate call per calendar month; cached raw under
    pipeline/cache/hindcast/. The free API rate-limits, so a 429 waits and
    retries rather than failing the run."""
    import requests

    CACHE.mkdir(parents=True, exist_ok=True)
    cache_path = CACHE / f"hindcast-{y:04d}-{m:02d}.json"
    if cache_path.exists():
        return json.loads(cache_path.read_text())
    lats = ",".join(str(c["lat"]) for c in cells)
    lons = ",".join(str(c["lon"]) for c in cells)
    hourly = ",".join(VAR[n] for n in range(1, LEAD_DAYS + 1))
    url = (f"{PREVIOUS_RUNS_URL}?latitude={lats}&longitude={lons}"
           f"&hourly={hourly}&models={MODEL}&timezone=Africa%2FLagos"
           f"&start_date={first.isoformat()}&end_date={last.isoformat()}")
    for attempt in range(6):
        r = requests.get(url, headers=F.UA, timeout=300)
        if r.status_code == 429 and attempt < 5:
            wait = 60 * (attempt + 1)
            print(f"    rate-limited; waiting {wait}s ...", flush=True)
            time.sleep(wait)
            continue
        r.raise_for_status()
        cache_path.write_text(json.dumps(r.json()))
        return r.json()
    raise SystemExit("still rate-limited after retries; run again later (cached months are kept)")


def daily_totals(loc: dict, n_days: int):
    """Per-lead-day daily rain totals (mm) for one location; None where missing."""
    out = {}
    for n in range(1, LEAD_DAYS + 1):
        vals = loc["hourly"][VAR[n]]
        days = []
        for j in range(n_days):
            chunk = vals[j * 24:(j + 1) * 24]
            days.append(None if any(v is None for v in chunk) else float(np.sum(chunk)))
        out[n] = days
    return out


def main() -> None:
    generated_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    today = datetime.now(F.WAT).date()
    yesterday = today - timedelta(days=1)

    # ---- inputs ------------------------------------------------------------
    grid = json.loads((F.EVENTS / "rain_history_grid_daily.json").read_text())
    cells = grid["meta"]["cells"]
    date_idx = {x: i for i, x in enumerate(grid["dates"])}
    series = grid["series"]
    fd_doc = json.loads((F.EVENTS / "flood_days.json").read_text())
    fd_days = fd_doc["days"]
    areas_by_date = {
        day["date"]: [(a["lon"], a["lat"]) for a in day.get("areas", [])
                      if a.get("lon") is not None and a.get("lat") is not None]
        for day in fd_days
    }

    # flood days within 5 km of each cell (the same rule as forecast.py)
    local_flood = {}
    for c in cells:
        local_flood[c["id"]] = {
            day for day in areas_by_date
            if any(F.haversine_km(c["lon"], c["lat"], lon, lat) <= F.AREA_MATCH_KM
                   for lon, lat in areas_by_date[day])
        }

    # ---- fetch April-November of every year the archive covers -------------
    years = list(range(ARCHIVE_START.year, today.year + 1))
    months = []
    for y in years:
        for m in range(4, 12):
            first, last = month_days(y, m, yesterday)
            if first <= last:
                months.append((y, m, first, last))
    print(f"hindcast months: {len(months)} "
          f"({months[0][2].isoformat()} .. {months[-1][3].isoformat()})")

    fc_days: list[str] = []          # every fetched calendar day
    # totals[day][cell_index][lead] = mm forecast total (or None)
    totals: dict[str, list] = {}
    for y, m, first, last in months:
        print(f"  fetching {y}-{m:02d} ({first} .. {last}) ...", flush=True)
        data = fetch_month(cells, y, m, first, last)
        time.sleep(5)  # stay well under the free tier's call rate
        assert len(data) == len(cells), "one location per cell expected, in order"
        n_days = len(data[0]["hourly"]["time"]) // 24
        if n_days == 0:
            continue
        for j in range(n_days):
            day = data[0]["hourly"]["time"][j * 24][:10]
            if day not in totals:
                totals[day] = [None] * len(cells)
                fc_days.append(day)
        for ci, loc in enumerate(data):
            per_lead = daily_totals(loc, n_days)
            for j in range(n_days):
                day = loc["hourly"]["time"][j * 24][:10]
                totals[day][ci] = [per_lead[n][j] for n in range(1, LEAD_DAYS + 1)]

    # ---- score against IMERG and reported floods ---------------------------
    by_lead = {n: {"n_scored": 0, "hits": 0, "misses": 0, "false_alarms": 0,
                   "n_warnings": 0, "warnings_no_flood_nearby": 0}
               for n in range(1, LEAD_DAYS + 1)}
    for day in fc_days:
        i = date_idx.get(day)
        if i is None:
            continue
        for ci, c in enumerate(cells):
            obs = series[c["id"]]["total_mm"][i]
            if obs is None:
                continue
            flood_near = day in local_flood[c["id"]]
            for n in range(1, LEAD_DAYS + 1):
                fc = totals[day][ci][n - 1]
                if fc is None:
                    continue
                b = by_lead[n]
                b["n_scored"] += 1
                if fc >= HEAVY and obs >= HEAVY:
                    b["hits"] += 1
                elif fc < HEAVY and obs >= HEAVY:
                    b["misses"] += 1
                elif fc >= HEAVY and obs < HEAVY:
                    b["false_alarms"] += 1
                if fc >= HEAVY:
                    b["n_warnings"] += 1
                    if not flood_near:
                        b["warnings_no_flood_nearby"] += 1

    # ---- the reported flood days -------------------------------------------
    lo, hi = fc_days[0], fc_days[-1]
    in_period = [day for day in areas_by_date
                 if areas_by_date[day] and lo <= day <= hi and F.d(day).month in F.WINDOW_MONTHS]
    flagged = {n: {"ge40": 0, "ge20": 0} for n in (1, 3)}
    n_with_data = 0
    for day in in_period:
        near_cells = set()
        for lon, lat in areas_by_date[day]:
            for ci, c in enumerate(cells):
                if F.haversine_km(c["lon"], c["lat"], lon, lat) <= F.AREA_MATCH_KM:
                    near_cells.add(ci)
        if not near_cells:
            continue
        if day not in totals or any(totals[day][ci] is None for ci in near_cells):
            continue
        n_with_data += 1
        for n in (1, 3):
            best = max(totals[day][ci][n - 1] for ci in near_cells)
            if best is not None and best >= HEAVY:
                flagged[n]["ge40"] += 1
            if best is not None and best >= SOME:
                flagged[n]["ge20"] += 1

    n_scored_total = sum(by_lead[n]["n_scored"] for n in by_lead)
    if n_scored_total == 0:
        raise SystemExit("no days could be scored; check the IMERG history covers the hindcast period")

    w1 = by_lead[1]
    meta = {
        "built_by": "pipeline/hindcast.py",
        "task": "42-forecast-scoring (docs/tasks/42-forecast-scoring.md), part B",
        "generated_at": generated_at,
        "endpoint": PREVIOUS_RUNS_URL,
        "model": (
            f"{MODEL} — the ECMWF IFS 0.25 deg DETERMINISTIC run (one member), "
            "served by the Open-Meteo Previous Runs API, whose archive for this "
            "model starts January 2024"
        ),
        "variables": ", ".join(VAR[n] for n in range(1, LEAD_DAYS + 1))
                     + " (hourly mm, summed to Africa/Lagos calendar days)",
        "period": {
            "start": lo, "end": hi,
            "months": "April to November of every year the archive covers",
            "years": years,
        },
        "cells": f"{len(cells)} IMERG 0.1 deg cell centres, same as the live forecast",
        "observations": "events/rain_history_grid_daily.json (NASA GPM IMERG daily totals per cell)",
        "flood_days": "events/flood_days.json; a cell matches a flood day when a reported area lies within 5 km",
        "cache": "pipeline/cache/hindcast/",
        "licence": "CC BY 4.0 (Open-Meteo); ECMWF IFS data (c) ECMWF; NASA IMERG open data",
        "caveat": (
            "ROUGH GUIDE ONLY: this hindcast scores a single deterministic ECMWF "
            "IFS run per lead time, not the 51-member ensemble the live forecast "
            "uses. A single run is noisier than an ensemble median, and a storm "
            "placed one cell off counts as a miss. Treat these numbers as an "
            "early estimate until the live archive (events/forecast/scores.json, "
            "score_forecasts.py) has enough days of its own."
        ),
        "method": (
            "For each day of April-November 2024-2026 covered by the archive and "
            "every cell, the day total forecast at lead times 1-7 days is "
            "compared with the IMERG observed total: hits, misses and false "
            "alarms at the 40 mm threshold. A reported flood day is counted as "
            "flagged when the forecast for its lead day reached the threshold in "
            "at least one cell within 5 km of a reported area. The false-alarm "
            "share is the fraction of forecast-40 mm cell-days with no flood "
            "reported within 5 km of that cell."
        ),
    }
    out = {
        "meta": meta,
        "period": {"start": lo, "end": hi},
        "n_flood_days_total": len(fd_days),
        "flood_days": {
            "n_in_period": len(in_period),
            "n_with_forecast_data": n_with_data,
            "day1_ge40": flagged[1]["ge40"],
            "day1_ge20": flagged[1]["ge20"],
            "day3_ge40": flagged[3]["ge40"],
            "day3_ge20": flagged[3]["ge20"],
        },
        "warnings": {
            "day1_cell_days": w1["n_warnings"],
            "day1_with_flood_reported_within_5km": w1["n_warnings"] - w1["warnings_no_flood_nearby"],
            "day1_without_flood_reported_within_5km": w1["warnings_no_flood_nearby"],
            "day1_false_alarm_share": (round(w1["warnings_no_flood_nearby"] / w1["n_warnings"], 3)
                                       if w1["n_warnings"] else None),
        },
        "by_lead_day": [dict(lead_day=n, **by_lead[n]) for n in range(1, LEAD_DAYS + 1)],
    }
    OUT.write_text(json.dumps(out, indent=1) + "\n")
    print(f"wrote {OUT.relative_to(F.ROOT)} "
          f"({n_scored_total} cell-days scored, {len(in_period)} flood days in period)")


if __name__ == "__main__":
    main()
