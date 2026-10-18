# Task 04 — GPM IMERG 30-minute rainfall for an event

Context: `docs/LAGOS_PLAN.md`, `events/lagos-2024-07-03/dossier.md` (§2, §3 hypothesis 1 "tidal lock"), `event.json`.

NASA Earthdata credentials are already stored in `~/.netrc` (`machine urs.earthdata.nasa.gov`). **Never print, copy or log
that file or the password.** Use it only via standard netrc handling (e.g. `requests` session with `trust_env`, or `earthaccess`
with `strategy="netrc"`).

## Write `pipeline/imerg.py`
`pipeline/.venv/bin/python pipeline/imerg.py events/lagos-2024-07-03`

1. Product: **GPM_3IMERGHH v07** (Final run, half-hourly, 0.1°) from NASA GES DISC. If Final isn't available for a date, fall back to
   Late run (`GPM_3IMERGHHL`) and record which run was used per timestep.
2. Use OPeNDAP or file download subset to the AOI bbox from `event.json` (pad by 0.1°) — **don't keep whole global files**; delete
   any temporary global HDF5 after subsetting. Time range = `window`.
3. Variable `precipitation` (mm/h). IMERG times are UTC; convert to the event timezone for output.
4. Outputs in `events/lagos-2024-07-03/`:
   - `rainfall_imerg.json` — `meta` (product, version, run, DOI, URLs, retrieved_at, licence "NASA open data", grid resolution,
     note: "satellite estimate; ~10 km cells smooth point intensities"), `times` (ISO with offset), and per `aoi.points` entry
     (except `offshore_tide`) the half-hourly series from the containing cell + the AOI-mean series.
   - `rainfall_imerg_grid.json` — compact grid for the map: lon/lat cell centres + a 2D array per timestep (mm/h, 2 decimals),
     only for the `focus` window to keep it small.
   - `rainfall_summary.json` — per point: max 30-min intensity (+ time), totals for 1/3/6/24 h ending at the max,
     7-day antecedent total before `focus.start`, and the time of rain onset (first ≥ 2 mm/h after ≥ 6 h of < 0.5 mm/h).
5. Add the needed packages to `pipeline/requirements.txt` (e.g. `earthaccess`, `h5py` or `xarray`+`netCDF4`/`pydap`) and install
   into `pipeline/.venv`.
6. Run it once and print the summary: run used, number of timesteps, per-point max intensity + time, onset time, 24 h totals.

Don't touch `src/`. Don't commit. If GES DISC returns 401/403, stop and report it — it usually means the
"NASA GESDISC DATA ARCHIVE" application hasn't been authorized in the Earthdata profile.
