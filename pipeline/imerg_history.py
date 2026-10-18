#!/usr/bin/env python3
"""Scan the GPM IMERG record (2000 → present) at the Lagos AOI points.

Builds the daily rainfall history and the first list of candidate flood
days for the multi-event catalog. Uses the GES DISC "Giovanni in the
Cloud" Time Series Service (the successor of the Hydrology Data Rods
service, retired ~Oct 2025) to pull point time series of IMERG
half-hourly precipitation: one request per point per chunk, Final run
(GPM_3IMERGHH v07) with a Late run (GPM_3IMERGHHL v07) tail for the
months Final does not cover yet.

Outputs:
- events/rain_history_daily.json    per WAT day: total mm + max 30-min
                                    intensity per point
- events/catalog_candidates.json    candidate flood days, merged and
                                    ranked by severity

Usage:
    pipeline/.venv/bin/python pipeline/imerg_history.py \
        [events/lagos-2024-07-03] [--start YYYY-MM-DD] [--end YYYY-MM-DD] \
        [--refresh]

Auth: reuses the .env credential loader from pipeline/imerg.py
(Earthdata_username / Earthdata_password), then creates an Earthdata
bearer token via earthaccess for the timeseries API. Credentials and
tokens are never printed, logged or written anywhere.
"""

from __future__ import annotations

import calendar
import json
import math
import re
import sys
import time
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import earthaccess
import requests

import imerg  # same directory: reuses the .env loader and helpers

TIMESERIES_URL = "https://api.giovanni.earthdata.nasa.gov/timeseries"
VARIABLE_FINAL = "GPM_3IMERGHH_07_precipitation"
VARIABLE_LATE = "GPM_3IMERGHHL_07_precipitation"
DOCS_URL = (
    "https://disc.gsfc.nasa.gov/information/howto?title=Giovanni%20In%20The%20Cloud:"
    "%20Time%20Series%20Service"
)
RECORD_START = datetime(2000, 6, 1, tzinfo=timezone.utc)  # IMERG archive start
CHUNK_YEARS = 2
DAILY_TOTAL_THRESHOLD_MM = 50.0
INTENSITY_THRESHOLD_MM_H = 30.0
RETRIES = 4
RETRY_DELAYS = (10.0, 30.0, 60.0, 120.0)
REQUEST_PAUSE = 1.0
LICENCE = "NASA open data"
GRID_NOTE = "satellite estimate; ~10 km cells smooth point intensities"
CACHE_DIR = imerg.PIPELINE_DIR / "cache" / "imerg_history"
EVENT_CHECK_DATES = ("2024-07-02", "2024-07-03")
KNOWN_EVENT_RE = re.compile(r"(\d{4}-\d{2}-\d{2})")


class FatalError(RuntimeError):
    """Error that retrying will not fix."""


