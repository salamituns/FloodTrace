#!/usr/bin/env python3
"""Task 16 - built-up change in Lagos (GHSL GHS-BUILT-S) vs flood evidence.

Measures how much the Lagos AOI has been built over since 2000 and tests
whether places with flood evidence gained more built-up surface than
equally-built places that were never reported:

  * GHS-BUILT-S R2023A (JRC, CC BY 4.0), 100 m Mollweide (ESRI:54009),
    epochs 1975/1990/2000/2010/2020/2025, tile R9_C19 - only the AOI-clipped
    rasters are kept under pipeline/cache/ghsl/ (zips and full tiles deleted).
  * 0.01 deg (~1 km) grid over bbox [2.6, 6.28, 4.45, 6.85]:
    built_frac per epoch = GHSL built-up m2 (pixels binned by centre) /
    cell area measured on the equal-area Mollweide plane.
    -> events/builtup_grid.geojson
  * Evidence test: points from events/*/evidence.geojson
    (location_confidence 'lga' excluded, duplicates within 200 m in the same
    event removed), each compared with 20 random land cells matched on
    b2020 within +/- 0.05; medians, share above the matched-background median
    and a 10,000-shuffle stratified permutation test (fixed seed), repeated
    for points within 2 km of the Lagos/Lekki lagoon shore.
    -> events/builtup_evidence_test.json

Land/water for the background "land cell" definition: ESA WorldCover 10 m
v200 (2021), class 80 = water, sampled at 80 m over each cell centre + 4
quarter points.  Lagoon shoreline: OSM relations 2116203 (Lagos Lagoon) and
2116202 (Lekki Lagoon), ODbL.
"""

import json
import math
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import rasterio
import requests
from pyproj import Transformer
from rasterio.enums import Resampling
from rasterio.windows import from_bounds
from shapely import transform as shapely_transform
from shapely.geometry import LineString, MultiLineString, Point
from shapely.ops import linemerge

REPO = Path(__file__).resolve().parents[1]
CACHE_GHSL = REPO / "pipeline" / "cache" / "ghsl"
CACHE_WC = REPO / "pipeline" / "cache" / "worldcover"
CACHE_OSM = REPO / "pipeline" / "cache" / "osm"
EVENTS = REPO / "events"

AOI = [2.6, 6.28, 4.45, 6.85]          # [min_lon, min_lat, max_lon, max_lat]
LON0, LAT0 = AOI[0], AOI[1]
CELL = 0.01
NX = int(round((AOI[2] - LON0) / CELL))   # 185
NY = int(round((AOI[3] - LAT0) / CELL))   # 57

EPOCHS = [1975, 1990, 2000, 2010, 2020, 2025]
GHSL_BASE = "https://jeodpp.jrc.ec.europa.eu/ftp/jrc-opendata/GHSL/GHS_BUILT_S_GLOBE_R2023A"
GHSL_TILE = "R9_C19"                    # 1 Mm x 1 Mm Mollweide tile covering the AOI
GHSL_PRODUCT = "GHS_BUILT_S_E{epoch}_GLOBE_R2023A_54009_100_V1_0"
GHSL_LICENCE = "CC BY 4.0 (European Union, GHSL R2023A)"
GHSL_OBSERVED_NOTE = (
    "GHSL R2023A built-up epochs come from spatial-temporal interpolation of five "
    "observed image collections: Landsat (MSS, TM, ETM) supports 1975, 1990, 2000 and "
    "2014, the Sentinel-2 composite (GHS-composite-S2 R2020A) supports 2018 (JRC Data "
    "Catalogue). Epochs between observations (1995, 2005, 2010, 2015, 2020) are "
    "interpolated; 2025 (and 2030) are projections past the last observed epoch, not "
    "observations."
)
CLIP_PAD_M = 2000.0                    # Mollweide metres of clip padding around the AOI

WORLDCOVER_TILES = (
    "https://esa-worldcover.s3.eu-central-1.amazonaws.com/v200/2021/map/"
    "ESA_WorldCover_10m_2021_v200_N06E000_Map.tif",
    "https://esa-worldcover.s3.eu-central-1.amazonaws.com/v200/2021/map/"
    "ESA_WorldCover_10m_2021_v200_N06E003_Map.tif",
)
WORLDCOVER_LICENCE = "CC BY 4.0 (ESA WorldCover 10 m v200, 2021)"
WC_PAD = 0.05                          # degrees: land mask sampled on the padded AOI
WC_LVL = 8                             # 10 m / 8 = ~80 m decimated reads
WATER_CLASS = 80
NODATA_CLASS = 0

LAGOON_RELS = {2116203: "Lagos Lagoon", 2116202: "Lekki Lagoon"}
OSM_LICENCE = "ODbL (OpenStreetMap contributors)"
OSM_UA = {"User-Agent": "FloodTrace/0.1 (research)"}
LAGOON_DIST_M = 2000.0
METRIC_CRS = "EPSG:32631"              # UTM 31N: metric, covers the whole AOI

EVIDENCE_TRIES = 6
EVIDENCE_RETRY_WAIT = 60               # another agent may be writing these files
BG_N = 20
BG_TOL = 0.05
DEDUP_M = 200.0
PERM_N = 10000
SEED = 20261017

GRID_OUT = EVENTS / "builtup_grid.geojson"
TEST_OUT = EVENTS / "builtup_evidence_test.json"

