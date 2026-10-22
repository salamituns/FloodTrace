#!/usr/bin/env python3
"""Rescan the IMERG record over every Lagos 0.1-degree cell.

Task 06 scanned four AOI points and missed the 3 Jul 2024 rain core at
the cell centred 6.45N 3.35E (Apapa / Mile 2), so that event ranked only
#26. This scan covers every IMERG cell centre inside the event AOI
bbox, dropping cells that are entirely Atlantic Ocean (Natural Earth
10m coastline test), and reuses the Task 06 caches for the four point
cells.

Outputs (in events/):
- rain_history_grid_daily.json  per WAT day, per cell: total mm +
  max 30-min intensity (compact parallel arrays)
- catalog_candidates_grid.json  candidates qualifying at any cell
- catalog_scan_compare.json     grid-only / point-only / rank changes

Usage:
    pipeline/.venv/bin/python pipeline/imerg_history_grid.py \
        [events/lagos-2024-07-03] [--start YYYY-MM-DD] [--end YYYY-MM-DD] \
        [--refresh] [--update]

--update (Task 47, the daily cloud run): read the committed
events/rain_history_grid_daily.json, fetch only from its last day minus 7
days to now (to catch NASA's late-arriving data), and merge: new values
replace old ones on overlapping days, every earlier day stays
byte-identical. Works without pipeline/cache/imerg_history/ present, and
leaves the catalog files alone (they are full-rescan artifacts).

Auth: reuses the .env credential loader through pipeline/imerg_history
(get_token); credentials and tokens are never printed, logged or
written anywhere.
"""

from __future__ import annotations

import json
import math
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import requests

import imerg
import imerg_history as hist

NE_COASTLINE_URL = (
    "https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/"
    "geojson/ne_10m_coastline.geojson"
)
NE_CACHE = imerg.PIPELINE_DIR / "cache" / "natural_earth" / "ne_10m_coastline.geojson"
OCEAN_LON_WINDOW = 0.15
CELL_HALF = 0.05
TOP_N = 25
BIGGEST_CHANGES = 10
EVENT_CHECK_DATES = ("2024-07-02", "2024-07-03", "2011-07-10")
UPDATE_BACKTRACK_DAYS = 7  # --update fetches from the last committed day minus this

# Small hand list of Lagos districts (name, lon, lat) for approximate
# cell labels; nearest entry wins.
DISTRICTS = [
    ("Badagry", 2.88, 6.42),
    ("Seme border", 2.72, 6.40),
    ("Ijanikin", 3.18, 6.48),
    ("Ojo", 3.20, 6.47),
    ("Festac Town", 3.27, 6.47),
    ("Mile 2 / Amuwo Odofin", 3.31, 6.46),
    ("Apapa", 3.36, 6.45),
    ("Lagos Island", 3.40, 6.45),
    ("Victoria Island", 3.42, 6.43),
    ("Ikoyi", 3.44, 6.46),
    ("Lekki Phase 1", 3.47, 6.44),
    ("Ajah", 3.56, 6.45),
    ("Sangotedo", 3.66, 6.47),
    ("Ibeju", 3.86, 6.47),
    ("Lekki Free Zone", 4.10, 6.42),
    ("Epe", 4.16, 6.58),
    ("Ikorodu", 3.52, 6.62),
    ("Imota", 3.80, 6.65),
    ("Agbowa-Ikosi", 3.92, 6.71),
    ("Kosofe", 3.40, 6.57),
    ("Maryland", 3.37, 6.57),
    ("Surulere", 3.35, 6.50),
    ("Yaba", 3.38, 6.51),
    ("Mushin", 3.35, 6.53),
    ("Oshodi", 3.34, 6.53),
    ("Ikeja", 3.35, 6.60),
    ("Ojodu Berger", 3.36, 6.64),
    ("Agege", 3.32, 6.63),
    ("Alimosho / Ipaja", 3.27, 6.60),
    ("Igando", 3.26, 6.56),
    ("Mowe / Ibafo", 3.42, 6.71),
    ("Ota", 3.68, 6.70),
]


