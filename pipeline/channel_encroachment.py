#!/usr/bin/env python3
"""Task 21 - building encroachment beside the blamed drainage channels, year by year.

Google Open Buildings 2.5D Temporal (Sentinel-2 based, annual composites
2016-2023, 4 m effective resolution stored as 0.5 m pixels, EPSG:32631) gives
annual building presence beside each channel.  For every drainage site with a
channel line the tool measures, per year, the built fraction (share of 4 m
cells with block-mean building_presence >= 0.5, sensitivity 0.4 / 0.6) in
three bands from the channel centreline - 0-10 m, 10-20 m, 20-50 m - clipped
to the site's 300 m radius, plus the area newly built per year (built in t and
t+1 and not built in t-1 and t-2, so flicker is suppressed).  A city-wide
baseline repeats the measurement on 200 random 300 m segments of OSM
waterways in the AOI [2.6, 6.28, 4.45, 6.85], at least 1 km from any named
site, so the blamed channels can be compared with channels in general.

Channel lines: OSM waterway=drain|canal|stream|ditch|river within the site's
300 m radius (Task 18's events/drainage_sites/<site>/osm.geojson when it was
fetched around the current geometry, otherwise a fresh Overpass query), plus
the geometry in events/drainage_sites.json where the site's structure IS a
channel and the line is a channel alignment rather than a road (curated per
site, reasons recorded in the output).  Sites with no channel line are
skipped and listed.

Data access: public GCS bucket open-buildings-temporal-data, manifest
11_EPSG_32631_<year>_06_30.json (token 11 covers Lagos; token 13 lies north
of the AOI), ranged COG reads via /vsicurl/ only - tiles are ~520 MB COGs and
are never downloaded.  Band: building_presence (uncalibrated model
confidence 0-1, nodata -99) -> 8x8 block-mean at 0.5 m (4 m cells, world
4 m-aligned grid), then thresholded.

Validation (3 sites): 2023 mask vs OSM building footprints (precision/recall
at 4 m, cell centre inside a footprint) over the site's 300 m buffer, plus a
visual overlay of the mask and OSM footprints on the latest Wayback chip.

Outputs:
  events/drainage_sites_buildings.json        all series, baseline, validation
  events/drainage_sites/<site>/ob_timeline.png  built fraction by year per
                     band, flood dates marked, baseline median and IQR shaded
  events/drainage_sites/<site>/ob_<year>.png    presence masks (2016/2019/2023)
  events/drainage_sites/<site>/ob_validation.png  (validation sites only)

Caches (small arrays + manifests) under pipeline/cache/open_buildings/ are
deleted at the end of a fully successful run (find -type f -delete).

Licence CC BY 4.0 or ODbL 1.0; cite Sirko et al. 2023 (arXiv 2310.11622).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

os.environ.setdefault("GDAL_DISABLE_READDIR_ON_OPEN", "EMPTY_DIR")
os.environ.setdefault("CPL_VSIL_CURL_ALLOWED_EXTENSIONS", ".tif,.TIF")
os.environ.setdefault("GDAL_HTTP_MAX_RETRY", "4")
os.environ.setdefault("GDAL_HTTP_RETRY_DELAY", "1")
os.environ.setdefault("GDAL_HTTP_TIMEOUT", "60")

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import requests
import rasterio
from matplotlib.colors import ListedColormap
from PIL import Image
from rasterio.features import rasterize
from rasterio.transform import from_origin
from rasterio.warp import transform as warp_transform
from rasterio.windows import Window
from shapely import contains_xy, distance as shapely_distance, points as shapely_points
from shapely.geometry import (LineString, MultiLineString, MultiPolygon,
                                 Point, Polygon)
from shapely import transform as sh_transform
from shapely.ops import substring, unary_union

REPO = Path(__file__).resolve().parents[1]
SITES_JSON = REPO / "events" / "drainage_sites.json"
IMAGERY_JSON = REPO / "events" / "drainage_sites_imagery.json"
SITES_DIR = REPO / "events" / "drainage_sites"
OUT_JSON = REPO / "events" / "drainage_sites_buildings.json"
CACHE = REPO / "pipeline" / "cache" / "open_buildings"
CACHE_MANIFESTS = CACHE / "manifests"
CACHE_SITES = CACHE / "sites"
CACHE_BASELINE = CACHE / "baseline"
CACHE_VALIDATION = CACHE / "validation"

UTM = "EPSG:32631"
YEARS = list(range(2016, 2024))
NEW_YEARS = list(range(2018, 2023))       # needs t-2..t+1 all present
BAND_EDGES = ((0.0, 10.0), (10.0, 20.0), (20.0, 50.0))
BAND_KEYS = ("0-10", "10-20", "20-50")
BAND_COLORS = ("#d62728", "#ff7f0e", "#1f77b4")
THR_MAIN = 0.5
THRS = (0.4, 0.5, 0.6)
CELL = 4.0                                # m, effective resolution
PX = 0.5                                   # m, native pixel
CHUNK = 256.0                              # m, read chunk = 512 px = 64 cells
SITE_RADIUS_M = 300.0
CHANNEL_BAND_MAX_M = 50.0
BAND_PAD_M = CHANNEL_BAND_MAX_M + 2.0

BASELINE_AOI = (2.6, 6.28, 4.45, 6.85)     # (w, s, e, n)
BASELINE_N_SEG = 200
BASELINE_SEG_M = 300.0
BASELINE_EXCL_SITE_M = 1000.0
BASELINE_MIN_SEP_M = 400.0
BASELINE_SEED = 21
WATERWAY_TYPES = ("drain", "canal", "stream", "ditch", "river")

TOKENS = ("11", "13")
GCS_MANIFEST = ("https://storage.googleapis.com/open-buildings-temporal-data"
                "/v1/manifests/{tok}_EPSG_32631_{year}_06_30.json")
OVERPASS_API = "https://overpass-api.de/api/interpreter"
UA = {"User-Agent": "FloodTrace/0.1 (research)"}

VALIDATION_SITES = ("alpha-beach-156", "agungi-collector", "olopomeji")

OB_SOURCE = ("Google Open Buildings 2.5D Temporal v1 "
             "(https://storage.googleapis.com/open-buildings-temporal-data), "
             "Sentinel-2 based annual building presence 2016-2023, "
             "4 m effective resolution, 0.5 m pixels, EPSG:32631")
OB_CITATION = "Sirko et al. 2023, arXiv:2310.11622"
OB_LICENCE = "CC BY 4.0 (or ODbL 1.0)"

# Per-site decision: use the drainage_sites.json geometry as the channel line?
# The task rule is "structure_name is a channel and location_confidence isn't
# not_found", with the task's own constraint "mapped channel lines, not road
# lines".  Where the recorded line is a road/carriageway it is not used even
# if the named structure is a drain; where it is the channel (or the only
# available alignment) it is used, with the confidence carried through.
GEOMETRY_USE = {
    "alpha-beach-156": (True,
        "site line is the OSM-mapped drain taken as the System 156 alignment "
        "(location_confidence street)"),
    "agungi-collector": (False,
        "named structure is a collector channel, but the recorded line is the "
        "Agungi Ajiran Road carriageway, not the channel: road lines excluded; "
        "mapped OSM drains within 300 m used instead"),
    "olopomeji": (False,
        "structure is the Iyana Oworo road section, not a channel; mapped OSM "
        "drains/streams within 300 m used"),
    "ikorodu-dammed": (True,
        "Gberigbe Road outfall channel; the line connects the named inspection "
        "points (Gberigbe-Ijede corridor), it is not a surveyed centreline "
        "(location_confidence neighbourhood) - rough alignment, read trends only"),
    "agric-bridge": (False,
        "structure is the AFA bridge / Agric-Isawo Road; the OSM drain within "
        "the radius is the channel"),
    "ijede-drain": (True,
        "Oko Ope-Abule Eko drainage project; the line connects the named "
        "endpoints, it is not a surveyed centreline (location_confidence "
        "neighbourhood) - rough alignment, read trends only"),
    "oko-oba-canal": (True,
        "Oko-Oba Canal channel traced on current imagery (Task 19 update, "
        "location_confidence exact)"),
    "alapere-ogudu": (False,
        "structure is expressway/road construction; the OSM drains and "
        "streams within the radius are the channels"),
    "marina-drainage": (False,
        "structure is a road where the claim is that drainage is absent; not a "
        "channel and no mapped waterway within 300 m"),
    "lekki-epe-rehab": (False,
        "structure is the Lekki-Epe Expressway (road works); the OSM stream "
        "within the radius is the channel"),
    "labora": (False,
        "new residential site with no mapped drain; no channel"),
    "ibeju-lekki-expy": (False,
        "roadside drains along the expressway; no channel line mapped within "
        "300 m"),
    "sangotedo-channel-notices": (True,
        "System 63b channel; centreline not in OSM: the geometry is the Lagos "
        "Business School inspection point (location_confidence street), so the "
        "bands are rings around the point rather than bands along a "
        "centreline - the 0-10 m band is ~20 cells, qualitative only"),
}

_tls = threading.local()


def log(msg: str) -> None:
    print(msg, flush=True)


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def r(x, nd=4):
    if x is None:
        return None
    x = float(x)
    if math.isnan(x):
        return None
    return round(x, nd)


# ---------------------------------------------------------------------------
# geometry helpers
# ---------------------------------------------------------------------------

def _warp(xs, ys, src, dst):
    return warp_transform(src, dst, list(xs), list(ys))


def to_utm(geom):
    def fn(coords):
        c = np.asarray(coords, dtype=float)
        nx_, ny_ = _warp(c[:, 0], c[:, 1], "EPSG:4326", UTM)
        return np.column_stack([nx_, ny_])
    return sh_transform(geom, fn)


def to_lonlat(geom):
    def fn(coords):
        c = np.asarray(coords, dtype=float)
        nx_, ny_ = _warp(c[:, 0], c[:, 1], UTM, "EPSG:4326")
        return np.column_stack([nx_, ny_])
    return sh_transform(geom, fn)


def geom_hash(obj) -> str:
    return hashlib.sha1(json.dumps(obj, sort_keys=True).encode()).hexdigest()[:12]


def line_parts(geom):
    if geom.is_empty:
        return []
    if isinstance(geom, LineString):
        return [geom]
    if isinstance(geom, MultiLineString):
        return [g for g in geom.geoms if g.length > 0]
    return []


def plot_line(ax, geom, **kw):
    for part in line_parts(geom):
        xs, ys = part.xy
        ax.plot(xs, ys, **kw)
    if isinstance(geom, Point):
        ax.plot(geom.x, geom.y, marker="o", **kw)


# ---------------------------------------------------------------------------
# Overpass
# ---------------------------------------------------------------------------

def overpass(query: str, retries: int = 6) -> dict:
    last = ""
    for attempt in range(retries):
        try:
            resp = requests.post(OVERPASS_API, data=query.encode("utf-8"),
                                 headers=UA, timeout=300)
            if resp.status_code == 200:
                data = resp.json()
                if "elements" in data:
                    return data
                last = f"server remark: {str(data.get('remark'))[:120]}"
            else:
                last = f"HTTP {resp.status_code}"
        except (requests.RequestException, ValueError) as exc:
            last = str(exc)[:120]
        time.sleep(10 * (attempt + 1))
    raise RuntimeError(f"Overpass failed after {retries} tries ({last})")


def waterway_query(s: float, w: float, n: float, e: float) -> str:
    return ("[out:json][timeout:240];\n(\n"
            f"  way[\"waterway\"~\"^({'|'.join(WATERWAY_TYPES)})$\"]"
            f"({s:.6f},{w:.6f},{n:.6f},{e:.6f});\n"
            ");\nout body geom;")


def overpass_waterway_lines(s, w, n, e, clip_to=None):
    """Waterway ways in a bbox as UTM LineStrings, optionally clipped."""
    data = overpass(waterway_query(s, w, n, e))
    lines = []
    for el in data.get("elements", []):
        if el.get("type") != "way":
            continue
        tags = el.get("tags", {})
        wt = tags.get("waterway")
        nodes = el.get("geometry")
        if wt not in WATERWAY_TYPES or not nodes or len(nodes) < 2:
            continue
        lons = [nd["lon"] for nd in nodes]
        lats = [nd["lat"] for nd in nodes]
        xs, ys = _warp(lons, lats, "EPSG:4326", UTM)
        line = LineString(list(zip(xs, ys)))
        if clip_to is not None:
            line = line.intersection(clip_to)
            for part in line_parts(line):
                if part.length >= 0.5:
                    lines.append((el.get("id"), wt, part))
        else:
            lines.append((el.get("id"), wt, line))
    return lines


def site_bbox_pad(coords_lonlat, pad_m):
    lat_c = sum(c[1] for c in coords_lonlat) / len(coords_lonlat)
    pad_lat = pad_m * 1.05 / 111_000.0
    pad_lon = pad_m * 1.05 / (111_320.0 * math.cos(math.radians(lat_c)))
    s = min(c[1] for c in coords_lonlat) - pad_lat
    n = max(c[1] for c in coords_lonlat) + pad_lat
    w = min(c[0] for c in coords_lonlat) - pad_lon
    e = max(c[0] for c in coords_lonlat) + pad_lon
    return (s, w, n, e)


# ---------------------------------------------------------------------------
# Open Buildings manifests / tiles
# ---------------------------------------------------------------------------

def fetch_manifest(tok: str, year: int) -> dict:
    CACHE_MANIFESTS.mkdir(parents=True, exist_ok=True)
    fp = CACHE_MANIFESTS / f"{tok}_{year}.json"
    if fp.exists():
        return json.loads(fp.read_text())
    url = GCS_MANIFEST.format(tok=tok, year=year)
    last = ""
    for attempt in range(5):
        try:
            resp = requests.get(url, headers=UA, timeout=180)
            if resp.status_code == 200:
                fp.write_text(resp.text)
                return json.loads(resp.text)
            last = f"HTTP {resp.status_code}"
        except requests.RequestException as exc:
            last = str(exc)[:120]
        time.sleep(5 * (attempt + 1))
    raise RuntimeError(f"manifest {url} failed ({last})")


def build_tile_index(region):  # region = (minx, miny, maxx, maxy) UTM
    """{year: [(tx, ty, wpx, hpx, https_url), ...]} for tiles hitting region."""
    minx, miny, maxx, maxy = region
    index = {}
    for year in YEARS:
        tiles = []
        for tok in TOKENS:
            try:
                man = fetch_manifest(tok, year)
            except RuntimeError as exc:
                log(f"  [warn] {exc}")
                continue
            prefix = man["uriPrefix"]
            if prefix.startswith("gs://"):
                https_prefix = prefix.replace(
                    "gs://", "https://storage.googleapis.com/", 1)
            else:
                https_prefix = prefix
            for ts in man.get("tilesets", []):
                for src in ts.get("sources", []):
                    at = src["affineTransform"]
                    dims = src.get("dimensions", ts.get("dimensions"))
                    w = dims["width"] * abs(at["scaleX"])
                    h = dims["height"] * abs(at["scaleY"])
                    tx, ty = at["translateX"], at["translateY"]
                    if tx > maxx or tx + w < minx or ty < miny or ty - h > maxy:
                        continue
                    uris = src.get("uris") or []
                    if not uris:
                        continue
                    tiles.append((tx, ty, dims["width"], dims["height"],
                                  https_prefix + uris[0]))
        index[year] = tiles
        if not tiles:
            log(f"  [warn] no Open Buildings tiles for {year} in region")
    return index


def get_ds(url: str):
    """Thread-local cached rasterio dataset for a COG URL."""
    cache = getattr(_tls, "ds", None)
    if cache is None:
        cache = {}
        _tls.ds = cache
    ent = cache.get(url)
    if ent is None:
        ds = rasterio.open("/vsicurl/" + url)
        descs = ds.descriptions or ()
        if "building_presence" in descs:
            band = descs.index("building_presence") + 1
        else:
            band = 3
        ent = (ds, band)
        cache[url] = ent
    return ent


def read_chunk_cells(year: int, cx: float, cyt: float) -> np.ndarray:
    """256 m chunk -> (64, 64) float32 of 4 m block-mean building presence.

    cx is the chunk's left edge, cyt its top edge; both multiples of 256 m
    (hence of 4 m, so 8-px blocks align with the world 4 m grid).
    """
    out_px = np.full((int(CHUNK / PX), int(CHUNK / PX)), np.nan, np.float32)
    x1, y1 = cx + CHUNK, cyt - CHUNK
    for tx, ty, wpx, hpx, url in TILE_INDEX[year]:
        if tx > x1 or tx + wpx * PX < cx or ty < y1 or ty - hpx * PX > cyt:
            continue
        ds, band = get_ds(url)
        col0 = int(round((cx - tx) / PX))
        row0 = int(round((ty - cyt) / PX))
        col_a, col_b = max(col0, 0), min(col0 + out_px.shape[1], wpx)
        row_a, row_b = max(row0, 0), min(row0 + out_px.shape[0], hpx)
        if col_b <= col_a or row_b <= row_a:
            continue
        data = ds.read(band, window=Window(col_a, row_a, col_b - col_a,
                                           row_b - row_a))
        valid = data != -99.0
        sl_r = slice(row_a - row0, row_b - row0)
        sl_c = slice(col_a - col0, col_b - col0)
        tgt = out_px[sl_r, sl_c]
        fill = np.isnan(tgt) & valid
        tgt[fill] = data[fill]
    h, w = out_px.shape
    blocks = out_px.reshape(h // 8, 8, w // 8, 8)
    cnt = (~np.isnan(blocks)).sum(axis=(1, 3))
    sums = np.nansum(blocks, axis=(1, 3))
    cells = np.full((h // 8, w // 8), np.nan, np.float32)
    nz = cnt > 0
    cells[nz] = (sums[nz] / cnt[nz]).astype(np.float32)
    return cells


# ---------------------------------------------------------------------------
# bands on the 4 m grid
# ---------------------------------------------------------------------------

def band_cells(channel, clip_geom, gx0=None, gy_top=None, nx=None, ny=None):
    """World-4m-aligned grid; cells in 0-10/10-20/20-50 m from `channel`,
    clipped to `clip_geom` (site buffer).  Returns grid meta + cell arrays."""
    minx, miny, maxx, maxy = channel.bounds
    minx -= BAND_PAD_M; miny -= BAND_PAD_M
    maxx += BAND_PAD_M; maxy += BAND_PAD_M
    if gx0 is None:
        gx0 = math.floor(minx / CELL) * CELL
        gy_top = math.ceil(maxy / CELL) * CELL
        nx = int(math.ceil((maxx - gx0) / CELL))
        ny = int(math.ceil((gy_top - miny) / CELL))
    xs = gx0 + CELL * np.arange(nx) + CELL / 2.0
    ys = gy_top - CELL * np.arange(ny) - CELL / 2.0
    xx, yy = np.meshgrid(xs, ys)
    pts = shapely_points(xx.ravel(), yy.ravel())
    d = shapely_distance(pts, channel)
    band = np.zeros(xx.size, np.int8)
    band[d <= 10] = 1
    band[(d > 10) & (d <= 20)] = 2
    band[(d > 20) & (d <= 50)] = 3
    if clip_geom is not None:
        inside = contains_xy(clip_geom, xx.ravel(), yy.ravel())
        band = np.where(inside, band, 0)
    keep = band > 0
    ii, jj = np.divmod(np.nonzero(keep)[0], nx)
    return dict(gx0=gx0, gy_top=gy_top, nx=nx, ny=ny,
                bi=ii.astype(np.int32), bj=jj.astype(np.int32),
                band_id=band[keep].astype(np.int8))


def chunk_set(meta):
    """256 m chunks that contain at least one band cell."""
    gx0, gy_top, nx = meta["gx0"], meta["gy_top"], meta["nx"]
    cx = gx0 + CELL * meta["bj"]
    cyt = gy_top - CELL * meta["bi"]
    ccx = np.floor(cx / CHUNK) * CHUNK
    ccy = np.ceil(cyt / CHUNK) * CHUNK
    return sorted(set(zip(ccx.tolist(), ccy.tolist())))


def read_grid(meta, year, chunks) -> np.ndarray:
    """(ny, nx) float32 block-mean presence for one year."""
    grid = np.full((meta["ny"], meta["nx"]), np.nan, np.float32)
    for cx, cyt in chunks:
        cells = read_chunk_cells(year, cx, cyt)
        j0 = int((cx - meta["gx0"]) / CELL)
        i0 = int((meta["gy_top"] - cyt) / CELL)
        jc0, jc1 = max(j0, 0), min(j0 + cells.shape[1], meta["nx"])
        ic0, ic1 = max(i0, 0), min(i0 + cells.shape[0], meta["ny"])
        if jc1 <= jc0 or ic1 <= ic0:
            continue
        grid[ic0:ic1, jc0:jc1] = cells[ic0 - i0:ic1 - i0,
                                       jc0 - j0:jc1 - j0]
    return grid


def band_series(vals, band_id):
    """vals: {year: (n,) float}; band_id: (n,) int 1..3.
    Returns per band: built fraction per threshold per year, newly built m2
    per year, n valid cells per year."""
    n = band_id.size
    out = {}
    for b in range(1, 4):
        sel = band_id == b
        entry = {"n_cells": int(sel.sum()), "built_fraction": {}, "newly_built_m2": {},
                 "n_valid": {}}
        masks = {}
        for y in YEARS:
            v = vals[y][sel]
            ok = ~np.isnan(v)
            entry["n_valid"][y] = int(ok.sum())
            masks[y] = np.where(ok, v >= THR_MAIN, False)
            for thr in THRS:
                frac = float(((v >= thr) & ok).sum() / ok.sum()) if ok.any() else None
                entry["built_fraction"].setdefault(thr, {})[y] = frac
        for t in NEW_YEARS:
            m_t = masks[t]; m_t1 = masks[t + 1]
            m_tm1 = masks[t - 1]; m_tm2 = masks[t - 2]
            newc = int((m_t & m_t1 & ~m_tm1 & ~m_tm2).sum())
            entry["newly_built_m2"][t] = float(newc * CELL * CELL) if n else 0.0
        out[b] = entry
    return out


# ---------------------------------------------------------------------------
# sites: channel assembly
# ---------------------------------------------------------------------------

def cached_site_waterways(site, site_dir):
    """Waterway lines from Task 18's osm.geojson, if it was fetched around the
    CURRENT geometry (its site feature records the geometry used)."""
    fp = site_dir / "osm.geojson"
    if not fp.exists():
        return None, "no osm.geojson"
    try:
        d = json.loads(fp.read_text())
    except ValueError:
        return None, "osm.geojson unreadable"
    site_feats = [f for f in d.get("features", [])
                 if f.get("properties", {}).get("kind") == "site"]
    if not site_feats or geom_hash(site_feats[0].get("geometry")) != geom_hash(site["geometry"]):
        return None, "osm.geojson fetched around a previous geometry"
    lines = []
    for f in d.get("features", []):
        pr = f.get("properties", {})
        if pr.get("kind") != "waterway":
            continue
        g = to_utm(_shape(f["geometry"]))
        for part in line_parts(g):
            if part.length >= 0.5:
                lines.append((pr.get("id"), pr.get("waterway"), part))
    return lines, "events/drainage_sites/%s/osm.geojson (current geometry)" % site["site_id"]


def _shape(gj):
    if gj["type"] == "Point":
        return Point(gj["coordinates"])
    if gj["type"] == "LineString":
        return LineString(gj["coordinates"])
    if gj["type"] == "MultiLineString":
        return MultiLineString([LineString(c) for c in gj["coordinates"]])
    if gj["type"] == "Polygon":
        return Polygon(gj["coordinates"][0], gj["coordinates"][1:])
    if gj["type"] == "MultiPolygon":
        return MultiPolygon(gj["coordinates"])
    raise ValueError(gj["type"])


def channels_for_site(site, site_dir, site_geom_utm, site_buffer):
    """Assemble the channel geometry + provenance; None if no channel line."""
    sid = site["site_id"]
    lines, src = cached_site_waterways(site, site_dir)
    provenance = {}
    if lines is not None:
        provenance["osm_waterways"] = {
            "n_ways": len({lid for lid, _, _ in lines}),
            "total_length_m": round(sum(p.length for _, _, p in lines), 1),
            "types": sorted({wt for _, wt, _ in lines}),
            "source": src,
        }
    else:
        # fresh Overpass query around the current geometry
        coords = ([site["geometry"]["coordinates"]]
                  if site["geometry"]["type"] == "Point"
                  else site["geometry"]["coordinates"])
        s, w, n, e = site_bbox_pad(coords, SITE_RADIUS_M)
        try:
            lines = overpass_waterway_lines(s, w, n, e, clip_to=site_buffer)
            provenance["osm_waterways"] = {
                "n_ways": len({lid for lid, _, _ in lines}),
                "total_length_m": round(sum(p.length for _, _, p in lines), 1),
                "types": sorted({wt for _, wt, _ in lines}),
                "source": "fresh Overpass query around current geometry",
            }
        except RuntimeError as exc:
            lines = []
            provenance["osm_waterways"] = {
                "n_ways": 0, "total_length_m": 0.0, "types": [],
                "source": f"Overpass query failed ({str(exc)[:80]})",
            }
    use_geom, geom_note = GEOMETRY_USE[sid]
    provenance["site_geometry_used"] = use_geom
    provenance["site_geometry_type"] = site["geometry"]["type"]
    provenance["location_confidence"] = site.get("location_confidence")
    provenance["geometry_note"] = geom_note

    parts = [p for _, _, p in lines]
    geom_ch = None
    if use_geom and site["geometry"]["type"] == "LineString":
        parts.append(site_geom_utm)
        geom_ch = site_geom_utm
    elif use_geom and site["geometry"]["type"] == "Point":
        geom_ch = site_geom_utm
    if not parts and geom_ch is None:
        return None, provenance
    if geom_ch is not None and isinstance(geom_ch, Point):
        channel = geom_ch
    else:
        channel = unary_union(parts) if parts else None
        if channel is None or channel.is_empty:
            return None, provenance
    return channel, provenance


# ---------------------------------------------------------------------------
# per-site run
# ---------------------------------------------------------------------------

def run_site(site, site_dir, executor):
    sid = site["site_id"]
    geom_lonlat = _shape(site["geometry"])
    site_geom_utm = to_utm(geom_lonlat)
    site_buffer = site_geom_utm.buffer(SITE_RADIUS_M)
    channel, prov = channels_for_site(site, site_dir, site_geom_utm, site_buffer)
    if channel is None:
        return {"site_id": sid, "included": False, "channel": prov}
    meta = band_cells(channel, site_buffer)
    n_cells = meta["bi"].size
    if n_cells == 0:
        prov["note"] = "no band cells"
        return {"site_id": sid, "included": False, "channel": prov}

    # cache
    fp = CACHE_SITES / f"{sid}.npz"
    vals = {}
    if fp.exists():
        z = np.load(fp)
        if str(z["geom_hash"]) == geom_hash(site["geometry"]):
            for y in YEARS:
                vals[y] = z[f"pres{y}"]
            meta = dict(gx0=float(z["gx0"]), gy_top=float(z["gy_top"]),
                        nx=int(z["nx"]), ny=int(z["ny"]),
                        bi=z["bi"], bj=z["bj"], band_id=z["band_id"])
            log(f"[sites] {sid}: {n_cells} band cells (cached)")
            return {"site_id": sid, "included": True, "channel": prov,
                    "meta": meta, "vals": vals, "_channel": channel}

    chunks = chunk_set(meta)
    log(f"[sites] {sid}: channel {type(channel).__name__}, "
        f"{n_cells} band cells, {len(chunks)} chunks x {len(YEARS)} years")

    def work(args):
        y, ck = args
        return y, ck, read_chunk_cells(y, ck[0], ck[1])

    grids = {}
    fut = [executor.submit(work, (y, ck)) for y in YEARS for ck in chunks]
    for f in as_completed(fut):
        y, ck, cells = f.result()
        grids.setdefault(y, []).append((ck, cells))

    for y in YEARS:
        grid = np.full((meta["ny"], meta["nx"]), np.nan, np.float32)
        for ck, cells in grids.get(y, []):
            j0 = int((ck[0] - meta["gx0"]) / CELL)
            i0 = int((meta["gy_top"] - ck[1]) / CELL)
            jc0, jc1 = max(j0, 0), min(j0 + cells.shape[1], meta["nx"])
            ic0, ic1 = max(i0, 0), min(i0 + cells.shape[0], meta["ny"])
            if jc1 <= jc0 or ic1 <= ic0:
                continue
            grid[ic0:ic1, jc0:jc1] = cells[ic0 - i0:ic1 - i0,
                                           jc0 - j0:jc1 - j0]
        vals[y] = grid[meta["bi"], meta["bj"]]

    CACHE_SITES.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(fp, bi=meta["bi"], bj=meta["bj"],
                         band_id=meta["band_id"], gx0=meta["gx0"],
                         gy_top=meta["gy_top"], nx=meta["nx"], ny=meta["ny"],
                         geom_hash=geom_hash(site["geometry"]),
                         **{f"pres{y}": vals[y] for y in YEARS})
    return {"site_id": sid, "included": True, "channel": prov,
            "meta": meta, "vals": vals, "_channel": channel}


# ---------------------------------------------------------------------------
# baseline
# ---------------------------------------------------------------------------

def fetch_baseline_waterways():
    fp = CACHE / "waterways_aoi.json"
    if fp.exists():
        return json.loads(fp.read_text())
    w, s, e, n = BASELINE_AOI
    data = overpass(waterway_query(s, w, n, e))
    fp.parent.mkdir(parents=True, exist_ok=True)
    fp.write_text(json.dumps(data))
    return data


def sample_segments(data, sites_union):
    """200 random 300 m waterway segments >= 1 km from any named site."""
    lines = []
    for el in data.get("elements", []):
        if el.get("type") != "way" or not el.get("geometry"):
            continue
        tags = el.get("tags", {})
        if tags.get("waterway") not in WATERWAY_TYPES:
            continue
        nodes = el["geometry"]
        if len(nodes) < 2:
            continue
        xs, ys = _warp([nd["lon"] for nd in nodes],
                       [nd["lat"] for nd in nodes], "EPSG:4326", UTM)
        line = LineString(list(zip(xs, ys)))
        if line.length >= BASELINE_SEG_M:
            lines.append((el.get("id"), line))
    if not lines:
        raise RuntimeError("no OSM waterways >= 300 m in the baseline AOI")
    rng = np.random.default_rng(BASELINE_SEED)
    lengths = np.array([l.length for _, l in lines])
    p = lengths / lengths.sum()
    segs = []
    mids = []
    spacing = BASELINE_MIN_SEP_M
    attempts = 0
    while len(segs) < BASELINE_N_SEG and attempts < 45000:
        attempts += 1
        if attempts in (15000, 30000):
            spacing = 200.0 if attempts == 15000 else 0.0
        idx = int(rng.choice(len(lines), p=p))
        way_id, line = lines[idx]
        u = float(rng.uniform(0, line.length - BASELINE_SEG_M))
        seg = substring(line, u, u + BASELINE_SEG_M)
        if seg.distance(sites_union) <= BASELINE_EXCL_SITE_M:
            continue
        mid = seg.interpolate(0.5, normalized=True)
        if spacing > 0 and mids:
            dd = min((mid.distance(m) for m in mids))
            if dd < spacing:
                continue
        segs.append((way_id, seg))
        mids.append(mid)
    return segs, dict(n_ways_ge_300m=len(lines), attempts=attempts,
                      n_accepted=len(segs))


def run_baseline(executor, sites_union):
    fp = CACHE_BASELINE / "segments.npz"
    data = fetch_baseline_waterways()
    segs, sampling = sample_segments(data, sites_union)
    log(f"[baseline] {sampling['n_ways_ge_300m']} waterway ways >= 300 m; "
        f"{sampling['n_accepted']} segments accepted in {sampling['attempts']} attempts")

    if fp.exists():
        z = np.load(fp)
        if int(z["n_seg"]) == len(segs):
            return dict(built=z["built"], nvalid=z["nvalid"], newly=z["newly"],
                        way_ids=z["way_ids"], mid_lon=z["mid_lon"],
                        mid_lat=z["mid_lat"], sampling=sampling, cached=True)

    def work(args):
        way_id, seg = args
        meta = band_cells(seg, None)
        chunks = chunk_set(meta)
        grids = []
        for y in YEARS:
            grid = np.full((meta["ny"], meta["nx"]), np.nan, np.float32)
            for ck in chunks:
                cells = read_chunk_cells(y, ck[0], ck[1])
                j0 = int((ck[0] - meta["gx0"]) / CELL)
                i0 = int((meta["gy_top"] - ck[1]) / CELL)
                jc0, jc1 = max(j0, 0), min(j0 + cells.shape[1], meta["nx"])
                ic0, ic1 = max(i0, 0), min(i0 + cells.shape[0], meta["ny"])
                if jc1 <= jc0 or ic1 <= ic0:
                    continue
                grid[ic0:ic1, jc0:jc1] = cells[ic0 - i0:ic1 - i0,
                                               jc0 - j0:jc1 - j0]
            grids.append(grid[meta["bi"], meta["bj"]])
        vals = {y: grids[i] for i, y in enumerate(YEARS)}
        ser = band_series(vals, meta["band_id"])
        built = np.zeros((3, len(YEARS)))
        nvalid = np.zeros((3, len(YEARS)))
        newly = np.zeros((3, len(NEW_YEARS)))
        for b in range(1, 4):
            e = ser[b]
            for yi, y in enumerate(YEARS):
                frac = e["built_fraction"][THR_MAIN][y]
                built[b - 1, yi] = np.nan if frac is None else frac
                nvalid[b - 1, yi] = e["n_valid"][y]
            for ti, t in enumerate(NEW_YEARS):
                newly[b - 1, ti] = e["newly_built_m2"][t]
        mid = seg.interpolate(0.5, normalized=True)
        return way_id, mid, built, nvalid, newly

    built = np.full((len(segs), 3, len(YEARS)), np.nan)
    nvalid = np.zeros((len(segs), 3, len(YEARS)), np.int32)
    newly = np.zeros((len(segs), 3, len(NEW_YEARS)))
    way_ids = np.zeros(len(segs), np.int64)
    mid_lon = np.zeros(len(segs)); mid_lat = np.zeros(len(segs))
    done = 0
    fut = [executor.submit(work, s) for s in segs]
    for f in as_completed(fut):
        way_id, mid, b, nv, nw = f.result()
        i = done
        way_ids[i] = way_id or 0
        mlon, mlat = _warp([mid.x], [mid.y], UTM, "EPSG:4326")
        mid_lon[i], mid_lat[i] = mlon[0], mlat[0]
        built[i] = b; nvalid[i] = nv; newly[i] = nw
        done += 1
        if done % 20 == 0:
            log(f"[baseline] {done}/{len(segs)} segments")
    CACHE_BASELINE.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(fp, n_seg=len(segs), built=built, nvalid=nvalid,
                        newly=newly, way_ids=way_ids, mid_lon=mid_lon,
                        mid_lat=mid_lat)
    return dict(built=built, nvalid=nvalid, newly=newly, way_ids=way_ids,
                mid_lon=mid_lon, mid_lat=mid_lat, sampling=sampling)


# ---------------------------------------------------------------------------
# validation
# ---------------------------------------------------------------------------

def osm_buildings(site_dir, site):
    fp = site_dir / "osm.geojson"
    d = json.loads(fp.read_text())
    polys = []
    for f in d.get("features", []):
        if f.get("properties", {}).get("kind") != "building":
            continue
        g = to_utm(_shape(f["geometry"]))
        if g.geom_type == "Polygon":
            polys.append(g)
        elif g.geom_type == "MultiPolygon":
            polys.extend(g.geoms)
    return polys


def run_validation(site, site_dir, executor, channel=None):
    sid = site["site_id"]
    fp = CACHE_VALIDATION / f"{sid}.npz"
    geom_utm = to_utm(_shape(site["geometry"]))
    site_buffer = geom_utm.buffer(SITE_RADIUS_M)
    minx, miny, maxx, maxy = site_buffer.bounds
    gx0 = math.floor(minx / CELL) * CELL
    gy_top = math.ceil(maxy / CELL) * CELL
    nx = int(math.ceil((maxx - gx0) / CELL))
    ny = int(math.ceil((gy_top - miny) / CELL))
    if fp.exists():
        z = np.load(fp)
        grid2023 = z["grid2023"]
    else:
        chunks = []
        for cyt in np.arange(gy_top, miny - CHUNK, -CHUNK):
            for cx in np.arange(gx0, maxx + CHUNK, CHUNK):
                chunks.append((float(cx), float(cyt)))
        grid2023 = np.full((ny, nx), np.nan, np.float32)
        futs = [executor.submit(read_chunk_cells, 2023, ck[0], ck[1])
                for ck in chunks]
        for ck, f in zip(chunks, futs):
            cells = f.result()
            j0 = int((ck[0] - gx0) / CELL)
            i0 = int((gy_top - ck[1]) / CELL)
            jc0, jc1 = max(j0, 0), min(j0 + cells.shape[1], nx)
            ic0, ic1 = max(i0, 0), min(i0 + cells.shape[0], ny)
            if jc1 <= jc0 or ic1 <= ic0:
                continue
            grid2023[ic0:ic1, jc0:jc1] = cells[ic0 - i0:ic1 - i0,
                                               jc0 - j0:jc1 - j0]
        CACHE_VALIDATION.mkdir(parents=True, exist_ok=True)
        np.savez_compressed(fp, grid2023=grid2023, gx0=gx0, gy_top=gy_top,
                            nx=nx, ny=ny)
    ob_built = grid2023 >= THR_MAIN
    aff = from_origin(gx0, gy_top, CELL, CELL)
    bpolys = osm_buildings(site_dir, site)
    osm_mask = rasterize([(p, 1) for p in bpolys], out_shape=(ny, nx),
                         transform=aff, fill=0, dtype="uint8") == 1
    xs = gx0 + CELL * np.arange(nx) + CELL / 2.0
    ys = gy_top - CELL * np.arange(ny) - CELL / 2.0
    xx, yy = np.meshgrid(xs, ys)
    pts = shapely_points(xx.ravel(), yy.ravel())
    inside = contains_xy(site_buffer, xx.ravel(), yy.ravel()).reshape(ny, nx)
    valid = ~np.isnan(grid2023) & inside
    if channel is not None:
        d = shapely_distance(pts, channel).reshape(ny, nx)
    else:
        d = np.full(xx.size, np.inf)
    near = d <= 20.0

    def scores(mask):
        m = mask & valid
        ob = ob_built & m
        osm = osm_mask & m
        tp = int((ob & osm).sum())
        prec = tp / int(ob.sum()) if ob.any() else None
        rec = tp / int(osm.sum()) if osm.any() else None
        return {"precision": r(prec), "recall": r(rec),
                "n_ob_built": int(ob.sum()), "n_osm_built": int(osm.sum())}

    return dict(sid=sid, overall=scores(np.ones_like(valid)),
                within_20m=scores(near), grid2023=grid2023, gx0=gx0,
                gy_top=gy_top, nx=nx, ny=ny, channel=channel,
                site_geom=geom_utm, buffer=site_buffer, bpolys=bpolys)


def wayback_overlay(site, site_dir, val):
    sid = site["site_id"]
    img = json.loads(IMAGERY_JSON.read_text())
    entry = next((s for s in img["sites"] if s["site_id"] == sid), None)
    if entry is None:
        return None, None
    chips = [i for i in entry.get("images", [])
             if (SITES_DIR / sid / Path(i["file"]).name).exists()]
    if not chips:
        return None, None
    chip = max(chips, key=lambda i: i["acq_date"])
    chip_path = SITES_DIR / sid / Path(chip["file"]).name
    geom_utm = to_utm(_shape(entry["geometry"]))
    minx, miny, maxx, maxy = geom_utm.bounds
    if entry["geometry"]["type"] == "Point":
        extent = (minx - 250, maxx + 250, miny - 250, maxy + 250)
    else:
        extent = (minx - 150, maxx + 150, miny - 150, maxy + 150)
    m = re.search(r"\((\d+) x (\d+) m\)", entry.get("chip_window") or "")
    if m:
        w_m, h_m = float(m.group(1)), float(m.group(2))
        if abs((extent[1] - extent[0]) - w_m) > 6 or abs((extent[3] - extent[2]) - h_m) > 6:
            cx = (extent[0] + extent[1]) / 2
            cy = (extent[2] + extent[3]) / 2
            extent = (cx - w_m / 2, cx + w_m / 2, cy - h_m / 2, cy + h_m / 2)

    fig, ax = plt.subplots(figsize=(9, 7), dpi=150)
    pil = Image.open(chip_path).convert("RGB")
    ax.imshow(np.asarray(pil), extent=extent, origin="upper", zorder=0)
    masked = np.ma.masked_invalid(np.where(val["grid2023"] >= THR_MAIN, 1.0, 0.0))
    cmap = ListedColormap([(0, 0, 0, 0), (1, 0, 0, 0.45)])
    ax.imshow(masked, extent=(val["gx0"], val["gx0"] + CELL * val["nx"],
                             val["gy_top"] - CELL * val["ny"], val["gy_top"]),
              origin="upper", cmap=cmap, vmin=0, vmax=1, zorder=2,
              interpolation="nearest")
    for p in val["bpolys"]:
        ex, ey = p.exterior.xy
        ax.plot(ex, ey, color="cyan", lw=0.5, alpha=0.9, zorder=3)
    if val["channel"] is not None:
        plot_line(ax, val["channel"], color="yellow", lw=2.2, zorder=4)
    plot_line(ax, val["site_geom"], color="white", lw=1.2, ls="--", zorder=5)
    ax.set_xlim(extent[0], extent[1])
    ax.set_ylim(extent[2], extent[3])
    ax.set_title(f"{sid} - Open Buildings 2023 built cells (red) vs OSM "
                 f"footprints (cyan) over Esri Wayback {chip['acq_date']}",
                 fontsize=9)
    ax.set_xticks([]); ax.set_yticks([])
    out = site_dir / "ob_validation.png"
    fig.savefig(out, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return out, chip["acq_date"]


# ---------------------------------------------------------------------------
# plots
# ---------------------------------------------------------------------------

def event_date(site):
    ev = site.get("event_id", "")
    m = re.match(r"lagos-(\d{4}-\d{2}-\d{2})$", ev)
    if not m:
        return None
    y, mo, d = (int(x) for x in m.group(1).split("-"))
    doy = (datetime(y, mo, d) - datetime(y, 1, 1)).days + 1
    return m.group(1), y + (doy - 1) / 365.25


def timeline_png(site, res, base_stats):
    sid = site["site_id"]
    ser = band_series(res["vals"], res["meta"]["band_id"])
    fig, ax = plt.subplots(figsize=(8, 4.6), dpi=150)
    yy = YEARS
    for b in range(1, 4):
        col = BAND_COLORS[b - 1]
        frac = [np.nan if ser[b]["built_fraction"][THR_MAIN][y] is None
                else ser[b]["built_fraction"][THR_MAIN][y] for y in YEARS]
        lbl = f"{BAND_KEYS[b-1]} m (n={ser[b]['n_cells']})"
        ax.plot(yy, frac, color=col, marker="o", ms=3.5, lw=1.6, label=lbl)
        bs = base_stats[b - 1]
        if bs is not None:
            ax.plot(yy, bs["median"], color=col, lw=1.0, ls="--", alpha=0.7)
            ax.fill_between(yy, bs["q1"], bs["q3"], color=col, alpha=0.10,
                            lw=0)
    ev = event_date(site)
    if ev is not None:
        dtxt, x = ev
        if 2016 <= x <= 2023.99:
            ax.axvline(x, color="black", lw=1.0, ls=":", alpha=0.7)
            ax.annotate(f"flood {dtxt}", xy=(x, 0.02), xycoords=("data", "axes fraction"),
                        rotation=90, fontsize=7, ha="right", va="bottom")
        else:
            ax.annotate(f"flood {dtxt} ->", xy=(0.995, 0.97),
                        xycoords="axes fraction", fontsize=7, ha="right",
                        va="top", color="black")
    ax.set_xticks(YEARS)
    ax.set_ylim(0, 1)
    ax.set_ylabel("built fraction (presence >= 0.5, 4 m cells)")
    ax.set_xlabel("Open Buildings year")
    prov = res["channel"]
    ax.set_title(f"{sid} - building cover beside channel "
                 f"(dashed = city-wide baseline median, shaded = IQR)",
                 fontsize=9)
    ax.legend(fontsize=7, loc="upper left")
    ax.grid(alpha=0.25, lw=0.5)
    out = SITES_DIR / sid / "ob_timeline.png"
    fig.savefig(out, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return out


def mask_png(site, res, year):
    sid = site["site_id"]
    meta = res["meta"]
    grid = np.full((meta["ny"], meta["nx"]), np.nan, np.float32)
    grid[meta["bi"], meta["bj"]] = res["vals"][year]
    mask = np.ma.masked_invalid((grid >= THR_MAIN).astype(np.float32))
    cmap = ListedColormap(["#efefef", "#d62728"])
    cmap.set_bad("#ffffff", alpha=0.0)
    aspect = meta["ny"] / max(meta["nx"], 1)
    fig, ax = plt.subplots(figsize=(7, float(np.clip(7 * aspect, 2.2, 10.0))),
                           dpi=150)
    ax.imshow(mask, extent=(meta["gx0"], meta["gx0"] + CELL * meta["nx"],
                            meta["gy_top"] - CELL * meta["ny"], meta["gy_top"]),
              origin="upper", cmap=cmap, vmin=0, vmax=1,
              interpolation="nearest")
    if res.get("_channel") is not None:
        plot_line(ax, res["_channel"], color="yellow", lw=1.8)
    ax.set_xticks([]); ax.set_yticks([])
    ax.set_title(f"{sid} - {year}: cells built (presence >= 0.5); "
                 f"channel in yellow", fontsize=9)
    out = SITES_DIR / sid / f"ob_{year}.png"
    fig.savefig(out, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return out


# ---------------------------------------------------------------------------
# report
# ---------------------------------------------------------------------------

def baseline_stats(built):
    stats = []
    for b in range(3):
        med, q1, q3, mean_ = [], [], [], []
        for yi in range(len(YEARS)):
            v = built[:, b, yi]
            v = v[~np.isnan(v)]
            if v.size == 0:
                med.append(np.nan); q1.append(np.nan); q3.append(np.nan); mean_.append(np.nan)
            else:
                med.append(float(np.median(v)))
                q1.append(float(np.percentile(v, 25)))
                q3.append(float(np.percentile(v, 75)))
                mean_.append(float(v.mean()))
        stats.append({"median": med, "q1": q1, "q3": q3, "mean": mean_})
    return stats


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--sites", help="comma-separated site_ids to run (default all)")
    ap.add_argument("--skip-baseline", action="store_true")
    ap.add_argument("--keep-cache", action="store_true")
    args = ap.parse_args()

    t0 = time.time()
    CACHE.mkdir(parents=True, exist_ok=True)
    sites = json.loads(SITES_JSON.read_text())["sites"]
    if args.sites:
        only = set(args.sites.split(","))
        sites = [s for s in sites if s["site_id"] in only]

    # region for the tile index: all site buffers + baseline AOI
    corners = []
    for s in sites:
        g = to_utm(_shape(s["geometry"]))
        corners.append(g.buffer(SITE_RADIUS_M).bounds)
    w, s_, e, n = BASELINE_AOI
    bxs, bys = _warp([w, e, w, e], [s_, s_, n, n], "EPSG:4326", UTM)
    corners.append((min(bxs), min(bys), max(bxs), max(bys)))
    region = (min(c[0] for c in corners), min(c[1] for c in corners),
              max(c[2] for c in corners), max(c[3] for c in corners))
    log(f"[ob] tile index for region x {region[0]:.0f}-{region[2]:.0f}, "
        f"y {region[1]:.0f}-{region[3]:.0f}")
    global TILE_INDEX
    TILE_INDEX = build_tile_index(region)
    for y in YEARS:
        log(f"  {y}: {len(TILE_INDEX[y])} tiles in region")

    executor = ThreadPoolExecutor(max_workers=8)

    # ---- sites ------------------------------------------------------------
    results = {}
    skipped = []
    for s in sites:
        site_dir = SITES_DIR / s["site_id"]
        res = run_site(s, site_dir, executor)
        if not res["included"]:
            skipped.append(s["site_id"])
        results[s["site_id"]] = res
        log(f"[sites] done {s['site_id']} (included={res['included']})")

    # ---- baseline ----------------------------------------------------------
    base = None
    base_stats_ = None
    if not args.skip_baseline:
        all_sites = json.loads(SITES_JSON.read_text())["sites"]
        sites_union = unary_union([to_utm(_shape(s["geometry"])) for s in all_sites])
        base = run_baseline(executor, sites_union)
        base_stats_ = baseline_stats(base["built"])
        log(f"[baseline] {base['sampling']['n_accepted']} segments, "
            f"{'cached' if base.get('cached') else 'computed'}")

    # ---- validation ---------------------------------------------------------
    validations = {}
    if not args.skip_baseline:
        for sid in VALIDATION_SITES:
            if sid not in results or not results[sid]["included"]:
                continue
            val = run_validation(next(s for s in sites if s["site_id"] == sid),
                                 SITES_DIR / sid, executor,
                                 channel=results[sid]["_channel"])
            overlay, chip_date = wayback_overlay(
                next(s for s in sites if s["site_id"] == sid),
                SITES_DIR / sid, val)
            validations[sid] = {
                "overall": val["overall"], "within_20m": val["within_20m"],
                "chip_date": chip_date,
                "overlay": str(overlay.relative_to(REPO)) if overlay else None,
            }
            log(f"[validation] {sid}: precision "
                f"{val['overall']['precision']} recall {val['overall']['recall']}")

    # ---- plots --------------------------------------------------------------
    for s in sites:
        res = results[s["site_id"]]
        if not res["included"]:
            continue
        files = {"timeline": None, "masks": []}
        if base_stats_ is not None:
            files["timeline"] = str(timeline_png(s, res, base_stats_).relative_to(REPO))
        for y in (2016, 2019, 2023):
            files["masks"].append(str(mask_png(s, res, y).relative_to(REPO)))
        res["files"] = files

    # ---- JSON ---------------------------------------------------------------
    out = {"meta": {
        "task": "21-open-buildings-encroachment",
        "generated": utc_now(),
        "source": OB_SOURCE,
        "access": ("public GCS bucket open-buildings-temporal-data; manifests "
                   "11_EPSG_32631_<year>_06_30.json (token 11 covers Lagos; "
                   "token 13 lies north of the AOI); ranged COG reads via "
                   "/vsicurl/ - no tile downloaded"),
        "licence": OB_LICENCE,
        "citation": OB_CITATION,
        "thresholds": {"primary": THR_MAIN, "sensitivity": [0.4, 0.6],
                       "note": "building_presence is an uncalibrated model "
                               "confidence; thresholded, never read as a probability"},
        "method": {
            "bands": "0-10 / 10-20 / 20-50 m from the channel centreline "
                     "(or rings around the point for point-geometry sites), "
                     "clipped to the site's 300 m radius",
            "resampling": "8x8 block-mean of the 0.5 m building_presence "
                          "pixels -> 4 m cells on a world 4 m-aligned grid, "
                          "then thresholded",
            "built_fraction": "share of band cells with valid data whose "
                              "block-mean presence >= threshold",
            "newly_built": "a cell is newly built in year t if built in t and "
                           "t+1 and not built in t-1 and t-2 (threshold 0.5); "
                           "defined for 2018-2022 only; area = cells x 16 m^2",
            "channels": "OSM waterway=drain|canal|stream|ditch|river within the "
                        "site's 300 m radius (Task 18 osm.geojson when current, "
                        "else a fresh Overpass query), plus the site geometry "
                        "where the recorded structure is a channel and the line "
                        "is a channel alignment rather than a road (per-site "
                        "decisions recorded under channel.geometry_note)",
            "baseline": f"{BASELINE_N_SEG} random {BASELINE_SEG_M:.0f} m segments "
                        f"of OSM waterways in the AOI {list(BASELINE_AOI)}, at "
                        f"least {BASELINE_EXCL_SITE_M:.0f} m from any named site "
                        f"(seed {BASELINE_SEED}); same bands and series",
            "nodata": "presence nodata -99 excluded before the block-mean",
        },
        "caveats": [
            "4 m effective resolution: the 0-10 m band is 2-3 cells wide - "
            "read trends, not exact counts",
            "Open Buildings 2.5D Temporal annual composites are dated "
            "<year>_06_30 and are Sentinel-2 derived; small or temporary "
            "structures may be missed",
            "OSM waterways and buildings are current-date data; channel "
            "alignments for ikorodu-dammed and ijede-drain are town-to-town "
            "corridors, not surveyed centrelines",
            "sangotedo-channel-notices has no centreline: bands are rings "
            "around the Lagos Business School inspection point",
        ],
        "site_count": len(sites),
        "included": sorted(k for k, v in results.items() if v["included"]),
        "skipped_no_channel": skipped,
    }, "sites": [], "baseline": None, "validation": None}

    for s in sites:
        res = results[s["site_id"]]
        if not res["included"]:
            out["sites"].append({
                "site_id": s["site_id"], "event_id": s.get("event_id"),
                "included": False,
                "skip_reason": "no channel line within the site's 300 m radius "
                               "and no usable channel geometry",
                "channel": res["channel"],
            })
            continue
        ser = band_series(res["vals"], res["meta"]["band_id"])
        bands = {}
        for b in range(1, 4):
            e = ser[b]
            bands[BAND_KEYS[b - 1]] = {
                "n_cells": e["n_cells"],
                "n_valid": {str(y): e["n_valid"][y] for y in YEARS},
                "built_fraction": {str(y): r(e["built_fraction"][THR_MAIN][y]) for y in YEARS},
                "built_fraction_thr_0.4": {str(y): r(e["built_fraction"][0.4][y]) for y in YEARS},
                "built_fraction_thr_0.6": {str(y): r(e["built_fraction"][0.6][y]) for y in YEARS},
                "newly_built_m2": {str(t): r(e["newly_built_m2"][t], 1) for t in NEW_YEARS},
            }
        site_out = {
            "site_id": s["site_id"], "event_id": s.get("event_id"),
            "included": True, "channel": res["channel"], "bands": bands,
        }
        if "files" in res:
            site_out["files"] = res["files"]
        out["sites"].append(site_out)

    if base is not None:
        nb = {}
        for b in range(3):
            st = base_stats_[b]
            nb[BAND_KEYS[b]] = {
                "n_segments_with_data": {str(y): int((~np.isnan(base["built"][:, b, YEARS.index(y)])).sum()) for y in YEARS},
                "median": {str(y): r(st["median"][i]) for i, y in enumerate(YEARS)},
                "iqr": {"q1": {str(y): r(st["q1"][i]) for i, y in enumerate(YEARS)},
                        "q3": {str(y): r(st["q3"][i]) for i, y in enumerate(YEARS)}},
                "mean": {str(y): r(st["mean"][i]) for i, y in enumerate(YEARS)},
                "newly_built_m2_sum": {str(t): r(float(np.nansum(base["newly"][:, b, i])), 1)
                                       for i, t in enumerate(NEW_YEARS)},
                "newly_built_m2_median_per_segment": {
                    str(t): r(float(np.nanmedian(base["newly"][:, b, i])), 1)
                    if np.any(~np.isnan(base["newly"][:, b, i])) else None
                    for i, t in enumerate(NEW_YEARS)},
            }
        per_seg = []
        for i in range(base["built"].shape[0]):
            per_seg.append({
                "way_id": int(base["way_ids"][i]),
                "midpoint": [r(base["mid_lon"][i], 5), r(base["mid_lat"][i], 5)],
                "built_fraction": {
                    BAND_KEYS[b]: {"2016": r(base["built"][i, b, 0]),
                                   "2023": r(base["built"][i, b, 7])}
                    for b in range(3)},
            })
        out["baseline"] = {
            "aoi": list(BASELINE_AOI),
            "segment_length_m": BASELINE_SEG_M,
            "n_segments": int(base["built"].shape[0]),
            "sampling": base["sampling"],
            "exclusion": f">= {BASELINE_EXCL_SITE_M:.0f} m from any named site",
            "bands": nb,
            "per_segment": per_seg,
        }

    out["validation"] = {
        "method": "2023 presence >= 0.5 mask vs OSM building footprints "
                  "(Task 18 osm.geojson, current geometry) at 4 m: a cell is "
                  "OSM-built when its centre falls inside a footprint. "
                  "Precision = fraction of Open-Buildings-built cells that "
                  "contain an OSM footprint; recall = fraction of OSM "
                  "footprint cells the mask detects. OSM completeness varies "
                  "across Lagos, so recall is an agreement score, not a "
                  "ground-truth accuracy; overlays saved against the latest "
                  "Wayback chip.",
        "sites": validations,
    }

    OUT_JSON.write_text(json.dumps(out, indent=1))
    log(f"[out] {OUT_JSON.relative_to(REPO)}")

    # ---- printed tables ------------------------------------------------------
    print()
    print("=" * 118)
    print("Building cover beside the blamed channels (Open Buildings presence >= 0.5, 4 m cells)")
    print("=" * 118)
    hdr = (f"{'site':<28} {'chan src':<9} {'0-10m 16':>9} {'0-10m 23':>9} "
           f"{'delta':>7} {'base d16':>9} {'base d23':>9} {'pctile':>7}")
    print(hdr)
    print("-" * 118)

    def fmt(v, w=9, nd=3):
        return f"{v:>{w}.{nd}f}" if v is not None else f"{'n/a':>{w}}"

    for s in sites:
        res = results[s["site_id"]]
        if not res["included"]:
            print(f"{s['site_id']:<28} {'SKIP':<9} no channel line")
            continue
        ser = band_series(res["vals"], res["meta"]["band_id"])
        b1 = ser[1]["built_fraction"][THR_MAIN]
        f16, f23 = b1[2016], b1[2023]
        src = "geom" if res["channel"]["site_geometry_used"] else "osm"
        if res["channel"]["site_geometry_used"] and res["channel"]["osm_waterways"]["n_ways"] > 0:
            src = "both"
        row = f"{s['site_id']:<28} {src:<9} {fmt(f16)} {fmt(f23)}"
        if f16 is not None and f23 is not None:
            row += f" {f23 - f16:>+7.3f}"
        else:
            row += f" {'n/a':>7}"
        if base is not None:
            seg_d = base["built"][:, 0, 7] - base["built"][:, 0, 0]
            seg_d = seg_d[~np.isnan(seg_d)]
            v16 = base["built"][:, 0, 0]; v16 = v16[~np.isnan(v16)]
            v23 = base["built"][:, 0, 7]; v23 = v23[~np.isnan(v23)]
            d16 = float(np.median(v16)) if v16.size else float("nan")
            d23 = float(np.median(v23)) if v23.size else float("nan")
            row += f" {d16:>9.3f} {d23:>9.3f}"
            if f16 is not None and f23 is not None and seg_d.size:
                pct = float((seg_d <= (f23 - f16)).mean())
                row += f" {pct:>7.1%}"
            else:
                row += f" {'n/a':>7}"
        print(row)
    print()
    print("Newly built area (m^2) in the 0-10 m band, by year  (rule: built in t & t+1, "
          "not built in t-1 & t-2; >= 0.5)")
    hdr2 = f"{'site':<28}" + "".join(f" {y:>8}" for y in NEW_YEARS) + f" {'total':>9}"
    print(hdr2)
    print("-" * (28 + 9 * (len(NEW_YEARS) + 1)))
    for s in sites:
        res = results[s["site_id"]]
        if not res["included"]:
            continue
        ser = band_series(res["vals"], res["meta"]["band_id"])
        nb = ser[1]["newly_built_m2"]
        row = f"{s['site_id']:<28}"
        tot = 0.0
        for t in NEW_YEARS:
            v = nb[t]
            tot += v
            row += f" {v:>8.0f}"
        row += f" {tot:>9.0f}"
        print(row)
    if skipped:
        print()
        print("Skipped (no channel line): " + ", ".join(skipped))
    if validations:
        print()
        print("Validation (2023 mask vs OSM footprints, 4 m cells):")
        for sid, v in validations.items():
            o, n = v["overall"], v["within_20m"]
            print(f"  {sid:<28} precision {o['precision']}  recall {o['recall']}"
                  f"   | within 20 m: precision {n['precision']}  recall {n['recall']}")
    print()
    print("Read trends, not exact counts: 4 m effective resolution makes the "
          "0-10 m band 2-3 cells wide; ikorodu-dammed and ijede-drain use rough "
          "corridor alignments; sangotedo rings a point, not a centreline.")

    # ---- cache cleanup --------------------------------------------------------
    if not args.keep_cache:
        subprocess.run(["find", str(CACHE), "-type", "f", "-delete"],
                       check=True)
        log(f"[cache] removed files under {CACHE.relative_to(REPO)}")

    log(f"[done] {time.time() - t0:.0f} s")
    executor.shutdown()


if __name__ == "__main__":
    main()
