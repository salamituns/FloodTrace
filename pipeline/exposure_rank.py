#!/usr/bin/env python3
"""Task 10 - exposure-weighted ranking of the rainfall candidates.

Ranks the Task 07 grid candidates (events/catalog_candidates_grid.json) by
rain-where-people-are instead of by the single wettest cell:

  * GHS-POP R2023A population (JRC, CC BY 4.0), 30 arc-sec WGS84, epochs
    2000..2025, aggregated onto the 68 IMERG cells from Task 07.
  * Per candidate, using the epoch nearest the event year:
      pop_exposed_50mm        people in cells whose candidate total >= 50 mm
      pop_exposed_30mmh       people in cells with any 30-min peak >= 30 mm/h
      pop_weighted_rain_mm    sum(total x pop) / sum(pop) over all cells
      urban_cells_over_threshold  cells over threshold among the cells that
                              hold the top 80% of the population
      suspect_peak            any cell peak > 70 mm/h
  * exposure_rank orders candidates by pop_exposed_50mm
    (ties broken by pop_weighted_rain_mm).

Only the GHS-POP tile covering the AOI is downloaded; it is clipped to the
AOI bbox (padded 0.1 deg) and only the clipped rasters are kept under
pipeline/cache/ghsl/ (zips and full tiles are deleted - disk is tight).

Outputs:
  events/exposure_cells.json    per-cell population for each epoch
  events/catalog_ranked.json     candidates + exposure fields, sorted by
                                 exposure_rank
"""

import json
import math
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import rasterio
import requests
from rasterio.windows import from_bounds

REPO = Path(__file__).resolve().parents[1]
CACHE = REPO / "pipeline" / "cache" / "ghsl"
EVENTS = REPO / "events"

EPOCHS = [2000, 2005, 2010, 2015, 2020, 2025]
DAILY_GRID = EVENTS / "rain_history_grid_daily.json"
CANDIDATES = EVENTS / "catalog_candidates_grid.json"
EXPOSURE_OUT = EVENTS / "exposure_cells.json"
RANKED_OUT = EVENTS / "catalog_ranked.json"

GHSL_BASE = (
    "https://jeodpp.jrc.ec.europa.eu/ftp/jrc-opendata/GHSL/GHS_POP_GLOBE_R2023A"
)
LICENCE = "CC BY 4.0 (European Union, GHSL R2023A)"

DAILY_TOTAL_THRESHOLD_MM = 50.0
INTENSITY_THRESHOLD_MM_H = 30.0
SUSPECT_PEAK_MM_H = 70.0
URBAN_POP_FRACTION = 0.80


def log(msg: str) -> None:
    print(msg, flush=True)


# ---------------------------------------------------------------------------
# GHS-POP tile download + clip
# ---------------------------------------------------------------------------

def tile_id_for(bbox: dict) -> tuple:
    """Row/column of the 10 deg GHS-POP 30ss tile covering the bbox."""
    lons = (bbox["min_lon"], bbox["max_lon"])
    lats = (bbox["min_lat"], bbox["max_lat"])
    cols = {math.floor((lon + 180.0) / 10.0) + 1 for lon in lons}
    rows = {math.floor((90.0 - lat) / 10.0) + 1 for lat in lats}
    if len(cols) != 1 or len(rows) != 1:
        raise SystemExit(f"AOI spans several GHS-POP tiles: rows {rows}, cols {cols}")
    return f"R{rows.pop()}_C{cols.pop()}"


def ghsl_urls(epoch: int, tile: str) -> tuple:
    name = f"GHS_POP_E{epoch}_GLOBE_R2023A_4326_30ss_V1_0"
    return (
        f"{GHSL_BASE}/GHS_POP_E{epoch}_GLOBE_R2023A_4326_30ss/V1-0/tiles/{name}_{tile}.zip",
        name,
    )