def cell_id(lat: float, lon: float) -> str:
    return f"c{lat:.2f}N{lon:.2f}E"


def cell_centres(bbox: list[float]) -> list[tuple[float, float]]:
    """IMERG 0.1 deg cell centres (x.x5, odd multiples of 0.05) in the bbox."""
    lon_min, lat_min, lon_max, lat_max = bbox

    def centres(lo: float, hi: float) -> list[float]:
        k_min = math.ceil(round((lo - 0.05) / 0.1, 6))
        k_max = math.floor(round((hi - 0.05) / 0.1, 6))
        return [round(0.1 * k + 0.05, 2) for k in range(k_min, k_max + 1)]

    return [(lon, lat) for lat in centres(lat_min, lat_max) for lon in centres(lon_min, lon_max)]


def ensure_coastline() -> Path | None:
    """Local copy of the Natural Earth 10m coastline (downloaded once)."""
    if NE_CACHE.is_file():
        return NE_CACHE
    try:
        NE_CACHE.parent.mkdir(parents=True, exist_ok=True)
        response = requests.get(NE_COASTLINE_URL, timeout=300)
        response.raise_for_status()
        NE_CACHE.write_text(response.text, encoding="utf-8")
        return NE_CACHE
    except Exception as exc:
        print(
            f"warning: Natural Earth coastline unavailable ({exc}); "
            "keeping all cells",
            file=sys.stderr,
        )
        return None


def shoreline_vertices(path: Path, lon_min: float, lon_max: float) -> list[tuple[float, float]]:
    geo = json.loads(path.read_text(encoding="utf-8"))
    vertices: list[tuple[float, float]] = []
    for feature in geo.get("features", []):
        geometry = feature.get("geometry") or {}
        if geometry.get("type") == "LineString":
            parts = [geometry["coordinates"]]
        elif geometry.get("type") == "MultiLineString":
            parts = geometry["coordinates"]
        else:
            continue
        for part in parts:
            for lon, lat in part:
                if lon_min - 0.5 <= lon <= lon_max + 0.5 and 5.5 < lat < 7.5:
                    vertices.append((float(lon), float(lat)))
    return vertices


def entirely_ocean_cells(
    centres: list[tuple[float, float]], vertices: list[tuple[float, float]]
) -> list[tuple[float, float]]:
    """Cells with no land: their top edge lies south of the outer shoreline.

    The outer Gulf of Guinea shoreline is the SOUTHERNMOST coastline
    chain at each longitude; lagoon and harbour vertices sit further
    north and must not turn coastal cells into ocean (lagoon shore is
    kept by definition anyway).
    """
    dropped = []
    for lon, lat in centres:
        near = [vlat for vlon, vlat in vertices if abs(vlon - lon) <= OCEAN_LON_WINDOW]
        if not near:
            continue
        shore_lat = min(near)
        if lat + CELL_HALF < shore_lat:
            dropped.append((lon, lat))
    return dropped


def nearest_place(lon: float, lat: float) -> str:
    return min(
        DISTRICTS,
        key=lambda entry: (entry[1] - lon) ** 2 + (entry[2] - lat) ** 2,
    )[0]


def point_cell_names(event_dir: Path) -> dict[tuple[float, float], str]:
    """Map Task 06 point cells to their cache names (reuse, don't refetch)."""
    saved_path = event_dir / "rainfall_imerg.json"
    if not saved_path.is_file():
        return {}
    saved = json.loads(saved_path.read_text(encoding="utf-8")).get("points", {})
    mapping: dict[tuple[float, float], str] = {}
    for name, entry in saved.items():
        if entry.get("cell_lon") and entry.get("cell_lat"):
            mapping[(float(entry["cell_lon"]), float(entry["cell_lat"]))] = name
    return mapping


def last_committed_day(grid: dict) -> date | None:
    """Last date in grid['dates'] with a value for at least one cell.

    The same definition as score_forecasts.py's imerg_last_day and
    run_daily.py's imerg_state, so all three agree on where the history ends.
    """
    for index in range(len(grid["dates"]) - 1, -1, -1):
        if any(cell["total_mm"][index] is not None for cell in grid["series"].values()):
            return date.fromisoformat(grid["dates"][index])
    return None