def iso_z(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def get_token() -> str:
    """Earthdata bearer token from the project .env (never printed)."""
    imerg.load_env_credentials()
    earthaccess.login(strategy="environment")
    return earthaccess.get_edl_token()["access_token"]


def request_series(
    lat: float, lon: float, start: datetime, end: datetime, variable: str, token: str
) -> str:
    params = {
        "data": variable,
        "location": f"[{lat},{lon}]",
        "time": f"{start:%Y-%m-%dT%H:%M:%S}/{end:%Y-%m-%dT%H:%M:%S}",
        "version": "07",
    }
    last_error: Exception | None = None
    for attempt in range(RETRIES):
        try:
            response = requests.get(
                TIMESERIES_URL,
                params=params,
                headers={"Authorization": f"Bearer {token}"},
                timeout=300,
            )
            if response.status_code in (401, 403):
                raise FatalError(
                    f"HTTP {response.status_code}: Earthdata token rejected; the "
                    'profile probably needs to authorize "NASA GESDISC DATA '
                    'ARCHIVE" (https://disc.gsfc.nasa.gov/earthdata-login)'
                )
            if response.status_code == 400:
                raise FatalError(f"HTTP 400 for {params['location']}: {response.text[:200]}")
            if response.status_code == 404:
                # The service 404s when the range has no coverage at all
                # (e.g. Final-run chunks past the archive end); empty series.
                return ""
            response.raise_for_status()
            text = response.text
            if not text.strip():
                return ""  # out of coverage for this run; empty series
            if "Timestamp (UTC)" not in text:
                raise FatalError(f"unexpected response (no CSV header): {text[:200]}")
            return text
        except FatalError:
            raise
        except Exception as exc:
            last_error = exc
            time.sleep(RETRY_DELAYS[min(attempt, len(RETRY_DELAYS) - 1)])
    raise RuntimeError(f"timeseries request failed after {RETRIES} attempts: {last_error}")


def parse_stamp(text: str) -> datetime | None:
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(text, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def parse_series(text: str) -> tuple[dict[str, str], list[tuple[datetime, float]]]:
    """Header block + 'Timestamp (UTC),Data' rows -> (header, steps)."""
    header: dict[str, str] = {}
    rows: list[tuple[datetime, float]] = []
    in_data = False
    for line in text.splitlines():
        line = line.strip()
        if not line or "," not in line:
            continue
        key, _, value = line.partition(",")
        key, value = key.strip(), value.strip()
        if not in_data:
            if key.startswith("Timestamp"):
                in_data = True
            else:
                header[key] = value
            continue
        stamp = parse_stamp(key)
        if stamp is None:
            continue
        try:
            rate = float(value)
        except ValueError:
            continue
        if not math.isfinite(rate) or rate < 0:
            continue  # fill value (-9999.9) or missing
        rows.append((stamp, rate))
    return header, rows


def time_chunks(start: datetime, end: datetime, years: int) -> list[tuple[datetime, datetime]]:
    """Year-aligned chunks so cached files stay stable across runs."""
    chunks = []
    current = start
    while current < end:
        boundary = datetime(current.year + years, 1, 1, tzinfo=timezone.utc)
        chunk_end = min(boundary, end)
        if chunk_end <= current:
            chunk_end = end
        chunks.append((current, chunk_end))
        current = chunk_end
    return chunks


def fetch_series(
    name: str,
    lat: float,
    lon: float,
    start: datetime,
    end: datetime,
    variable: str,
    token: str,
    refresh: bool,
) -> tuple[dict[str, str], list[tuple[datetime, float]]]:
    cache_path = CACHE_DIR / (
        f"{name}_{variable}_{lat:.3f}x{lon:.3f}"
        f"_{start:%Y%m%dT%H%M%S}_{end:%Y%m%dT%H%M%S}.csv"
    )
    text = None
    if cache_path.is_file() and not refresh:
        text = cache_path.read_text(encoding="utf-8")
    if text is None:
        time.sleep(REQUEST_PAUSE)  # be polite to NASA services
        text = request_series(lat, lon, start, end, variable, token)
        cache_path.write_text(text, encoding="utf-8")
    return parse_series(text)


def fetch_point_record(
    name: str, lat: float, lon: float, start: datetime, end: datetime, token: str, refresh: bool
) -> tuple[dict[str, str], list[tuple[datetime, float]], dict[str, str], list[tuple[datetime, float]]]:
    """Final-run chunks over [start, end] + a Late-run tail if needed."""
    final_header: dict[str, str] = {}
    final_rows: list[tuple[datetime, float]] = []
    for chunk_start, chunk_end in time_chunks(start, end, CHUNK_YEARS):
        header, rows = fetch_series(
            name, lat, lon, chunk_start, chunk_end, VARIABLE_FINAL, token, refresh
        )
        final_header = final_header or header
        final_rows.extend(rows)
    late_header: dict[str, str] = {}
    late_rows: list[tuple[datetime, float]] = []
    if final_rows:
        last_final = max(stamp for stamp, _ in final_rows)
        if last_final < end - timedelta(minutes=30):
            late_start = last_final + timedelta(minutes=30)
            late_header, late_rows = fetch_series(
                name, lat, lon, late_start, end, VARIABLE_LATE, token, refresh
            )
    return final_header, final_rows, late_header, late_rows


def daily_stats(series: dict[datetime, float], tz: ZoneInfo) -> dict[date, list[float]]:
    """WAT calendar day -> [total mm, max 30-min mm/h, valid steps]."""
    days: dict[date, list[float]] = {}
    for stamp, rate in series.items():
        day = stamp.astimezone(tz).date()
        entry = days.setdefault(day, [0.0, 0.0, 0])
        entry[0] += rate * 0.5
        entry[1] = max(entry[1], rate)
        entry[2] += 1
    return days


def find_known_event(out_dir: Path, start: date, end: date) -> str | None:
    for entry in sorted(out_dir.iterdir()):
        if not entry.is_dir():
            continue
        match = KNOWN_EVENT_RE.search(entry.name)
        if match and start <= date.fromisoformat(match.group(1)) <= end:
            return entry.name
    return None


def run(event_dir: Path, start: datetime, end: datetime, refresh: bool) -> str:
    event_path = event_dir / "event.json"
    if not event_path.is_file():
        raise SystemExit(f"missing {event_path}")
    event = json.loads(event_path.read_text(encoding="utf-8"))
    tz = ZoneInfo(event["timezone"])
    out_dir = event_dir.parent
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    points = {
        name: (float(coords[0]), float(coords[1]))  # lon, lat
        for name, coords in event["aoi"]["points"].items()
        if name != "offshore_tide"
    }
    # Pin each query to the same IMERG cell the event package uses
    # (pipeline/imerg.py output) so the catalog and event files agree;
    # points exactly on a cell boundary (lagos_island is) snap
    # differently between services otherwise.
    query_cells: dict[str, tuple[float, float]] = {}
    saved_path = event_dir / "rainfall_imerg.json"
    if saved_path.is_file():
        saved_points = json.loads(saved_path.read_text(encoding="utf-8")).get(
            "points", {}
        )
        for name, (plon, plat) in points.items():
            saved = saved_points.get(name) or {}
            if saved.get("cell_lon") and saved.get("cell_lat"):
                query_cells[name] = (
                    float(saved["cell_lon"]),
                    float(saved["cell_lat"]),
                )

    token = get_token()
    series_by_point: dict[str, dict[datetime, float]] = {}
    cells: dict[str, dict[str, float]] = {}
    dois: set[str] = set()
    prod_names: set[str] = set()
    final_ends: list[datetime] = []
    n_late_rows = 0
    for name, (plon, plat) in points.items():
        qlon, qlat = query_cells.get(name, (plon, plat))
        f_header, f_rows, l_header, l_rows = fetch_point_record(
            name, qlat, qlon, start, end, token, refresh
        )
        combined: dict[datetime, float] = {}
        for stamp, rate in f_rows:
            combined[stamp] = rate
        for stamp, rate in l_rows:
            combined.setdefault(stamp, rate)
        series_by_point[name] = combined
        for header in (f_header, l_header):
            if header.get("lat") and header.get("lon"):
                cells[name] = {
                    "lat": float(header["lat"]),
                    "lon": float(header["lon"]),
                }
            if header.get("doi"):
                dois.add(header["doi"])
            if header.get("prod_name"):
                prod_names.add(header["prod_name"])
        if f_rows:
            final_ends.append(max(stamp for stamp, _ in f_rows))
        n_late_rows += len(l_rows)
        print(f"  {name}: {len(combined)} half-hour steps", file=sys.stderr)
    if not series_by_point or not any(series_by_point.values()):
        raise SystemExit("no IMERG data returned for any point")

    day_stats = {name: daily_stats(series, tz) for name, series in series_by_point.items()}
    all_days = sorted({day for stats in day_stats.values() for day in stats})

    final_end = min(final_ends) if final_ends else None
    data_end = max(
        stamp for series in series_by_point.values() for stamp in series
    ).astimezone(tz).date()
    run_meta = {
        "final": {
            "variable": VARIABLE_FINAL,
            "period": [iso_z(start), iso_z(final_end) if final_end else None],
        },
        "late": None,
    }
    if n_late_rows and final_end:
        run_meta["late"] = {
            "variable": VARIABLE_LATE,
            "period": [iso_z(final_end + timedelta(minutes=30)), iso_z(end)],
        }

    daily_payload = {
        "meta": {
            "method": (
                "GES DISC Giovanni in the Cloud Time Series Service (successor of "
                "the retired Hydrology Data Rods service); point time series, one "
                "request per point per chunk, cached under pipeline/cache/imerg_history"
            ),
            "product": sorted(prod_names),
            "version": "07",
            "run": run_meta,
            "variable": "/Grid/precipitation",
            "units": {"rate": "mm/h", "total": "mm"},
            "doi": sorted(dois),
            "urls": {"api": TIMESERIES_URL, "docs": DOCS_URL},
            "retrieved_at": imerg.utc_now_iso(),
            "licence": LICENCE,
            "grid_resolution": "0.1 degree (~10 km)",
            "note": GRID_NOTE,
            "timezone": "daily totals are WAT calendar days (Africa/Lagos)",
            "points": {
                name: {
                    "lon": plon,
                    "lat": plat,
                    "query_lon": query_cells.get(name, (plon, plat))[0],
                    "query_lat": query_cells.get(name, (plon, plat))[1],
                    "cell_lon": cells.get(name, {}).get("lon"),
                    "cell_lat": cells.get(name, {}).get("lat"),
                }
                for name, (plon, plat) in points.items()
            },
        },
        "dates": [day.isoformat() for day in all_days],
        "points": {
            name: {
                "total_mm": [
                    imerg.clean(stats[day][0]) if day in stats else None
                    for day in all_days
                ],
                "max_30min_mm_h": [
                    imerg.clean(stats[day][1]) if day in stats else None
                    for day in all_days
                ],
            }
            for name, stats in day_stats.items()
        },
    }
    imerg.write_json(out_dir / "rain_history_daily.json", daily_payload)

    def day_values(day: date) -> dict[str, tuple[float | None, float | None]]:
        values = {}
        for name, stats in day_stats.items():
            entry = stats.get(day)
            values[name] = (entry[0] if entry else None, entry[1] if entry else None)
        return values

    # Candidate days: any point total >= DAILY_TOTAL_THRESHOLD_MM or any
    # 30-min peak >= INTENSITY_THRESHOLD_MM_H; merge consecutive days.
    qualifying: list[date] = []
    for day in all_days:
        values = day_values(day)
        if any(
            (total is not None and total >= DAILY_TOTAL_THRESHOLD_MM)
            or (peak is not None and peak >= INTENSITY_THRESHOLD_MM_H)
            for total, peak in values.values()
        ):
            qualifying.append(day)
    groups: list[list[date]] = []
    for day in qualifying:
        if groups and day - groups[-1][-1] == timedelta(days=1):
            groups[-1].append(day)
        else:
            groups.append([day])

    candidates = []
    for group in groups:
        start_day, end_day = group[0], group[-1]
        per_point: dict[str, dict[str, float | None]] = {}
        max_total, max_point, max_peak = None, None, None
        for name in points:
            totals = [day_stats[name][d][0] for d in group if d in day_stats[name]]
            peaks = [day_stats[name][d][1] for d in group if d in day_stats[name]]
            per_point[name] = {
                "total_mm": imerg.clean(sum(totals)) if totals else None,
                "max_30min_mm_h": imerg.clean(max(peaks)) if peaks else None,
            }
            if totals and (max_total is None or sum(totals) > max_total):
                max_total, max_point = sum(totals), name
            if peaks and (max_peak is None or max(peaks) > max_peak):
                max_peak = max(peaks)
        antecedent_days = [
            start_day - timedelta(days=offset) for offset in range(7, 0, -1)
        ]
        antecedent_values = []
        for day in antecedent_days:
            spatial = [
                day_stats[name][day][0]
                for name in points
                if day in day_stats.get(name, {})
            ]
            if spatial:
                antecedent_values.append(sum(spatial) / len(spatial))
        candidates.append(
            {
                "start": start_day.isoformat(),
                "end": end_day.isoformat(),
                "days": [d.isoformat() for d in group],
                "points": per_point,
                "max_point_total_mm": imerg.clean(max_total),
                "max_point": max_point,
                "max_peak_mm_h": imerg.clean(max_peak),
                "antecedent_7d_mean_mm": imerg.clean(
                    sum(antecedent_values) / len(antecedent_values)
                )
                if antecedent_values
                else None,
                "known_event_id": find_known_event(out_dir, start_day, end_day),
            }
        )
    candidates.sort(
        key=lambda c: (
            -(c["max_point_total_mm"] or 0.0),
            -(c["max_peak_mm_h"] or 0.0),
            c["start"],
        )
    )
    for rank, candidate in enumerate(candidates, start=1):
        candidate["rank"] = rank

    catalog_payload = {
        "meta": {
            "method": daily_payload["meta"]["method"],
            "product": sorted(prod_names),
            "version": "07",
            "run": run_meta,
            "urls": {"api": TIMESERIES_URL, "docs": DOCS_URL},
            "retrieved_at": imerg.utc_now_iso(),
            "licence": LICENCE,
            "note": GRID_NOTE,
            "thresholds": {
                "daily_total_mm": DAILY_TOTAL_THRESHOLD_MM,
                "max_30min_mm_h": INTENSITY_THRESHOLD_MM_H,
            },
            "notes": [
                "a day qualifies if any point daily total >= 50 mm or any "
                "30-min intensity >= 30 mm/h",
                "consecutive qualifying days are merged into one candidate",
                "severity = max point total over the candidate; rank 1 is most severe",
                "antecedent_7d_mean_mm: mean over the 7 days before the start of "
                "the across-point mean daily total",
            ],
        },
        "candidates": candidates,
    }
    imerg.write_json(out_dir / "catalog_candidates.json", catalog_payload)

    lines = [
        "FloodTrace IMERG history scan",
        f"period covered: {all_days[0]} .. {all_days[-1]} ({len(all_days)} days with data)",
        "runs: final through "
        + (f"{final_ends and min(final_ends).date()}" if final_ends else "n/a")
        + (f", late tail {n_late_rows} steps" if n_late_rows else ", no late tail"),
        f"candidates: {len(candidates)}",
        "top 25 by severity:",
    ]
    for candidate in candidates[:25]:
        lines.append(
            f"  {candidate['rank']:>2}. {candidate['start']}..{candidate['end']}  "
            f"{candidate['max_point']} {candidate['max_point_total_mm']} mm, "
            f"peak {candidate['max_peak_mm_h']} mm/h"
            + (f", known: {candidate['known_event_id']}" if candidate["known_event_id"] else "")
        )
    target = None
    for candidate in candidates:
        if any(candidate["start"] <= d <= candidate["end"] for d in EVENT_CHECK_DATES):
            target = candidate
            break
    if target:
        lines.append(
            f"2024-07-02/03: appears in candidate rank {target['rank']} "
            f"({target['start']}..{target['end']}, {target['max_point']} "
            f"{target['max_point_total_mm']} mm)"
        )
    else:
        details = []
        for day in (date.fromisoformat(d) for d in EVENT_CHECK_DATES):
            values = day_values(day)
            totals = [t for t, _ in values.values() if t is not None]
            peaks = [p for _, p in values.values() if p is not None]
            details.append(
                f"{day}: max total {max(totals, 0.0):.1f} mm, max 30-min "
                f"{max(peaks, 0.0):.1f} mm/h"
            )
        lines.append(
            "2024-07-02/03: does NOT qualify as a candidate ("
            + "; ".join(details)
            + ")"
        )
    months = Counter(candidate["start"][5:7] for candidate in candidates)
    lines.append("candidates by start month:")
    lines.extend(
        f"  {calendar.month_abbr[month]}: {months.get(f'{month:02d}', 0)}"
        for month in range(1, 13)
    )
    lines.append(
        "wrote rain_history_daily.json, catalog_candidates.json (in " + str(out_dir) + ")"
    )
    summary = "\n".join(lines)
    print(summary)
    return summary


def main() -> None:
    usage = (
        "usage: pipeline/.venv/bin/python pipeline/imerg_history.py "
        "[event-dir] [--start YYYY-MM-DD] [--end YYYY-MM-DD] [--refresh]"
    )
    refresh = "--refresh" in sys.argv
    start = RECORD_START
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
        elif arg != "--refresh":
            positional.append(arg)
        index += 1
    if len(positional) > 1 or index != len(args):
        raise SystemExit(usage)
    event_dir = Path(positional[0]) if positional else Path("events/lagos-2024-07-03")
    run(event_dir, start, end, refresh)


if __name__ == "__main__":
    main()
