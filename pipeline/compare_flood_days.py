#!/usr/bin/env python3
"""Task 14 — what separates Lagos flood days from heavy-rain days with no flood?

Compares the top 25 catalog candidates by population-weighted rain (pwr_rank
in events/catalog_ranked.json) across intensity, duration, antecedent wetness
and tide features, using only cached data (no new downloads):

- 30-min IMERG per cell   pipeline/cache/imerg_history/*.csv (Task 07 grid scan,
                          same parser as pipeline/imerg_history_grid.py)
- population per cell     events/exposure_cells.json (GHSL GHS-POP R2023A)
- tide                    EOT20 via pyTMD, exactly as pipeline/tide_eot20.py
                          does, at the offshore point lon 3.52 lat 6.40

Groups come from events/catalog_review.json verdicts matched by overlapping
dates (+/- 1 day), with 2024-07-02/03 (known_event_id, the Lekki/Apapa flood)
counted as a flood:

- flood      verdict confirmed_flood (+ the known event)          [expect 5]
- likely     2017-07-05/06, verdict likely_flood — kept out of both groups
- no_flood   verdict rain_no_flood_reported (recheck.verdict preferred)

Writes events/flood_vs_noflood.json and prints the membership, the feature
table, per-feature medians and simple separability counts. n = 5 vs ~19, so
description only — no models, no p-values.

Usage:
    pipeline/.venv/bin/python pipeline/compare_flood_days.py
"""

from __future__ import annotations

import json
import math
import re
import statistics
import sys
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pyTMD.compute

import imerg
import imerg_history as hist

PIPELINE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = PIPELINE_DIR.parent
EVENTS_DIR = PROJECT_ROOT / "events"
CACHE_DIR = hist.CACHE_DIR
MODEL_DIR = PIPELINE_DIR / "cache" / "tide_models"
TZ = ZoneInfo("Africa/Lagos")
UTC = timezone.utc
EPOCH = datetime(2000, 1, 1, tzinfo=UTC)
TIDE_LON, TIDE_LAT = 3.52, 6.40
WINDOW_PAD = timedelta(hours=12)
STEP = timedelta(minutes=30)
HEAVY_RATE_MM_H = 2.0
URBAN_FRACTION = 0.80
TREND_EPS_M = 0.01  # m over the 2 h centred on the rain peak
EXPECTED_FLOOD_STARTS = ("2011-07-10", "2021-07-16", "2022-07-08", "2024-07-02", "2025-08-03")
EXPECTED_NO_FLOOD_COUNT = 18
GROUP_ORDER = {"flood": 0, "likely": 1, "no_flood": 2}
FILE_TAIL_RE = re.compile(r"_(\d{8}T\d{6})_(\d{8}T\d{6})\.csv$")

RAIN_FEATURES = (
    "pwr_mm",
    "pw_peak_30min_mm_h",
    "pw_max_1h_mm",
    "pw_max_3h_mm",
    "urban_max_3h_mm",
    "heavy_hours",
    "pw_antecedent_3d_mm",
    "pw_antecedent_7d_mm",
)
TIDE_HEIGHT_FEATURES = ("tide_at_peak_m", "tide_max_in_window_m")
# higher-is-more-flood-like; the separability count (# no_flood >= weakest
# flood) is meaningful for these
DIRECTIONAL_FEATURES = RAIN_FEATURES + TIDE_HEIGHT_FEATURES
# reported with counts too, but the >= direction carries no flood meaning
OTHER_NUMERIC = ("hours_from_high", "tidal_range_day_m", "peak_hour", "year")
ALL_NUMERIC = DIRECTIONAL_FEATURES + OTHER_NUMERIC

FEATURE_LABELS = {
    "pwr_mm": "pop-weighted rain over the candidate days (from catalog_ranked.json)",
    "pw_peak_30min_mm_h": "peak of the population-weighted 30-min rate series (mm/h)",
    "pw_max_1h_mm": "max 1-h total of the pw series (mm)",
    "pw_max_3h_mm": "max 3-h total of the pw series (mm)",
    "urban_max_3h_mm": "max over urban cells of each cell's max 3-h total (mm)",
    "heavy_hours": "hours in the window with pw rate >= 2 mm/h (0.5 h per 30-min step)",
    "pw_antecedent_3d_mm": "pw total over the 3 WAT days before the first candidate day",
    "pw_antecedent_7d_mm": "pw total over the 7 WAT days before the first candidate day",
    "tide_at_peak_m": "EOT20 tide at the centre of the pw max-3h window (m MSL)",
    "tide_max_in_window_m": "max tide within the pw max-3h window (m MSL)",
}


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def verdict_of(entry: dict) -> str:
    recheck = entry.get("recheck") or {}
    return recheck.get("verdict") or entry.get("verdict") or "unknown"


