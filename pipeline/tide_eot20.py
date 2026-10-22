"""Astronomical tide at the event's offshore point from the EOT20 global ocean tide model.

    pipeline/.venv/bin/python pipeline/tide_eot20.py events/<event-id>

EOT20 (Hart-Davis et al. 2021, DGFI-TUM; CC BY 4.0, doi:10.17882/79489) is open, so this works for any year — unlike the
Open-Meteo marine series, which has no data before ~2022. Expects the model under pipeline/cache/tide_models/EOT20/ocean_tides/.

Writes events/<id>/tide_eot20.json in the same shape as tide.json (Open-Meteo style: utc_offset_seconds + hourly.time /
hourly.sea_level_height_msl) so the app can use either. Values are tide only (no surge, no lagoon damping or lag).
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pyTMD.compute

# The EOT20 model directory (about 2.1 GB) lives under pipeline/cache/ and is
# never committed. FLOODTRACE_TIDE_MODEL_DIR points the code at it elsewhere,
# e.g. at an empty directory to prove a run does not need the model (Task 47).
MODEL_DIR = Path(
    os.environ.get("FLOODTRACE_TIDE_MODEL_DIR")
    or Path(__file__).resolve().parent / "cache" / "tide_models"
)
EPOCH = datetime(2000, 1, 1, tzinfo=timezone.utc)


def main(event_dir: Path) -> None:
    ev = json.loads((event_dir / "event.json").read_text())
    lon, lat = ev["aoi"]["points"]["offshore_tide"]
    start = datetime.fromisoformat(ev["window"]["start"])
    end = datetime.fromisoformat(ev["window"]["end"])
    offset = start.utcoffset() or timedelta(0)

    times = []
    t = start
    while t < end:
        times.append(t)
        t += timedelta(hours=1)
    delta = np.array([(x.astimezone(timezone.utc) - EPOCH).total_seconds() for x in times])

    tide = pyTMD.compute.tide_elevations(
        np.array([lon]),  # time-series mode: x/y are station locations, output is (stations, times)
        np.array([lat]),
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
    assert values.size == len(times), (values.size, len(times))

    out = {
        "utc_offset_seconds": int(offset.total_seconds()),
        "timezone": ev["timezone"],
        "latitude": lat,
        "longitude": lon,
        "hourly_units": {"time": "iso8601", "sea_level_height_msl": "m"},
        "hourly": {
            # Local wall time without offset, matching Open-Meteo's tide.json.
            "time": [x.replace(tzinfo=None).isoformat(timespec="minutes") for x in times],
            "sea_level_height_msl": [None if np.isnan(v) else round(float(v), 3) for v in values],
        },
        "meta": {
            "product": "EOT20 global ocean tide model (astronomical tide, 17 constituents)",
            "citation": "Hart-Davis et al. (2021), EOT20, SEANOE, doi:10.17882/79489",
            "licence": "CC BY 4.0",
            "method": "pyTMD.compute.tide_elevations, extrapolate=True, cutoff=20 km",
            "note": "tide only — no storm surge, no lagoon damping or phase lag",
            "retrieved_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        },
    }
    (event_dir / "tide_eot20.json").write_text(json.dumps(out, indent=1))
    valid = values[~np.isnan(values)]
    print(f"{event_dir.name}: {len(valid)}/{len(values)} hours, range {valid.min():+.2f} … {valid.max():+.2f} m")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    main(Path(sys.argv[1]))
