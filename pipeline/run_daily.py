#!/usr/bin/env python3
"""Task 45 (docs/tasks/45-daily-run.md): run the forecast every day, and keep score by itself.

One entry point for the daily maintenance of the forecast. Steps, in order,
each as a subprocess of the venv's Python with the repo root as its working
directory:

  1. pipeline/forecast.py            every day (today's forecast).
  2. pipeline/imerg_history_grid.py  only when events/rain_history_grid_daily.json
     ends 5 or more days before today (Africa/Lagos), and at most once a day
     (the file's meta.retrieved_at must not be today). It reads the Earthdata
     login from .env by itself; this wrapper never touches credentials and
     never passes any as arguments.
  3. pipeline/score_forecasts.py     after a successful IMERG refresh, and on
     its own when events/forecast/scores.json is missing.

Why the IMERG step gets no --start/--end: the script accepts a date range, but
it rewrites rain_history_grid_daily.json to cover only the requested window,
so a narrow range would throw away the 2000-present history the scorer and the
analogues depend on. The default full range is the narrowest safe range, and
it is cheap: responses are cached per 2-year chunk under
pipeline/cache/imerg_history, so only the newest chunk hits the API.

A failing step is logged and the run carries on to the next independent step
(IMERG failing must not cost anyone today's forecast). The run exits non-zero
if any step failed.

Single instance: events/forecast/.run_daily.lock, held with fcntl.flock for
the whole run. A second concurrent run prints "already running" and exits 0.

Logs: events/forecast/logs/run_daily-YYYY-MM.log, one file per month
(Africa/Lagos). Each step logs a timestamp, the step name, its duration and
its exit code; on failure the last 20 lines of its output follow.

Status: events/forecast/status.json after every run, validated against
pipeline/schemas/run_daily_status.schema.json before it is written.

Usage:
    pipeline/.venv/bin/python pipeline/run_daily.py
    pipeline/.venv/bin/python pipeline/run_daily.py --skip-imerg

--skip-imerg  never run the IMERG step (testing; the Earthdata refresh is the
              owner's to run).
--fail-step N debug: force step N (forecast | imerg | score_forecasts) to run
              and fail, to exercise the failure path. The real command for
              that step is NOT executed (a deliberate failing subprocess runs
              instead), so --fail-step imerg makes no network calls and
              touches no credentials.
"""
from __future__ import annotations

import argparse
import fcntl
import json
import os
import subprocess
import sys
import time
from datetime import date, datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import jsonschema

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "pipeline"))

EVENTS = ROOT / "events"
OUT_DIR = EVENTS / "forecast"
LOG_DIR = OUT_DIR / "logs"
LOCK_PATH = OUT_DIR / ".run_daily.lock"
STATUS_PATH = OUT_DIR / "status.json"
SCHEMA_PATH = ROOT / "pipeline" / "schemas" / "run_daily_status.schema.json"

GRID_PATH = EVENTS / "rain_history_grid_daily.json"
SCORES_PATH = OUT_DIR / "scores.json"

LAGOS = ZoneInfo("Africa/Lagos")
IMERG_LAG_DAYS = 5     # refresh the satellite history when it ends this far behind today
TAIL_LINES = 20        # lines of step output logged on failure

VENV_PY = ROOT / "pipeline" / ".venv" / "bin" / "python"
STEPS = {
    "forecast": [str(VENV_PY), "pipeline/forecast.py"],
    "imerg": [str(VENV_PY), "pipeline/imerg_history_grid.py"],
    "score_forecasts": [str(VENV_PY), "pipeline/score_forecasts.py"],
}


def now_iso() -> str:
    return datetime.now(LAGOS).isoformat(timespec="seconds")


def log(line: str) -> None:
    stamp = now_iso()
    with (LOG_DIR / f"run_daily-{stamp[:7]}.log").open("a", encoding="utf-8") as fh:
        fh.write(f"{stamp} {line}\n")
    print(line, flush=True)


def run_step(name: str, command: list[str]) -> dict:
    """Run one step, log the outcome, return its status record."""
    started = now_iso()
    log(f"step {name} start")
    t0 = time.monotonic()
    proc = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
    seconds = round(time.monotonic() - t0, 1)
    finished = now_iso()
    record = {
        "status": "ok" if proc.returncode == 0 else "failed",
        "started_at": started,
        "finished_at": finished,
        "exit_code": proc.returncode,
        "seconds": seconds,
    }
    if proc.returncode == 0:
        log(f"step {name} ok exit=0 duration={seconds}s")
    else:
        log(f"step {name} FAILED exit={proc.returncode} duration={seconds}s; last output:")
        lines = (proc.stdout.strip().splitlines() + proc.stderr.strip().splitlines())[-TAIL_LINES:]
        for line in lines:
            log(f"  | {line}")
    return record


def fail_step_command(name: str) -> list[str]:
    """A command that fails on purpose; the real step command is never run."""
    message = f"step {name} failed on purpose (--fail-step)"
    return [str(VENV_PY), "-c", f"import sys; sys.exit({message!r})"]