def download(url: str, dest: Path) -> None:
    log(f"  downloading {dest.name} ...")
    for attempt in range(1, 5):
        try:
            with requests.get(url, stream=True, timeout=300) as r:
                r.raise_for_status()
                with open(dest, "wb") as f:
                    for chunk in r.iter_content(chunk_size=1 << 20):
                        f.write(chunk)
            return
        except requests.RequestException as exc:
            if attempt == 4:
                raise
            log(f"  attempt {attempt} failed ({exc}); retrying in {5*attempt}s")
            time.sleep(5 * attempt)


def clip_ghsl(epoch: int, tile: str, bbox: dict) -> Path:
    """Ensure the AOI-clipped GHS-POP raster for `epoch` exists; return it."""
    clipped = CACHE / f"GHS_POP_E{epoch}_GLOBE_R2023A_4326_30ss_AOI.tif"
    if clipped.exists():
        return clipped

    url, name = ghsl_urls(epoch, tile)
    with tempfile.TemporaryDirectory(prefix="ghsl_") as tmp:
        tmp = Path(tmp)
        zip_path = tmp / f"{name}_{tile}.zip"
        download(url, zip_path)

        import zipfile

        with zipfile.ZipFile(zip_path) as zf:
            tif_members = [m for m in zf.namelist() if m.endswith(".tif")]
            if len(tif_members) != 1:
                raise SystemExit(f"expected one tif in {zip_path.name}, got {tif_members}")
            full_tif = tmp / Path(tif_members[0]).name
            with zf.open(tif_members[0]) as src_member, open(full_tif, "wb") as out:
                out.write(src_member.read())

        left, bottom = bbox["min_lon"], bbox["min_lat"]
        right, top = bbox["max_lon"], bbox["max_lat"]
        with rasterio.open(full_tif) as src:
            if src.crs is None or src.crs.to_epsg() != 4326:
                raise SystemExit(f"unexpected CRS {src.crs} in {full_tif.name}")
            bounds = src.bounds
            if not (bounds.left <= left and bounds.right >= right
                    and bounds.bottom <= bottom and bounds.top >= top):
                raise SystemExit(
                    f"tile {tile} ({bounds}) does not cover the AOI bbox "
                    f"({left}, {bottom}, {right}, {top})"
                )
            win = from_bounds(left, bottom, right, top, transform=src.transform)
            # expand the window to whole pixels so the bbox is fully covered
            col_off = math.floor(win.col_off)
            row_off = math.floor(win.row_off)
            width = math.ceil(win.col_off + win.width) - col_off
            height = math.ceil(win.row_off + win.height) - row_off
            win = rasterio.windows.Window(col_off, row_off, width, height)
            data = src.read(1, window=win)
            profile = src.profile.copy()

        data = np.asarray(data, dtype=np.float64)
        nodata = profile.get("nodata")
        if nodata is not None:
            data[data == nodata] = 0.0
        data[data < 0] = 0.0  # GHSL nodata flags (e.g. -200) -> no population

        profile.update(
            driver="GTiff", dtype="float32", nodata=None, count=1,
            height=data.shape[0], width=data.shape[1],
            transform=rasterio.windows.transform(win, profile["transform"]),
            compress="deflate",
        )
        with rasterio.open(clipped.with_suffix(".tif.tmp"), "w", **profile) as dst:
            dst.write(data.astype(np.float32), 1)
        clipped.with_suffix(".tif.tmp").rename(clipped)
    # zip and full tile lived in the temp dir: already gone; only the clipped
    # raster remains under pipeline/cache/ghsl/
    return clipped


# ---------------------------------------------------------------------------
# Population aggregation to the 68 IMERG cells
# ---------------------------------------------------------------------------

def cell_key(lon: float, lat: float) -> tuple:
    """Bin index of the 0.1 deg cell centred on (lon, lat).

    The cell spans [lon-0.05, lon+0.05) x [lat-0.05, lat+0.05); pixel centres
    are binned with floor(coord*10). Cell centres are odd multiples of 0.05,
    so centre*10 - 0.5 is an exact integer.
    """
    return (int(lon * 10 - 0.5), int(lat * 10 - 0.5))


