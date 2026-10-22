#!/usr/bin/env python3
"""Task 42, part A (docs/tasks/42-forecast-scoring.md): score the archived
daily forecasts against what actually fell.

For every archived run in events/forecast/ (the dated files), each cell and
each forecast day that the IMERG satellite history now covers, it computes:

  * the Brier score of the run's chance of at least 20 mm and at least 40 mm,
    compared with a climatology baseline (that cell's own frequency of
    >= 20 / >= 40 mm days in the April-November window) and
    skill = 1 - Brier / Brier_climatology;
  * hits, misses and false alarms for the run's plain level, where medium or
    high counts as a "warning", against two events: IMERG >= 40 mm in that
    cell, and a flood reported within 5 km. The 5 km rule and the other
    thresholds are imported from pipeline/forecast.py, not copied.

Scores are grouped by lead time (day 1 ... day 7). Below 30 scored cell-days
for a lead day, "enough_data" is false, and the app shows nothing.

Output: events/forecast/scores.json. Nothing is fetched here. The IMERG
history (events/rain_history_grid_daily.json) is refreshed separately with
pipeline/imerg_history_grid.py, which needs Earthdata credentials: refresh
IMERG first, then run this script. Days the satellite record does not yet
cover are simply not scored.

Usage:
    pipeline/.venv/bin/python pipeline/score_forecasts.py
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone

import forecast as F  # noqa: E402  (same directory; runs under pipeline/.venv)

OUT = F.OUT_DIR / "scores.json"
WARNING_LEVELS = ("medium", "high")
MIN_CELL_DAYS = 30          # below this, a lead day has "not enough data yet"
RUN_FILE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}(-\d{4})?\.json$")


def new_bucket() -> dict:
    return {
        "n_scored": 0,
        "n_scored_calibrated": 0,   # cell-days from runs that carry calibration
        "brier20": 0.0, "clim20": 0.0,
        "brier40": 0.0, "clim40": 0.0,
        "hits_imerg": 0, "misses_imerg": 0, "fa_imerg": 0,
        "hits_flood": 0, "misses_flood": 0, "fa_flood": 0,
        # median >= 40 mm vs IMERG >= 40 mm, raw vs calibrated (calibrated runs
        # only): [hits, misses, false alarms]
        "med40_raw": [0, 0, 0],
        "med40_cal": [0, 0, 0],
    }


def _hmf(triple: list) -> dict:
    return {"hits": triple[0], "misses": triple[1], "false_alarms": triple[2]}


def finish_bucket(b: dict) -> dict:
    """Turn raw sums into the reported means/counts; None when nothing scored."""
    n = b["n_scored"]
    out = {"n_scored": n, "enough_data": n >= MIN_CELL_DAYS}
    if n == 0:
        for k in ("brier_ge_20mm", "brier_clim_ge_20mm", "skill_ge_20mm",
                  "brier_ge_40mm", "brier_clim_ge_40mm", "skill_ge_40mm"):
            out[k] = None
    else:
        br20, cl20 = b["brier20"] / n, b["clim20"] / n
        br40, cl40 = b["brier40"] / n, b["clim40"] / n
        out.update({
            "brier_ge_20mm": round(br20, 4),
            "brier_clim_ge_20mm": round(cl20, 4),
            "skill_ge_20mm": round(1 - br20 / cl20, 4) if cl20 > 0 else None,
            "brier_ge_40mm": round(br40, 4),
            "brier_clim_ge_40mm": round(cl40, 4),
            "skill_ge_40mm": round(1 - br40 / cl40, 4) if cl40 > 0 else None,
        })
    out["vs_imerg_ge_40mm"] = {"hits": b["hits_imerg"], "misses": b["misses_imerg"],
                              "false_alarms": b["fa_imerg"]}
    out["vs_flood_reported_5km"] = {"hits": b["hits_flood"], "misses": b["misses_flood"],
                                    "false_alarms": b["fa_flood"]}
    # the calibrated runs' two medians (Task 44): raw vs IMERG >= 40 mm, and the
    # calibrated median_mm vs the same observation
    out["median_ge_40mm"] = {
        "n_scored_calibrated_runs": b["n_scored_calibrated"],
        "raw": _hmf(b["med40_raw"]),
        "calibrated": _hmf(b["med40_cal"]),
    }
    return out


def main() -> None:
    generated_at = datetime.now(timezone.utc).isoformat(timespec="seconds")

    # ---- inputs (same files as forecast.py) -------------------------------
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

    # the April-November window the forecast pipeline uses: the year-months the
    # catalog actually searched, 2014 onward.
    searched_ym = {e["year_month"] for e in fd_doc["meta"]["search_coverage"]}

    def in_window(day: str) -> bool:
        return day[:7] in searched_ym and F.d(day).month in F.WINDOW_MONTHS and day >= "2014-01-01"

    window_days = [x for x in grid["dates"] if in_window(x)]

    # last day the IMERG history actually has a value for (it ends mid-update)
    imerg_last_day = None
    for day in reversed(grid["dates"]):
        if any(series[c["id"]]["total_mm"][date_idx[day]] is not None for c in cells):
            imerg_last_day = day
            break

    # climatology: that cell's own frequency of >= 20 / >= 40 mm days in the window
    clim = {}
    for c in cells:
        cid = c["id"]
        vals = [series[cid]["total_mm"][date_idx[day]] for day in window_days]
        vals = [v for v in vals if v is not None]
        clim[cid] = (sum(v >= 20 for v in vals) / len(vals) if vals else 0.0,
                     sum(v >= 40 for v in vals) / len(vals) if vals else 0.0)

    # flood days within 5 km of each cell (the same rule as forecast.py)
    local_flood = {}
    for c in cells:
        cid = c["id"]
        local_flood[cid] = {
            day for day in areas_by_date
            if any(F.haversine_km(c["lon"], c["lat"], lon, lat) <= F.AREA_MATCH_KM
                   for lon, lat in areas_by_date[day])
        }

    runs = sorted(p.name for p in F.OUT_DIR.glob("*.json") if RUN_FILE_RE.match(p.name))
    print(f"archived runs found: {len(runs)}")

    lead = {i: new_bucket() for i in range(1, 8)}
    total = new_bucket()
    # lead-1 warning behaviour against reported flood days, for the plain sentence
    # One run per forecast date, so a same-day rerun (time-suffixed file) is not
    # counted twice. Keep the earliest calibrated run: the forecast people saw
    # that morning, not a rerun made after the rain had already started.
    def run_rank(doc: dict) -> tuple:
        return (not doc["meta"].get("calibration", {}).get("applied"),
                doc["meta"]["run"]["generated_at"])

    chosen_by_date: dict[str, tuple[str, dict]] = {}
    for name in runs:
        doc = json.loads((F.OUT_DIR / name).read_text())
        rd = doc["meta"]["run"]["run_date"]
        prev = chosen_by_date.get(rd)
        if prev is None or run_rank(doc) < run_rank(prev[1]):
            chosen_by_date[rd] = (name, doc)
    run_by_date = {rd: doc for rd, (_, doc) in chosen_by_date.items()}

    warn_cell_days = 0
    warn_cell_days_no_flood = 0
    flood_days_covered = 0
    flood_days_flagged = 0
    calibrated_runs = []   # runs whose rain is calibrated (Task 44)

    for rd in sorted(chosen_by_date):
        name, doc = chosen_by_date[rd]
        fdays = doc["meta"]["run"]["forecast_days"]
        if doc["meta"].get("calibration", {}).get("applied"):
            calibrated_runs.append(name)
        for cid, cell in doc["cells"].items():
            raw = series.get(cid)
            for di, block in enumerate(cell["days"]):
                day = block["date"]
                i = date_idx.get(day)
                if i is None or raw is None:
                    continue
                obs = raw["total_mm"][i]
                if obs is None:
                    continue
                p20 = block["rain"]["chance_ge_20mm"]
                p40 = block["rain"]["chance_ge_40mm"]
                o20 = 1.0 if obs >= 20 else 0.0
                o40 = 1.0 if obs >= 40 else 0.0
                f20, f40 = clim[cid]
                warn = block["level"] in WARNING_LEVELS
                imerg40 = obs >= 40
                flood = day in local_flood.get(cid, ())
                li = di + 1
                for b in (lead[li], total):
                    b["n_scored"] += 1
                    b["brier20"] += (p20 - o20) ** 2
                    b["clim20"] += (f20 - o20) ** 2
                    b["brier40"] += (p40 - o40) ** 2
                    b["clim40"] += (f40 - o40) ** 2
                    if warn and imerg40:
                        b["hits_imerg"] += 1
                    elif warn:
                        b["fa_imerg"] += 1
                    elif imerg40:
                        b["misses_imerg"] += 1
                    if warn and flood:
                        b["hits_flood"] += 1
                    elif warn:
                        b["fa_flood"] += 1
                    elif flood:
                        b["misses_flood"] += 1
                # the two medians of a calibrated run (raw_median_mm is the
                # uncalibrated one, median_mm the calibrated one)
                if "raw_median_mm" in block["rain"]:
                    raw_ge = block["rain"]["raw_median_mm"] >= 40
                    cal_ge = block["rain"]["median_mm"] >= 40
                    for b in (lead[li], total):
                        b["n_scored_calibrated"] += 1
                        if raw_ge and imerg40:
                            b["med40_raw"][0] += 1
                        elif raw_ge:
                            b["med40_raw"][2] += 1
                        elif imerg40:
                            b["med40_raw"][1] += 1
                        if cal_ge and imerg40:
                            b["med40_cal"][0] += 1
                        elif cal_ge:
                            b["med40_cal"][2] += 1
                        elif imerg40:
                            b["med40_cal"][1] += 1

    # lead-1 warnings (medium or high in any cell) against reported flood days:
    # a flood day is "flagged" when the newest run issued that day put a warning
    # in a cell within 5 km of one of its reported areas.
    for day, areas in areas_by_date.items():
        if not areas:
            continue
        doc = run_by_date.get(day)
        if doc is None:
            continue
        flood_days_covered += 1
        flagged = False
        for cid, cell in doc["cells"].items():
            near = any(F.haversine_km(cell["centre"]["lon"], cell["centre"]["lat"],
                                     lon, lat) <= F.AREA_MATCH_KM for lon, lat in areas)
            if not near:
                continue
            block = cell["days"][0]
            if block["date"] == day and block["level"] in WARNING_LEVELS:
                flagged = True
        if flagged:
            flood_days_flagged += 1
        # warning cell-days against flood days within 5 km
        for cid, cell in doc["cells"].items():
            block = cell["days"][0]
            if block["date"] != day or block["level"] not in WARNING_LEVELS:
                continue
            warn_cell_days += 1
            if day not in local_flood.get(cid, ()):
                warn_cell_days_no_flood += 1

    n_scored = total["n_scored"]
    meta = {
        "built_by": "pipeline/score_forecasts.py",
        "task": "42-forecast-scoring (docs/tasks/42-forecast-scoring.md), part A",
        "generated_at": generated_at,
        "method": (
            "Every archived forecast run is compared with what the IMERG satellite "
            "later measured for the same cell and day. Brier scores use the run's "
            "chance of at least 20 / 40 mm against the observed total; the "
            "climatology baseline is that cell's own frequency of such days in the "
            "April-November window (the year-months the catalog searched, 2014 "
            "onward), and skill = 1 - Brier / Brier_climatology. A medium or high "
            "level counts as a warning, scored as hits, misses and false alarms "
            "against IMERG >= 40 mm in that cell and against a flood reported "
            "within 5 km (the same rule as pipeline/forecast.py). Grouped by lead "
            "time, day 1 to day 7. Below 30 scored cell-days for a lead day, "
            "enough_data is false."
        ),
        "imerg_last_day": imerg_last_day,
        "archive_runs": runs,
        "archive_first_run_date": runs[0].split(".")[0] if runs else None,
        "calibrated_runs": calibrated_runs,
        "calibration": (
            "Runs listed in calibrated_runs carry CALIBRATED rain (quantile mapping "
            "fitted by pipeline/calibrate.py; see each run's meta.calibration): their "
            "chance fields and median_mm are IMERG-equivalent, and raw_median_mm keeps "
            "the uncalibrated median beside it. Runs before that are raw, so the Brier "
            "and warning scores mix the two regimes while the archive fills. "
            "median_ge_40mm scores the raw and the calibrated median of the "
            "calibrated runs against IMERG >= 40 mm, so the calibration's effect on "
            "the medians shows there first."
        ),
        "imerg_refresh": (
            "The IMERG history (events/rain_history_grid_daily.json) is refreshed "
            "separately: run pipeline/imerg_history_grid.py first (it needs "
            "Earthdata credentials), then run this script. Days the satellite "
            "record does not yet cover are not scored."
        ),
        "note": None,
    }

    if n_scored == 0:
        first = meta["archive_first_run_date"] or "(no runs archived yet)"
        last = imerg_last_day or "(no IMERG data)"
        meta["note"] = (
            f"Nothing to score yet: no archived forecast day is covered by the "
            f"IMERG history. The archive starts {first} and IMERG covers through {last}. "
            "Refresh IMERG (see imerg_refresh) and run again."
        )
        print("nothing to score yet")
    else:
        print(f"scored {n_scored} cell-days across {len(chosen_by_date)} forecast dates ({len(runs)} archived runs)")

    fa_share = round(warn_cell_days_no_flood / warn_cell_days, 3) if warn_cell_days else None
    out = {
        "meta": meta,
        "n_scored": n_scored,
        "enough_data": n_scored >= MIN_CELL_DAYS,
        "totals": finish_bucket(total),
        "warnings_vs_flood_days_lead1": {
            "flood_days_covered": flood_days_covered,
            "flood_days_flagged": flood_days_flagged,
            "warning_cell_days": warn_cell_days,
            "warning_cell_days_without_flood_reported_within_5km": warn_cell_days_no_flood,
            "false_alarm_share": fa_share,
        },
        "by_lead_day": [dict(lead_day=i, **finish_bucket(lead[i])) for i in range(1, 8)],
    }
    OUT.write_text(json.dumps(out, indent=1) + "\n")
    print(f"wrote {OUT.relative_to(F.ROOT)}")


if __name__ == "__main__":
    main()
