# Task 45: run the forecast every day, and keep score by itself

Read `docs/FORECAST.md` first.

## Why
The forecast is only useful if it is fresh. It only earns trust if we keep checking it against what actually fell. Today both steps are manual. The app already marks a forecast older than 36 hours as out of date (`forecastFreshness` in `src/lib/forecast.ts`), so a missed run shows up honestly. The aim is to make missed runs rare.

## Do
1. **`pipeline/run_daily.py`**: one entry point that runs the steps in order, each as a subprocess with the venv's Python:
   1. `forecast.py`, every day.
   2. `imerg_history_grid.py`, which refreshes the satellite rain. Run it only when `events/rain_history_grid_daily.json` ends 5 or more days before today, and at most once a day. Check its arguments (`--start/--end`) and pass the narrowest range that brings it up to date, if it supports one. It reads the Earthdata login from `.env` by itself.
      - **You must not read `.env`.**
      - **You must not run this step yourself.** Add a `--skip-imerg` flag and use it in all your test runs. I will run the IMERG step.
   3. `score_forecasts.py`, after any successful IMERG refresh. It also runs on its own if `scores.json` is missing.

   **Behaviour:**
   - **Single instance.** Use a lock file (`events/forecast/.run_daily.lock`, with `fcntl.flock`) so two runs never overlap.
   - **Failures.** If a step fails, log it and carry on to the next independent step. For example, IMERG failing must not stop today's forecast, which runs first anyway. Exit non-zero if any step failed.
   - **Logs.** Write to `events/forecast/logs/run_daily-YYYY-MM.log`, one file per month. Each step gets a timestamp, the step name, its duration and its exit code, plus the last 20 lines of its output on failure. Add `events/forecast/logs/` and the lock file to `.gitignore`.
   - **Status file.** After every run, write `events/forecast/status.json` with:
     - `last_run`;
     - per step: `ok`, `skipped` or `failed`, plus a time;
     - `imerg_through`;
     - `n_scored` from `scores.json`.

     Add a schema for it next to the others.
   - **No secrets anywhere.** Never pass credentials as arguments, and never echo the environment.
2. **macOS schedule: `ops/com.floodtrace.daily.plist`**, a launchd LaunchAgent template.
   - Run `run_daily.py` at 06:30 local time every day.
   - Set `WorkingDirectory`.
   - Point `StandardOutPath` and `StandardErrorPath` into the logs folder.
   - Use `__REPO__` as a placeholder for the repo path.
   - Why launchd rather than cron: launchd runs a missed job once when a sleeping Mac wakes; cron just skips it. Say this in a comment.
3. **`ops/install_daily.sh` and `ops/uninstall_daily.sh`.**
   - Install: fill `__REPO__` with the repo's absolute path, copy the plist to `~/Library/LaunchAgents/`, then `launchctl bootstrap gui/$(id -u) …`.
   - Uninstall: `launchctl bootout …` and delete that one plist file with `rm -f` on its exact path. Nothing else.
   - **Don't run install yourself.** I will, after checking.
4. **Docs.** Replace "Run it daily" in `docs/FORECAST.md`. Cover:
   - what runs when;
   - how to install and uninstall;
   - where the logs and `status.json` are;
   - how to check the last run;
   - what the 36-hour "out of date" line in the app means.

## Check
- `pipeline/.venv/bin/python pipeline/run_daily.py --skip-imerg` runs end to end today.
  - Run it twice. The second run reuses today's cache and archives a time-suffixed file, as `forecast.py` already does.
  - Show me the `status.json` and the log lines.
- Start two runs at once by hand, *both in the foreground in one shell command* (for example `python … & python …; wait`). The second must exit cleanly with "already running". This is the one allowed exception to "no background processes", and only for this test.
- Simulate a failing step, for example with a temporary env var that makes `score_forecasts` fail. The run must log it, still write the status, and exit non-zero. Remove the test hook afterwards, or keep it as a documented `--fail-step` debug flag.
- `plutil -lint ops/com.floodtrace.daily.plist` passes.
- `npx tsc --noEmit`, `npm run build` and `npx tsx scripts/check-forecast.ts` all pass.

## Rules
- Foreground only, except the one lock test above.
- No `rm -rf`.
- Don't commit.
- Don't read `.env`.
- Don't run the IMERG step.
- Don't install the LaunchAgent.
- Don't start a dev server or open a browser.
- Cursor is working on Task 46 in `pipeline/compare_models.py` and `pipeline/cache/hindcast/`. Don't touch those, `hindcast.py` or `calibrate.py`.
