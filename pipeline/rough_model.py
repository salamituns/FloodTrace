#!/usr/bin/env python3
"""Rough-model water: where rain the drains can't take away could stand (Task 40, section C).

NOTE (21 Oct 2026): this layer was DROPPED from the app (Task 40b). Its own
validation, kept in events/rough_model/meta.json, showed it matched reported
floods no better than chance: at 20-80 mm of excess rain 2.2% of reported flood
spots fell inside the model's water against a 4-5% random baseline, and at 100
and 150 mm it reached 45-48% against a 44-45% baseline, because nearly all low
ground near the lagoon turns wet at once. The app now shows evidence water only.
This script is kept so the result can be reproduced; it also regenerates
roads.json and building_counts.json, which the evidence impacts still use.

A deliberately simple model, documented in plain words in the output meta:
- terrain: FABDEM 30 m (bare earth, buildings removed), smoothed 5x5 so DEM noise
  doesn't read as a pond;
- HAND: each cell's height above the nearest mapped waterway, lagoon or sea
  (straight-line nearest, not routed down a flow path);
- depressions: a priority-flood fill finds the hollows; a hollow holds rain up to its rim;
- scenarios: 20 / 40 / 60 / 80 / 100 / 150 mm of EXCESS rain (rain minus what the drains
  take away). Drain capacity is a stated parameter (10 mm/h) and the storm is assumed to
  last 6 h, so the 40 mm scenario is roughly a 100 mm storm;
- water stands where the excess rain is deeper than the cell's HAND, or in a hollow,
  whichever is deeper. Only the built-up area is kept, and only depths >= 10 cm.

Outputs under events/rough_model/:
- scenario_<n>mm.png  depth-coloured overlay (transparent where dry); bounds in meta.json.
  Alternate 30 m cells are drawn lighter, so the layer reads as a model, not a photo.
- water_polygons.json the same water as compact polygons, for the "what's hit" layer;
- building_counts.json building footprints per ~550 m cell from OSM, for "about N buildings";
- roads.json          named OSM roads near any possible water, for the same layer;
- meta.json           method, parameters, terrain verdict, validation, building coverage, sizes.

Honesty: our own terrain check (events/terrain/verdict.txt) found terrain only weakly
predicts which spot floods (flooded spots sit about 2 cm lower than their surroundings,
while the DEM's vertical error is about 2 m). The validation block scores every scenario
against the flood spots and the 3 Jul 2024 radar flood map and reports it even though it's poor.

Usage:
  pipeline/.venv/bin/python pipeline/rough_model.py             # everything; tiles fetched once into the cache
  pipeline/.venv/bin/python pipeline/rough_model.py --no-fetch # reuse cached tiles / roads only

Foreground only. No credentials. (A new venv package was needed: mapbox-vector-tile,
to decode OpenFreeMap vector tiles for the building counts and coverage report.)
"""

from __future__ import annotations

import argparse
import heapq
import json
import math
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import rasterio
import requests
from PIL import Image
from rasterio.features import rasterize, shapes
from rasterio.windows import Window
from scipy.ndimage import distance_transform_edt, uniform_filter
import shapely
from shapely.geometry import LineString, box, shape
from shapely.ops import unary_union
from shapely.prepared import prep

ROOT = Path(__file__).resolve().parents[1]
EVENTS = ROOT / "events"
OUT = EVENTS / "rough_model"
CACHE = ROOT / "pipeline" / "cache"
OFM_CACHE = CACHE / "openfreemap"
OSM_CACHE = CACHE / "osm"

DEM_TIF = CACHE / "dem" / "fabdem_aoi.tif"  # bare earth; GLO-30 includes buildings, don't use it
WATERWAYS = CACHE / "osm" / "waterways_aoi.geojson"
LAGOON = CACHE / "osm" / "lagoon_polygons.geojson"
SEA = CACHE / "osm" / "aoi_sea_polygon.geojson"

# Lagos urban core. The DEM covers 2.55-4.5 E; the far outskirts (Badagry side, Epe side)
# are cropped to keep the PNGs small - recorded in meta.json as the crop.
ANALYSIS_BBOX = [2.92, 6.35, 4.21, 6.78]

SCENARIOS_MM = [20, 40, 60, 80, 100, 150]
DRAIN_MM_PER_H = 10.0  # the stated drain-capacity assumption
STORM_H = 6.0          # assumed storm duration
MIN_DEPTH_M = 0.10
DEPTH_CAP_M = 2.0  # never claim more than 2 m: the DEM's vertical error is about 2 m
BUILT_SHARE_MIN = 0.05  # a GHSL cell counts as built-up at >= 5% built surface in 2020
SMOOTH_CELLS = 5        # 5x5 mean (~150 m) before HAND/fill, to kill DEM-noise ponds
DISC_RADIUS_M = {"street": 120.0}  # evidence-water disc radius by geocode confidence
DISC_RADIUS_DEFAULT_M = 400.0