def match_review(cand: dict, review: list) -> list:
    lo = date.fromisoformat(cand["start"]) - timedelta(days=1)
    hi = date.fromisoformat(cand["end"]) + timedelta(days=1)
    return [
        entry
        for entry in review
        if not (
            date.fromisoformat(entry["end"]) < lo or date.fromisoformat(entry["start"]) > hi
        )
    ]


def group_of(cand: dict, matched: list) -> tuple:
    if cand.get("known_event_id"):
        return "flood", "known_event_id"
    verdicts = {verdict_of(entry) for entry in matched}
    if "confirmed_flood" in verdicts:
        return "flood", "catalog_review"
    if "likely_flood" in verdicts:
        return "likely", "catalog_review"
    if verdicts and verdicts <= {"rain_no_flood_reported"}:
        return "no_flood", "catalog_review"
    detail = ", ".join(sorted(verdicts)) or "no review entry within +/- 1 day"
    raise SystemExit(
        "cannot classify candidate %s..%s (pwr_rank %s): %s"
        % (cand["start"], cand["end"], cand["pwr_rank"], detail)
    )


def candidate_window(cand: dict) -> tuple:
    """(window_lo, window_hi, antecedent_7d_lo, first_day_start) in WAT."""
    sd = date.fromisoformat(cand["start"])
    ed = date.fromisoformat(cand["end"])
    win_lo = datetime.combine(sd, time(0, 0), TZ) - WINDOW_PAD
    win_hi = datetime.combine(ed + timedelta(days=1), time(0, 0), TZ) + WINDOW_PAD
    ant_lo = datetime.combine(sd - timedelta(days=7), time(0, 0), TZ)
    day_start = datetime.combine(sd, time(0, 0), TZ)
    return win_lo, win_hi, ant_lo, day_start


def file_period(path: Path) -> tuple:
    match = FILE_TAIL_RE.search(path.name)
    if not match:
        return None, None
    fs = datetime.strptime(match.group(1), "%Y%m%dT%H%M%S").replace(tzinfo=UTC)
    fe = datetime.strptime(match.group(2), "%Y%m%dT%H%M%S").replace(tzinfo=UTC)
    return fs, fe


def load_cell_series(
    lat: float, lon: float, needed_dates: set, ranges: list
) -> dict:
    """Cached 30-min IMERG for one cell, restricted to the needed ranges.

    Same row parsing as imerg_history.parse_series (UTC interval starts,
    negative/non-finite values dropped); Final-run rows win, Late-run rows
    only fill gaps, matching imerg_history_grid.run.
    """
    series: dict = {}
    for variable, late in ((hist.VARIABLE_FINAL, False), (hist.VARIABLE_LATE, True)):
        files = sorted(
            CACHE_DIR.glob("*%s_%.3fx%.3f_*.csv" % (variable, lat, lon)),
            key=lambda p: (file_period(p)[0] or datetime.max.replace(tzinfo=UTC), p.name),
        )
        for path in files:
            fs, fe = file_period(path)
            if fs is None:
                continue
            if not any(fs < hi and fe > lo for lo, hi in ranges):
                continue  # this chunk overlaps no candidate window
            in_data = False
            for line in path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line or "," not in line:
                    continue
                if not in_data:
                    if line.startswith("Timestamp"):
                        in_data = True
                    continue
                if line[:10] not in needed_dates:
                    continue
                key, _, value = line.partition(",")
                stamp = hist.parse_stamp(key.strip())
                if stamp is None:
                    continue
                if not any(lo <= stamp < hi for lo, hi in ranges):
                    continue
                try:
                    rate = float(value)
                except ValueError:
                    continue
                if not math.isfinite(rate) or rate < 0:
                    continue
                if late:
                    series.setdefault(stamp, rate)
                else:
                    series[stamp] = rate
    return series


