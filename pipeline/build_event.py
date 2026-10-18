#!/usr/bin/env python3
"""One-command Tier A event builder for FloodTrace.

Usage:
    pipeline/.venv/bin/python pipeline/build_event.py <event_id> \
        --start YYYY-MM-DD --end YYYY-MM-DD \
        [--focus-start ISO --focus-end ISO] [--out DIR] [--force] \
        [--name NAME] [--point NAME=LON,LAT]... \
        [--sar-pre ID --sar-during ID --sar-post ID]

What it does (docs/INTAKE_PLAN.md pipeline step 3, docs/tasks/27):
 1. writes event.json from the lagos-2025-08-04 template: same AOI and
    points (override with --point), window = start - 6 d .. end + 7 d,
    focus defaulting to the wettest 48 h in the IMERG daily history
    (events/rain_history_grid_daily.json, WAT calendar days), and
    cause_prelim / key_events / open_questions left empty with
    status "draft" for the evidence agent to fill in;
 2. runs, in order and stopping at the first failure:
    fetch_open_data.py, imerg.py, tide_eot20.py, then sar_flood.py only
    if a Sentinel-1 pass falls inside focus (--sar-* give the Planetary
    Computer sentinel-1-rtc item ids the map needs);
 3. adds or updates the events/catalog.json entry (built: true,
    status: "draft") when building into events/<event_id>.

Each step is skipped when all of its outputs already exist; --force
re-runs everything. Credentials are loaded by imerg.py itself from the
project .env and are never printed here.

Rebuild test (docs/tasks/27): the reviewed lagos-2021-07-16 window is
2021-07-09..23 (date -7 d .. date +7 d, built by hand before this
-6 d/+7 d rule), so it reproduces exactly with --start 2021-07-15
--end 2021-07-16 and the reviewed focus and points:

    pipeline/.venv/bin/python pipeline/build_event.py lagos-2021-07-16 \
        --start 2021-07-15 --end 2021-07-16 \
        --focus-start 2021-07-15T06:00:00+01:00 \
        --focus-end 2021-07-17T06:00:00+01:00 \
        --name "Lagos Island Flood 2021" \
        --point oshodi=3.35,6.55 --point ikorodu=- \
        --out pipeline/cache/rebuild_test/lagos-2021-07-16
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

PIPELINE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = PIPELINE_DIR.parent
EVENTS_DIR = PROJECT_ROOT / "events"
VENV_PY = PIPELINE_DIR / ".venv" / "bin" / "python"
TEMPLATE_EVENT = EVENTS_DIR / "lagos-2025-08-04" / "event.json"
RAIN_HISTORY = EVENTS_DIR / "rain_history_grid_daily.json"
CATALOG = EVENTS_DIR / "catalog.json"
TZ = "Africa/Lagos"
LOCAL_OFFSET = "+01:00"  # WAT, fixed offset for date-only arguments
WINDOW_PAD_START = timedelta(days=6)
WINDOW_PAD_END = timedelta(days=7)


def local_midnight(day: date) -> str:
    return f"{day.isoformat()}T00:00:00{LOCAL_OFFSET}"


def parse_iso(value: str) -> datetime:
    return datetime.fromisoformat(value)


def fail(message: str) -> None:
    print(f"\nFAILED: {message}", file=sys.stderr)
    raise SystemExit(1)


# ---------------------------------------------------------------- template


def wettest_48h(window_start: date, window_end: date) -> tuple[date, date]:
    """Wettest 48 h = the two consecutive WAT days in the window with the
    highest mean IMERG daily total across AOI cells. Focus runs from the
    first day's midnight, so an overnight storm straddles both days."""
    data = json.loads(RAIN_HISTORY.read_text(encoding="utf-8"))
    dates = data.get("dates", [])
    index = {d: i for i, d in enumerate(dates)}
    series = data.get("series", {})
    best_day: date | None = None
    best_score = None
    day = window_start
    while day + timedelta(days=1) <= window_end:
        next_day = day + timedelta(days=1)
        i1, i2 = index.get(day.isoformat()), index.get(next_day.isoformat())
        if i1 is None or i2 is None:
            day += timedelta(days=1)
            continue
        totals = []
        for cell in series.values():
            a, b = cell["total_mm"][i1], cell["total_mm"][i2]
            if a is not None and b is not None:
                totals.append(a + b)
        if totals:
            score = sum(totals) / len(totals)
            if best_score is None or score > best_score:
                best_score, best_day = score, day
        day += timedelta(days=1)
    if best_day is None:
        fail(
            "cannot default the focus: no IMERG daily history covers the "
            f"window {window_start}..{window_end} in {RAIN_HISTORY.name}; "
            "pass --focus-start/--focus-end explicitly"
        )
    print(
        f"[event.json] default focus: wettest 48 h = {best_day.isoformat()} "
        f"(AOI mean {best_score:.1f} mm over the two days)"
    )
    return best_day, best_day + timedelta(days=2)