def imerg_state() -> tuple[date | None, str | None]:
    """(last day the grid history has a value for, when it was last refreshed).

    "Ends" is defined exactly as score_forecasts.py's imerg_last_day: the
    last date in grid['dates'] that has a value for at least one cell.
    """
    if not GRID_PATH.is_file():
        return None, None
    grid = json.loads(GRID_PATH.read_text(encoding="utf-8"))
    dates = grid["dates"]
    series = grid["series"].values()
    through = None
    for index in range(len(dates) - 1, -1, -1):
        if any(cell["total_mm"][index] is not None for cell in series):
            through = date.fromisoformat(dates[index])
            break
    return through, grid["meta"].get("retrieved_at")


def n_scored() -> int | None:
    if not SCORES_PATH.is_file():
        return None
    return json.loads(SCORES_PATH.read_text(encoding="utf-8")).get("n_scored")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--skip-imerg", action="store_true",
        help="never run the IMERG step (testing; the Earthdata refresh is run by the owner)",
    )
    parser.add_argument(
        "--fail-step", choices=list(STEPS), metavar="STEP",
        help="debug: force STEP to run and fail, to exercise the failure path "
             "(the real command for that step is not executed)",
    )
    args = parser.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    # ---- single instance ---------------------------------------------------
    lock = LOCK_PATH.open("w")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        print("already running")
        log("another run is already in progress; exiting")
        return

    run_started = now_iso()
    log(f"run_daily start pid={os.getpid()} "
        f"skip_imerg={args.skip_imerg} fail_step={args.fail_step}")
    steps: dict[str, dict] = {}
    failures = 0

    # ---- 1. forecast: every day ---------------------------------------------
    if args.fail_step == "forecast":
        steps["forecast"] = run_step("forecast", fail_step_command("forecast"))
    else:
        steps["forecast"] = run_step("forecast", STEPS["forecast"])
    failures += steps["forecast"]["status"] == "failed"

    # ---- 2. IMERG: only when 5+ days behind, at most once a day ------------
    through, retrieved_at = imerg_state()
    today = datetime.now(LAGOS).date()
    imerg_ran = False
    if args.fail_step == "imerg":
        steps["imerg"] = run_step("imerg", fail_step_command("imerg"))
    elif args.skip_imerg:
        steps["imerg"] = {"status": "skipped", "at": now_iso(), "reason": "--skip-imerg"}
    elif through is None:
        steps["imerg"] = run_step("imerg", STEPS["imerg"])
    elif retrieved_at and retrieved_at[:10] == datetime.now(timezone.utc).date().isoformat():
        steps["imerg"] = {
            "status": "skipped", "at": now_iso(),
            "reason": f"already refreshed today (retrieved_at {retrieved_at})",
        }
    elif (today - through).days >= IMERG_LAG_DAYS:
        steps["imerg"] = run_step("imerg", STEPS["imerg"])
    else:
        steps["imerg"] = {
            "status": "skipped", "at": now_iso(),
            "reason": f"IMERG history ends {through.isoformat()} "
                      f"({(today - through).days} days behind, fewer than {IMERG_LAG_DAYS})",
        }
    imerg_ran = steps["imerg"]["status"] == "ok"
    if steps["imerg"]["status"] == "skipped":
        log(f"step imerg skipped: {steps['imerg']['reason']}")
    failures += steps["imerg"]["status"] == "failed"

    # ---- 3. score: after a successful IMERG refresh, or when missing --------
    if args.fail_step == "score_forecasts":
        steps["score_forecasts"] = run_step(
            "score_forecasts", fail_step_command("score_forecasts"))
    elif imerg_ran or not SCORES_PATH.is_file():
        steps["score_forecasts"] = run_step("score_forecasts", STEPS["score_forecasts"])
    else:
        steps["score_forecasts"] = {
            "status": "skipped", "at": now_iso(),
            "reason": "no IMERG refresh this run and scores.json exists",
        }
        log(f"step score_forecasts skipped: {steps['score_forecasts']['reason']}")
    failures += steps["score_forecasts"]["status"] == "failed"

    # ---- status -------------------------------------------------------------
    if imerg_ran:
        through, _ = imerg_state()
    status = {
        "meta": {
            "built_by": "pipeline/run_daily.py",
            "task": "45-daily-run (docs/tasks/45-daily-run.md)",
            "schema": "pipeline/schemas/run_daily_status.schema.json",
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        },
        "last_run": run_started,
        "ok": failures == 0,
        "steps": steps,
        "imerg_through": through.isoformat() if through else None,
        "n_scored": n_scored(),
    }
    jsonschema.validate(status, json.loads(SCHEMA_PATH.read_text(encoding="utf-8")))
    STATUS_PATH.write_text(json.dumps(status, indent=2, allow_nan=False) + "\n",
                           encoding="utf-8")

    counts = {s: sum(1 for record in steps.values() if record["status"] == s)
              for s in ("ok", "skipped", "failed")}
    log(f"run_daily done exit={1 if failures else 0} "
        f"({counts['ok']} ok, {counts['skipped']} skipped, {counts['failed']} failed)")
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