TR_4326_54009 = Transformer.from_crs("EPSG:4326", "ESRI:54009", always_xy=True)
TR_54009_4326 = Transformer.from_crs("ESRI:54009", "EPSG:4326", always_xy=True)
TR_4326_UTM = Transformer.from_crs("EPSG:4326", METRIC_CRS, always_xy=True)


def log(msg: str) -> None:
    print(msg, flush=True)


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _download_curl(url: str, dest: Path) -> None:
    subprocess.run(
        ["curl", "-sS", "--fail", "-L", "--max-time", "600", "-o", str(dest), url],
        check=True)


def _download_requests(url: str, dest: Path) -> None:
    with requests.get(url, stream=True, timeout=600,
                      headers={"User-Agent": "FloodTrace/0.1 (research)"}) as r:
        r.raise_for_status()
        with open(dest, "wb") as f:
            for chunk in r.iter_content(chunk_size=1 << 20):
                f.write(chunk)


def download(url: str, dest: Path, tries: int = 8) -> None:
    """Download to dest.  The JRC portal intermittently answers 404 to
    valid URLs over HTTP/1.1 (python-requests) while serving the same URL
    over HTTP/2 (curl), so curl is preferred with requests as fallback
    and 404s are waited out."""
    log(f"  downloading {dest.name} ...")
    last_exc = None
    for attempt in range(1, tries + 1):
        try:
            _download_curl(url, dest)
            return
        except (OSError, subprocess.SubprocessError) as exc:
            last_exc = exc
            log(f"  curl failed ({exc}); trying python-requests")
        try:
            _download_requests(url, dest)
            return
        except requests.RequestException as exc:
            last_exc = exc
            if attempt == tries:
                raise
            wait = (45 if getattr(exc, "response", None) is not None
                    and exc.response.status_code == 404 else 10 * attempt)
            log(f"  attempt {attempt} failed ({exc}); retrying in {wait}s")
            time.sleep(wait)
    raise last_exc


def aoi_mollweide() -> tuple:
    lons = [AOI[0], AOI[0], AOI[2], AOI[2]]
    lats = [AOI[1], AOI[3], AOI[1], AOI[3]]
    xs, ys = TR_4326_54009.transform(lons, lats)
    return min(xs), min(ys), max(xs), max(ys)


# ---------------------------------------------------------------------------
# GHSL GHS-BUILT-S tile download + AOI clip
# ---------------------------------------------------------------------------

def clip_builtup(epoch: int, moll_bbox: tuple) -> Path:
    """Ensure the AOI-clipped GHS-BUILT-S raster for `epoch` exists."""
    clipped = CACHE_GHSL / f"GHS_BUILT_S_E{epoch}_GLOBE_R2023A_54009_100_AOI.tif"
    if clipped.exists():
        return clipped

    prod = GHSL_PRODUCT.format(epoch=epoch)
    url = (f"{GHSL_BASE}/{prod}/V1-0/tiles/{prod}_{GHSL_TILE}.zip")
    staged = CACHE_GHSL / f"{prod}_{GHSL_TILE}.zip"
    with tempfile.TemporaryDirectory(prefix="ghsl_builtup_") as tmp:
        tmp = Path(tmp)
        zip_path = tmp / f"{prod}_{GHSL_TILE}.zip"
        if staged.exists():
            # pre-staged zip (e.g. fetched from the shell: the JRC portal is
            # flaky about 404s); it is deleted after a successful clip
            zip_path.write_bytes(staged.read_bytes())
        else:
            download(url, zip_path)

        import zipfile
        with zipfile.ZipFile(zip_path) as zf:
            tif_members = [m for m in zf.namelist() if m.endswith(".tif")]
            if len(tif_members) != 1:
                raise SystemExit(f"expected one tif in {zip_path.name}, got {tif_members}")
            full_tif = tmp / Path(tif_members[0]).name
            with zf.open(tif_members[0]) as src_member, open(full_tif, "wb") as out:
                out.write(src_member.read())

        left, bottom, right, top = moll_bbox
        with rasterio.open(full_tif) as src:
            if src.crs is None or "54009" not in src.crs.to_string():
                raise SystemExit(f"unexpected CRS {src.crs} in {full_tif.name}")
            bounds = src.bounds
            if not (bounds.left <= left and bounds.right >= right
                    and bounds.bottom <= bottom and bounds.top >= top):
                raise SystemExit(
                    f"tile {GHSL_TILE} ({bounds}) does not cover the AOI window "
                    f"({left:.0f}, {bottom:.0f}, {right:.0f}, {top:.0f})")
            win = from_bounds(left - CLIP_PAD_M, bottom - CLIP_PAD_M,
                              right + CLIP_PAD_M, top + CLIP_PAD_M,
                              transform=src.transform)
            col_off = math.floor(win.col_off)
            row_off = math.floor(win.row_off)
            width = math.ceil(win.col_off + win.width) - col_off
            height = math.ceil(win.row_off + win.height) - row_off
            win = rasterio.windows.Window(col_off, row_off, width, height)
            data = src.read(1, window=win)
            profile = src.profile.copy()

        data = np.asarray(data)
        nodata = profile.get("nodata")
        valid = np.ones(data.shape, dtype=bool) if nodata is None else data != nodata
        data = np.where(valid, np.clip(data, 0, 10000), 0).astype("uint16")

        profile.update(
            driver="GTiff", dtype="uint16", nodata=None, count=1,
            height=data.shape[0], width=data.shape[1],
            transform=rasterio.windows.transform(win, profile["transform"]),
            compress="deflate",
        )
        with rasterio.open(clipped.with_suffix(".tif.tmp"), "w", **profile) as dst:
            dst.write(data, 1)
        clipped.with_suffix(".tif.tmp").rename(clipped)
    staged.unlink(missing_ok=True)   # zips are not kept: disk is tight
    # zip and full tile lived in the temp dir: gone; only the clipped raster
    # remains under pipeline/cache/ghsl/
    return clipped