def parse_point(spec: str) -> tuple[str, list[float] | None]:
    name, sep, value = spec.partition("=")
    name = name.strip()
    if not sep or not name:
        fail(f"--point expects NAME=LON,LAT (or NAME=- to remove), got {spec!r}")
    if value.strip() == "-":
        if name == "offshore_tide":
            fail("offshore_tide cannot be removed (tide and rainfall steps need it)")
        return name, None
    try:
        lon, lat = (float(v) for v in value.split(","))
    except ValueError:
        fail(f"--point expects NAME=LON,LAT, got {spec!r}")
    return name, [lon, lat]


def build_event_json(
    event_id: str,
    name: str,
    window_start: date,
    window_end: date,
    focus_start: datetime,
    focus_end: datetime,
    point_overrides: list[tuple[str, list[float] | None]],
) -> dict:
    template = json.loads(TEMPLATE_EVENT.read_text(encoding="utf-8"))
    points: dict[str, list[float]] = dict(template["aoi"]["points"])
    for point_name, coords in point_overrides:
        if coords is None:
            points.pop(point_name, None)
        else:
            points[point_name] = coords
    return {
        "id": event_id,
        "name": name,
        "timezone": TZ,
        "window": {
            "start": local_midnight(window_start),
            "end": local_midnight(window_end),
        },
        "focus": {
            "start": focus_start.isoformat(),
            "end": focus_end.isoformat(),
        },
        "aoi": {"name": template["aoi"]["name"], "bbox": template["aoi"]["bbox"], "points": points},
        "status": "draft",
        "cause_prelim": "",
        "open_questions": [],
        "key_events": [],
        "sources": {},
    }


# ------------------------------------------------------------------- steps

STEPS: list[tuple[str, str, list[str]]] = [
    # (step, script, outputs written into the event dir)
    ("fetch_open_data", "fetch_open_data.py",
     ["tide.json", "rainfall_reanalysis.json", "satellite_passes.json",
      "drainage_osm.geojson"]),
    ("imerg", "imerg.py",
     ["rainfall_imerg.json", "rainfall_imerg_grid.json", "rainfall_summary.json"]),
    ("tide_eot20", "tide_eot20.py",
     ["tide_eot20.json"]),
]

SAR_OUTPUTS = ["sar/stats.json"]


def python_bin() -> str:
    return str(VENV_PY) if VENV_PY.is_file() else sys.executable


def run_step(step: str, script: str, outputs: list[str], event_dir: Path,
             force: bool) -> bool:
    missing = [name for name in outputs
               if not (event_dir / name).is_file()]
    if not force and not missing:
        print(f"[{step}] skipped: outputs exist ({', '.join(outputs)})")
        return True
    cmd = [python_bin(), str(PIPELINE_DIR / script), str(event_dir)]
    print(f"[{step}] running {' '.join(cmd)}")
    code = subprocess_run(cmd)
    if code != 0:
        print(
            f"\nFAILED at step {step}: {script} exited {code}. "
            "Stopping; later steps were not run.\n"
            "  Fix the cause and re-run the same command - completed steps "
            "are skipped, failed steps re-run.",
            file=sys.stderr,
        )
        return False
    still = [name for name in outputs if not (event_dir / name).is_file()]
    if still:
        print(
            f"\nFAILED at step {step}: {script} exited 0 but did not write "
            f"{', '.join(still)}.",
            file=sys.stderr,
        )
        return False
    print(f"[{step}] ok")
    return True


def subprocess_run(cmd: list[str]) -> int:
    import subprocess
    # Child stdout/stderr are inherited, never captured, so no credential
    # can end up in this script's buffers; imerg.py loads .env itself.
    return subprocess.run(cmd, cwd=PROJECT_ROOT).returncode


def s1_passes_in_focus(event_dir: Path, focus_start: datetime,
                       focus_end: datetime) -> list[dict]:
    path = event_dir / "satellite_passes.json"
    if not path.is_file():
        return []
    passes = []
    for product in json.loads(path.read_text(encoding="utf-8")).get("products", []):
        if product.get("collection") != "SENTINEL-1":
            continue
        when = product.get("acquisition_start_local")
        if when and focus_start <= parse_iso(when) <= focus_end:
            passes.append(product)
    return sorted(passes, key=lambda p: p.get("acquisition_start_local") or "")


# ----------------------------------------------------------------- catalog


def update_catalog(event_id: str, name: str, event_date: date,
                   event_dir: Path) -> None:
    if event_dir != EVENTS_DIR / event_id:
        print(
            "[catalog] skipped: --out is not events/<event_id>, "
            "so catalog.json is left untouched (test build)"
        )
        return
    catalog = json.loads(CATALOG.read_text(encoding="utf-8"))
    entry = next((e for e in catalog.get("events", []) if e.get("id") == event_id),
                 None)
    if entry is None:
        entry = {"id": event_id, "areas": []}
        catalog.setdefault("events", []).append(entry)
        print(f"[catalog] added {event_id} (built, draft)")
    entry["name"] = name
    entry["date"] = event_date.isoformat()
    entry["status"] = "draft"
    entry["built"] = True
    CATALOG.write_text(json.dumps(catalog, indent=1) + "\n", encoding="utf-8")
    print(f"[catalog] updated {event_id}: built=true, status=draft")