def merge_grid_history(old: dict, new_dates: list[str], new_series: dict) -> dict:
    """Merge a freshly fetched window into the committed grid history.

    A pure function (Task 47): it reads only its arguments, mutates nothing
    and returns a new payload.

    - on days the refresh fetched, a new value replaces the committed one
      (the Final run supersedes the Late run as NASA publishes it);
    - where the refresh has no value for a day, the committed value stays,
      so a partial API response never erases history;
    - days before the window are untouched, byte-identical;
    - days after the last committed one are appended, in date order.
    """
    old_dates = list(old["dates"])
    merged_dates = sorted(set(old_dates) | set(new_dates))
    old_index = {day: i for i, day in enumerate(old_dates)}
    new_index = {day: i for i, day in enumerate(new_dates)}
    series = {}
    for cell_id, old_cell in old["series"].items():
        new_cell = new_series.get(cell_id)
        totals: list[float | None] = []
        peaks: list[float | None] = []
        for day in merged_dates:
            oi = old_index.get(day)
            ni = new_index.get(day) if new_cell is not None else None
            old_total = old_cell["total_mm"][oi] if oi is not None else None
            old_peak = old_cell["max_30min_mm_h"][oi] if oi is not None else None
            new_total = new_cell["total_mm"][ni] if ni is not None else None
            new_peak = new_cell["max_30min_mm_h"][ni] if ni is not None else None
            totals.append(new_total if new_total is not None else old_total)
            peaks.append(new_peak if new_peak is not None else old_peak)
        series[cell_id] = {"total_mm": totals, "max_30min_mm_h": peaks}
    return {"meta": old["meta"], "dates": merged_dates, "series": series}