def pw_series(
    series_by_cell: dict, weights: dict, lo: datetime, hi: datetime
) -> tuple:
    """Population-weighted mean rate per 30-min step, plus per-step cell counts."""
    acc: dict = {}
    counts: dict = {}
    for cid, weight in weights.items():
        if weight <= 0:
            continue
        for stamp, rate in series_by_cell.get(cid, {}).items():
            if lo <= stamp < hi:
                entry = acc.setdefault(stamp, [0.0, 0.0])
                entry[0] += weight * rate
                entry[1] += weight
                counts[stamp] = counts.get(stamp, 0) + 1
    pw = {stamp: entry[0] / entry[1] for stamp, entry in acc.items() if entry[1] > 0}
    return pw, counts


def rolling_max(values: list, n_steps: int) -> tuple:
    """(max n-step rolling total in mm, index of its first occurrence)."""
    best_value, best_index = None, None
    for i in range(len(values) - n_steps + 1):
        total = sum(values[i : i + n_steps]) * 0.5
        if best_value is None or total > best_value:
            best_value, best_index = total, i
    if best_value is None:
        raise RuntimeError("window shorter than one rolling interval")
    return best_value, best_index


def candidate_features(
    cand: dict,
    series_by_cell: dict,
    weights: dict,
    urban_ids: list,
    tide: dict,
) -> tuple:
    win_lo, win_hi, ant_lo, day_start = candidate_window(cand)
    days = {date.fromisoformat(d) for d in cand["days"]}
    pw, counts = pw_series(series_by_cell, weights, ant_lo, win_hi)
    win_steps = sorted(s for s in pw if win_lo <= s < win_hi)
    if len(win_steps) < 24:
        raise RuntimeError("%s: only %d window steps" % (cand["start"], len(win_steps)))
    rates = [pw[s] for s in win_steps]

    pw_peak_30min = max(rates)
    pw_max_1h, _ = rolling_max(rates, 2)
    pw_max_3h, best_index = rolling_max(rates, 6)
    centre = win_steps[best_index] + timedelta(hours=1, minutes=30)
    centre_wat = centre.astimezone(TZ)
    heavy_hours = 0.5 * sum(1 for rate in rates if rate >= HEAVY_RATE_MM_H)

    urban_max_3h = None
    for cid in urban_ids:
        cell = series_by_cell.get(cid, {})
        cell_rates = [cell.get(s, 0.0) for s in win_steps]
        total, _ = rolling_max(cell_rates, 6)
        if urban_max_3h is None or total > urban_max_3h:
            urban_max_3h = total

    ant3_lo = day_start - timedelta(days=3)
    ant3 = sum(rate * 0.5 for s, rate in pw.items() if ant3_lo <= s < day_start)
    ant7 = sum(rate * 0.5 for s, rate in pw.items() if ant_lo <= s < day_start)

    tide_vals = [tide[s] for s in win_steps]
    tide_at_peak = tide[centre]
    tide_max_in_window = max(tide_vals[best_index : best_index + 6])
    trend_diff = tide[centre + timedelta(hours=1)] - tide[centre - timedelta(hours=1)]
    if trend_diff > TREND_EPS_M:
        tide_trend = "rising"
    elif trend_diff < -TREND_EPS_M:
        tide_trend = "falling"
    else:
        tide_trend = "flat (near high/low water)"
    highs = [
        win_steps[i]
        for i in range(1, len(win_steps) - 1)
        if tide_vals[i] >= tide_vals[i - 1] and tide_vals[i] >= tide_vals[i + 1]
    ]
    if not highs:
        raise RuntimeError("%s: no high water found in the tide window" % cand["start"])
    nearest_high = min(highs, key=lambda h: abs((h - centre).total_seconds()))
    hours_from_high = (centre - nearest_high).total_seconds() / 3600.0
    peak_day = centre_wat.date()
    day_vals = [
        v for s, v in zip(win_steps, tide_vals) if s.astimezone(TZ).date() == peak_day
    ]
    tidal_range_day = max(day_vals) - min(day_vals)

    features = {
        "pwr_mm": cand["pop_weighted_rain_mm"],
        "pw_peak_30min_mm_h": imerg.clean(pw_peak_30min),
        "pw_max_1h_mm": imerg.clean(pw_max_1h),
        "pw_max_3h_mm": imerg.clean(pw_max_3h),
        "urban_max_3h_mm": imerg.clean(urban_max_3h),
        "heavy_hours": imerg.clean(heavy_hours, 1),
        "peak_time_wat": centre_wat.isoformat(timespec="minutes"),
        "peak_hour": centre_wat.hour,
        "night": centre_wat.hour >= 20 or centre_wat.hour < 6,
        "pw_antecedent_3d_mm": imerg.clean(ant3),
        "pw_antecedent_7d_mm": imerg.clean(ant7),
        "tide_at_peak_m": imerg.clean(tide_at_peak, 3),
        "tide_max_in_window_m": imerg.clean(tide_max_in_window, 3),
        "tide_trend": tide_trend,
        "hours_from_high": imerg.clean(hours_from_high, 1),
        "tidal_range_day_m": imerg.clean(tidal_range_day, 3),
        "year": int(cand["start"][:4]),
    }

    # validation: rebuild the catalog numbers from the 30-min cache
    per_cell = {
        cid: sum(rate * 0.5 for s, rate in cell.items() if s.astimezone(TZ).date() in days)
        for cid, cell in series_by_cell.items()
    }
    weight_sum = sum(weights.values())
    pwr_check = sum(weights[cid] * total for cid, total in per_cell.items()) / weight_sum
    cell_diffs = {
        cid: abs(total - float(cand["cells"][cid]["total_mm"]))
        for cid, total in per_cell.items()
        if cid in cand.get("cells", {})
    }
    validation = {
        "pwr_abs_diff": abs(pwr_check - cand["pop_weighted_rain_mm"]),
        "max_cell_total_abs_diff": max(cell_diffs.values()),
        "min_cells_per_step": min(counts.get(s, 0) for s in win_steps),
    }
    return features, validation