# -------------------------------------------------------------------- main


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("event_id")
    parser.add_argument("--start", required=True, help="flood period start (YYYY-MM-DD)")
    parser.add_argument("--end", required=True, help="flood period end (YYYY-MM-DD)")
    parser.add_argument("--focus-start", help="ISO datetime, e.g. 2021-07-15T06:00:00+01:00")
    parser.add_argument("--focus-end", help="ISO datetime; focus must lie inside the window")
    parser.add_argument("--out", help="event dir (default events/<event_id>)")
    parser.add_argument("--force", action="store_true", help="re-run every step")
    parser.add_argument("--name", help="event name (default: 'Lagos Flood <Mon YYYY>')")
    parser.add_argument("--point", action="append", default=[],
                        help="add/override a point NAME=LON,LAT, or remove it with NAME=-")
    parser.add_argument("--sar-pre", help="sentinel-1-rtc item id, pre-flood scene")
    parser.add_argument("--sar-during", help="sentinel-1-rtc item id, during-flood scene")
    parser.add_argument("--sar-post", help="sentinel-1-rtc item id, post-flood scene")
    args = parser.parse_args()

    try:
        start = date.fromisoformat(args.start)
        end = date.fromisoformat(args.end)
    except ValueError:
        fail("--start/--end must be YYYY-MM-DD")
    if end < start:
        fail("--end is before --start")
    window_start = start - WINDOW_PAD_START
    window_end = end + WINDOW_PAD_END

    if bool(args.focus_start) != bool(args.focus_end):
        fail("--focus-start and --focus-end must be given together")
    if args.focus_start:
        try:
            focus_start = parse_iso(args.focus_start)
            focus_end = parse_iso(args.focus_end)
        except ValueError:
            fail("--focus-start/--focus-end must be ISO datetimes")
        if focus_end <= focus_start:
            fail("--focus-end is not after --focus-start")
        if not (parse_iso(local_midnight(window_start)) <= focus_start
                and focus_end <= parse_iso(local_midnight(window_end))):
            fail("focus must lie inside the window "
                 f"{window_start}..{window_end}")
    else:
        day, after = wettest_48h(window_start, window_end)
        focus_start = parse_iso(local_midnight(day))
        focus_end = parse_iso(local_midnight(after))

    name = args.name or f"Lagos Flood {start.strftime('%b %Y')}"
    event_dir = Path(args.out) if args.out else EVENTS_DIR / args.event_id
    event_dir.mkdir(parents=True, exist_ok=True)

    print(f"building {args.event_id}")
    print(f"  event dir : {event_dir}")
    print(f"  window    : {window_start} .. {window_end} (start - 6 d, end + 7 d)")
    print(f"  focus     : {focus_start.isoformat()} .. {focus_end.isoformat()}")
    print(f"  status    : draft (template: {TEMPLATE_EVENT.relative_to(PROJECT_ROOT)})")

    # Step 0: event.json (idempotent like the rest)
    event_path = event_dir / "event.json"
    if event_path.is_file() and not args.force:
        print("[event.json] skipped: output exists")
    else:
        event = build_event_json(
            args.event_id, name, window_start, window_end,
            focus_start, focus_end,
            [parse_point(spec) for spec in args.point],
        )
        event_path.write_text(json.dumps(event, indent=2) + "\n", encoding="utf-8")
        print(f"[event.json] wrote {event_path}")

    ok = True
    for step, script, outputs in STEPS:
        ok = run_step(step, script, outputs, event_dir, args.force)
        if not ok:
            return

    # Step 4: SAR, only when a Sentinel-1 pass falls inside focus.
    passes = s1_passes_in_focus(event_dir, focus_start, focus_end)
    if not passes:
        print("[sar] skipped: no Sentinel-1 pass inside focus")
    else:
        for p in passes:
            print(f"[sar] pass in focus: {p.get('name')} at {p.get('acquisition_start_local')}")
        if not (args.sar_pre and args.sar_during and args.sar_post):
            print(
                "\nFAILED at step sar: a Sentinel-1 pass falls inside focus, "
                "so sar_flood.py should run, but it needs pre/during/post "
                "sentinel-1-rtc item ids.\n"
                "  Re-run with --sar-pre ID --sar-during ID --sar-post ID "
                "(Planetary Computer sentinel-1-rtc items around the pass).",
                file=sys.stderr,
            )
            return
        event = json.loads(event_path.read_text(encoding="utf-8"))
        event["sar"] = {
            "collection": "sentinel-1-rtc",
            "pre": args.sar_pre,
            "during": args.sar_during,
            "post": args.sar_post,
        }
        event_path.write_text(json.dumps(event, indent=2) + "\n", encoding="utf-8")
        run_step("sar", "sar_flood.py", SAR_OUTPUTS, event_dir, args.force)

    update_catalog(args.event_id, name, end, event_dir)
    print(f"\ndone: {args.event_id} (status draft). Next: run the evidence agent "
          "(Task 12 + Task 15 brief), then review before it reaches the app.")


if __name__ == "__main__":
    main()