CELL_DEG = 0.005  # ~550 m building-count cells for the "about N buildings" estimate
DEPTH_EDGES_M = [0.10, 0.20, 0.30, 0.50, 1.0]  # class upper edges; last class = everything deeper
CLASS_RGB = [(206, 230, 247), (178, 212, 240), (140, 190, 228), (95, 162, 210), (58, 128, 187)]
ALPHA_MAIN, ALPHA_STIPPLE = 205, 150  # the stipple: every other 30 m cell is lighter

ROAD_KINDS = {
    "motorway", "motorway_link", "trunk", "trunk_link", "primary", "primary_link",
    "secondary", "secondary_link", "tertiary", "tertiary_link", "unclassified",
    "residential", "living_street", "service", "busway",
}
UA = {"User-Agent": "FloodTrace pipeline (flood forensics; one-off, cached)"}


def say(msg: str) -> None:
    print(msg, flush=True)


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def save_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, separators=(",", ":")), encoding="utf-8")


# ── slippy-tile helpers ───────────────────────────────────────────────────


def tile_float(lon: float, lat: float, z: int) -> tuple[float, float]:
    n = 2**z
    r = math.radians(lat)
    return (lon + 180) / 360 * n, (1 - math.log(math.tan(r) + 1 / math.cos(r)) / math.pi) / 2 * n


def tile_bounds(x: int, y: int, z: int) -> tuple[float, float, float, float]:
    """(west, south, east, north) in lon/lat."""
    n = 2**z

    def lat_of(ty: float) -> float:
        return math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * ty / n))))

    return x / n * 360 - 180, lat_of(y + 1), (x + 1) / n * 360 - 180, lat_of(y)


def tile_range(bbox: list[float], z: int) -> tuple[range, range]:
    x0, y0 = tile_float(bbox[0], bbox[3], z)
    x1, y1 = tile_float(bbox[2], bbox[1], z)
    return range(int(math.floor(x0)), int(math.ceil(x1))), range(int(math.floor(y0)), int(math.ceil(y1)))


# ── DEM window ────────────────────────────────────────────────────────────


def read_dem_window() -> tuple[np.ndarray, Any, list[float]]:
    with rasterio.open(DEM_TIF) as ds:
        r0, c0 = ds.index(ANALYSIS_BBOX[0], ANALYSIS_BBOX[3])
        r1, c1 = ds.index(ANALYSIS_BBOX[2], ANALYSIS_BBOX[1])
        win = Window(c0, r0, c1 - c0, r1 - r0)
        dem = ds.read(1, window=win).astype(np.float32)
        transform = ds.window_transform(win)
        bounds = list(rasterio.windows.bounds(win, ds.transform))
    return dem, transform, bounds


# ── HAND and depression filling ───────────────────────────────────────────


def drainage_mask(shape_grid: tuple[int, int], transform: Any) -> np.ndarray:
    feats = []
    for path in (WATERWAYS, LAGOON, SEA):
        gj = load_json(path)
        for f in gj.get("features", []):
            if f.get("geometry"):
                feats.append((f["geometry"], 1))
    return rasterize(feats, out_shape=shape_grid, transform=transform, fill=0, all_touched=True).astype(bool)


def hand_above_drainage(dem: np.ndarray, drain: np.ndarray) -> np.ndarray:
    _, (jr, jc) = distance_transform_edt(~drain, return_indices=True)
    hand = dem - dem[jr, jc]
    np.maximum(hand, 0, out=hand)
    hand[drain] = 0.0
    return hand.astype(np.float32)


def fill_depressions(elev: np.ndarray, drain: np.ndarray) -> np.ndarray:
    """Priority-flood (Barnes). Seeds: window border + every mapped water cell, so
    hollows spill at the level of the water they drain to, not at the crop edge."""
    h, w = elev.shape
    filled = elev.astype(np.float64, copy=True)
    raw = elev.tolist()
    visited = np.zeros((h, w), dtype=bool)
    heap: list[tuple[float, int, int]] = []
    heappush, heappop = heapq.heappush, heapq.heappop

    def seed(r: int, c: int) -> None:
        visited[r, c] = True
        heappush(heap, (raw[r][c], r, c))

    for r in range(h):
        seed(r, 0)
        seed(r, w - 1)
    for c in range(1, w - 1):
        seed(0, c)
        seed(h - 1, c)
    for r, c in zip(*np.nonzero(drain)):
        if not visited[r, c]:
            seed(int(r), int(c))
    say(f"  priority-flood: {len(heap):,} seeds, {h * w:,} cells …")
    t0 = time.time()
    while heap:
        e, r, c = heappop(heap)
        for nr, nc in ((r - 1, c), (r + 1, c), (r, c - 1), (r, c + 1)):
            if 0 <= nr < h and 0 <= nc < w and not visited[nr, nc]:
                visited[nr, nc] = True
                re = raw[nr][nc]
                if re <= e:
                    filled[nr, nc] = e
                    heappush(heap, (e, nr, nc))
                else:
                    heappush(heap, (re, nr, nc))
    say(f"  filled in {time.time() - t0:.0f} s")
    return filled