def build_grid_arrays(clipped: dict) -> dict:
    """Aggregate built-up m2 per epoch into the 0.01 deg grid.

    Returns dict with per-epoch built_frac arrays (NY, NX), cell areas and
    AOI totals.  Pixels are binned by their centre (equal-area Mollweide
    pixel = exactly 10,000 m2), cell area is measured on the same
    Mollweide plane, so built_frac is self-consistent and <= 1.
    """
    # cell area per latitude row: equal-area projection -> area of a cell
    # polygon measured in 54009 equals its true surface area
    lat_edges = LAT0 + (np.arange(NY) + 0.5) * CELL
    xs = np.empty(NY)
    for i, lat in enumerate(lat_edges):
        ring = [(LON0, lat), (LON0 + CELL, lat),
                (LON0 + CELL, lat + CELL), (LON0, lat + CELL), (LON0, lat)]
        px, py = TR_4326_54009.transform([c[0] for c in ring], [c[1] for c in ring])
        xs[i] = 0.5 * abs(sum(px[j] * py[j + 1] - px[j + 1] * py[j]
                              for j in range(len(ring) - 1)))
    area_m2 = xs  # (NY,)
    log(f"  grid: {NX} x {NY} cells; cell area "
        f"{area_m2.min()/1e6:.3f}..{area_m2.max()/1e6:.3f} km2 "
        f"(AOI total {area_m2.sum()*NX/1e6:,.0f} km2)")

    built = {}
    totals = {}
    for epoch, path in clipped.items():
        with rasterio.open(path) as src:
            t = src.transform
            data = src.read(1)
        cols = t.c + (np.arange(src.width) + 0.5) * t.a
        rows = t.f + (np.arange(src.height) + 0.5) * t.e
        xx = np.tile(cols, src.height)          # pixel centre x (54009)
        yy = np.repeat(rows, src.width)         # pixel centre y (54009)
        lon, lat = TR_54009_4326.transform(xx, yy)
        ix = np.floor((lon - LON0) / CELL)
        iy = np.floor((lat - LAT0) / CELL)
        inb = (ix >= 0) & (ix < NX) & (iy >= 0) & (iy < NY)
        flat = (iy[inb].astype(np.int64) * NX + ix[inb].astype(np.int64))
        vals = data.reshape(-1)[inb].astype(np.float64)
        sums = np.bincount(flat, weights=vals, minlength=NX * NY)
        frac = np.clip(sums.reshape(NY, NX) / area_m2[:, None], 0.0, 1.0)
        built[epoch] = frac
        totals[epoch] = float(sums.sum() / 1e6)  # km2 of built-up surface
        log(f"  epoch {epoch}: AOI built-up {totals[epoch]:.0f} km2 "
            f"({frac.max():.2f} max cell, {int((frac > 0).sum())} non-zero cells)")
    return {"built_frac": built, "area_m2": area_m2, "totals_km2": totals}


# ---------------------------------------------------------------------------
# Land / water mask (ESA WorldCover) and lagoon shoreline (OSM)
# ---------------------------------------------------------------------------