def run_update(event_dir: Path, end: datetime, refresh: bool) -> str:
    """Incremental refresh of the committed rain history (--update, Task 47).

    Fetches only (the committed history's last day - 7 days) .. end, to catch
    NASA's late-arriving data, and merges the fresh window into
    events/rain_history_grid_daily.json: new values replace old ones on
    overlapping days, every earlier day stays byte-identical. Needs no cache
    directory and no coastline file: the cells come from the committed file's
    meta. The catalog files are full-rescan artifacts and are left alone; the
    scorer and the forecast read only the daily grid.
    """
    out_dir = event_dir.parent
    grid_path = out_dir / "rain_history_grid_daily.json"
    if not grid_path.is_file():
        raise SystemExit(
            f"missing {grid_path}: --update refreshes a committed history; "
            "run the full scan (without --update) first"
        )
    committed = json.loads(grid_path.read_text(encoding="utf-8"))
    last_day = last_committed_day(committed)
    if last_day is None:
        raise SystemExit(f"{grid_path} has no values; run the full scan first")
    tz = ZoneInfo(
        json.loads((event_dir / "event.json").read_text(encoding="utf-8"))["timezone"]
    )
    start = datetime(
        last_day.year, last_day.month, last_day.day, tzinfo=timezone.utc
    ) - timedelta(days=UPDATE_BACKTRACK_DAYS)

    hist.CACHE_DIR.mkdir(parents=True, exist_ok=True)
    token = hist.get_token()
    cells = committed["meta"]["cells"]
    print(
        f"incremental IMERG refresh {start:%Y-%m-%d} .. {end:%Y-%m-%d} UTC "
        f"({last_day.isoformat()} - {UPDATE_BACKTRACK_DAYS} days .. now), "
        f"{len(cells)} cells",
        flush=True,
    )
    new_stats: dict[str, dict[date, list[float]]] = {}
    final_ends: list[datetime] = []
    n_late_rows = 0
    for index, cell in enumerate(cells):
        lon, lat = float(cell["lon"]), float(cell["lat"])
        cache_name = cell.get("point") or cell["id"]  # point cells reuse Task 06 caches
        f_header, f_rows, l_header, l_rows = hist.fetch_point_record(
            cache_name, lat, lon, start, end, token, refresh
        )
        combined: dict[datetime, float] = {}
        for stamp, rate in f_rows:
            combined[stamp] = rate
        for stamp, rate in l_rows:
            combined.setdefault(stamp, rate)
        new_stats[cell["id"]] = hist.daily_stats(combined, tz)
        if f_rows:
            final_ends.append(max(stamp for stamp, _ in f_rows))
        n_late_rows += len(l_rows)
        print(
            f"  [{index + 1}/{len(cells)}] {cell['id']} "
            f"({cell.get('place', nearest_place(lon, lat))}): "
            f"{len(combined)} steps",
            file=sys.stderr,
            flush=True,
        )
    new_days = sorted({day for stats in new_stats.values() for day in stats})
    if not new_days:
        raise SystemExit("no IMERG data returned for any cell in the update window")
    new_dates = [day.isoformat() for day in new_days]
    new_series = {
        cid: {
            "total_mm": [
                imerg.clean(stats[day][0]) if day in stats else None for day in new_days
            ],
            "max_30min_mm_h": [
                imerg.clean(stats[day][1]) if day in stats else None for day in new_days
            ],
        }
        for cid, stats in new_stats.items()
    }

    merged = merge_grid_history(committed, new_dates, new_series)
    final_end = min(final_ends) if final_ends else None
    run_meta = {
        "final": {
            "variable": hist.VARIABLE_FINAL,
            "period": [hist.iso_z(start), hist.iso_z(final_end) if final_end else None],
        },
        "late": None,
    }
    if n_late_rows and final_end:
        run_meta["late"] = {
            "variable": hist.VARIABLE_LATE,
            "period": [hist.iso_z(final_end + timedelta(minutes=30)), hist.iso_z(end)],
        }
    old_retrieved_at = merged["meta"].get("retrieved_at")
    merged["meta"] = dict(merged["meta"])
    merged["meta"]["product"] = (
        ["GPM_3IMERGHH.07", "GPM_3IMERGHHL.07"] if n_late_rows else ["GPM_3IMERGHH.07"]
    )
    merged["meta"]["run"] = run_meta
    merged["meta"]["retrieved_at"] = imerg.utc_now_iso()
    merged["meta"]["update"] = {
        "mode": "incremental (--update)",
        "fetched": [hist.iso_z(start), hist.iso_z(end)],
        "previous_retrieved_at": old_retrieved_at,
        "note": (
            f"only {start:%Y-%m-%d} .. now was fetched; days before that are "
            "unchanged from the previous scan"
        ),
    }
    imerg.write_json(grid_path, merged)

    lines = [
        "FloodTrace IMERG incremental refresh",
        f"window fetched: {start:%Y-%m-%d} .. {end:%Y-%m-%d} UTC over {len(cells)} cells",
        f"history now covers: {merged['dates'][0]} .. {merged['dates'][-1]} "
        f"({len(merged['dates'])} days)",
        "runs: final through "
        + (f"{final_end.date()}" if final_end else "n/a")
        + (f", late tail {n_late_rows} cell-steps" if n_late_rows else ", no late tail"),
        f"wrote {grid_path} (merged; earlier days byte-identical)",
    ]
    summary = "\n".join(lines)
    print(summary)
    return summary


def summary_of(candidate: dict, kind: str) -> dict:
    payload = {
        "rank": candidate["rank"],
        "start": candidate["start"],
        "end": candidate["end"],
    }
    if kind == "grid":
        payload.update(
            {
                "max_cell": candidate["max_cell"],
                "max_cell_total_mm": candidate["max_cell_total_mm"],
                "max_peak_mm_h": candidate["max_peak_mm_h"],
                "cells_over_threshold": candidate["cells_over_threshold"],
                "known_event_id": candidate["known_event_id"],
            }
        )
    else:
        payload.update(
            {
                "max_point": candidate["max_point"],
                "max_point_total_mm": candidate["max_point_total_mm"],
                "max_peak_mm_h": candidate["max_peak_mm_h"],
            }
        )
    return payload


