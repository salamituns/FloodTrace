#!/usr/bin/env python3
"""Precompute the EOT20 astronomical tide into events/forecast/tide_table.json.

Task 47 (docs/tasks/47-cloud-daily-run.md). Tides are deterministic, so the
daily run in GitHub Actions does not need the 2.1 GB EOT20 model: this script
computes the tide once, locally, for every offshore point the forecast uses
(aoi.points.offshore_tide in every events/lagos-* event.json), hourly from
2026-01-01 to 2031-01-01, and forecast.py reads the table whenever its window
is inside it. Regenerate (and push) before the table runs out, or point a
local run back at the model.

Heights are rounded to the centimetre and stored as one compact array per
point (metres above mean sea level), so the file stays a few hundred KB
instead of the 2.1 GB model. Times are implicit: index 0 is meta.start, one
value per hour, fixed UTC+1 (Africa/Lagos has no daylight saving), which is
exactly the hour grid forecast.py uses.

Usage:
    pipeline/.venv/bin/python pipeline/tide_table.py

Needs the EOT20 model under pipeline/cache/tide_models/EOT20/ (or at
$FLOODTRACE_TIDE_MODEL_DIR); writes events/forecast/tide_table.json.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pyTMD.compute

from tide_eot20 import EPOCH, MODEL_DIR

ROOT = Path(__file__).resolve().parent.parent
EVENTS = ROOT / "events"
OUT_PATH = EVENTS / "forecast" / "tide_table.json"

WAT = timezone(timedelta(hours=1))  # Africa/Lagos: fixed UTC+1, no DST
TABLE_START = datetime(2026, 1, 1, 0, 0, tzinfo=WAT)
TABLE_END = datetime(2031, 1, 1, 0, 0, tzinfo=WAT)  # exclusive
INTERVAL_HOURS = 1


def offshore_points() -> list[dict]:
    """Every offshore tide point the forecast can use, deduplicated.

    forecast.py takes the point from the last events/lagos-* event.json, but
    the table carries the points of all events so a new event with a moved
    point still hits the table.
    """
    points: list[dict] = []
    seen: set[tuple[float, float]] = set()
    for event_dir in sorted(p for p in EVENTS.iterdir()
                            if p.is_dir() and p.name.startswith("lagos-")):
        ev = json.loads((event_dir / "event.json").read_text(encoding="utf-8"))
        lon, lat = (float(v) for v in ev["aoi"]["points"]["offshore_tide"])
        if (lon, lat) in seen:
            continue
        seen.add((lon, lat))
        points.append({
            "lon": lon,
            "lat": lat,
            "source": f"events/{event_dir.name}/event.json aoi.points.offshore_tide",
        })
    if not points:
        raise SystemExit("no events/lagos-* directories with aoi.points.offshore_tide found")
    return points


def main() -> None:
    if not (MODEL_DIR / "EOT20").is_dir():
        raise SystemExit(
            f"EOT20 model not found under {MODEL_DIR} (the 2.1 GB model is not "
            "committed); see docs/FORECAST.md"
        )

    start, end = TABLE_START, TABLE_END
    n_hours = int((end - start).total_seconds()) // 3600
    times, t = [], start
    while t < end:
        times.append(t)
        t += timedelta(hours=INTERVAL_HOURS)
    assert len(times) == n_hours
    delta = np.array([(x.astimezone(timezone.utc) - EPOCH).total_seconds() for x in times])

    points_meta = offshore_points()
    print(f"computing {n_hours} hourly values at {len(points_meta)} point(s) ...")
    out_points = []
    for point in points_meta:
        tide = pyTMD.compute.tide_elevations(
            np.array([point["lon"]]),  # time-series mode: (stations, times)
            np.array([point["lat"]]),
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
        values = np.ma.filled(np.ma.asarray(tide, dtype=float), np.nan).reshape(-1)
        if values.size != n_hours or np.isnan(values).any():
            raise SystemExit(
                f"EOT20 returned {values.size} values ({np.isnan(values).sum()} NaN) "
                f"for {point['lon']}, {point['lat']}; expected {n_hours} valid hours"
            )
        # centimetre precision: the honest resolution of the model, and what
        # keeps the file small; forecast.py rounds its live computation to the
        # same centimetre, so table and model agree exactly.
        out_points.append({
            "lon": point["lon"],
            "lat": point["lat"],
            "values": [round(float(v), 2) for v in values],
        })
        valid = values[~np.isnan(values)]
        print(f"  {point['lon']}, {point['lat']}: {valid.min():+.2f} … {valid.max():+.2f} m")

    out = {
        "meta": {
            "product": "EOT20 global ocean tide model (astronomical tide, 17 constituents)",
            "citation": "Hart-Davis et al. (2021), EOT20, SEANOE, doi:10.17882/79489",
            "licence": "CC BY 4.0",
            "model": "EOT20 via pyTMD.compute.tide_elevations, extrapolate=True, cutoff=20 km",
            "datum": "mean sea level (heights in metres above MSL; tide only, no surge)",
            "start": start.isoformat(),
            "end": end.isoformat(),  # exclusive: the last value is end - 1 h
            "interval_hours": INTERVAL_HOURS,
            "timezone": "fixed UTC+1 (Africa/Lagos has no daylight saving); "
                        "index 0 is meta.start, one value per hour",
            "points": points_meta,
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "built_by": "pipeline/tide_table.py",
            "note": "precomputed so the daily run needs no 2.1 GB model "
                    "(docs/tasks/47-cloud-daily-run.md); regenerate with "
                    "pipeline/tide_table.py before 2031-01-01",
        },
        "points": out_points,
    }
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(out, separators=(",", ":")) + "\n"
    OUT_PATH.write_text(text, encoding="utf-8")
    size = OUT_PATH.stat().st_size
    print(f"wrote {OUT_PATH.relative_to(ROOT)} "
          f"({size} bytes, {size / 1e6:.2f} MB, {n_hours} hours per point)")
    if size >= 3_000_000:
        raise SystemExit(f"tide table is {size} bytes; keep it under 3 MB")


if __name__ == "__main__":
    main()