# ── scenario water ────────────────────────────────────────────────────────


def built_mask(shape_grid: tuple[int, int], transform: Any) -> tuple[np.ndarray, tuple[list[float], list[float]]]:
    grid = load_json(EVENTS / "builtup_grid.geojson")
    feats, lons, lats = [], [], []
    for f in grid["features"]:
        if f["properties"].get("b2020", 0) >= BUILT_SHARE_MIN:
            feats.append((f["geometry"], 1))
            ring = f["geometry"]["coordinates"][0] if f["geometry"]["type"] == "Polygon" else f["geometry"]["coordinates"][0][0]
            lons.append(sum(p[0] for p in ring) / len(ring))
            lats.append(sum(p[1] for p in ring) / len(ring))
    m = rasterize(feats, out_shape=shape_grid, transform=transform, fill=0, all_touched=False).astype(bool)
    return m, (lons, lats)


def d8_flow_accumulation(elev: np.ndarray) -> np.ndarray:
    """Number of cells (self included) whose D8 steepest-descent path ends at each cell.
    Cells with no lower neighbour are pits: their accumulation is their catchment size."""
    h, w = elev.shape
    padded = np.pad(elev, 1, constant_values=np.inf)
    drop = np.zeros((h, w), np.float32)
    recv = np.full(h * w, -1, np.int64)
    flat_idx = np.arange(h * w, dtype=np.int64).reshape(h, w)
    for dr, dc in ((-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1)):
        nb = padded[1 + dr:1 + dr + h, 1 + dc:1 + dc + w]
        d = elev - nb
        better = (d > drop).ravel()
        drop = np.where(d > drop, d, drop)
        recv = np.where(better, flat_idx.ravel() + dr * w + dc, recv)
    order = np.argsort(elev.ravel(), kind="stable")[::-1]  # high ground first
    acc = np.ones(h * w, np.int32)
    say(f"  D8 accumulation over {h * w:,} cells …")
    t0 = time.time()
    for i in order:
        j = int(recv[i])
        if j >= 0:
            acc[j] += acc[i]
    say(f"  accumulated in {time.time() - t0:.0f} s")
    return acc.reshape(h, w)


def scenario_water(excess_m: float, hand: np.ndarray, dep: np.ndarray, acc: np.ndarray) -> np.ndarray:
    """Water depth per cell. Two mechanisms, whichever is deeper:
    - the excess rain stands above the nearest mapped water level (bathtub on HAND);
    - a hollow fills with the rain that falls on it AND on the ground that drains into it
      (D8 accumulation), up to its rim."""
    w = np.maximum(excess_m - hand, 0.0)
    np.maximum(w, np.minimum(dep, excess_m * acc), out=w)
    np.minimum(w, DEPTH_CAP_M, out=w)  # the DEM's ~2 m vertical error caps honest claims
    return w.astype(np.float32)


def write_png(path: Path, depth: np.ndarray) -> None:
    """Indexed PNG: depth classes in a cool light blue; every other 30 m cell is drawn
    lighter (the stipple), so the layer never passes for a real flood."""
    h, w = depth.shape
    idx = np.zeros((h, w), dtype=np.uint8)
    for i, edge in enumerate(DEPTH_EDGES_M):
        lo = DEPTH_EDGES_M[i - 1] if i else -1.0
        hi = edge if i < len(DEPTH_EDGES_M) - 1 else float("inf")
        cls = np.where((depth > lo) & (depth <= hi), i + 1, 0)
        checker = (np.arange(h)[:, None] + np.arange(w)[None, :]) % 2
        idx = np.where(cls > 0, cls * 2 - checker, idx).astype(np.uint8)
    img = Image.fromarray(idx, mode="P")
    pal: list[int] = []
    for rgb in CLASS_RGB:
        pal += list(rgb) + list(rgb)  # class*2-1 = solid, class*2 = lighter stipple cell
    img.putpalette(pal)
    img.info["transparency"] = bytes([0] + [ALPHA_MAIN, ALPHA_STIPPLE] * len(CLASS_RGB))
    path.parent.mkdir(parents=True, exist_ok=True)
    img.save(path, optimize=True)


def round_coords(poly: Any, nd: int = 4) -> Any:
    return shapely.transform(poly, lambda a: np.round(a, nd))


def safe_union(geoms: list[Any]) -> Any:
    """union that tolerates invalid rings (they occur after simplification/rounding)."""
    valid = []
    for g in geoms:
        g = g.buffer(0) if not g.is_valid else g
        if not g.is_empty and g.area > 0:
            valid.append(g)
    out = unary_union(valid) if valid else None
    return (out.buffer(0) if not out.is_valid else out) if out is not None else box(*ANALYSIS_BBOX)


