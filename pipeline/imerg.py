#!/usr/bin/env python3
"""Fetch GPM IMERG half-hourly rainfall for a FloodTrace event package.

Reads events/<id>/event.json, downloads GPM IMERG v07 half-hourly
precipitation (Final run GPM_3IMERGHH, Late run GPM_3IMERGHHL as a
per-timestep fallback) from NASA GES DISC for the event window, and
subsets it to the AOI bbox padded by 0.1 degree. Temporary global HDF5
granules are deleted right after subsetting. Outputs, in the event dir:

- rainfall_imerg.json      per-point and AOI-mean half-hourly series
- rainfall_imerg_grid.json compact grid for the map, focus window only
- rainfall_summary.json    per-point maxima, duration totals, rain onset

Usage:
    pipeline/.venv/bin/python pipeline/imerg.py events/lagos-2024-07-03

Auth: NASA Earthdata credentials from the project .env
(Earthdata_username / Earthdata_password), parsed here and passed to
earthaccess via the environment (strategy="environment"); the .env
and its values are never printed, copied or logged.
"""

from __future__ import annotations

import json
import math
import os
import re
import sys
import tempfile
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import earthaccess
import h5py
import numpy as np

PIPELINE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = PIPELINE_DIR.parent
ENV_FILE = PROJECT_ROOT / ".env"

PRODUCT_FINAL = "GPM_3IMERGHH"
PRODUCT_LATE = "GPM_3IMERGHHL"
COLLECTION_VERSION = "07"
DOI_FINAL = "10.5067/GPM/IMERG/3B-HHR/07"
DOI_LATE = "10.5067/GPM/IMERG/3B-HHR-L/07"
URL_FINAL = "https://disc.gsfc.nasa.gov/datasets/GPM_3IMERGHH_07/summary"
URL_LATE = "https://disc.gsfc.nasa.gov/datasets/GPM_3IMERGHHL_07/summary"
BBOX_PAD_DEG = 0.1
HALF_CELL = 0.05  # IMERG cells are 0.1 deg, centres offset by 0.05
EPS = 1e-6
RETRIES = 3
RETRY_DELAYS = (10.0, 30.0, 60.0)
MAX_CONSECUTIVE_FAILURES = 10
PROGRESS_EVERY = 48
LICENCE = "NASA open data"
GRID_RESOLUTION = "0.1 degree (~10 km)"
GRID_NOTE = "satellite estimate; ~10 km cells smooth point intensities"
ONSET_RATE = 2.0  # mm/h
DRY_RATE = 0.5  # mm/h
DRY_STEPS = 12  # 6 hours of 30-minute steps
HALF_HOUR = timedelta(minutes=30)

AUTH_ERROR = (
    "GES DISC returned 401/403. This usually means the Earthdata profile has not\n"
    'authorized the "NASA GESDISC DATA ARCHIVE" application yet:\n'
    "https://disc.gsfc.nasa.gov/earthdata-login"
)

# e.g. 3B-HHR-E.MS.MRG.3IMERG.20240703-S000000-E001559.0000.V07B
NATIVE_TIME_RE = re.compile(r"(\d{8})-S(\d{6})-E(\d{6})\.\d{4}\.V\w+")


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace(
        "+00:00", "Z"
    )