def ensure_land_mask() -> dict:
    """Per-cell land classification from WorldCover, cached as .npz."""
    CACHE_WC.mkdir(parents=True, exist_ok=True)
    cache = CACHE_WC / "aoi_cell_land_mask.npz"
    if cache.exists():
        with np.load(cache) as z:
            return {"any_land": z["any_land"], "all_water": z["all_water"],
                     "n_samples": int(z["n_samples"]),
                     "generated_at": str(z["generated_at"])}
    log("  sampling ESA WorldCover 10 m (80 m overview) over the AOI ...")
    west, south = LON0 - WC_PAD, LAT0 - WC_PAD
    east, north = AOI[2] + WC_PAD, AOI[3] + WC_PAD
    cls = None
    for url in WORLDCOVER_TILES:
        with rasterio.open("/vsicurl/" + url) as src:
            assert src.crs is not None and src.crs.to_epsg() == 4326
            data = src.read(1, out_shape=(src.height // WC_LVL, src.width // WC_LVL),
                            resampling=Resampling.nearest)
            b = src.bounds
            res = (b.right - b.left) / (src.width // WC_LVL)   # decimated resolution
            if cls is None:
                # both tiles share the same 4326 pixel grid (0-3 and 3-6 lon, top 9.0)
                ncol = int(round((east - west) / res))
                nrow = int(round((north - south) / res))
                cls = np.zeros((nrow, ncol), dtype="uint8")
                assert abs(west - b.left - round((west - b.left) / res) * res) < 1e-9, "grid misalignment"
            # tile pixel (tr, tc) == combined pixel (tr - sr_off, tc - sc_off)
            sr_off = int(round((b.top - north) / res))
            sc_off = int(round((west - b.left) / res))
            nrows_t, ncols_t = data.shape
            r0 = max(0, -sr_off)
            r1 = min(nrow, nrows_t - sr_off)
            c0 = max(0, -sc_off)
            c1 = min(ncol, ncols_t - sc_off)
            cls[r0:r1, c0:c1] = data[r0 + sr_off:r1 + sr_off, c0 + sc_off:c1 + sc_off]
    # sample each 0.01 deg cell at its centre + 4 quarter points
    offs = [(0.0, 0.0), (0.00375, 0.00375), (0.00375, -0.00375),
            (-0.00375, 0.00375), (-0.00375, -0.00375)]
    any_land = np.zeros((NY, NX), dtype=bool)
    all_water = np.ones((NY, NX), dtype=bool)
    ci = np.arange(NX)
    ri = np.arange(NY)
    clon = LON0 + (ci + 0.5) * CELL
    clat = LAT0 + (ri + 0.5) * CELL
    for dlon, dlat in offs:
        plon = clon[None, :] + dlon
        plat = clat[:, None] + dlat
        col = np.floor((plon - west) / res).astype(np.int64)
        row = np.floor((north - plat) / res).astype(np.int64)
        ok = (col >= 0) & (col < ncol) & (row >= 0) & (row < nrow)
        col = np.clip(col, 0, ncol - 1)
        row = np.clip(row, 0, nrow - 1)
        v = cls[row, col]
        land = ok & (v != WATER_CLASS) & (v != NODATA_CLASS)
        water = ok & (v == WATER_CLASS)
        any_land |= land
        all_water &= water
    np.savez_compressed(cache, any_land=any_land, all_water=all_water,
                        n_samples=len(offs), generated_at=utc_now())
    log(f"  land cells (any of {len(offs)} samples non-water): "
        f"{int(any_land.sum())} / {NY*NX}; all-water: {int(all_water.sum())}")
    return {"any_land": any_land, "all_water": all_water,
            "n_samples": len(offs), "generated_at": utc_now()}


def ensure_lagoon_shore() -> MultiLineString:
    """Lagos + Lekki lagoon shoreline lines from OSM, cached as geojson."""
    CACHE_OSM.mkdir(parents=True, exist_ok=True)
    cache = CACHE_OSM / "lagos_lekki_lagoon_shore.geojson"
    if cache.exists():
        gj = json.loads(cache.read_text())
        lines = []
        for f in gj["features"]:
            g = f["geometry"]
            if g["type"] == "LineString":
                lines.append(LineString(g["coordinates"]))
            else:
                lines.extend(LineString(c) for c in g["coordinates"])
        return MultiLineString(lines) if lines else MultiLineString()

    log("  fetching OSM lagoon relations ...")
    lines_by_name = {}
    for rid, name in LAGOON_RELS.items():
        last_exc = None
        for attempt in range(1, 4):
            try:
                r = requests.get(
                    f"https://api.openstreetmap.org/api/0.6/relation/{rid}/full.json",
                    headers=OSM_UA, timeout=180)
                r.raise_for_status()
                d = r.json()
                break
            except requests.RequestException as exc:
                last_exc = exc
                time.sleep(10 * attempt)
        else:
            raise SystemExit(f"could not fetch OSM relation {rid} ({name}): {last_exc}")
        els = d["elements"]
        nd = {e["id"]: (e["lon"], e["lat"]) for e in els if e["type"] == "node"}
        ways = {e["id"]: e for e in els if e["type"] == "way"}
        rel = next(e for e in els if e["type"] == "relation" and e["id"] == rid)
        lines = []
        for m in rel.get("members", []):
            if m["type"] == "way" and m.get("ref") in ways:
                coords = [nd[n] for n in ways[m["ref"]].get("nodes", []) if n in nd]
                if len(coords) >= 2:
                    lines.append(LineString(coords))
        lines_by_name[name] = lines
        log(f"  {name}: {len(lines)} member ways")

    features = []
    all_lines = []
    for name, lines in lines_by_name.items():
        merged = linemerge(MultiLineString(lines))
        all_lines.extend(lines)
        features.append({
            "type": "Feature",
            "properties": {"name": name, "relation_id": [k for k, v in LAGOON_RELS.items() if v == name][0]},
            "geometry": (merged.__geo_interface__ if merged.geom_type == "LineString"
                         else {"type": "MultiLineString",
                               "coordinates": [list(p.coords) for p in merged.geoms]}),
        })
    shore = MultiLineString(all_lines)
    gj = {
        "type": "FeatureCollection",
        "meta": {
            "source": "OpenStreetMap API 0.6 relation geometry (member ways incl. inner rings)",
            "relations": {str(k): v for k, v in LAGOON_RELS.items()},
            "licence": OSM_LICENCE,
            "note": "shoreline lines; used via a 2 km buffer to flag lagoon-shore points",
            "generated_at": utc_now(),
        },
        "features": features,
    }
    cache.write_text(json.dumps(gj))
    return shore


# ---------------------------------------------------------------------------
# Evidence points
# ---------------------------------------------------------------------------

def load_evidence(path: Path) -> dict:
    """Load an evidence.geojson, retrying if another agent is mid-write."""
    for attempt in range(1, EVIDENCE_TRIES + 1):
        try:
            text = path.read_text()
            gj = json.loads(text)
            if not isinstance(gj.get("features"), list):
                raise ValueError("missing features list")
            return gj
        except (json.JSONDecodeError, ValueError, UnicodeDecodeError) as exc:
            if attempt == EVIDENCE_TRIES:
                raise SystemExit(f"could not parse {path} after {attempt} tries: {exc}")
            log(f"  {path.name} failed to parse ({exc.__class__.__name__}); "
                f"retry in {EVIDENCE_RETRY_WAIT}s (concurrent write?)")
            time.sleep(EVIDENCE_RETRY_WAIT)
    raise SystemExit("unreachable")


def collect_evidence2() -> tuple:
    events = sorted(d for d in EVENTS.iterdir()
                    if d.is_dir() and (d / "evidence.geojson").exists())
    points = []
    stats = {"raw": 0, "lga_excluded": 0, "dupes_dropped": 0,
             "no_coords": 0, "outside_grid": 0, "events": [e.name for e in events]}
    for evd in events:
        gj = load_evidence(evd / "evidence.geojson")
        points_ev = []
        n_lga = 0
        for i, f in enumerate(gj.get("features", [])):
            g = f.get("geometry") or {}
            props = f.get("properties") or {}
            coords = g.get("coordinates")
            if (g.get("type") != "Point" or not coords or len(coords) < 2
                    or coords[0] is None or coords[1] is None):
                stats["no_coords"] += 1
                continue
            stats["raw"] += 1
            if props.get("location_confidence") == "lga":
                n_lga += 1
                continue
            lon, lat = float(coords[0]), float(coords[1])
            pid = props.get("id") or f"{evd.name}-f{i}"
            x, y = TR_4326_UTM.transform(lon, lat)
            if any(math.hypot(x - q["_x"], y - q["_y"]) <= DEDUP_M for q in points_ev):
                stats["dupes_dropped"] += 1
                continue
            points_ev.append({
                "event": evd.name, "id": pid, "lon": lon, "lat": lat,
                "location_name": props.get("location_name"),
                "location_confidence": props.get("location_confidence"),
                "kind": props.get("kind"),
                "observed_at": props.get("observed_at"),
                "_x": x, "_y": y,
            })
        stats["lga_excluded"] += n_lga
        points.extend(points_ev)
        log(f"  {evd.name}: {len(gj.get('features', []))} features -> "
            f"{len(points_ev)} kept ({n_lga} lga excluded, dedupes counted)")
    return points, stats


# ---------------------------------------------------------------------------
# Matched-background test
# ---------------------------------------------------------------------------

def matched_test(point_rows: list, rng: np.random.Generator) -> dict:
    """Stratified matched-background test on d2000_2020 (change in built frac).

    point_rows: dicts with d (evidence change) and bg (list of background
    changes).  Statistic: median over points of (d - median(bg)).
    Permutation: within each point's matched stratum the evidence value is
    exchangeable with its background (H0); 10,000 shuffles.
    """
    rows = [r for r in point_rows if r.get("_bg")]
    n = len(rows)
    if n == 0:
        return {"n_points": 0, "note": "no matched points"}
    m = max(len(r["_bg"]) for r in rows)
    M = np.full((n, 1 + m), np.nan)
    for i, r in enumerate(rows):
        M[i, 0] = r["_d"]
        M[i, 1:1 + len(r["_bg"])] = r["_bg"]
    bg_med = np.nanmedian(M[:, 1:], axis=1)
    delta = M[:, 0] - bg_med
    t_obs = float(np.median(delta))

    # permutation: shuffle each row, first element becomes pseudo-evidence
    count = 0
    for _ in range(PERM_N):
        P = rng.permuted(M, axis=1)
        t_star = np.nanmedian(P[:, 0] - np.nanmedian(P[:, 1:], axis=1))
        if abs(t_star) >= abs(t_obs) - 1e-12:
            count += 1
    p = (1 + count) / (PERM_N + 1)

    above = sum(1 for i in range(n) if M[i, 0] > bg_med[i])
    below = sum(1 for i in range(n) if M[i, 0] < bg_med[i])
    return {
        "n_points": n,
        "n_full_stratum": int(sum(1 for r in rows if len(r["_bg"]) >= BG_N)),
        "evidence_median_d2000_2020": round(float(np.median(M[:, 0])), 4),
        "matched_background_median_d2000_2020": round(float(np.median(bg_med)), 4),
        "median_matched_difference": round(t_obs, 4),
        "mean_matched_difference": round(float(np.mean(delta)), 4),
        "share_above_background_median": round(above / n, 4),
        "share_below_background_median": round(below / n, 4),
        "n_above": above, "n_below": below, "n_ties": n - above - below,
        "permutation": {
            "statistic": "median over points of (evidence d2000-2020 - median of matched background d2000-2020)",
            "n_shuffles": PERM_N,
            "p_two_sided": round(p, 4),
            "seed": SEED,
            "method": "within-stratum label exchange; evidence value shuffled with its 20 matched background cells",
        },
    }


def run_evidence_test(grid: dict, land_mask: dict, shore: MultiLineString) -> dict:
    rng = np.random.default_rng(SEED)
    frac = grid["built_frac"]
    any_land = land_mask["any_land"]
    any_built = np.zeros((NY, NX), dtype=bool)
    for e in EPOCHS:
        any_built |= frac[e] > 0
    # land for the background pool: any sampled land OR any built-up
    # (reclaimed cells whose centre sits on water still count as land)
    land_cell = any_land | any_built
    b2020 = frac[2020]
    b2000 = frac[2000]
    d = b2020 - b2000

    points, stats = collect_evidence2()
    log(f"  evidence: {len(points)} points ({stats['raw']} raw, "
        f"{stats['lga_excluded']} lga excluded, {stats['dupes_dropped']} dupes dropped)")

    # lagoon shoreline (metric) + evidence cells to exclude from pools
    shore_m = shapely_transform(
        shore, lambda c: np.column_stack(TR_4326_UTM.transform(c[:, 0], c[:, 1])))
    evidence_cells = set()
    out_points = []
    pool_sizes = []
    for p in points:
        ix = int(math.floor((p["lon"] - LON0) / CELL))
        iy = int(math.floor((p["lat"] - LAT0) / CELL))
        if not (0 <= ix < NX and 0 <= iy < NY):
            stats["outside_grid"] += 1
            continue
        evidence_cells.add((iy, ix))
        dist_m = shore_m.distance(Point(p["_x"], p["_y"]))
        rec = {
            "event": p["event"], "id": p["id"],
            "lon": round(p["lon"], 5), "lat": round(p["lat"], 5),
            "location_name": p["location_name"],
            "location_confidence": p["location_confidence"],
            "cell": [ix, iy],
            "b2000": round(float(b2000[iy, ix]), 3),
            "b2020": round(float(b2020[iy, ix]), 3),
            "b2025": round(float(grid["built_frac"][2025][iy, ix]), 3),
            "d2000_2020": round(float(d[iy, ix]), 3),
            "near_lagoon_shore": bool(dist_m <= LAGOON_DIST_M),
            "lagoon_shore_distance_m": round(float(dist_m), 0),
            "_d": float(d[iy, ix]),
            "_b2020": float(b2020[iy, ix]),
        }
        out_points.append(rec)
    # background pools
    for rec in out_points:
        tol = np.abs(b2020 - rec["_b2020"]) <= BG_TOL
        pool = tol & land_cell
        for (cy, cx) in evidence_cells:
            pool[cy, cx] = False
        idx = np.flatnonzero(pool.reshape(-1))
        k = min(BG_N, idx.size)
        pool_sizes.append(idx.size)
        if k == 0:
            rec["bg"] = None
            rec["bg_n_pool"] = 0
            continue
        sel = rng.choice(idx, size=k, replace=False)
        bg_d = d.reshape(-1)[sel]
        rec["bg_n_pool"] = int(idx.size)
        rec["bg_d"] = [round(float(v), 4) for v in bg_d]
        rec["bg_median_d"] = round(float(np.median(bg_d)), 4)
        rec["bg_b2020_range"] = [round(float(b2020.reshape(-1)[sel].min()), 3),
                                  round(float(b2020.reshape(-1)[sel].max()), 3)]
        rec["_bg"] = [float(v) for v in bg_d]
    n_empty = sum(1 for r in out_points if not r.get("_bg"))
    if n_empty:
        log(f"  WARNING: {n_empty} points had an empty matched pool (excluded from the test)")

    rows_all = [r for r in out_points if r.get("_bg")]
    results_all = matched_test(rows_all, np.random.default_rng(SEED))
    lag_rows = [r for r in rows_all if r["near_lagoon_shore"]]
    results_lag = matched_test(lag_rows, np.random.default_rng(SEED))

    per_event = {}
    for ev in sorted(stats["events"]):
        rows_ev = [r for r in rows_all if r["event"] == ev]
        per_event[ev] = {
            "n_points": len(rows_ev),
            "median_d2000_2020": round(float(np.median([r["_d"] for r in rows_ev])), 4) if rows_ev else None,
            "median_bg_d2000_2020": round(float(np.median([r["bg_median_d"] for r in rows_ev])), 4) if rows_ev else None,
        }

    # background stats
    land_idx = np.flatnonzero(land_cell.reshape(-1))
    bg_note = {
        "n_land_cells": int(land_cell.sum()),
        "land_definition": "WorldCover-2021 land at cell centre or quarter points, or any built-up in any epoch",
        "matching": f"b2020 within +/- {BG_TOL} of the evidence point's cell",
        "draws_per_point": BG_N,
        "evidence_cells_excluded": len(evidence_cells),
        "pool_sizes": {
            "min": int(min(pool_sizes)) if pool_sizes else 0,
            "median": int(np.median(pool_sizes)) if pool_sizes else 0,
            "max": int(max(pool_sizes)) if pool_sizes else 0,
        },
        "aoi_land_cell_median_b2020": round(float(np.median(b2020.reshape(-1)[land_idx])), 4),
        "aoi_land_cell_median_d": round(float(np.median(d.reshape(-1)[land_idx])), 4),
    }

    out_points_json = []
    for r in out_points:
        rr = {k: v for k, v in r.items() if not k.startswith("_")}
        out_points_json.append(rr)

    return {
        "meta": {
            "task": "16-builtup-change",
            "question": ("did flooded (reported) places gain more built-up surface since 2000 "
                         "than equally-built places that were never reported?"),
            "sources": {
                "builtup": f"GHSL GHS-BUILT-S R2023A, 100 m Mollweide, tile {GHSL_TILE}, {GHSL_LICENCE}",
                "land_mask": f"ESA WorldCover 10 m v200 (2021), {WORLDCOVER_LICENCE}",
                "lagoon_shore": f"OSM relations {sorted(LAGOON_RELS)}, {OSM_LICENCE}",
                "evidence": "events/*/evidence.geojson (five events)",
            },
            "method": {
                "filtering": (f"location_confidence 'lga' excluded; duplicates within "
                              f"{DEDUP_M:.0f} m in the same event removed (first kept)"),
                "catch": ("flood reports come from where people are, so reported points look "
                          "more built-up whatever the cause; the comparison is therefore "
                          "matched on 2020 built-up level, not on land at large"),
                "matching": (f"for each point, {BG_N} random land cells with b2020 within "
                             f"+/- {BG_TOL} of the point's cell; cells holding any evidence "
                             f"point excluded; d2000_2020 compared with a stratified "
                             f"permutation test ({PERM_N:,} shuffles, seed {SEED})"),
                "lagoon_subset": (f"points within {LAGOON_DIST_M:.0f} m of the Lagos/Lekki "
                                  "lagoon shoreline (OSM), where reclamation is most likely"),
            },
            "caveats": [
                "small sample: a few hundred geolocated reports across five events",
                "1 km cells are coarse: a report and its cell average very different ground",
                "GHSL under-detects informal settlements (dense, low-rise, metal roofs) and "
                "small structures; absolute built fractions are lower bounds in such areas",
                "GHSL epochs are model output: Landsat supports 1975/1990/2000/2014, "
                "Sentinel-2 2018; 2020 is interpolated, 2025 is a projection",
                "evidence locations are mostly neighbourhood centroids, not the flooded spot",
                "background matched only on b2020; unmeasured confounders (elevation, "
                "drainage, population density) are not controlled",
                "matched on b2020, controls with the same 2020 built-up level can have "
                "reached it recently (high gain) while reported core areas were already "
                "built by 2000 (saturated, low gain): a negative difference mainly "
                "reflects saturation and reporting patterns, not protection",
            ],
            "generated_at": utc_now(),
        },
        "counts": stats,
        "background": bg_note,
        "results": {"all_points": results_all, "lagoon_shore_subset": results_lag},
        "per_event": per_event,
        "points": out_points_json,
    }


# ---------------------------------------------------------------------------
# Outputs
# ---------------------------------------------------------------------------

def write_grid(grid: dict, land_mask: dict) -> None:
    frac = grid["built_frac"]
    any_built = np.zeros((NY, NX), dtype=bool)
    for e in EPOCHS:
        any_built |= frac[e] > 0
    kept = int(any_built.sum())
    log(f"  grid cells with built-up in any epoch: {kept} of {NY*NX} "
        f"({int((land_mask['any_land'] & ~any_built).sum())} land cells dropped as all-zero)")
    features = []
    for iy in range(NY):
        for ix in range(NX):
            if not any_built[iy, ix]:
                continue
            x0 = round(LON0 + ix * CELL, 6)
            x1 = round(x0 + CELL, 6)
            y0 = round(LAT0 + iy * CELL, 6)
            y1 = round(y0 + CELL, 6)
            props = {f"b{e}": round(float(frac[e][iy, ix]), 3) for e in EPOCHS}
            props["d2000_2020"] = round(float(frac[2020][iy, ix] - frac[2000][iy, ix]), 3)
            features.append({
                "type": "Feature",
                "properties": props,
                "geometry": {"type": "Polygon", "coordinates": [[
                    [x0, y0], [x1, y0], [x1, y1], [x0, y1], [x0, y0]]]},
            })
    gj = {
        "type": "FeatureCollection",
        "meta": {
            "task": "16-builtup-change",
            "source": "GHSL GHS-BUILT-S R2023A (JRC European Commission)",
            "product": [GHSL_PRODUCT.format(epoch=e) + f"_{GHSL_TILE}" for e in EPOCHS],
            "licence": GHSL_LICENCE,
            "epochs": EPOCHS,
            "epoch_status": GHSL_OBSERVED_NOTE,
            "b2025_status": "in the R2023A release, but projected (not observed): "
                            "interpolated/extrapolated past the last observed epoch (2018)",
            "aoi_bbox": AOI,
            "grid": "0.01 deg (~1.1 x 1.1 km) cells over the AOI",
            "method": ("built_frac = GHSL built-up m2 (100 m pixels binned by centre) / "
                       "cell area measured on the equal-area Mollweide plane (ESRI:54009); "
                       "values clipped to 0-1, rounded to 3 decimals"),
            "kept_cells": ("cells with built-up in at least one epoch (cells that are 0 in "
                           "every epoch are dropped); land/water classification from ESA "
                           "WorldCover 10 m v200 (2021) is used for the evidence test only"),
            "land_mask": f"ESA WorldCover 10 m v200 (2021), {WORLDCOVER_LICENCE}, "
                         f"sampled at cell centre + 4 quarter points",
            "caveats": [
                "GHSL misses much informal settlement; built fractions are lower bounds there",
                "2020 is interpolated between observations (2018 observed), 2025 projected",
                "1 km cells average over very different ground in a heterogeneous city",
            ],
            "generated_at": utc_now(),
        },
        "features": features,
    }
    GRID_OUT.write_text(json.dumps(gj, separators=(",", ":")))
    size = GRID_OUT.stat().st_size
    log(f"  wrote {GRID_OUT.name}: {kept} features, {size/1e6:.1f} MB"
        + (" (WARNING: over 8 MB)" if size > 8e6 else ""))


def main() -> None:
    log("== Task 16: built-up change vs flood evidence ==")
    CACHE_GHSL.mkdir(parents=True, exist_ok=True)

    moll = aoi_mollweide()
    log(f"AOI bbox {AOI} -> Mollweide window x {moll[0]:.0f}..{moll[2]:.0f}, "
        f"y {moll[1]:.0f}..{moll[3]:.0f} m")

    log("[1/5] GHSL GHS-BUILT-S tiles (100 m Mollweide, tile R9_C19)")
    clipped = {}
    for epoch in EPOCHS:
        clipped[epoch] = clip_builtup(epoch, moll)
        log(f"  {epoch}: {clipped[epoch].name} "
            f"({clipped[epoch].stat().st_size/1e6:.1f} MB)")

    log("[2/5] aggregating to the 0.01 deg grid")
    grid = build_grid_arrays(clipped)

    log("[3/5] land mask (ESA WorldCover)")
    land_mask = ensure_land_mask()

    log("[4/5] lagoon shoreline (OSM)")
    shore = ensure_lagoon_shore()
    shore_km = shapely_transform(
        shore, lambda c: np.column_stack(TR_4326_UTM.transform(c[:, 0], c[:, 1]))).length / 1000
    log(f"  shoreline: {len(shore.geoms)} lines, {shore_km:.0f} km total")

    log("[5/5] evidence test + outputs")
    write_grid(grid, land_mask)
    test = run_evidence_test(grid, land_mask, shore)
    TEST_OUT.write_text(json.dumps(test, indent=1))
    log(f"wrote {TEST_OUT.name} ({TEST_OUT.stat().st_size/1e6:.1f} MB)")

    # ---- summary ----
    log("")
    log("== AOI built-up surface (GHSL, km2) ==")
    for e in EPOCHS:
        log(f"  {e}: {grid['totals_km2'][e]:>8.0f} km2")
    log(f"  change 2000 -> 2020: "
        f"{grid['totals_km2'][2020] - grid['totals_km2'][2000]:+.0f} km2 "
        f"({100*(grid['totals_km2'][2020]/max(grid['totals_km2'][2000],1e-9)-1):+.0f}%)")

    res = test["results"]["all_points"]
    resl = test["results"]["lagoon_shore_subset"]
    log("")
    log("== Evidence test (matched on 2020 built-up level) ==")
    log(f"  points: {res['n_points']} (lagoon-shore subset: {resl.get('n_points', 0)})")
    log(f"  median d2000-2020, evidence:        {res['evidence_median_d2000_2020']:+.3f}")
    log(f"  median d2000-2020, matched controls: {res['matched_background_median_d2000_2020']:+.3f}")
    log(f"  median matched difference:          {res['median_matched_difference']:+.3f}")
    log(f"  share of evidence points above their control median: "
        f"{res['share_above_background_median']*100:.0f}% ({res['n_above']}/{res['n_points']})")
    log(f"  permutation p (two-sided, {res['permutation']['n_shuffles']:,} shuffles): "
        f"{res['permutation']['p_two_sided']}")
    if resl.get("n_points"):
        log(f"  lagoon-shore subset: evidence {resl['evidence_median_d2000_2020']:+.3f} vs "
            f"controls {resl['matched_background_median_d2000_2020']:+.3f}; "
            f"share above {resl['share_above_background_median']*100:.0f}%; "
            f"p={resl['permutation']['p_two_sided']}")
    log("")
    log("== Interpretation (cautious) ==")
    sign = res.get("median_matched_difference")
    p_val = res.get("permutation", {}).get("p_two_sided")
    if sign is None or p_val is None or p_val > 0.05:
        log("  * Result: no detectable difference in how much flooded (reported)")
        log("    places and equally-built places gained built-up surface. At this")
        log("    resolution the built-over-more hypothesis is not supported - but")
        log("    see the caveats: this is a small, coarsely-located sample.")
    elif sign > 0:
        log("  * Result: flooded (reported) places gained MORE built-up surface than")
        log("    equally-built non-reported places. Suggestive, not causal proof:")
        log("    reports come from where people are, and matching on 2020 built-up")
        log("    level does not control for elevation, drainage or density.")
    else:
        log("  * Result: flooded (reported) places gained LESS built-up surface than")
        log("    equally-built non-reported controls (the opposite of the naive")
        log("    built-over-more story). Most reports come from the old, largely")
        log("    built-out core (Lagos Island, Apapa, Ikeja, Ikoyi/VI) whose cells")
        log("    were already near-saturated in 2000 and physically cannot gain")
        log("    much more, while the matched 2020 built-up band includes newer,")
        log("    fast-growing areas (Lekki axis, peri-urban estates) that gained")
        log("    a lot. So the negative association mainly reflects saturation")
        log("    and reporting patterns, not protection from building.")
    log("  * The evidence sample is small (126 points) and geolocated to")
    log("    neighbourhood centres; 1 km cells average over very different ground.")
    log("  * GHSL misses much informal settlement, so built fractions are lower")
    log("    bounds where flooding is often reported; 2020 is interpolated and")
    log("    2025 is a projection past the last observed epoch (2018).")
    log("  * A null result would mean: at this resolution, flooded and equally-")
    log("    built non-flooded places gained built-up surface at similar rates.")
    log("    It would NOT mean built-up change is irrelevant to flooding - only")
    log("    that this coarse test cannot see it: finer land-cover, accurate")
    log("    flood footprints (SAR) and within-city controls would be needed.")
    log("  * Either sign of this test is confounded: what would really test the")
    log("    reclamation hypothesis is per-parcel change on the water's edge")
    log("    (GHS-BUILT-S at 100 m vs OSM building dates / SAR footprints),")
    log("    not 1 km averages.")
    log("  * b2025 is in the R2023A release but is projected, not observed:")
    log("    the last image-supported epoch is 2018 (Sentinel-2); 1975/1990/2000")
    log("    are Landsat-supported, 2020 is interpolated between 2018 and 2025.")


if __name__ == "__main__":
    try:
        main()
    except SystemExit as exc:
        log(f"FATAL: {exc}")
        sys.exit(1)