def polygons_of(wet: np.ndarray, transform: Any) -> list[Any]:
    polys = [shape(g) for g, _ in shapes(wet.astype(np.uint8), mask=wet, transform=transform, connectivity=4)]
    if not polys:
        return []
    merged = unary_union(polys).simplify(0.00025)
    geoms = merged.geoms if merged.geom_type == "MultiPolygon" else [merged]
    return [round_coords(g) for g in geoms if not g.is_empty and g.area >= 6e-7]


def poly_to_json(p: Any) -> list[list[list[float]]]:
    g = p.__geo_interface__
    if g["type"] == "Polygon":
        return [[list(pt) for pt in ring] for ring in g["coordinates"]]
    return [[[list(pt) for pt in ring] for ring in poly] for poly in g["coordinates"]]


# ── evidence inputs (flood spots, radar flood) ────────────────────────────


def evidence_inputs() -> tuple[list[dict], list[Any]]:
    spots = load_json(EVENTS / "flood_spots.json")["spots"]
    sar = load_json(EVENTS / "lagos-2024-07-03" / "sar" / "flood.geojson")
    radar = [shape(f["geometry"]) for f in sar["features"] if f["properties"].get("class") == "open_flood"]
    return spots, radar


# ── OpenFreeMap tiles: coverage, building counts ──────────────────────────


def ofm_base_url(no_fetch: bool) -> str | None:
    if no_fetch:
        return None
    r = requests.get("https://tiles.openfreemap.org/planet", headers=UA, timeout=30)
    r.raise_for_status()
    return r.json()["tiles"][0].split("/{z}")[0]


def fetch_tile(base: str, z: int, x: int, y: int) -> tuple[int, int, bytes]:
    path = OFM_CACHE / f"{z}_{x}_{y}.pbf"
    if path.is_file():
        return x, y, path.read_bytes()
    for attempt in range(3):
        try:
            r = requests.get(f"{base}/{z}/{x}/{y}.pbf", headers=UA, timeout=60)
            r.raise_for_status()
            data = r.content
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
            return x, y, data
        except Exception:
            if attempt == 2:
                raise
            time.sleep(2 * (attempt + 1))
    raise RuntimeError("unreachable")


def building_count(data: bytes) -> int:
    if not data:
        return 0
    import mapbox_vector_tile

    decoded = mapbox_vector_tile.decode(data)
    return len(decoded.get("building", {}).get("features", []))


def fetch_counts(base: str, z: int, tiles: set[tuple[int, int]]) -> dict[str, int]:
    """tiles -> {'x/y': n_buildings}, fetched politely (8 at a time) and cached on disk."""
    todo = sorted(tiles)
    say(f"  fetching {len(todo)} z{z} tiles …")
    counts: dict[str, int] = {}
    with ThreadPoolExecutor(max_workers=8) as pool:
        for i, (x, y, data) in enumerate(pool.map(lambda t: fetch_tile(base, z, t[0], t[1]), todo)):
            counts[f"{x}/{y}"] = building_count(data)
            if (i + 1) % 100 == 0:
                say(f"    {i + 1}/{len(todo)}")
    return counts


ROAD_BBOX = [2.7, 6.38, 4.35, 6.75]  # the same AOI bbox as Task 39

# ── OSM buildings + roads, from a local Geofabrik extract ─────────────────
# Overpass could not serve either city-wide query: 504 gateway timeouts on every
# mirror, even for rural quarter-tiles. Both datasets instead come from one pass
# over the Geofabrik Nigeria extract (new venv package: osmium).

PBF_URL = "https://download.geofabrik.de/africa/nigeria-latest.osm.pbf"
PBF_PATH = OSM_CACHE / "nigeria-latest.osm.pbf"
EXTRACT_CACHE = OSM_CACHE / "lagos_extract.json"
BUILDINGS_BBOX = [ANALYSIS_BBOX[0] - 0.05, ANALYSIS_BBOX[1] - 0.05,
                  ANALYSIS_BBOX[2] + 0.05, ANALYSIS_BBOX[3] + 0.05]


def ensure_pbf(no_fetch: bool) -> Path:
    if PBF_PATH.is_file() and PBF_PATH.stat().st_size > 10_000_000:
        say("cache hit Geofabrik Nigeria extract")
        return PBF_PATH
    if no_fetch:
        raise SystemExit("--no-fetch but no cached extract; run once without it")
    say("downloading the Geofabrik Nigeria extract (one-off, cached) …")
    OSM_CACHE.mkdir(parents=True, exist_ok=True)
    tmp = PBF_PATH.with_name(PBF_PATH.name + ".part")
    with requests.get(PBF_URL, headers=UA, stream=True, timeout=600) as r:
        r.raise_for_status()
        total = int(r.headers.get("Content-Length", 0))
        done = 0
        with open(tmp, "wb") as f:
            for chunk in r.iter_content(1 << 20):
                f.write(chunk)
                done += len(chunk)
                if total and done % (50 << 20) < (1 << 20):
                    say(f"  {done >> 20}/{total >> 20} MiB")
    tmp.rename(PBF_PATH)
    say(f"  {PBF_PATH.stat().st_size >> 20} MiB saved")
    return PBF_PATH