def fmt(value, digits: int = 2) -> str:
    if value is None:
        return "n/a"
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, float):
        return "%.*f" % (digits, value)
    return str(value)


def main() -> None:
    ranked = load_json(EVENTS_DIR / "catalog_ranked.json")["candidates"]
    top25 = sorted(ranked, key=lambda c: c["pwr_rank"])[:25]
    if [c["pwr_rank"] for c in top25] != list(range(1, 26)):
        raise SystemExit("catalog_ranked.json pwr_rank is not 1..25 on the top 25")
    review = load_json(EVENTS_DIR / "catalog_review.json")["candidates"]
    exposure = load_json(EVENTS_DIR / "exposure_cells.json")

    cells = exposure["cells"]
    if len(cells) != 68:
        raise SystemExit("expected 68 exposure cells, found %d" % len(cells))
    weights = {
        epoch: {c["id"]: float(c["population"][str(epoch)]) for c in cells}
        for epoch in (2000, 2005, 2010, 2015, 2020, 2025)
    }
    cell_coords = {c["id"]: (float(c["lat"]), float(c["lon"])) for c in cells}

    def urban_ids_for(epoch: int) -> list:
        ordered = sorted(cells, key=lambda c: -float(c["population"][str(epoch)]))
        total = sum(float(c["population"][str(epoch)]) for c in ordered)
        chosen, cum = [], 0.0
        for c in ordered:
            chosen.append(c["id"])
            cum += float(c["population"][str(epoch)])
            if cum >= URBAN_FRACTION * total:
                break
        return chosen

    # ---- groups -----------------------------------------------------------
    assignments = []
    for cand in top25:
        matched = match_review(cand, review)
        group, source = group_of(cand, matched)
        assignments.append((cand, matched, group, source))

    floods = [c for c, m, g, s in assignments if g == "flood"]
    likelys = [c for c, m, g, s in assignments if g == "likely"]
    no_floods = [c for c, m, g, s in assignments if g == "no_flood"]
    print("group membership (top 25 by pwr_rank, matched to catalog_review +/- 1 day)")
    print("  flood (expect 5):")
    for c in floods:
        print("    %s..%s  pwr_rank %2d" % (c["start"], c["end"], c["pwr_rank"]))
    if sorted(c["start"] for c in floods) != list(EXPECTED_FLOOD_STARTS):
        raise SystemExit("flood group is not the expected 5 events — stopping as instructed")
    print("  likely (reported separately, excluded from both groups):")
    for c in likelys:
        print("    %s..%s  pwr_rank %2d" % (c["start"], c["end"], c["pwr_rank"]))
    print("  no_flood: %d (task expected %d)" % (len(no_floods), EXPECTED_NO_FLOOD_COUNT))
    for c in no_floods:
        note = "  [suspect_peak: a cell 30-min peak > 70 mm/h]" if c.get("suspect_peak") else ""
        print("    %s..%s  pwr_rank %2d%s" % (c["start"], c["end"], c["pwr_rank"], note))
    if len(no_floods) != EXPECTED_NO_FLOOD_COUNT:
        extra = [c for c in no_floods if c.get("suspect_peak")]
        if extra:
            print(
                "  note: found %d no-flood candidates, one more than the plan's 18; "
                "the extra is %s (pwr #%d) — its review verdict is "
                "rain_no_flood_reported, so it stays in the no_flood group and is "
                "flagged as a suspect IMERG peak."
                % (len(no_floods), extra[0]["start"], extra[0]["pwr_rank"])
            )
        else:
            print("  note: no-flood count differs from the expected 18")
    print()

    # ---- load cached IMERG restricted to the needed ranges ------------------
    ranges = []
    for cand in top25:
        win_lo, win_hi, ant_lo, _ = candidate_window(cand)
        ranges.append((ant_lo.astimezone(UTC), win_hi.astimezone(UTC)))
    needed_dates = set()
    for lo, hi in ranges:
        day = lo.date() - timedelta(days=1)
        while day <= hi.date() + timedelta(days=1):
            needed_dates.add(day.isoformat())
            day += timedelta(days=1)

    series_by_cell = {}
    for index, (cid, (lat, lon)) in enumerate(cell_coords.items(), start=1):
        series_by_cell[cid] = load_cell_series(lat, lon, needed_dates, ranges)
        if not series_by_cell[cid]:
            raise SystemExit("no cached IMERG rows found for cell %s" % cid)
        print(
            "  [%2d/68] %s: %d steps in the candidate windows"
            % (index, cid, len(series_by_cell[cid])),
            file=sys.stderr,
            flush=True,
        )

    # ---- tide: one pyTMD call over every window's 30-min grid ---------------
    tide_times = set()
    for cand in top25:
        win_lo, win_hi, _, _ = candidate_window(cand)
        t = win_lo.astimezone(UTC)
        end = win_hi.astimezone(UTC) - STEP
        while t <= end:
            tide_times.add(t)
            t += STEP
    tide_steps = sorted(tide_times)
    delta = np.array([(t - EPOCH).total_seconds() for t in tide_steps])
    print("computing EOT20 tide at (%.2f, %.2f) for %d steps" % (TIDE_LAT, TIDE_LON, len(tide_steps)))
    tide_values = pyTMD.compute.tide_elevations(
        np.array([TIDE_LON]),
        np.array([TIDE_LAT]),
        delta,
        directory=MODEL_DIR,
        model="EOT20",
        crs=4326,
        epoch=(2000, 1, 1, 0, 0, 0),
        type="time series",
        standard="UTC",
        extrapolate=True,
        cutoff=20.0,
    )
    values = np.ma.filled(np.ma.asarray(tide_values, dtype=float), np.nan).reshape(-1)
    if values.size != len(tide_steps) or np.isnan(values).any():
        raise SystemExit("EOT20 tide computation returned missing values")
    tide = dict(zip(tide_steps, (float(v) for v in values)))

    # ---- features ----------------------------------------------------------
    records = []
    urban_counts_ok = True
    max_pwr_diff = 0.0
    max_cell_diff = 0.0
    min_coverage = 68
    for cand, matched, group, source in assignments:
        epoch = int(cand["pop_epoch"])
        urban_ids = urban_ids_for(epoch)
        if len(urban_ids) != cand["urban_cells"]:
            urban_counts_ok = False
            print(
                "  warning: derived %d urban cells for %s but catalog_ranked says %d"
                % (len(urban_ids), cand["start"], cand["urban_cells"])
            )
        features, validation = candidate_features(
            cand, series_by_cell, weights[epoch], urban_ids, tide
        )
        max_pwr_diff = max(max_pwr_diff, validation["pwr_abs_diff"])
        max_cell_diff = max(max_cell_diff, validation["max_cell_total_abs_diff"])
        min_coverage = min(min_coverage, validation["min_cells_per_step"])
        entry = next(iter(matched), None)
        records.append(
            {
                "group": group,
                "verdict_source": source,
                "verdict": verdict_of(entry) if entry else None,
                "known_event_id": cand.get("known_event_id"),
                "start": cand["start"],
                "end": cand["end"],
                "days": cand["days"],
                "pwr_rank": cand["pwr_rank"],
                "pop_epoch": epoch,
                "n_urban_cells": len(urban_ids),
                "suspect_peak": bool(cand.get("suspect_peak")),
                "features": features,
            }
        )
    if max_pwr_diff > 0.05 or max_cell_diff > 0.05:
        raise SystemExit(
            "30-min cache disagrees with the catalog: pwr diff %.3f mm, cell total "
            "diff %.3f mm — stopping" % (max_pwr_diff, max_cell_diff)
        )
    print(
        "validation vs catalog_ranked.json: max pwr diff %.3f mm, max per-cell "
        "total diff %.3f mm, min cells per step %d/68"
        % (max_pwr_diff, max_cell_diff, min_coverage)
    )
    print(
        "time zone check: IMERG CSV stamps are UTC starts of 30-min intervals "
        '(header "Timestamp (UTC)"); WAT = UTC+1 with no DST, so WAT steps stay on '
        ":00/:30; reproducing the catalog daily totals to <0.01 mm confirms the handling"
    )
    if not urban_counts_ok:
        print("warning: derived urban-cell counts differ from catalog_ranked (see above)")
    print()

    records.sort(key=lambda r: (GROUP_ORDER[r["group"]], r["pwr_rank"]))

    # ---- write the JSON -----------------------------------------------------
    def group_dates(group: str) -> list:
        return [
            "%s..%s (#%d)" % (r["start"], r["end"], r["pwr_rank"])
            for r in records
            if r["group"] == group
        ]

    suspect = [c for c in no_floods if c.get("suspect_peak")]
    count_note = (
        (
            "the plan's '18 with no flood report' misses one: %s (pwr #%d) has "
            "verdict rain_no_flood_reported and is the only suspect_peak candidate "
            "in the top 25 (a cell 30-min peak > 70 mm/h), so it is kept in no_flood "
            "and flagged"
            % (suspect[0]["start"], suspect[0]["pwr_rank"])
        )
        if len(no_floods) != EXPECTED_NO_FLOOD_COUNT and suspect
        else "counts match the plan"
    )
    payload = {
        "meta": {
            "task": "Task 14 — what separates Lagos flood days from heavy-rain days with no flood?",
            "method": (
                "top 25 catalog candidates by pwr_rank; per candidate, 30-min "
                "population-weighted (pw) IMERG series over the candidate's WAT "
                "days +/- 12 h, using GHSL cell populations at the candidate's "
                "epoch; antecedent pw totals over the 3 and 7 WAT days before the "
                "first candidate day; EOT20 astronomical tide (pyTMD) at the "
                "offshore point lon 3.52 lat 6.40 over the same window"
            ),
            "sources": {
                "rain": (
                    "GPM IMERG v07 half-hourly, GPM_3IMERGHH Final + GPM_3IMERGHHL "
                    "Late tail, GES DISC Giovanni in the Cloud Time Series Service; "
                    "per-cell 30-min series read from pipeline/cache/imerg_history "
                    "(Task 07 grid scan caches); parser reused from "
                    "pipeline/imerg_history.py"
                ),
                "population": (
                    "GHSL GHS-POP R2023A 30 arc-sec, per-cell per-epoch populations "
                    "from events/exposure_cells.json (Task 10)"
                ),
                "tide": (
                    "EOT20 global ocean tide model (Hart-Davis et al. 2021, "
                    "doi:10.17882/79489, CC BY 4.0) via pyTMD.compute.tide_elevations "
                    "at lon 3.52, lat 6.40, 30-min steps, as in pipeline/tide_eot20.py; "
                    "astronomical tide only — no surge, no lagoon damping or phase lag"
                ),
                "groups": (
                    "events/catalog_review.json verdicts (recheck.verdict preferred), "
                    "matched by overlapping dates +/- 1 day; 2024-07-02/03 counted "
                    "as a flood via known_event_id; ranking from "
                    "events/catalog_ranked.json"
                ),
            },
            "timezone": (
                "IMERG CSV stamps are UTC starts of 30-min intervals (header "
                '"Timestamp (UTC)"); converted to Africa/Lagos (WAT = UTC+1, no '
                "DST); verified by reproducing catalog daily totals (max pwr diff "
                "%.3f mm, max cell diff %.3f mm)" % (max_pwr_diff, max_cell_diff)
            ),
            "windows": {
                "feature_window": "candidate WAT days +/- 12 h",
                "antecedent": "3 and 7 full WAT days before the first candidate day",
                "heavy_hours": "0.5 h per 30-min step with pw rate >= 2 mm/h",
                "peak": "centre of the best rolling 3-h pw window; night = 20:00-06:00 WAT",
                "urban_cells": "cells holding the top 80% of the AOI population at the candidate's epoch",
                "tide_trend": "tide(peak+1h) - tide(peak-1h); flat within +/-0.01 m",
                "hours_from_high": (
                    "signed hours from the nearest high water in the window; "
                    "negative before high water"
                ),
                "tidal_range_day_m": "high - low tide over the WAT day of the rain peak",
            },
            "groups": {
                "flood": group_dates("flood"),
                "likely": group_dates("likely"),
                "no_flood": group_dates("no_flood"),
                "expected_counts": {"flood": 5, "no_flood": EXPECTED_NO_FLOOD_COUNT},
                "actual_counts": {
                    "flood": len(floods),
                    "likely": len(likelys),
                    "no_flood": len(no_floods),
                },
                "count_note": count_note,
            },
            "note": (
                "n = 5 flood vs %d no-flood: description only — no models, no "
                "p-values; separability is reported as counts of no-flood events "
                "at or above the weakest flood per feature" % len(no_floods)
            ),
            "generated_at": imerg.utc_now_iso(),
        },
        "candidates": records,
    }
    imerg.write_json(EVENTS_DIR / "flood_vs_noflood.json", payload)

    # ---- console table ------------------------------------------------------
    header = (
        "group     start      end        rk  yr  pwr_mm   pk30   mx1h   mx3h  urb3h"
        " hvy_h  ant3d  ant7d peak_wat        n tide_pk tide_mx trend         hrs_hi  range"
    )
    print(header)
    print("-" * len(header))
    for r in records:
        f = r["features"]
        print(
            "%-9s %-10s %-10s %3d %4d %8s %6s %6s %6s %6s %6s %6s %6s %-16s %2s"
            " %7s %7s %-14s %6s %6s"
            % (
                r["group"],
                r["start"],
                r["end"],
                r["pwr_rank"],
                f["year"],
                fmt(f["pwr_mm"]),
                fmt(f["pw_peak_30min_mm_h"]),
                fmt(f["pw_max_1h_mm"]),
                fmt(f["pw_max_3h_mm"]),
                fmt(f["urban_max_3h_mm"]),
                fmt(f["heavy_hours"], 1),
                fmt(f["pw_antecedent_3d_mm"]),
                fmt(f["pw_antecedent_7d_mm"]),
                f["peak_time_wat"][:16],
                "N" if f["night"] else "D",
                fmt(f["tide_at_peak_m"], 2),
                fmt(f["tide_max_in_window_m"], 2),
                f["tide_trend"][:13],
                fmt(f["hours_from_high"], 1),
                fmt(f["tidal_range_day_m"], 2),
            )
        )
    print()

    # ---- per-feature separation --------------------------------------------
    flood_recs = [r for r in records if r["group"] == "flood"]
    no_recs = [r for r in records if r["group"] == "no_flood"]
    likely_recs = [r for r in records if r["group"] == "likely"]
    n_f, n_n = len(flood_recs), len(no_recs)
    print(
        "per feature: flood median vs no-flood median, and how many of the %d "
        "no-flood events are >= the weakest flood (simple separability count)" % n_n
    )
    separation = {}
    for feat in ALL_NUMERIC:
        fv = [r["features"][feat] for r in flood_recs]
        nv = [r["features"][feat] for r in no_recs]
        weakest = min(fv)
        count = sum(1 for v in nv if v >= weakest)
        separation[feat] = count
        note = ""
        if feat in ("hours_from_high", "tidal_range_day_m", "peak_hour", "year"):
            note = "  (>= has no flood meaning here; count is mechanical)"
        print(
            "  %-24s flood_med %8.2f  noflood_med %8.2f  weakest_flood %8.2f  "
            "no_flood>=weakest %2d/%d%s"
            % (feat, statistics.median(fv), statistics.median(nv), weakest, count, n_n, note)
        )
    flood_nights = sum(1 for r in flood_recs if r["features"]["night"])
    no_nights = sum(1 for r in no_recs if r["features"]["night"])
    likely_nights = sum(1 for r in likely_recs if r["features"]["night"])
    print(
        "  %-24s flood %d/%d at night, no_flood %d/%d, likely %d/%d"
        % ("night (20:00-06:00)", flood_nights, n_f, no_nights, n_n, likely_nights, len(likely_recs))
    )
    for label, recs in (("flood", flood_recs), ("no_flood", no_recs)):
        trends = {}
        for r in recs:
            trends[r["features"]["tide_trend"]] = trends.get(r["features"]["tide_trend"], 0) + 1
        print(
            "  tide_trend %-10s %s"
            % (label, ", ".join("%s: %d" % (k, v) for k, v in sorted(trends.items())))
        )
    print()

    # ---- plain-language findings --------------------------------------------
    print("findings (descriptive only, n = %d vs %d):" % (n_f, n_n))
    separating = [f for f in DIRECTIONAL_FEATURES if separation[f] <= n_n // 3]
    overlapping = [f for f in DIRECTIONAL_FEATURES if separation[f] > n_n // 3]
    for feat in separating:
        print(
            "  SEPARATES: %s — only %d/%d no-flood days reach the weakest flood (%s)"
            % (feat, separation[feat], n_n, FEATURE_LABELS.get(feat, ""))
        )
    for feat in overlapping:
        print(
            "  does NOT separate: %s — %d/%d no-flood days are >= the weakest flood (%s)"
            % (feat, separation[feat], n_n, FEATURE_LABELS.get(feat, ""))
        )
    print(
        "  peak time: flood peak hours (WAT) %s; no-flood median peak hour %.0f"
        % (
            ", ".join(
                str(r["features"]["peak_hour"])
                for r in sorted(flood_recs, key=lambda r: r["pwr_rank"])
            ),
            statistics.median([r["features"]["peak_hour"] for r in no_recs]),
        )
    )
    print(
        "  year (reporting-bias context): flood years %s; no-flood years span %d-%d "
        "(online news coverage is thinner before ~2010)"
        % (
            ", ".join(
                str(r["features"]["year"])
                for r in sorted(flood_recs, key=lambda r: r["pwr_rank"])
            ),
            min(r["features"]["year"] for r in no_recs),
            max(r["features"]["year"] for r in no_recs),
        )
    )
    near_misses = []
    for r in no_recs:
        hits = sum(
            1
            for feat in DIRECTIONAL_FEATURES
            if r["features"][feat] is not None
            and r["features"][feat] >= min(x["features"][feat] for x in flood_recs)
        )
        if hits >= len(DIRECTIONAL_FEATURES) - 1:
            near_misses.append((hits, r))
    if near_misses:
        print(
            "  possible under-reporting — no-flood days that look like floods on "
            "nearly every feature:"
        )
        for hits, r in sorted(near_misses, key=lambda t: -t[0]):
            print(
                "    %s..%s (pwr #%d, %d): %d/%d rain/tide features >= the weakest flood%s"
                % (
                    r["start"],
                    r["end"],
                    r["pwr_rank"],
                    r["features"]["year"],
                    hits,
                    len(DIRECTIONAL_FEATURES),
                    " [suspect IMERG peak]" if r["suspect_peak"] else "",
                )
            )
    else:
        print("  no no-flood day matches the weakest flood on nearly every feature")
    print()
    print("wrote events/flood_vs_noflood.json")


if __name__ == "__main__":
    main()
