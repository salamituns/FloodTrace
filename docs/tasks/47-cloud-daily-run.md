# Task 47: run the daily forecast in GitHub Actions

Read `docs/FORECAST.md`, `pipeline/run_daily.py`, `pipeline/imerg.py`, `pipeline/imerg_history_grid.py`, `pipeline/tide_eot20.py` and the tide code in `pipeline/forecast.py` first.

## Why
FloodTrace is going public for people in Lagos. The site will be on Cloudflare Pages, rebuilt on every push to `main`. The daily run must happen in the cloud, with nobody's laptop involved:
1. a GitHub Actions job runs `run_daily.py`;
2. it commits the new forecast;
3. Cloudflare redeploys.

On a fresh runner, three things block that today. Fix them so the pipeline runs on a clean machine.

## Do
1. **Credentials from the environment (`pipeline/imerg.py`).** If `EARTHDATA_USERNAME` and `EARTHDATA_PASSWORD` are already set in the environment, use them and don't require `.env`. Otherwise, keep today's `.env` parsing exactly as it is.
   - Never print, log or echo the values. Never write them to a file.
   - The error message for missing credentials must name both options, without showing values.
2. **Tides without the 2.1 GB model.** Tides are deterministic, so precompute them.
   - Add `pipeline/tide_table.py`. Using the existing EOT20 code and the local model in `pipeline/cache/tide_models/`, it writes `events/forecast/tide_table.json`: hourly tide height at every point `forecast.py` uses, from 2026-01-01 to 2031-01-01, with the model, the datum and the points in `meta`.
   - Keep it small: round to the centimetre, store a compact array per point, and aim for under 3 MB. Report the size.
   - `forecast.py` reads the table when the forecast window is inside it, and falls back to computing live otherwise. It fails with a clear message if neither is available.
   - **Check:** for today's run, the high tides and the near-high-tide flags from the table must be identical to the live computation. Diff the two outputs and show it.
3. **Incremental IMERG refresh (`imerg_history_grid.py`).** Add `--update`:
   - read the committed `events/rain_history_grid_daily.json`;
   - fetch only from (its last day − 7 days) to today, to catch NASA's late-arriving data;
   - merge, with new values replacing old ones on overlapping days;
   - leave every earlier day byte-identical.
   - Work without `pipeline/cache/imerg_history/` present.
   - `run_daily.py` must call the IMERG step with `--update`.
   - Write the merge as a pure function, and add a unit test for it with synthetic data. **You can't run the real fetch** (no credentials), and you must not try.
4. **The workflow: `.github/workflows/daily.yml`.**
   - **Triggers:** `schedule: cron '30 5 * * *'` (06:30 Lagos, which is UTC+1 with no daylight saving), plus `workflow_dispatch` for manual runs.
   - **Steps:** checkout, then Python 3 (match the venv's minor version) with pip cache from `pipeline/requirements.txt`, then `python pipeline/run_daily.py`.
     - Put the secrets in `env` *only on that step*: `EARTHDATA_USERNAME: ${{ secrets.EARTHDATA_USERNAME }}` and the same for the password.
     - `run_daily.py` uses `pipeline/.venv/bin/python`. Make the interpreter configurable: default to `sys.executable` when the venv doesn't exist.
   - **Commit only if something changed**, and only these paths: `events/forecast/`, `events/rain_history_grid_daily.json` and the status file. Author it as `github-actions[bot]`, with a message like `Daily forecast 2026-10-23`, then push.
     - Handle a race with a human push: `git pull --rebase` and retry once.
   - `permissions: contents: write` and nothing more; `concurrency: daily-forecast`; `timeout-minutes: 30`.
   - **If the run fails:** the job must still commit `status.json` if the forecast step succeeded, and then fail visibly, so GitHub emails the owner.
   - Make sure `run_daily.py` doesn't need the lock directory or the logs folder to pre-exist. On CI the logs go to the job output; don't commit them.
5. **Repo growth.** Each daily forecast file is about 0.5 MB, which is about 200 MB a year in git history.
   - Measure how well consecutive runs delta-compress. Make a temporary bare repo in `/tmp`, commit 3 runs and use `git count-objects -v`.
   - If it's poor, propose (don't implement) a fix in the docs.
6. **Docs.** In `docs/FORECAST.md`:
   - the cloud run is now the primary way to run;
   - the Mac LaunchAgent is optional;
   - the secrets the owner must add (names only), and how to trigger a manual run;
   - how to read a failed run.

## Check
- Simulate a clean runner locally:
  - hide the tide model *without deleting or moving anything*: point the code at an empty directory through an env var or argument;
  - run `pipeline/.venv/bin/python pipeline/run_daily.py --skip-imerg`.

  The forecast must succeed from `tide_table.json` alone.
- The tide diff from step 2 shows no change.
- The merge unit test passes.
- `.env` handling is unchanged: with no env vars set, the loader still reads `.env`. Prove this by reading the code path, **not by running it**.
- Run `actionlint` on the workflow if it's installed. Otherwise, at least parse the YAML.
- `npx tsc --noEmit`, `npm run build` and `npx tsx scripts/check-forecast.ts` all pass.

## Rules
- Foreground only.
- No `rm -rf`.
- Don't commit or push.
- Don't read `.env`.
- Don't run the IMERG fetch.
- Don't start a dev server or open a browser.
- Cursor is working on Task 48 in `src/`, `README.md`, `LICENSE` and the media-evidence data. Don't touch those.