def parse_iso(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def iso_z(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def floor_half_hour(dt: datetime) -> datetime:
    dt = dt.astimezone(timezone.utc)
    minute = 0 if dt.minute < 30 else 30
    return dt.replace(minute=minute, second=0, microsecond=0)


def half_hour_steps(start_utc: datetime, end_utc: datetime) -> list[datetime]:
    steps = []
    current = floor_half_hour(start_utc)
    while current < end_utc:
        steps.append(current)
        current += HALF_HOUR
    if not steps:
        raise SystemExit("event window contains no 30-minute steps")
    return steps


def clean(value: float | None, digits: int = 2) -> float | None:
    if value is None:
        return None
    value = float(value)
    if not math.isfinite(value):
        return None
    return round(value, digits)


def write_json(path: Path, payload: dict) -> None:
    path.write_text(
        json.dumps(payload, indent=2, allow_nan=False) + "\n", encoding="utf-8"
    )


def load_env_credentials() -> None:
    """Load Earthdata credentials into os.environ.

    The environment first: CI sets EARTHDATA_USERNAME and EARTHDATA_PASSWORD
    directly, and then no .env is needed. Otherwise the project .env is
    parsed exactly as before (a laptop run). The .env contents and the
    credential values are never printed, logged or written anywhere else.
    """
    if os.environ.get("EARTHDATA_USERNAME") and os.environ.get("EARTHDATA_PASSWORD"):
        return
    if not ENV_FILE.is_file():
        raise SystemExit(
            "credentials missing: set EARTHDATA_USERNAME and EARTHDATA_PASSWORD "
            f"in the environment, or create {ENV_FILE} with Earthdata_username "
            "and Earthdata_password entries"
        )
    found: dict[str, str] = {}
    for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line.lower().startswith("export "):
            line = line[len("export ") :]
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip().lower()
        value = value.strip().strip('"').strip("'")
        if key in ("earthdata_username", "earthdata_password") and value:
            found[key] = value
    if "earthdata_username" not in found or "earthdata_password" not in found:
        raise SystemExit(
            "credentials missing: set EARTHDATA_USERNAME and EARTHDATA_PASSWORD "
            "in the environment, or give .env Earthdata_username and "
            "Earthdata_password entries"
        )
    os.environ["EARTHDATA_USERNAME"] = found["earthdata_username"]
    os.environ["EARTHDATA_PASSWORD"] = found["earthdata_password"]


def granule_native_id(granule) -> str:
    """Best-effort native id across earthaccess versions."""
    candidates: list[str] = []
    for getter in (
        lambda: granule.native_id(),
        lambda: granule["meta"]["native-id"],
        lambda: granule["umm"]["NativeId"],
    ):
        try:
            value = getter()
        except Exception:
            continue
        if isinstance(value, str):
            candidates.append(value)
    for value in candidates:
        if "IMERG" in value:
            return value
    return "\n".join(candidates)


def granule_step(granule) -> datetime | None:
    """30-minute interval start (UTC) covered by a granule."""
    native = granule_native_id(granule)
    match = NATIVE_TIME_RE.search(native)
    if match:
        day, start = match.group(1), match.group(2)
        return datetime.strptime(day + start, "%Y%m%d%H%M%S").replace(
            tzinfo=timezone.utc
        )
    try:
        beg = granule["umm"]["TemporalExtent"]["RangeDateTime"]["BeginningDateTime"]
    except Exception:
        return None
    # Whether CMR records the interval start or end, flooring to the half
    # hour gives the interval start.
    return floor_half_hour(parse_iso(beg))


def search_granules(
    short_name: str, start_utc: datetime, end_utc: datetime, expected: int
) -> dict:
    results = earthaccess.search_data(
        short_name=short_name,
        version=COLLECTION_VERSION,
        temporal=(iso_z(start_utc), iso_z(end_utc)),
        count=expected + 24,
    )
    by_step: dict[datetime, object] = {}
    for granule in results:
        step = granule_step(granule)
        if step is not None and step not in by_step:
            by_step[step] = granule
    return by_step


def download_granule(granule, tmp_dir: Path) -> list[Path]:
    last_error: Exception | None = None
    for attempt in range(RETRIES):
        # Clear leftovers so a partial download never gets re-read.
        for stale in tmp_dir.iterdir():
            stale.unlink(missing_ok=True)
        try:
            files = earthaccess.download([granule], str(tmp_dir))
            paths = [Path(f) for f in files if str(f).lower().endswith(".hdf5")]
            if not paths:
                paths = [Path(f) for f in files]
            if not paths:
                raise RuntimeError("earthaccess returned no files")
            return paths
        except SystemExit:
            raise
        except Exception as exc:
            message = str(exc)
            if "401" in message or "403" in message:
                raise SystemExit(AUTH_ERROR) from exc
            last_error = exc
            time.sleep(RETRY_DELAYS[min(attempt, len(RETRY_DELAYS) - 1)])
    raise RuntimeError(f"download failed after {RETRIES} attempts: {last_error}")


def find_dataset(handle: h5py.File, name: str):
    for path in (f"Grid/{name}", name):
        if path in handle:
            return handle[path]
    raise RuntimeError(f"variable {name!r} not found in IMERG granule")


def grid_slices(
    lon: np.ndarray, lat: np.ndarray, bbox: list[float]
) -> tuple[int, int, int, int]:
    """Index range of cells intersecting the (padded) bbox."""
    lon_min, lat_min, lon_max, lat_max = bbox
    lon_idx = np.where(
        (lon >= lon_min - HALF_CELL - EPS) & (lon <= lon_max + HALF_CELL + EPS)
    )[0]
    lat_idx = np.where(
        (lat >= lat_min - HALF_CELL - EPS) & (lat <= lat_max + HALF_CELL + EPS)
    )[0]
    if lon_idx.size == 0 or lat_idx.size == 0:
        raise RuntimeError(f"AOI bbox {bbox} selects no IMERG cells")
    return int(lon_idx[0]), int(lon_idx[-1]) + 1, int(lat_idx[0]), int(lat_idx[-1]) + 1


def read_grid(path: Path) -> tuple[np.ndarray, np.ndarray]:
    with h5py.File(path, "r") as handle:
        lon = np.asarray(find_dataset(handle, "lon")[:], dtype=float)
        lat = np.asarray(find_dataset(handle, "lat")[:], dtype=float)
    return lon, lat


def read_precip(path: Path, slices_: tuple[int, int, int, int]) -> np.ndarray:
    """AOI subset of precipitation (mm/h), NaN where missing."""
    lon_lo, lon_hi, lat_lo, lat_hi = slices_
    with h5py.File(path, "r") as handle:
        dataset = find_dataset(handle, "precipitation")
        shape = dataset.shape
        if len(shape) == 2:
            raw = dataset[lon_lo:lon_hi, lat_lo:lat_hi]
        elif len(shape) == 3 and shape[0] == 1:
            raw = dataset[0, lon_lo:lon_hi, lat_lo:lat_hi]
        elif len(shape) == 3 and shape[2] == 1:
            raw = dataset[lon_lo:lon_hi, lat_lo:lat_hi, 0]
        else:
            raise RuntimeError(f"unexpected precipitation shape {shape}")
    precip = np.array(raw, dtype=np.float32)
    precip[~np.isfinite(precip)] = np.nan
    precip[precip < 0] = np.nan  # IMERG fill values are large negatives
    return precip


def aoi_mean(precip: np.ndarray | None) -> float:
    if precip is None:
        return math.nan
    finite = precip[np.isfinite(precip)]
    if finite.size == 0:
        return math.nan
    return float(finite.mean())


def max_intensity(values: list[float], steps: list[datetime]):
    best_value = math.nan
    best_step: datetime | None = None
    for value, step in zip(values, steps):
        if math.isfinite(value) and (not math.isfinite(best_value) or value > best_value):
            best_value, best_step = value, step
    return best_value, best_step


def total_over(values: list[float], steps: list[datetime], lo: datetime, hi: datetime) -> float:
    """Depth total (mm) over 30-min steps in [lo, hi); each step is rate * 0.5 h."""
    total = 0.0
    for value, step in zip(values, steps):
        if lo <= step < hi and math.isfinite(value):
            total += value * 0.5
    return total


def find_onsets(values: list[float], steps: list[datetime]) -> list[datetime]:
    """All times where rate >= ONSET_RATE after DRY_STEPS steps < DRY_RATE."""
    onsets = []
    for i in range(DRY_STEPS, len(values)):
        window = values[i - DRY_STEPS : i]
        if any(not math.isfinite(v) for v in window):
            continue
        if max(window) >= DRY_RATE:
            continue
        if math.isfinite(values[i]) and values[i] >= ONSET_RATE:
            onsets.append(steps[i])
    return onsets


def run(event_dir: Path) -> str:
    event_path = event_dir / "event.json"
    if not event_path.is_file():
        raise SystemExit(f"missing {event_path}")
    event = json.loads(event_path.read_text(encoding="utf-8"))
    tz = ZoneInfo(event["timezone"])
    win_start = parse_iso(event["window"]["start"]).astimezone(timezone.utc)
    win_end = parse_iso(event["window"]["end"]).astimezone(timezone.utc)
    focus_start = parse_iso(event["focus"]["start"]).astimezone(timezone.utc)
    focus_end = parse_iso(event["focus"]["end"]).astimezone(timezone.utc)
    bbox = [float(v) for v in event["aoi"]["bbox"]]
    padded = [
        bbox[0] - BBOX_PAD_DEG,
        bbox[1] - BBOX_PAD_DEG,
        bbox[2] + BBOX_PAD_DEG,
        bbox[3] + BBOX_PAD_DEG,
    ]
    points = {
        name: coords
        for name, coords in event["aoi"]["points"].items()
        if name != "offshore_tide"
    }
    steps = half_hour_steps(win_start, win_end)

    def local(dt: datetime) -> str:
        return dt.astimezone(tz).isoformat()

    times = [local(step) for step in steps]

    load_env_credentials()
    earthaccess.login(strategy="environment")

    final_map = search_granules(PRODUCT_FINAL, win_start, win_end, len(steps))
    late_map: dict = {}
    late_searched = False
    chosen: list[tuple[datetime, object | None, str]] = []
    for step in steps:
        granule = final_map.get(step)
        if granule is not None:
            chosen.append((step, granule, "final"))
            continue
        if not late_searched:
            late_map = search_granules(PRODUCT_LATE, win_start, win_end, len(steps))
            late_searched = True
        granule = late_map.get(step)
        chosen.append((step, granule, "late" if granule is not None else "missing"))
    if not any(granule is not None for _, granule, _ in chosen):
        raise SystemExit(
            f"no IMERG granules found for {PRODUCT_FINAL} or {PRODUCT_LATE} "
            f"(version {COLLECTION_VERSION}) in the window; check the collection "
            'version and that the Earthdata profile authorizes "NASA GESDISC '
            'DATA ARCHIVE"'
        )

    # Download each granule, keep only the AOI subset, delete the file.
    subsets: list[np.ndarray | None] = [None] * len(steps)
    slices_: tuple[int, int, int, int] | None = None
    lon_sub: np.ndarray | None = None
    lat_sub: np.ndarray | None = None
    failures: list[str] = []
    consecutive_failures = 0
    cache_dir = PIPELINE_DIR / "cache"
    cache_dir.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="imerg_", dir=cache_dir) as tmp:
        tmp_dir = Path(tmp)
        for index, (step, granule, run_name) in enumerate(chosen):
            if granule is None:
                continue
            try:
                paths = download_granule(granule, tmp_dir)
                try:
                    if slices_ is None:
                        lon_all, lat_all = read_grid(paths[0])
                        slices_ = grid_slices(lon_all, lat_all, padded)
                        lon_sub = lon_all[slices_[0] : slices_[1]]
                        lat_sub = lat_all[slices_[2] : slices_[3]]
                    subsets[index] = read_precip(paths[0], slices_)
                finally:
                    for path in paths:
                        path.unlink(missing_ok=True)
                consecutive_failures = 0
            except SystemExit:
                raise
            except Exception as exc:
                consecutive_failures += 1
                failures.append(f"{iso_z(step)} ({run_name}): {exc}")
                if consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
                    raise SystemExit(
                        "too many consecutive granule failures:\n  "
                        + "\n  ".join(failures[-5:])
                    )
            if (index + 1) % PROGRESS_EVERY == 0:
                print(
                    f"  {index + 1}/{len(chosen)} granules processed",
                    file=sys.stderr,
                )

    if lon_sub is None or lat_sub is None:
        raise SystemExit("no IMERG granules could be read for the window")

    runs = [run_name for _, _, run_name in chosen]
    n_final = runs.count("final")
    n_late = runs.count("late")
    n_missing = runs.count("missing")

    # Per-point series from the containing cell (nearest cell centre).
    point_values: dict[str, list[float]] = {}
    point_cells: dict[str, tuple[float, float]] = {}
    for name, coords in points.items():
        plon, plat = float(coords[0]), float(coords[1])
        i = int(np.abs(lon_sub - plon).argmin())
        j = int(np.abs(lat_sub - plat).argmin())
        point_cells[name] = (float(lon_sub[i]), float(lat_sub[j]))
        values = []
        for precip in subsets:
            if precip is None:
                values.append(math.nan)
                continue
            value = float(precip[i, j])
            values.append(value if math.isfinite(value) else math.nan)
        point_values[name] = values
    mean_values = [aoi_mean(precip) for precip in subsets]

    imerg_payload = {
        "meta": {
            "product": PRODUCT_FINAL,
            "product_fallback": PRODUCT_LATE,
            "version": COLLECTION_VERSION,
            "run": {"final": n_final, "late": n_late, "missing": n_missing},
            "doi": {"final": DOI_FINAL, "late": DOI_LATE},
            "urls": {"final": URL_FINAL, "late": URL_LATE},
            "retrieved_at": utc_now_iso(),
            "licence": LICENCE,
            "grid_resolution": GRID_RESOLUTION,
            "note": GRID_NOTE,
            "units": "mm/h",
            "time_reference": (
                "start of each 30-minute interval, in the event timezone "
                "(IMERG times are UTC)"
            ),
            "window": event["window"],
        },
        "times": times,
        "runs": runs,
        "points": {
            name: {
                "lon": float(coords[0]),
                "lat": float(coords[1]),
                "cell_lon": round(point_cells[name][0], 2),
                "cell_lat": round(point_cells[name][1], 2),
                "series": [clean(v) for v in point_values[name]],
            }
            for name, coords in points.items()
        },
        "aoi_mean": {"series": [clean(v) for v in mean_values]},
    }
    write_json(event_dir / "rainfall_imerg.json", imerg_payload)

    focus_indices = [
        k for k, step in enumerate(steps) if focus_start <= step < focus_end
    ]
    grid_payload = {
        "meta": {
            "product": PRODUCT_FINAL,
            "version": COLLECTION_VERSION,
            "units": "mm/h",
            "licence": LICENCE,
            "retrieved_at": utc_now_iso(),
            "focus": event["focus"],
            "bbox_padded": padded,
            "note": GRID_NOTE,
            "data_order": (
                "data[t][i][j] = precipitation at lat[i], lon[j]; null = no data; "
                "cells intersecting the padded bbox are included"
            ),
        },
        "times": [times[k] for k in focus_indices],
        "runs": [runs[k] for k in focus_indices],
        "lon": [round(float(v), 2) for v in lon_sub],
        "lat": [round(float(v), 2) for v in lat_sub],
        "data": [],
    }
    for k in focus_indices:
        precip = subsets[k]
        if precip is None:
            grid_payload["data"].append(None)
        else:
            grid_payload["data"].append(
                [[clean(float(v)) for v in row] for row in precip.T]
            )
    write_json(event_dir / "rainfall_imerg_grid.json", grid_payload)

    def point_summary(values: list[float]) -> dict:
        peak_value, peak_step = max_intensity(values, steps)
        if peak_step is not None:
            totals = {
                f"{hours}h": clean(
                    total_over(
                        values,
                        steps,
                        peak_step - timedelta(hours=hours) + HALF_HOUR,
                        peak_step + HALF_HOUR,
                    )
                )
                for hours in (1, 3, 6, 24)
            }
        else:
            totals = {"1h": None, "3h": None, "6h": None, "24h": None}
        onsets = find_onsets(values, steps)
        in_focus = [s for s in onsets if s <= focus_end]
        onset_step = in_focus[-1] if in_focus else None
        return {
            "max_intensity_mm_per_h": clean(peak_value),
            "max_time": local(peak_step) if peak_step is not None else None,
            "totals_mm": totals,
            "antecedent_7d_mm": clean(
                total_over(values, steps, focus_start - timedelta(days=7), focus_start)
            ),
            "onset_time": local(onset_step) if onset_step is not None else None,
            "onsets_all": [local(s) for s in onsets],
        }

    summary_points = {
        name: point_summary(values) for name, values in point_values.items()
    }
    summary_payload = {
        "meta": {
            "product": PRODUCT_FINAL,
            "version": COLLECTION_VERSION,
            "licence": LICENCE,
            "retrieved_at": utc_now_iso(),
            "units": {"intensity": "mm/h", "totals": "mm"},
            "notes": [
                "totals cover 30-min intervals in (t_max - duration, t_max]",
                "antecedent_7d covers [focus.start - 7 days, focus.start)",
                (
                    f"onset: first half-hour >= {ONSET_RATE} mm/h after {DRY_STEPS} "
                    f"steps (6 h) below {DRY_RATE} mm/h; onset_time is the last "
                    "qualifying onset at or before focus.end"
                ),
                GRID_NOTE,
            ],
        },
        "points": summary_points,
        "aoi_mean": point_summary(mean_values),
    }
    write_json(event_dir / "rainfall_summary.json", summary_payload)

    def fmt(value: float | None, digits: int = 2) -> str:
        return "n/a" if value is None else f"{value:.{digits}f}"

    lines = [
        "FloodTrace IMERG rainfall",
        f"event: {event.get('id', event_dir.name)}",
        f"runs: {n_final} final, {n_late} late, {n_missing} missing",
        f"timesteps: {len(steps)} ({times[0]} .. {times[-1]})",
    ]
    for name in points:
        entry = summary_points[name]
        lines.append(
            f"{name}: max {fmt(entry['max_intensity_mm_per_h'])} mm/h at "
            f"{entry['max_time']}, onset {entry['onset_time']}, "
            f"24h total {fmt(entry['totals_mm']['24h'], 1)} mm"
        )
    mean_entry = summary_payload["aoi_mean"]
    lines.append(
        f"aoi_mean: max {fmt(mean_entry['max_intensity_mm_per_h'])} mm/h at "
        f"{mean_entry['max_time']}"
    )
    if failures:
        lines.append(f"granule failures: {len(failures)}")
    lines.append(
        "wrote rainfall_imerg.json, rainfall_imerg_grid.json, rainfall_summary.json"
    )
    summary_text = "\n".join(lines)
    print(summary_text)
    return summary_text


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit(
            "usage: pipeline/.venv/bin/python pipeline/imerg.py events/<event-id>"
        )
    run(Path(sys.argv[1]))


if __name__ == "__main__":
    main()