def aggregate_population(clipped: Path, cells: list) -> dict:
    """Sum 30 arc-sec population pixels into the IMERG cells."""
    keys = {cell_key(c["lon"], c["lat"]): c["id"] for c in cells}
    pop = {c["id"]: 0.0 for c in cells}
    with rasterio.open(clipped) as src:
        data = np.asarray(src.read(1), dtype=np.float64)
        t = src.transform
    xs = t.c + (np.arange(data.shape[1]) + 0.5) * t.a
    ys = t.f + (np.arange(data.shape[0]) + 0.5) * t.e
    kx = np.floor(xs * 10 + 1e-9).astype(int)
    ky = np.floor(ys * 10 + 1e-9).astype(int)
    for i in range(data.shape[0]):
        row_key = ky[i]
        if row_key not in {k[1] for k in keys}:
            continue
        row = data[i]
        for j in range(data.shape[1]):
            cell_id = keys.get((kx[j], row_key))
            if cell_id is not None:
                pop[cell_id] += max(row[j], 0.0)
    return pop


# ---------------------------------------------------------------------------
# Exposure metrics
# ---------------------------------------------------------------------------

def nearest_epoch(year: int) -> int:
    return min(EPOCHS, key=lambda e: (abs(e - year), e))


def cell_over_threshold(total_mm, peak_mm_h) -> bool:
    if total_mm is None or peak_mm_h is None:
        return False
    return total_mm >= DAILY_TOTAL_THRESHOLD_MM or peak_mm_h >= INTENSITY_THRESHOLD_MM_H