def run(event_dir: Path, start: datetime, end: datetime, refresh: bool) -> str:
    event_path = event_dir / "event.json"
    if not event_path.is_file():
        raise SystemExit(f"missing {event_path}")
    event = json.loads(event_path.read_text(encoding="utf-8"))
    tz = ZoneInfo(event["timezone"])
    out_dir = event_dir.parent
    bbox = [float(value) for value in event["aoi"]["bbox"]]

    centres = cell_centres(bbox)
    coast = ensure_coastline()
    dropped: list[tuple[float, float]] = []
    if coast is not None:
        dropped = entirely_ocean_cells(
            centres, shoreline_vertices(coast, bbox[0], bbox[2])
        )
    dropped_set = set(dropped)
    cells = [(lon, lat) for lon, lat in centres if (lon, lat) not in dropped_set]
    point_cells = point_cell_names(event_dir)

    hist.CACHE_DIR.mkdir(parents=True, exist_ok=True)
    token = hist.get_token()
    cell_stats: dict[tuple[float, float], dict[date, list[float]]] = {}
    final_ends: list[datetime] = []
    n_late_rows = 0
    reused = 0
    for index, (lon, lat) in enumerate(cells):
        cache_name = point_cells.get((lon, lat)) or cell_id(lat, lon)
        f_header, f_rows, l_header, l_rows = hist.fetch_point_record(
            cache_name, lat, lon, start, end, token, refresh
        )
        combined: dict[datetime, float] = {}
        for stamp, rate in f_rows:
            combined[stamp] = rate
        for stamp, rate in l_rows:
            combined.setdefault(stamp, rate)
        cell_stats[(lon, lat)] = hist.daily_stats(combined, tz)
        if f_rows:
            final_ends.append(max(stamp for stamp, _ in f_rows))
        n_late_rows += len(l_rows)
        if cache_name in point_cells.values():
            reused += 1
        print(
            f"  [{index + 1}/{len(cells)}] {cell_id(lat, lon)} "
            f"({nearest_place(lon, lat)}): {len(combined)} steps",
            file=sys.stderr,
            flush=True,
        )
    if not any(stats for stats in cell_stats.values()):
        raise SystemExit("no IMERG data returned for any cell")

    all_days = sorted({day for stats in cell_stats.values() for day in stats})
    final_end = min(final_ends) if final_ends else None
    run_meta = {
        "final": {
            "variable": hist.VARIABLE_FINAL,
            "period": [hist.iso_z(start), hist.iso_z(final_end) if final_end else None],
        },
        "late": None,
    }
    if n_late_rows and final_end:
        run_meta["late"] = {
            "variable": hist.VARIABLE_LATE,
            "period": [hist.iso_z(final_end + timedelta(minutes=30)), hist.iso_z(end)],
        }

    cell_meta = [
        {
            "id": cell_id(lat, lon),
            "lon": lon,
            "lat": lat,
            "place": nearest_place(lon, lat),
            "point": point_cells.get((lon, lat)),
        }
        for lon, lat in cells
    ]
    ocean_filter = {
        "source": "Natural Earth 10m coastline (ne_10m_coastline.geojson, cached under pipeline/cache/natural_earth)"
        if coast is not None
        else "unavailable",
        "rule": (
            "a cell is entirely Atlantic Ocean when its top edge (centre + 0.05) "
            "lies south of the southernmost (outer) coastline vertex within "
            "+/-0.15 deg of longitude; lagoon/harbour vertices are north of the "
            "outer shore and do not count as ocean"
        ),
        "cells_dropped": [
            {"lon": lon, "lat": lat} for lon, lat in dropped
        ],
    }
    grid_daily_payload = {
        "meta": {
            "method": (
                "grid rescan over every IMERG 0.1 deg cell centre in the event "
                "AOI bbox; GES DISC Giovanni in the Cloud Time Series Service, "
                "one request per cell per chunk, cached under "
                "pipeline/cache/imerg_history (Task 06 caches reused for the "
                "four point cells)"
            ),
            "product": ["GPM_3IMERGHH.07", "GPM_3IMERGHHL.07"]
            if n_late_rows
            else ["GPM_3IMERGHH.07"],
            "version": "07",
            "run": run_meta,
            "variable": "/Grid/precipitation",
            "units": {"rate": "mm/h", "total": "mm"},
            "urls": {"api": hist.TIMESERIES_URL, "docs": hist.DOCS_URL},
            "retrieved_at": imerg.utc_now_iso(),
            "licence": hist.LICENCE,
            "grid_resolution": "0.1 degree (~10 km)",
            "note": hist.GRID_NOTE,
            "timezone": "daily totals are WAT calendar days (Africa/Lagos)",
            "aoi_bbox": bbox,
            "ocean_filter": ocean_filter,
            "cells": cell_meta,
            "places_note": "approximate labels from a small hand list of Lagos districts",
        },
        "dates": [day.isoformat() for day in all_days],
        "series": {
            cell_id(lat, lon): {
                "total_mm": [
                    imerg.clean(stats[day][0]) if day in stats else None
                    for day in all_days
                ],
                "max_30min_mm_h": [
                    imerg.clean(stats[day][1]) if day in stats else None
                    for day in all_days
                ],
            }
            for (lon, lat), stats in cell_stats.items()
        },
    }
    imerg.write_json(out_dir / "rain_history_grid_daily.json", grid_daily_payload)

    # Candidates: any cell over threshold on any day; merge consecutive days.
    total_threshold = hist.DAILY_TOTAL_THRESHOLD_MM
    peak_threshold = hist.INTENSITY_THRESHOLD_MM_H
    qualifying: list[date] = []
    for day in all_days:
        for stats in cell_stats.values():
            entry = stats.get(day)
            if entry and (
                entry[0] >= total_threshold or entry[1] >= peak_threshold
            ):
                qualifying.append(day)
                break
    groups: list[list[date]] = []
    for day in qualifying:
        if groups and day - groups[-1][-1] == timedelta(days=1):
            groups[-1].append(day)
        else:
            groups.append([day])

    candidates = []
    for group in groups:
        start_day, end_day = group[0], group[-1]
        cells_payload: dict[str, dict[str, float | None]] = {}
        extent = 0
        max_total, max_cell, max_peak = None, None, None
        for (lon, lat), stats in cell_stats.items():
            totals: list[float] = []
            peaks: list[float] = []
            over = False
            for day in group:
                entry = stats.get(day)
                if not entry:
                    continue
                totals.append(entry[0])
                peaks.append(entry[1])
                if entry[0] >= total_threshold or entry[1] >= peak_threshold:
                    over = True
            cells_payload[cell_id(lat, lon)] = {
                "total_mm": imerg.clean(sum(totals)) if totals else None,
                "max_30min_mm_h": imerg.clean(max(peaks)) if peaks else None,
            }
            group_total = sum(totals) if totals else None
            if group_total is not None and (max_total is None or group_total > max_total):
                max_total, max_cell = group_total, (lon, lat)
            group_peak = max(peaks) if peaks else None
            if group_peak is not None and (max_peak is None or group_peak > max_peak):
                max_peak = group_peak
            if over:
                extent += 1
        antecedent_values = []
        for day in (start_day - timedelta(days=offset) for offset in range(7, 0, -1)):
            spatial = [
                stats[day][0] for stats in cell_stats.values() if day in stats
            ]
            if spatial:
                antecedent_values.append(sum(spatial) / len(spatial))
        candidates.append(
            {
                "start": start_day.isoformat(),
                "end": end_day.isoformat(),
                "days": [day.isoformat() for day in group],
                "cells": cells_payload,
                "max_cell": {
                    "id": cell_id(max_cell[1], max_cell[0]),
                    "lon": max_cell[0],
                    "lat": max_cell[1],
                    "place": nearest_place(max_cell[0], max_cell[1]),
                },
                "max_cell_total_mm": imerg.clean(max_total),
                "max_peak_mm_h": imerg.clean(max_peak),
                "cells_over_threshold": extent,
                "antecedent_7d_mean_daily_mm": imerg.clean(
                    sum(antecedent_values) / len(antecedent_values)
                )
                if antecedent_values
                else None,
                "known_event_id": hist.find_known_event(out_dir, start_day, end_day),
            }
        )
    candidates.sort(
        key=lambda c: (
            -(c["max_cell_total_mm"] or 0.0),
            -(c["max_peak_mm_h"] or 0.0),
            c["start"],
        )
    )
    for rank, candidate in enumerate(candidates, start=1):
        candidate["rank"] = rank

    catalog_payload = {
        "meta": {
            "method": grid_daily_payload["meta"]["method"],
            "product": grid_daily_payload["meta"]["product"],
            "version": "07",
            "run": run_meta,
            "urls": {"api": hist.TIMESERIES_URL, "docs": hist.DOCS_URL},
            "retrieved_at": imerg.utc_now_iso(),
            "licence": hist.LICENCE,
            "note": hist.GRID_NOTE,
            "thresholds": {
                "daily_total_mm": total_threshold,
                "max_30min_mm_h": peak_threshold,
            },
            "notes": [
                "a day qualifies if any cell daily total >= 50 mm or any "
                "30-min intensity >= 30 mm/h; consecutive qualifying days merge",
                "severity = max cell total over the candidate; rank 1 is most severe",
                "cells_over_threshold counts cells qualifying on at least one "
                "candidate day (spatial extent proxy)",
                "antecedent_7d_mean_daily_mm: mean over the 7 days before the "
                "start of the across-cell mean daily total",
            ],
            "ocean_filter": ocean_filter,
            "cells": cell_meta,
        },
        "candidates": candidates,
    }
    imerg.write_json(out_dir / "catalog_candidates_grid.json", catalog_payload)

    # Compare with the Task 06 point scan (catalog_candidates.json stays as is).
    point_candidates = json.loads(
        (out_dir / "catalog_candidates.json").read_text(encoding="utf-8")
    )["candidates"]
    grid_used: set[int] = set()
    rank_changes = []
    only_point = []
    for point_candidate in point_candidates:
        matches = [
            grid_candidate
            for grid_candidate in candidates
            if not (
                grid_candidate["end"] < point_candidate["start"]
                or point_candidate["end"] < grid_candidate["start"]
            )
        ]
        if not matches:
            only_point.append(summary_of(point_candidate, "point"))
            continue
        for grid_candidate in matches:
            grid_used.add(grid_candidate["rank"])
        rank_changes.append(
            {
                "point_start": point_candidate["start"],
                "point_end": point_candidate["end"],
                "point_rank": point_candidate["rank"],
                "grid_start": matches[0]["start"],
                "grid_end": matches[0]["end"],
                "grid_rank": matches[0]["rank"],
                "change": matches[0]["rank"] - point_candidate["rank"],
            }
        )
    only_grid = [
        summary_of(grid_candidate, "grid")
        for grid_candidate in candidates
        if grid_candidate["rank"] not in grid_used
    ]
    compare_payload = {
        "meta": {
            "point_scan": "events/catalog_candidates.json (4 AOI points, Task 06)",
            "grid_scan": "events/catalog_candidates_grid.json (every AOI cell)",
            "matching": (
                "candidates correspond when their [start, end] spans overlap; "
                "point-scan qualifying days are a subset of grid-scan days, so "
                "each point candidate maps into exactly one (possibly longer) "
                "grid candidate"
            ),
            "counts": {
                "point_candidates": len(point_candidates),
                "grid_candidates": len(candidates),
                "matched": len(rank_changes),
                "only_grid": len(only_grid),
                "only_point": len(only_point),
            },
            "retrieved_at": imerg.utc_now_iso(),
        },
        "only_grid": only_grid,
        "only_point": only_point,
        "rank_changes": rank_changes,
    }
    imerg.write_json(out_dir / "catalog_scan_compare.json", compare_payload)

    def candidate_for(candidates_: list[dict], days: tuple[str, ...]) -> dict | None:
        for candidate in candidates_:
            if any(candidate["start"] <= day <= candidate["end"] for day in days):
                return candidate
        return None

    lines = [
        "FloodTrace IMERG grid rescan",
        f"aoi bbox: {bbox}",
        f"cells scanned: {len(cells)} of {len(centres)} centres in bbox "
        f"({len(dropped)} dropped as entirely Atlantic Ocean, {reused} Task 06 "
        "point cells reused from cache)",
        f"period covered: {all_days[0]} .. {all_days[-1]} ({len(all_days)} days with data)",
        "runs: final through "
        + (f"{final_end.date()}" if final_end else "n/a")
        + (f", late tail {n_late_rows} cell-steps" if n_late_rows else ", no late tail"),
        f"candidates: {len(candidates)} "
        f"(point scan had {len(point_candidates)}; grid-only {len(only_grid)}, "
        f"point-only {len(only_point)})",
        f"top {TOP_N} by severity:",
    ]
    for candidate in candidates[:TOP_N]:
        lines.append(
            f"  {candidate['rank']:>3}. {candidate['start']}..{candidate['end']}  "
            f"{candidate['max_cell']['id']} ({candidate['max_cell']['place']}) "
            f"{candidate['max_cell_total_mm']} mm, peak {candidate['max_peak_mm_h']} "
            f"mm/h, {candidate['cells_over_threshold']} cells over threshold"
            + (
                f", known: {candidate['known_event_id']}"
                if candidate["known_event_id"]
                else ""
            )
        )
    for label, days in (
        ("2024-07-02/03", ("2024-07-02", "2024-07-03")),
        ("2011-07-10", ("2011-07-10",)),
    ):
        target = candidate_for(candidates, days)
        point_target = candidate_for(point_candidates, days)
        if target:
            lines.append(
                f"{label}: grid rank {target['rank']} "
                f"({target['start']}..{target['end']}, "
                f"{target['max_cell']['place']} {target['max_cell_total_mm']} mm, "
                f"{target['cells_over_threshold']} cells over threshold)"
                + (
                    f", known: {target['known_event_id']}"
                    if target["known_event_id"]
                    else ""
                )
            )
            if point_target:
                lines.append(f"  point scan had it at rank {point_target['rank']}")
            else:
                lines.append("  not a candidate in the point scan")
        else:
            lines.append(f"{label}: no candidate in the grid scan")
    biggest = sorted(
        rank_changes, key=lambda entry: -abs(entry["change"])
    )[:BIGGEST_CHANGES]
    lines.append(f"{BIGGEST_CHANGES} biggest rank changes (grid_rank - point_rank):")
    for entry in biggest:
        lines.append(
            f"  {entry['point_start']}..{entry['point_end']}: "
            f"{entry['point_rank']} -> {entry['grid_rank']} "
            f"({entry['change']:+d})"
        )
    lines.append(
        "wrote rain_history_grid_daily.json, catalog_candidates_grid.json, "
        "catalog_scan_compare.json (in " + str(out_dir) + ")"
    )
    summary = "\n".join(lines)
    print(summary)
    return summary


def main() -> None:
    usage = (
        "usage: pipeline/.venv/bin/python pipeline/imerg_history_grid.py "
        "[event-dir] [--start YYYY-MM-DD] [--end YYYY-MM-DD] [--refresh] "
        "[--update]"
    )
    refresh = "--refresh" in sys.argv
    update = "--update" in sys.argv
    start = hist.RECORD_START
    end = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    positional: list[str] = []
    args = sys.argv[1:]
    index = 0
    while index < len(args):
        arg = args[index]
        if arg == "--start":
            index += 1
            start = datetime.fromisoformat(args[index]).replace(tzinfo=timezone.utc)
        elif arg == "--end":
            index += 1
            end = datetime.fromisoformat(args[index]).replace(tzinfo=timezone.utc)
        elif arg not in ("--refresh", "--update"):
            positional.append(arg)
        index += 1
    if len(positional) > 1 or index != len(args):
        raise SystemExit(usage)
    event_dir = Path(positional[0]) if positional else Path("events/lagos-2024-07-03")
    if update:
        run_update(event_dir, end, refresh)
    else:
        run(event_dir, start, end, refresh)


if __name__ == "__main__":
    main()