def in_bbox(lon: float, lat: float, bb: list[float]) -> bool:
    return bb[0] <= lon <= bb[2] and bb[1] <= lat <= bb[3]


def extract_osm(no_fetch: bool) -> tuple[list[tuple[float, float]], list[dict]]:
    """One pass over the local PBF: building way centres in the analysis window
    (real counts; the basemap's z14 tiles carry only a thinned subset), plus named
    roads in the AOI. Cached to JSON so reruns don't rescan."""
    if EXTRACT_CACHE.is_file():
        say("cache hit lagos_extract")
        d = load_json(EXTRACT_CACHE)
        return [tuple(c) for c in d["centres"]], d["roads"]
    import osmium

    centres: list[tuple[float, float]] = []
    roads: list[dict] = []
    seen: set[int] = set()  # ways can appear twice in an extract; dedupe by id
    ways = 0
    say("scanning the extract (building centres + named roads) …")
    fp = osmium.FileProcessor(str(ensure_pbf(no_fetch))).with_locations()
    for obj in fp:
        if not obj.is_way():
            continue
        ways += 1
        if ways % 2_000_000 == 0:
            say(f"  {ways:,} ways scanned, {len(centres):,} buildings, {len(roads):,} roads")
        tags = obj.tags
        building = tags.get("building")
        highway = tags.get("highway")
        named_road = highway in ROAD_KINDS and tags.get("name") is not None
        if building is None and not named_road:
            continue
        if obj.id in seen:
            continue
        seen.add(obj.id)
        coords = [(round(nd.lon, 6), round(nd.lat, 6)) for nd in obj.nodes]
        if len(coords) < 2:
            continue
        if building is not None:
            lon = sum(c[0] for c in coords) / len(coords)
            lat = sum(c[1] for c in coords) / len(coords)
            if in_bbox(lon, lat, BUILDINGS_BBOX):
                centres.append((round(lon, 5), round(lat, 5)))
        elif any(in_bbox(lon, lat, ROAD_BBOX) for lon, lat in coords):
            roads.append({"name": tags.get("name"), "kind": highway, "coords": coords})
    say(f"  {len(centres):,} buildings, {len(roads):,} named roads kept (of {ways:,} ways)")
    save_json(EXTRACT_CACHE, {"centres": [list(c) for c in centres], "roads": roads})
    return centres, roads




def bin_key(lon: float, lat: float) -> str:
    return f"{math.floor(lon / CELL_DEG)}/{math.floor(lat / CELL_DEG)}"