def main() -> None:
    daily = json.loads(DAILY_GRID.read_text())
    cells = daily["meta"]["cells"]
    bbox = daily["meta"]["aoi_bbox"]  # [min_lon, min_lat, max_lon, max_lat]
    pad = 0.1
    padded = {
        "min_lon": bbox[0] - pad, "min_lat": bbox[1] - pad,
        "max_lon": bbox[2] + pad, "max_lat": bbox[3] + pad,
    }
    catalog = json.loads(CANDIDATES.read_text())
    candidates = catalog["candidates"]
    log(f"{len(cells)} cells, {len(candidates)} grid candidates, "
        f"AOI bbox padded to ({padded['min_lon']}, {padded['min_lat']}, "
        f"{padded['max_lon']}, {padded['max_lat']})")

    CACHE.mkdir(parents=True, exist_ok=True)
    tile = tile_id_for(padded)
    log(f"GHS-POP 30ss tile covering the AOI: {tile}")

    cell_pop = {}
    totals = {}
    for epoch in EPOCHS:
        clipped = clip_ghsl(epoch, tile, padded)
        pop = aggregate_population(clipped, cells)
        cell_pop[epoch] = pop
        totals[epoch] = sum(pop.values())
        log(f"  epoch {epoch}: AOI population {totals[epoch]:,.0f} "
            f"({clipped.name})")

    # ---- events/exposure_cells.json ----
    exposure = {
        "meta": {
            "source": "GHSL GHS-POP R2023A (JRC European Commission)",
            "product": [f"GHS_POP_E{e}_GLOBE_R2023A_4326_30ss_V1_0_{tile}" for e in EPOCHS],
            "resolution": "30 arc-sec (~1 km), WGS84",
            "epochs": EPOCHS,
            "licence": LICENCE,
            "urls": {e: ghsl_urls(e, tile)[0] for e in EPOCHS},
            "aoi_bbox": bbox,
            "aggregation": (
                "sum of 30 arc-sec population pixels whose centres fall in "
                "each 0.1 deg IMERG cell (cell spans centre +/- 0.05 deg); "
                "GHSL nodata values treated as zero population"
            ),
            "note": "clipped rasters cached under pipeline/cache/ghsl/",
            "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        },
        "cells": [
            {
                "id": c["id"], "lon": c["lon"], "lat": c["lat"], "place": c["place"],
                "population": {str(e): round(cell_pop[e][c["id"]], 1) for e in EPOCHS},
            }
            for c in cells
        ],
    }
    EXPOSURE_OUT.write_text(json.dumps(exposure, indent=1))
    log(f"wrote {EXPOSURE_OUT.name}")

    # ---- candidate exposure metrics ----
    ranked = []
    for cand in candidates:
        year = int(cand["start"][:4])
        epoch = nearest_epoch(year)
        pop = cell_pop[epoch]
        pop_total = sum(pop.values())

        pop_50 = 0.0
        pop_30 = 0.0
        weighted_rain = 0.0
        qualifying = {}
        for cell_id, vals in cand["cells"].items():
            p = pop.get(cell_id, 0.0)
            total = vals.get("total_mm")
            peak = vals.get("max_30min_mm_h")
            weighted_rain += (total or 0.0) * p
            if total is not None and total >= DAILY_TOTAL_THRESHOLD_MM:
                pop_50 += p
            if peak is not None and peak >= INTENSITY_THRESHOLD_MM_H:
                pop_30 += p
            if cell_over_threshold(total, peak):
                qualifying[cell_id] = True
        pop_weighted_rain = weighted_rain / pop_total if pop_total else 0.0

        # urban cells = those holding the top 80% of population
        by_pop = sorted(pop.items(), key=lambda kv: kv[1], reverse=True)
        cum = 0.0
        urban = []
        for cell_id, p in by_pop:
            urban.append(cell_id)
            cum += p
            if cum >= URBAN_POP_FRACTION * pop_total:
                break
        urban_over = sum(1 for cell_id in urban if qualifying.get(cell_id))

        rec = dict(cand)  # all original fields, incl. rank/cells/max_cell/...
        rec.update({
            "pop_epoch": epoch,
            "pop_exposed_50mm": round(pop_50, 0),
            "pop_exposed_30mmh": round(pop_30, 0),
            "pop_weighted_rain_mm": round(pop_weighted_rain, 2),
            "urban_cells": len(urban),
            "urban_cells_over_threshold": urban_over,
            "suspect_peak": bool(cand["max_peak_mm_h"] is not None
                                 and cand["max_peak_mm_h"] > SUSPECT_PEAK_MM_H),
        })
        ranked.append(rec)

    ranked.sort(key=lambda r: (-r["pop_exposed_50mm"],
                               -r["pop_weighted_rain_mm"], r["start"]))
    for i, rec in enumerate(ranked, 1):
        rec["exposure_rank"] = i
    # Primary order: population-weighted rain. Absolute exposure saturates (dozens of candidates expose >90 % of the AOI),
    # so it mostly reflects the population epoch (recency), not the storm; pwr is epoch-independent and discounts the
    # rural fringe. With the 5 known floods (2011, 2022, Aug 2025, Jul 2024, 2017) it places all in the top ~22 of 641.
    ranked.sort(key=lambda r: (-r["pop_weighted_rain_mm"], -r["pop_exposed_50mm"], r["start"]))
    for i, rec in enumerate(ranked, 1):
        rec["pwr_rank"] = i

    out = {
        "meta": {
            "source": "exposure-weighted ranking of events/catalog_candidates_grid.json",
            "population_source": "GHSL GHS-POP R2023A, 30 arc-sec WGS84, CC BY 4.0",
            "epochs": EPOCHS,
            "epoch_rule": "epoch nearest the candidate start year",
            "population_file": EXPOSURE_OUT.name,
            "fields": {
                "pop_exposed_50mm": "people in cells whose candidate total >= 50 mm",
                "pop_exposed_30mmh": "people in cells with any 30-min peak >= 30 mm/h",
                "pop_weighted_rain_mm": "sum(cell total x cell pop) / sum(cell pop)",
                "urban_cells": "cells holding the top 80% of the AOI population",
                "urban_cells_over_threshold": "cells over threshold among the urban cells",
                "suspect_peak": "any cell 30-min peak > 70 mm/h",
                "pwr_rank": "PRIMARY: rank by pop_weighted_rain_mm (epoch-independent)",
                "exposure_rank": "secondary: rank by pop_exposed_50mm (saturates; skews recent)",
            },
            "thresholds": {
                "daily_total_mm": DAILY_TOTAL_THRESHOLD_MM,
                "max_30min_mm_h": INTENSITY_THRESHOLD_MM_H,
                "suspect_peak_mm_h": SUSPECT_PEAK_MM_H,
            },
            "note": "records keep all Task 07 fields; 'rank' is the Task 07 "
                    "severity rank; records are sorted by 'pwr_rank' (population-weighted rain); "
                    "'exposure_rank' orders by pop_exposed_50mm (ties by pop_weighted_rain_mm)",
            "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        },
        "candidates": ranked,
    }
    RANKED_OUT.write_text(json.dumps(out, indent=1))
    log(f"wrote {RANKED_OUT.name}")

    # ---- summary ----
    log("")
    log("== AOI population per epoch (68 IMERG cells) ==")
    for epoch in EPOCHS:
        log(f"  {epoch}: {totals[epoch]:>12,.0f}")
    log("  sanity check: ~8-9 M in 2000 rising to ~15-17 M in 2025 expected "
        "for this AOI; see report for commentary")

    log("")
    log("== top 25 by exposure_rank ==")
    log(f"{'#':>3}  {'dates':<24} {'pop>=50mm':>12} {'pop>=30mm/h':>12} "
        f"{'pop-rain':>9} {'cells':>5} {'urban':>6}  {'max cell':<16} {'mm':>7}  flags")
    for rec in ranked[:25]:
        days = rec["start"] if rec["start"] == rec["end"] else f'{rec["start"]}..{rec["end"]}'
        flags = []
        if rec["suspect_peak"]:
            flags.append("SUSPECT")
        if rec["known_event_id"]:
            flags.append(rec["known_event_id"])
        log(f"{rec['exposure_rank']:>3}  {days:<24} {rec['pop_exposed_50mm']:>12,.0f} "
            f"{rec['pop_exposed_30mmh']:>12,.0f} {rec['pop_weighted_rain_mm']:>9.1f} "
            f"{rec['cells_over_threshold']:>5} {rec['urban_cells_over_threshold']:>3}/{rec['urban_cells']:<2} "
            f"{rec['max_cell']['place']:<16} {rec['max_cell_total_mm']:>7.1f}  {','.join(flags)}")

    log("")
    log("== key events (severity rank -> exposure rank) ==")
    for date in ("2011-07-10", "2022-07-08", "2025-08-03", "2024-07-02",
                 "2024-07-03", "2017-07-05"):
        match = next((r for r in ranked if r["start"] <= date <= r["end"]), None)
        if match is None:
            log(f"  {date}: no candidate covers this date")
            continue
        days = match["start"] if match["start"] == match["end"] else f'{match["start"]}..{match["end"]}'
        log(f"  {date} ({days}): severity rank {match['rank']} -> exposure rank "
            f"{match['exposure_rank']}; {match['pop_exposed_50mm']:,.0f} people "
            f"exposed >= 50 mm, pop-weighted rain {match['pop_weighted_rain_mm']:.1f} mm"
            + (f"; known: {match['known_event_id']}" if match["known_event_id"] else ""))

    n_suspect = sum(1 for r in ranked if r["suspect_peak"])
    log("")
    log(f"suspect peaks (> {SUSPECT_PEAK_MM_H:.0f} mm/h in any cell): {n_suspect} of {len(ranked)}")


if __name__ == "__main__":
    try:
        main()
    except SystemExit as exc:
        log(f"FATAL: {exc}")
        sys.exit(1)