def coverage_report(z14_counts: dict[str, int], bins: dict[str, int], built_centres: tuple[list[float], list[float]]) -> dict:
    """Two honest numbers: what the 3D view can show (the basemap tiles), and what OSM
    actually has underneath (building footprints per ~550 m cell, named by area)."""
    tile_counts = list(z14_counts.values())
    tiles_with_buildings = sum(1 for n in tile_counts if n >= 1)

    lons, lats = built_centres
    cell_counts = [bins.get(bin_key(lon, lat), 0) for lon, lat in zip(lons, lats)]
    good_cells = sum(1 for n in cell_counts if n >= 1)
    q = sorted(cell_counts)
    quartiles = [q[len(q) // 4], q[len(q) // 2], q[(3 * len(q)) // 4]] if q else [0, 0, 0]

    places = [
        it for it in load_json(EVENTS / "search_index.json")["items"]
        if it["kind"] in ("suburb", "neighbourhood", "quarter", "town", "village")
    ]
    per_area: dict[str, list[int]] = defaultdict(list)
    for lon, lat, n in zip(lons, lats, cell_counts):
        best, bd = None, 2.0  # name a cell only for a place it could plausibly be called part of (~2 km)
        for p in places:
            d = math.hypot((p["lon"] - lon) * 111 * math.cos(math.radians(lat)), (p["lat"] - lat) * 111)
            if d < bd:
                best, bd = p["name"], d
        if best:
            per_area[best].append(n)
    stats = {a: (len(v), sorted(v)[len(v) // 2]) for a, v in per_area.items() if len(v) >= 8}
    good = sorted(stats.items(), key=lambda kv: -kv[1][1])[:6]
    poor = sorted(stats.items(), key=lambda kv: kv[1][1])[:6]

    return {
        "rendered": {
            "source": "OpenFreeMap planet vector tiles (OpenMapTiles schema); buildings exist only in z14 tiles",
            "tiles_checked": len(tile_counts),
            "tiles_with_buildings": tiles_with_buildings,
            "share_of_tiles_with_buildings": round(tiles_with_buildings / max(len(tile_counts), 1), 3),
            "note": "Even where mapping is dense, a z14 tile carries only a few dozen building features, "
                    "so the 3D view shows a sample of the buildings, not every one.",
        },
        "osm_underneath": {
            "source": "OpenStreetMap building footprints (Geofabrik extract, way centres)",
            "licence": "(c) OpenStreetMap contributors (ODbL)",
            "built_up_cells": len(lons),
            "built_up_cells_with_buildings": good_cells,
            "share_of_built_up_area_with_buildings": round(good_cells / max(len(lons), 1), 3),
            "quartile_buildings_per_cell": quartiles,
            "good_areas": [{"area": a, "cells": v[0], "median_buildings": v[1]} for a, v in good],
            "poor_areas": [{"area": a, "cells": v[0], "median_buildings": v[1]} for a, v in poor],
            "note": "OSM building coverage in Lagos is patchy; counts are real footprints, zeros included.",
        },
        "note": "The 3D view shows buildings only where OSM has outlines, thinned further by the z14 tiles.",
    }


# ── roads (named OSM roads near any possible water, from the same extract) ─


def build_roads(water_union: Any, roads_raw: list[dict]) -> dict:
    keep = prep(water_union.buffer(0.018))  # ~2 km: roads a 1.5 km area ring could still ask about
    roads = []
    for el in roads_raw:
        coords = [(round(lon, 4), round(lat, 4)) for lon, lat in el["coords"]]
        if len(coords) < 2:
            continue
        line = LineString(coords)
        if not keep.intersects(line):
            continue
        line = round_coords(line.simplify(0.00005))
        coords = [list(c) for c in line.coords]
        if len(coords) >= 2:
            roads.append({"name": el["name"], "kind": el["kind"], "coords": coords})
    say(f"  roads kept: {len(roads)} (of {len(roads_raw)} named ways)")
    return {
        "meta": {"source": "OpenStreetMap (Geofabrik extract), named roads near any possible water",
                 "licence": "(c) OpenStreetMap contributors (ODbL)", "coords": "lon/lat, ~11 m precision"},
        "roads": roads,
    }


# ── main ─────────────────────────────────────────────────────────────────


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--no-fetch", action="store_true", help="reuse cached tiles and roads")
    args = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    say("Reading FABDEM window …")
    dem, transform, bounds = read_dem_window()
    say(f"  grid {dem.shape[1]}x{dem.shape[0]} cells, bounds {[round(b, 4) for b in bounds]}")
    dem = uniform_filter(dem, size=SMOOTH_CELLS).astype(np.float32)
    say(f"Smoothed {SMOOTH_CELLS}x{SMOOTH_CELLS} (~{SMOOTH_CELLS * 30} m) to avoid noise-scale ponds")

    say("Rasterising waterways, lagoon and sea …")
    drain = drainage_mask(dem.shape, transform)
    say(f"  {int(drain.sum()):,} drainage cells ({drain.mean() * 100:.1f}% of the window)")
    say("HAND (height above nearest drainage) …")
    hand = hand_above_drainage(dem, drain)
    filled = fill_depressions(dem, drain)
    dep = np.maximum(filled - dem, 0.0).astype(np.float32)
    say(f"  depressions >= 10 cm: {int((dep >= MIN_DEPTH_M).sum()):,} cells")

    say("Built-up mask (GHSL 2020) …")
    built, built_centres = built_mask(dem.shape, transform)
    say(f"  {int(built.sum()):,} cells ({built.mean() * 100:.1f}% of the window)")

    spots, radar = evidence_inputs()
    n_placed_depths = sum(1 for s in spots for d in s.get("depths", []) if d.get("placed_by"))
    say(f"Evidence: {len(spots)} flood spots ({n_placed_depths} placed depths), {len(radar)} radar flood polygons")

    say("Flow accumulation (D8, for hollows that catch their neighbourhood's rain) …")
    acc = d8_flow_accumulation(dem)

    say("Scenarios …")
    wet_polys: dict[str, list] = {}
    wet_shapes: dict[str, list] = {}
    for mm in SCENARIOS_MM:
        w = scenario_water(mm / 1000.0, hand, dep, acc)
        w[drain] = 0.0
        w[~built] = 0.0
        w[w < MIN_DEPTH_M] = 0.0
        write_png(OUT / f"scenario_{mm}mm.png", w)
        polys = polygons_of(w > 0, transform)
        wet_shapes[str(mm)] = polys
        wet_polys[str(mm)] = [poly_to_json(p) for p in polys]
        say(f"  {mm} mm: {int((w > 0).sum()):,} wet cells ({(w > 0).sum() / built.sum() * 100:.1f}% of built-up), "
            f"max depth {float(w.max()):.2f} m, {len(wet_polys[str(mm)])} polygons")
    save_json(OUT / "water_polygons.json", {
        "meta": {"depth_min_m": MIN_DEPTH_M, "bounds": [round(b, 5) for b in bounds],
                 "note": "water >= 10 cm only, built-up cells only"},
        "scenarios": wet_polys,
    })

    say("Validating against the flood spots and the radar flood map …")
    inv = ~transform  # lon/lat -> (col, row)
    rows, cols = [], []
    for s in spots:
        c, r = inv * (s["lon"], s["lat"])
        rows.append(int(r))
        cols.append(int(c))
    in_window = [0 <= r < dem.shape[0] and 0 <= c < dem.shape[1] for r, c in zip(rows, cols)]
    radar_mask = rasterize([(g, 1) for g in radar], out_shape=dem.shape, transform=transform, fill=0, all_touched=True).astype(bool)
    radar_built = int((radar_mask & built).sum())
    validation: dict[str, Any] = {}
    for mm in SCENARIOS_MM:
        w = scenario_water(mm / 1000.0, hand, dep, acc)
        w[drain] = 0.0
        w[~built] = 0.0
        w[w < MIN_DEPTH_M] = 0.0
        wet = w > 0
        wet_share = float(wet.sum()) / max(float(built.sum()), 1.0)
        tested = [i for i, ok in enumerate(in_window) if ok]
        hits = sum(1 for i in tested if wet[rows[i], cols[i]])
        v: dict[str, Any] = {
            "wet_share_of_built_up": round(wet_share, 4),
            "n_spots_tested": len(tested),
            "spots_in_model_water": hits,
            "spot_hit_rate": round(hits / max(len(tested), 1), 4),
            "random_baseline_hit_rate": round(wet_share, 4),
            "random_expected_hits": round(wet_share * len(tested), 1),
        }
        if radar_built:
            v["radar_cells_built_up"] = radar_built
            v["radar_cells_in_model_water"] = int((radar_mask & built & wet).sum())
            v["radar_match_rate"] = round(float((radar_mask & built & wet).sum()) / radar_built, 4)
        validation[str(mm)] = v
    n_out = len(spots) - sum(in_window)
    validation["note"] = (
        f"{n_out} of {len(spots)} spots sit outside the cropped window. A spot 'hits' when its own "
        "30 m cell is model-wet. The random baseline is the share of built-up cells that are wet: "
        "scattering the spots at random would hit at that rate."
    )
    say("  " + json.dumps({k: v for k, v in validation.items() if k != "note"})[:600])

    base = ofm_base_url(args.no_fetch)
    z14_counts: dict[str, int] = {}
    bins: dict[str, int] = {}
    if base:
        say("OpenFreeMap z14 tiles over built-up Lagos (what the 3D view can show) …")
        xs, ys = tile_range(ANALYSIS_BBOX, 14)
        tiles = set()
        for lon, lat in zip(*built_centres):
            fx, fy = tile_float(lon, lat, 14)
            for dx in (-0.35, 0.35):
                for dy in (-0.35, 0.35):
                    x, y = int(fx + dx), int(fy + dy)
                    if x in xs and y in ys:
                        tiles.add((x, y))
        z14_counts = fetch_counts(base, 14, tiles)
    else:
        say("--no-fetch: reusing the tile stats and building counts from the last run")
        existing = load_json(OUT / "building_counts.json")
        z14_counts = existing["meta"]["z14_tile_counts"]
        bins = existing["counts"]

    say("OSM building centres (real counts; the z14 tiles carry only a thinned sample) …")
    centres, roads_raw = extract_osm(args.no_fetch)
    bins: dict[str, int] = {}
    for lon, lat in centres:
        k = bin_key(lon, lat)
        bins[k] = bins.get(k, 0) + 1
    say(f"  {len(centres):,} buildings in {len(bins):,} cells of {CELL_DEG} deg")
    coverage = coverage_report(z14_counts, bins, built_centres)
    say(f"  tiles with outlines: {coverage['rendered']['tiles_with_buildings']}/{coverage['rendered']['tiles_checked']} "
        f"({coverage['osm_underneath']['share_of_built_up_area_with_buildings'] * 100:.0f}% of built-up cells have OSM buildings)")
    say("  good: " + ", ".join(f"{a['area']} (median {a['median_buildings']})" for a in coverage["osm_underneath"]["good_areas"][:2]))
    say("  poor: " + ", ".join(f"{a['area']} (median {a['median_buildings']})" for a in coverage["osm_underneath"]["poor_areas"][:2]))

    save_json(OUT / "building_counts.json", {
        "meta": {"cell_deg": CELL_DEG,
                 "cell_area_m2": round(CELL_DEG * 111320 * CELL_DEG * 111320 * 0.9935),  # cos(6.6 deg)
                 "source": "OpenStreetMap building footprints (Geofabrik extract, way centres)",
                 "licence": "(c) OpenStreetMap contributors (ODbL)",
                 "note": "building footprints per ~550 m cell; zeros are not stored, so a missing cell means none mapped",
                 "z14_tile_counts": z14_counts},
        "counts": bins,
    })

    say("Roads near possible water …")
    water_union = safe_union([p for polys in wet_shapes.values() for p in polys])
    if water_union.is_empty:
        water_union = box(*ANALYSIS_BBOX)
    roads_payload = build_roads(water_union, roads_raw)
    save_json(OUT / "roads.json", roads_payload)

    say("meta.json …")
    verdict_lines = (EVENTS / "terrain" / "verdict.txt").read_text(encoding="utf-8").splitlines()
    files = []
    total = 0
    for p in sorted(OUT.iterdir()):
        if p.name == "meta.json" or not p.is_file():
            continue
        n = p.stat().st_size
        files.append({"name": p.name, "bytes": n})
        total += n
    save_json(OUT / "meta.json", {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="minutes"),
        "method": {
            "summary": "Fills low ground: each cell's height above the nearest mapped waterway, lagoon or sea "
                       "(HAND, straight-line nearest), plus local depression filling from a priority-flood pass. "
                       "Excess rain stands where it is deeper than the cell's HAND, and every hollow fills with the "
                       "rain on itself and on the ground that drains into it, up to its rim; whichever is deeper wins.",
            "dem": "FABDEM 30 m (bare earth). GLO-30 was not used: it includes buildings.",
            "smoothing": f"{SMOOTH_CELLS}x{SMOOTH_CELLS} mean filter (~{SMOOTH_CELLS * 30} m) before HAND and the fill, "
                         "so DEM noise does not read as ponds.",
            "hand": "Euclidean nearest drainage cell, not routed along a flow path.",
            "depressions": "Priority-flood fill seeded at the window border and at every mapped water cell; each hollow "
                           "then fills with the rain on itself and on its D8 catchment, capped by its rim.",
            "limits": "No drain network, no channel conveyance, no infiltration beyond the stated drain capacity: "
                      "only height above water, hollows and catchment area.",
            "stipple": "Every other 30 m cell in the PNGs is drawn ~25% lighter, so the layer can never pass for a real flood.",
            "crop": {
                "bounds": [round(b, 4) for b in bounds],
                "note": "Cropped to the Lagos urban core (about 2.9-4.2 E). The Badagry and Epe outskirts are outside the model.",
            },
        },
        "parameters": {
            "scenarios_mm": SCENARIOS_MM,
            "excess_rain": "rain minus what the drains take away",
            "drain_capacity_mm_per_h": DRAIN_MM_PER_H,
            "assumed_storm_hours": STORM_H,
            "storm_note": f"Drains sized at {DRAIN_MM_PER_H:g} mm/h take away {DRAIN_MM_PER_H * STORM_H:g} mm over a "
                          f"{STORM_H:g} h storm, so the {SCENARIOS_MM[1]} mm scenario is roughly a "
                          f"{SCENARIOS_MM[1] + DRAIN_MM_PER_H * STORM_H:g} mm storm.",
            "min_depth_m": MIN_DEPTH_M,
            "max_depth_m": DEPTH_CAP_M,
            "max_depth_note": "No cell is claimed deeper than 2 m: the DEM's vertical error is about 2 m.",
            "built_up": f"GHSL 2020 built-up share >= {BUILT_SHARE_MIN} per cell; only these cells are modelled",
            "evidence_disc_radius_m": {"street": DISC_RADIUS_M.get("street"), "other": DISC_RADIUS_DEFAULT_M},
        },
        "terrain_verdict": {
            "summary": "Our own test found 30 m terrain only weakly predicts which spot floods: flooded spots are about "
                       "2 cm lower than their surroundings while the DEM's vertical error is about 2 m.",
            "source": "events/terrain/verdict.txt",
            "lines": verdict_lines[:6],
        },
        "validation": validation,
        "building_coverage": coverage,
        "bounds": [round(b, 5) for b in bounds],
        "pngs": [{"name": f"scenario_{mm}mm.png", "scenario_mm": mm} for mm in SCENARIOS_MM],
        "files": files,
        "total_bytes": total,
        "licences": {
            "dem": "FABDEM V1-2 (Hawker et al.)",
            "basemap": "(c) OpenFreeMap contributors, (c) OpenStreetMap contributors (ODbL)",
            "roads": "(c) OpenStreetMap contributors (ODbL)",
            "evidence": "events/flood_spots.json (news reports) and Copernicus Sentinel-1 3 Jul 2024",
        },
    })
    say(f"events/rough_model total: {total / 1e6:.1f} MB in {len(files)} files")
    say("Done.")


if __name__ == "__main__":
    main()
