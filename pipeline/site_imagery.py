#!/usr/bin/env python3
"""Task 18 - dated before/after imagery + OSM context for the blamed drainage sites.

Imagery: Esri World Imagery Wayback (public, no login).  Release date is NOT
acquisition date, so for every release in waybackconfig.json the release's own
metadata MapServer is queried (identify) at the site point to get the real
acquisition date, source/sensor and resolution of the raster actually drawn
at the chip zoom.  Releases are deduped by acquisition date; the tool writes
one JPEG q85 chip per distinct date (cap 10 per site, spread across the
years, always keeping the closest date either side of the event date and of
each image_windows bound):

  events/drainage_sites/<site_id>/<acq-date>.jpg         chip
  events/drainage_sites/<site_id>/<acq-date>_marked.jpg  same chip, site geometry drawn
  events/drainage_sites/<site_id>/contact_sheet.jpg      all dates, labelled

Chip window: point sites 500 x 500 m, line sites bbox + 150 m; zoom 18,
falling back to 17 (or lower) when tiles are missing.  Tiles are cached under
pipeline/cache/wayback/tiles/ and the tile cache is deleted at the end of a
run.  Metadata identify responses are cached under pipeline/cache/wayback/meta/
(immutable, kept between runs).

OSM context: current data via Overpass - waterways/drains
(waterway=drain|canal|stream|river|ditch, culverts), buildings, bridge and
construction ways within 300 m of the geometry; drain length and building
count / footprint area within 5, 10 and 20 m of a mapped waterway (a setback
proxy - NOT the legal setback).  Saved as
events/drainage_sites/<site_id>/osm.geojson.

Output: events/drainage_sites_imagery.json (merged across runs: sites not in
the current run keep their existing entries) and a printed summary table.

The tool only produces imagery and measurements; it does not interpret what
changed.
"""

from __future__ import annotations

import argparse
import io
import json
import math
import re
import shutil
import sys
import threading
import time
import traceback
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import requests
from PIL import Image, ImageDraw, ImageFont
from shapely.geometry import (LineString, MultiLineString, MultiPolygon,
                                Point, Polygon)
from shapely.ops import unary_union

REPO = Path(__file__).resolve().parents[1]
CACHE_WB = REPO / "pipeline" / "cache" / "wayback"
CACHE_TILES = CACHE_WB / "tiles"
CACHE_META = CACHE_WB / "meta"
SITES_DIR = REPO / "events" / "drainage_sites"
OUT_JSON = REPO / "events" / "drainage_sites_imagery.json"
EVENTS = REPO / "events"

CONFIG_URL = "https://s3-us-west-2.amazonaws.com/config.maptiles.arcgis.com/waybackconfig.json"
OVERPASS_APIS = (
    # kumi.systems and private.coffee mirrors answered HTTP 500 to every
    # query on 2026-10-17, so only the main endpoint is used
    "https://overpass-api.de/api/interpreter",
)
UA = {"User-Agent": "FloodTrace/0.1 (research)"}
ATTRIBUTION = ("Esri World Imagery Wayback; imagery (c) Esri, Maxar, "
               "Earthstar Geographics and the GIS User Community")
OSM_LICENCE = "ODbL (OpenStreetMap contributors)"

MAX_RPS = 3.5                # task limit: <= 4 requests/s to Esri
ZOOM_FIRST = 18
ZOOM_MIN = 12
MAX_DATES = 10
JPEG_Q = 85
SHEET_Q = 80
POINT_HALF_M = 250.0          # point chip: 500 x 500 m
LINE_PAD_M = 150.0           # line chip: bbox + 150 m
OSM_RADIUS_M = 300.0
OSM_GEOJSON_MAX_BUILDINGS = 2000   # above this, osm.geojson keeps only buildings <= 50 m from a waterway
SETBACKS_M = (5.0, 10.0, 20.0)
BRIGHT_PIXEL = 0.92           # near-white threshold (cloud/haze heuristic)
BRIGHT_FLAG = 0.20            # flag possible cloud above this bright fraction
SHEET_THUMB_W = 600
SHEET_COLS = 4
CORRIDOR_NATIVE_PX = 1300   # corridor chip: highest zoom whose native chip fits this
CORRIDOR_MAX_PX = 1200      # corridor chip: downscale target (max side)
STATION_LINE_M = 1400.0     # line sites larger than this get 3 detail stations
DISK_BUDGET = 60 * 1024 * 1024

WATERWAY_TYPES = ("drain", "canal", "stream", "river", "ditch")
MARK_COLOR = (255, 214, 0)    # thin yellow outline on the site geometry

# Provisional sites (Task 18): site_id, lon, lat, event folder
PROVISIONAL = [
    ("alpha-beach-156", 3.515, 6.430, "lagos-2024-07-03"),
    ("agungi-collector", 3.518, 6.447, "lagos-2024-07-03"),
    ("olopomeji", 3.399, 6.548, "lagos-2024-07-03"),
    ("oko-oba-canal", 3.322, 6.637, "lagos-2022-07-08"),
    ("alapere-ogudu", 3.392, 6.592, "lagos-2021-07-16"),
    ("ikorodu", 3.504, 6.619, "lagos-2025-08-04"),
    ("ijede", 3.592, 6.566, "lagos-2025-08-04"),
    ("sangotedo", 3.636, 6.471, "lagos-2024-07-03"),
]


def log(msg: str) -> None:
    print(msg, flush=True)


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ---------------------------------------------------------------------------
# throttled HTTP
# ---------------------------------------------------------------------------

class Throttle:
    """Global request pacer: at most MAX_RPS requests/s across all threads."""

    def __init__(self, rps: float) -> None:
        self.interval = 1.0 / rps
        self.lock = threading.Lock()
        self.next_t = 0.0

    def wait(self) -> None:
        with self.lock:
            now = time.monotonic()
            base = max(now, self.next_t)
            self.next_t = base + self.interval
        delay = base - time.monotonic()
        if delay > 0:
            time.sleep(delay)


THROTTLE = Throttle(MAX_RPS)


def http_get(url: str, params: dict | None = None, timeout: int = 60,
             retries: int = 4, ok_404: bool = False) -> bytes | None:
    last = ""
    for attempt in range(retries):
        THROTTLE.wait()
        try:
            r = requests.get(url, params=params, headers=UA, timeout=timeout)
            if r.status_code == 200:
                return r.content
            if r.status_code == 404 and ok_404:
                return None
            if r.status_code == 429 or r.status_code >= 500:
                last = f"HTTP {r.status_code}"
            else:
                raise RuntimeError(f"HTTP {r.status_code} for {r.url}")
        except requests.RequestException as exc:
            last = str(exc)
        time.sleep(min(60, 5 * 2 ** attempt))
    raise RuntimeError(f"GET failed after {retries} tries: {url} ({last})")


# ---------------------------------------------------------------------------
# Esri World Imagery Wayback
# ---------------------------------------------------------------------------

def load_releases() -> list[dict]:
    cfg = json.loads(http_get(CONFIG_URL, timeout=120))
    CACHE_WB.mkdir(parents=True, exist_ok=True)
    (CACHE_WB / "waybackconfig.json").write_text(json.dumps(cfg, indent=1))
    releases = []
    for num, entry in cfg.items():
        m = re.search(r"Wayback (\d{4}-\d{2}-\d{2})", entry.get("itemTitle", ""))
        releases.append({
            "release": int(num),
            "release_date": m.group(1) if m else None,
            "tile_url": entry["itemURL"],
            "meta_url": entry["metadataLayerUrl"],
            "layer_id": entry.get("layerIdentifier"),
        })
    releases.sort(key=lambda r: (r["release_date"] or "9999-99-99", r["release"]))
    return releases


_layer_ids: dict[str, list[int]] = {}
_layer_lock = threading.Lock()


def meta_layer_ids(meta_url: str) -> list[int]:
    """Layer ids of a Wayback metadata MapServer (cached on disk)."""
    with _layer_lock:
        if meta_url in _layer_ids:
            return _layer_ids[meta_url]
        slug = re.sub(r"[^A-Za-z0-9]+", "_", meta_url.rstrip("/").split("/")[-2])
        cache = CACHE_META / f"service_{slug}.json"
        if cache.exists():
            ids = json.loads(cache.read_text())
        else:
            svc = json.loads(http_get(meta_url, params={"f": "json"}, timeout=90))
            ids = [l["id"] for l in svc.get("layers", [])]
            CACHE_META.mkdir(parents=True, exist_ok=True)
            cache.write_text(json.dumps(ids))
        _layer_ids[meta_url] = ids
        return ids


def identify(release: dict, lon: float, lat: float) -> dict:
    """Query one release's metadata layer at a point (disk-cached).

    Returns the raw identify JSON, or {"error": ..., "permanent": bool}.
    """
    CACHE_META.mkdir(parents=True, exist_ok=True)
    cache = CACHE_META / f"identify_{release['release']}_{lat:.5f}_{lon:.5f}.json"
    if cache.exists():
        out = json.loads(cache.read_text())
        if "error" not in out or out.get("permanent"):
            return out
        # transient error cached earlier: recompute below
    ids = ",".join(str(i) for i in meta_layer_ids(release["meta_url"]))
    params = {
        "geometry": json.dumps({"x": lon, "y": lat}),
        "geometryType": "esriGeometryPoint",
        "sr": "4326",
        "layers": f"all:{ids}",
        "tolerance": "10",       # tolerance 0 misses the drawn high-res rasters
        "mapExtent": json.dumps({"xmin": lon - 0.1, "ymin": lat - 0.1,
                                 "xmax": lon + 0.1, "ymax": lat + 0.1,
                                 "spatialReference": {"wkid": 4326}}),
        "imageDisplay": "1000,1000,96",
        "returnGeometry": "false",
        "f": "json",
    }
    try:
        out = json.loads(http_get(release["meta_url"] + "/identify", params=params,
                                  timeout=90))
        out.setdefault("results", [])
    except Exception as exc:  # service retired or network
        out = {"error": str(exc), "permanent": "HTTP 404" in str(exc)}
    cache.write_text(json.dumps(out))
    return out


def as_int(v: Any) -> int | None:
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def parse_date(raw: Any) -> date | None:
    if raw in (None, "Null", "", "null"):
        return None
    s = str(raw).strip()
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})", s)        # ISO: YYYY-MM-DD
    if m:
        return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    m = re.match(r"^(\d{4})(\d{2})(\d{2})", s)          # SRC_DATE: YYYYMMDD...
    if m:
        return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    m = re.match(r"^(\d{1,2})/(\d{1,2})/(\d{4})", s)    # SRC_DATE2: M/D/YYYY
    if m:
        return date(int(m.group(3)), int(m.group(1)), int(m.group(2)))
    return None


def parse_features(identify_json: dict) -> list[dict]:
    feats, seen = [], set()
    for res in identify_json.get("results", []):
        a = res.get("attributes", {})
        key = (res.get("layerId"), a.get("OBJECTID"))
        if key in seen:
            continue
        seen.add(key)
        res_m = None
        for v in (a.get("SRC_RES"), a.get("SAMP_RES")):
            if v not in (None, "Null", ""):
                try:
                    res_m = float(v)
                    break
                except ValueError:
                    pass
        feats.append({
            "layer_id": as_int(res.get("layerId")),
            "layer_name": res.get("layerName"),
            "acq_date": parse_date(a.get("SRC_DATE")) or parse_date(a.get("SRC_DATE2")),
            "sensor": str(a.get("SRC_DESC") or "").strip(),
            "product": str(a.get("NICE_NAME") or "").strip(),
            "vendor": str(a.get("NICE_DESC") or "").strip(),
            "resolution_m": res_m,
            "min_zoom": as_int(a.get("MinMapLevel")),
            "max_zoom": as_int(a.get("MaxMapLevel")),
            "block": str(a.get("BlockName") or "").strip(),
        })
    return feats


def feature_for_zoom(feats: list[dict], z: int) -> dict | None:
    """The raster drawn at zoom z: highest-resolution layer covering z."""
    cand = [f for f in feats
            if f["min_zoom"] is not None and f["max_zoom"] is not None
            and f["min_zoom"] <= z <= f["max_zoom"]]
    if not cand:
        return None
    return min(cand, key=lambda f: f["layer_id"])


def best_zoom_feature(feats: list[dict]) -> tuple[int | None, dict | None]:
    for z in range(ZOOM_FIRST, ZOOM_MIN - 1, -1):
        f = feature_for_zoom(feats, z)
        if f:
            return z, f
    return None, None


def date_groups(site_qp: tuple[float, float], releases: list[dict],
                stats: Counter) -> dict[date, list[dict]]:
    """Group releases by acquisition date of the raster drawn at the chip zoom."""
    groups: dict[date, list[dict]] = {}
    for rel in releases:
        ij = identify(rel, site_qp[0], site_qp[1])
        if "error" in ij:
            stats["identify_error"] += 1
            continue
        feats = parse_features(ij)
        if not feats:
            stats["no_metadata_at_point"] += 1
            continue
        z, f = best_zoom_feature(feats)
        if f is None:
            stats["low_zoom_only"] += 1
            continue
        if f["acq_date"] is None:
            stats["undated"] += 1
            continue
        groups.setdefault(f["acq_date"], []).append(
            {"zoom": z, "feats": feats, "release": rel})
    return groups


# ---------------------------------------------------------------------------
# web-mercator / local projection helpers
# ---------------------------------------------------------------------------

def lonlat_to_px(lon: float, lat: float, z: int) -> tuple[float, float]:
    n = 256 * (1 << z)
    x = (lon + 180.0) / 360.0 * n
    lat = max(-85.05112878, min(85.05112878, lat))
    s = math.sin(math.radians(lat))
    y = (0.5 - math.log((1 + s) / (1 - s)) / (4 * math.pi)) * n
    return x, y


def local_proj(lon0: float, lat0: float):
    """Local equirectangular projection (m) around (lon0, lat0); cm-accurate
    over the ~1 km scales used here."""
    p = math.radians(lat0)
    m_lat = 111132.92 - 559.82 * math.cos(2 * p) + 1.175 * math.cos(4 * p)
    m_lon = 111412.84 * math.cos(p) - 93.5 * math.cos(3 * p) + 0.118 * math.cos(5 * p)

    def to_xy(lon: float, lat: float) -> tuple[float, float]:
        return (lon - lon0) * m_lon, (lat - lat0) * m_lat

    def to_lonlat(x: float, y: float) -> tuple[float, float]:
        return lon0 + x / m_lon, lat0 + y / m_lat

    return to_xy, to_lonlat


# ---------------------------------------------------------------------------
# tiles / chips
# ---------------------------------------------------------------------------

class TileMissing(Exception):
    pass


def fetch_tile(release: dict, z: int, x: int, y: int) -> bytes | None:
    p = CACHE_TILES / str(release["release"]) / str(z) / f"{x}_{y}.jpg"
    if p.exists():
        return p.read_bytes()
    url = (release["tile_url"]
           .replace("{level}", str(z)).replace("{row}", str(y)).replace("{col}", str(x)))
    data = http_get(url, ok_404=True, timeout=60)
    if data is None:
        return None
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(data)
    return data


def build_chip(release: dict, z: int, corners_lonlat: list[tuple[float, float]]):
    """Mosaic the tiles covering the chip at zoom z; raise TileMissing if any
    tile is absent.  Returns (image, crop_left_px, crop_top_px) in absolute
    web-mercator pixel coords at zoom z."""
    xs, ys = [], []
    for lon, lat in corners_lonlat:
        px, py = lonlat_to_px(lon, lat, z)
        xs.append(px)
        ys.append(py)
    left, top = round(min(xs)), round(min(ys))
    right, bottom = round(max(xs)), round(max(ys))
    tx0, tx1 = left >> 8, right >> 8
    ty0, ty1 = top >> 8, bottom >> 8
    tiles: dict[tuple[int, int], bytes] = {}
    with ThreadPoolExecutor(max_workers=8) as ex:
        coords = [(tx, ty) for ty in range(ty0, ty1 + 1)
                  for tx in range(tx0, tx1 + 1)]
        for (tx, ty), data in zip(coords, ex.map(
                lambda c: fetch_tile(release, z, c[0], c[1]), coords)):
            if data is None:
                raise TileMissing(f"z{z} tile {tx}/{ty} missing in release {release['release']}")
            tiles[(tx, ty)] = data
    canvas = Image.new("RGB", ((tx1 - tx0 + 1) * 256, (ty1 - ty0 + 1) * 256))
    for (tx, ty), data in tiles.items():
        im = Image.open(io.BytesIO(data))
        im.load()
        canvas.paste(im, ((tx - tx0) * 256, (ty - ty0) * 256))
    img = canvas.crop((left - tx0 * 256, top - ty0 * 256,
                       right - tx0 * 256, bottom - ty0 * 256))
    return img, left, top


def render_date(target_date: date, group: list[dict],
                corners_lonlat: list[tuple[float, float]],
                max_zoom: int = ZOOM_FIRST):
    """Build the chip for one acquisition date, trying the releases that
    carry it (best zoom first, tiles probed top-down to ZOOM_MIN, never
    above max_zoom)."""
    order = sorted(group, key=lambda e: (-e["zoom"],
                                         e["release"]["release_date"] or "",
                                         e["release"]["release"]))
    for ent in order:
        rel, feats = ent["release"], ent["feats"]
        for z in range(min(ent["zoom"], max_zoom), ZOOM_MIN - 1, -1):
            fz = feature_for_zoom(feats, z)
            if fz is None or fz["acq_date"] != target_date:
                continue     # this release draws different imagery at z
            try:
                return (*build_chip(rel, z, corners_lonlat), fz, rel, z)
            except TileMissing:
                continue
    return None


def corridor_zoom(rect: tuple[float, float, float, float], lat0: float) -> int:
    """Highest zoom whose native whole-corridor chip fits CORRIDOR_NATIVE_PX."""
    max_dim = max(rect[2] - rect[0], rect[3] - rect[1])
    for z in range(ZOOM_FIRST, ZOOM_MIN - 1, -1):
        gsd = 156543.03392 * math.cos(math.radians(lat0)) / (1 << z)
        if max_dim / gsd <= CORRIDOR_NATIVE_PX:
            return z
    return ZOOM_MIN


def draw_marked(img: Image.Image, geom_px, kind: str) -> Image.Image:
    im = img.copy()
    d = ImageDraw.Draw(im)
    if kind == "Point":
        cx, cy = geom_px
        r = max(24, min(im.size) // 12)
        d.ellipse([cx - r, cy - r, cx + r, cy + r], outline=(0, 0, 0), width=5)
        d.ellipse([cx - r, cy - r, cx + r, cy + r], outline=MARK_COLOR, width=3)
        d.line([cx - 2 * r, cy, cx + 2 * r, cy], fill=(0, 0, 0), width=3)
        d.line([cx - 2 * r, cy, cx + 2 * r, cy], fill=MARK_COLOR, width=1)
        d.line([cx, cy - 2 * r, cx, cy + 2 * r], fill=(0, 0, 0), width=3)
        d.line([cx, cy - 2 * r, cx, cy + 2 * r], fill=MARK_COLOR, width=1)
    else:
        pts = [(x, y) for x, y in geom_px]
        d.line(pts, fill=(0, 0, 0), width=5)
        d.line(pts, fill=MARK_COLOR, width=3)
    return im


def brightness_stats(img: Image.Image) -> dict:
    a = np.asarray(img, dtype=np.float32) / 255.0
    lum = a[..., 0] * 0.299 + a[..., 1] * 0.587 + a[..., 2] * 0.114
    return {"mean_luminance": round(float(lum.mean()), 3),
            "bright_frac": round(float((lum > BRIGHT_PIXEL).mean()), 3)}


def label_font(size: int):
    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        return ImageFont.load_default()


def contact_sheet(site_id: str, images: list[dict], site_dir: Path) -> None:
    """One labelled contact sheet per site, <= 2500 px wide, from the marked chips."""
    if not images:
        return
    font = label_font(22)
    thumbs = []
    for im_ent in images:
        if not im_ent.get("marked_file"):
            continue     # date without a corridor chip (station details only)
        im = Image.open(site_dir / im_ent["marked_file"].split("/")[-1])
        w = SHEET_THUMB_W
        h = round(im.height * w / im.width)
        thumbs.append((im.resize((w, h), Image.LANCZOS), im_ent["label"]))
    cols = min(SHEET_COLS, len(thumbs))
    rows = math.ceil(len(thumbs) / cols)
    pad, label_h = 10, 34
    sheet = Image.new("RGB", (cols * (SHEET_THUMB_W + pad) + pad,
                              rows * (thumbs[0][0].height + label_h + pad) + pad),
                      (16, 16, 16))
    d = ImageDraw.Draw(sheet)
    for i, (thumb, text) in enumerate(thumbs):
        cx = pad + (i % cols) * (SHEET_THUMB_W + pad)
        cy = pad + (i // cols) * (thumb.height + label_h + pad)
        sheet.paste(thumb, (cx, cy))
        d.rectangle([cx, cy + thumb.height, cx + thumb.width, cy + thumb.height + label_h],
                    fill=(24, 24, 24))
        d.text((cx + 6, cy + thumb.height + 6), text, fill=(235, 235, 235), font=font)
    sheet.save(site_dir / "contact_sheet.jpg", "JPEG", quality=SHEET_Q, optimize=True)


# ---------------------------------------------------------------------------
# date selection
# ---------------------------------------------------------------------------

def select_dates(dates: list[date], anchors: list[date], cap: int = MAX_DATES) -> list[date]:
    """Anchor-nearest dates either side of each anchor, first/last, then
    maximin fill (even spread) up to cap."""
    dates = sorted(set(dates))
    if not dates:
        return []
    sel = {dates[0], dates[-1]}
    for a in sorted(set(anchors)):
        before = [d for d in dates if d <= a]
        after = [d for d in dates if d >= a]
        if before:
            sel.add(before[-1])
        if after:
            sel.add(after[0])
    if len(sel) > cap:                      # drop plain first/last if crowded
        sel.discard(dates[0])
        sel.discard(dates[-1])
    remaining = [d for d in dates if d not in sel]
    while remaining and len(sel) < cap:
        best = max(remaining, key=lambda d: (min(abs((d - s).days) for s in sel),
                                              -d.toordinal()))
        sel.add(best)
        remaining.remove(best)
    return sorted(sel)


# ---------------------------------------------------------------------------
# OSM context (Overpass, one query per site)
# ---------------------------------------------------------------------------

def overpass(query: str, retries: int = 6) -> dict:
    """One Overpass query; rotate mirrors on 429/5xx (the main endpoint
    intermittently answers 502)."""
    last = ""
    for attempt in range(retries):
        api = OVERPASS_APIS[attempt % len(OVERPASS_APIS)]
        try:
            THROTTLE.wait()
            r = requests.post(api, data=query.encode("utf-8"),
                              headers=UA, timeout=300)
            if r.status_code == 200:
                data = r.json()
                if "elements" not in data:
                    remark = data.get("remark") or str(data)[:200]
                    last = f"{api} error payload: {remark}"
                    continue        # retryable: server-side error/timeout
                return data
            last = f"{api} HTTP {r.status_code}"
        except (requests.RequestException, ValueError) as exc:
            last = f"{api} {exc}"
        time.sleep(15 * (attempt + 1))
    raise RuntimeError(f"Overpass failed after {retries} tries ({last})")


def polygonal_part(geom):
    if geom.is_empty:
        return None
    if geom.geom_type == "Polygon":
        return geom if not geom.is_empty else None
    parts = []
    for g in getattr(geom, "geoms", []):
        p = polygonal_part(g)
        if p is not None:
            parts.append(p)
    if not parts:
        return None
    return unary_union(parts)


def geojson_geom(geom, to_lonlat) -> dict:
    def line_string(coords):
        return [[round(c[0], 6), round(c[1], 6)]
                for c in (to_lonlat(x, y) for x, y in coords)]
    if isinstance(geom, (LineString,)):
        pts = list(geom.coords)
        return {"type": "LineString", "coordinates": line_string(pts)}
    if isinstance(geom, MultiLineString):
        return {"type": "MultiLineString",
                "coordinates": [line_string(list(ls.coords)) for ls in geom.geoms]}
    if isinstance(geom, Polygon):
        return {"type": "Polygon",
                "coordinates": [line_string(list(geom.exterior.coords))]
                + [line_string(list(r.coords)) for r in geom.interiors]}
    if isinstance(geom, MultiPolygon):
        return {"type": "MultiPolygon",
                "coordinates": [[line_string(list(p.exterior.coords))]
                                + [line_string(list(r.coords)) for r in p.interiors]
                                for p in geom.geoms]}
    return {"type": "LineString", "coordinates": line_string(list(geom.coords))}


def osm_query(bbox: tuple[float, float, float, float]) -> str:
    """Overpass query for waterways/culverts/buildings/bridge/construction
    ways inside a bbox (results are clipped to the 300 m buffer locally).
    Bbox fetch, not `around`: Overpass polyline-around proved unreliable
    (empty results / 5xx) while the same queries as bboxes work."""
    s, w, n, e = bbox
    bb = f"({s:.6f},{w:.6f},{n:.6f},{e:.6f})"
    return ("[out:json][timeout:240];\n(\n"
            f"  way[\"waterway\"~\"^({'|'.join(WATERWAY_TYPES)})$\"]{bb};\n"
            f"  way[\"culvert\"]{bb};\n"
            f"  way[\"tunnel\"=\"culvert\"]{bb};\n"
            f"  way[\"building\"]{bb};\n"
            f"  way[\"bridge\"]{bb};\n"
            f"  way[\"construction\"]{bb};\n"
            f"  way[\"highway\"=\"construction\"]{bb};\n"
            ");\nout body geom;")


def osm_context(site: dict, to_xy, to_lonlat, buf, site_dir: Path) -> dict:
    coords = site["geometry"]["coordinates"]
    gtype = site["geometry"]["type"]
    if gtype == "Point":
        coords = [coords]
    lat_c = sum(c[1] for c in coords) / len(coords)
    pad_lat = OSM_RADIUS_M * 1.05 / 111_000.0
    pad_lon = OSM_RADIUS_M * 1.05 / (111_320.0 * math.cos(math.radians(lat_c)))

    def seg_bbox(cs):
        return (min(c[1] for c in cs) - pad_lat, min(c[0] for c in cs) - pad_lon,
                max(c[1] for c in cs) + pad_lat, max(c[0] for c in cs) + pad_lon)

    n_queries = 1
    try:
        elements = overpass(osm_query(seg_bbox(coords)))["elements"]
    except Exception:
        if gtype != "LineString" or len(coords) < 3:
            raise
        # single query failed (large bbox / server strain): retry per segment,
        # deduped by element id
        elements, seen, n_queries = [], set(), 0
        for a, b in zip(coords, coords[1:]):
            dseg = overpass(osm_query(seg_bbox([a, b])), retries=4)
            n_queries += 1
            for el in dseg.get("elements", []):
                key = (el.get("type"), el.get("id"))
                if key not in seen:
                    seen.add(key)
                    elements.append(el)

    waterways, buildings = [], []
    bridges, constructions, culvert_other = [], [], []
    by_type: Counter = Counter()
    for el in elements:
        if el.get("type") != "way":
            continue
        tags = el.get("tags", {})
        geom = el.get("geometry")
        if not geom or len(geom) < 2:
            continue
        xy = [(n["lon"], n["lat"]) for n in geom]
        is_waterway = tags.get("waterway") in WATERWAY_TYPES
        culvert = "culvert" in tags or tags.get("tunnel") == "culvert"
        if is_waterway:
            line = LineString([to_xy(*c) for c in xy])
            clipped = line.intersection(buf)
            if clipped.is_empty or clipped.length < 0.5:
                continue
            waterways.append({"el": el, "geom": clipped,
                              "wt": tags["waterway"], "name": tags.get("name"),
                              "culvert": culvert})
            by_type[tags["waterway"]] += clipped.length
        elif culvert:
            culvert_other.append(el.get("id"))
        if "building" in tags:
            if len(xy) >= 4 and (round(xy[0][0], 7), round(xy[0][1], 7)) == \
                    (round(xy[-1][0], 7), round(xy[-1][1], 7)):
                poly = Polygon([to_xy(*c) for c in xy]).intersection(buf)
                p = polygonal_part(poly)
                if p is None or p.area < 1.0:
                    continue
                buildings.append({"el": el, "geom": p, "tags": tags})
        if "bridge" in tags:
            bridges.append(el)
        if ("construction" in tags or tags.get("highway") == "construction"
                or tags.get("building") == "construction"):
            constructions.append(el)

    drain_len = sum(w["geom"].length for w in waterways)
    union = unary_union([w["geom"] for w in waterways]) if waterways else None
    for b in buildings:
        b["dist_m"] = b["geom"].distance(union) if union is not None else None
        b["area_m2"] = b["geom"].area

    def within(m: float) -> dict:
        if union is None:
            return {"n": 0, "area_m2": 0.0,
                    "note": "no mapped waterway within 300 m"}
        sel = [b for b in buildings if b["dist_m"] <= m]
        return {"n": len(sel), "area_m2": round(sum(b["area_m2"] for b in sel), 1)}

    setbacks = {f"buildings_within_{int(m)}m": within(m) for m in SETBACKS_M}

    # ---- osm.geojson -----------------------------------------------------
    feats = [{
        "type": "Feature",
        "properties": {"kind": "site", "site_id": site["site_id"]},
        "geometry": site["geometry"],
    }]
    for w in waterways:
        feats.append({
            "type": "Feature",
            "properties": {"kind": "waterway", "id": w["el"]["id"],
                           "waterway": w["wt"], "name": w["name"],
                           "culvert": w["culvert"],
                           "length_m": round(w["geom"].length, 1)},
            "geometry": geojson_geom(w["geom"], to_lonlat)})
    geo_buildings = buildings
    geojson_building_note = None
    if len(buildings) > OSM_GEOJSON_MAX_BUILDINGS:
        geo_buildings = [b for b in buildings
                         if b["dist_m"] is not None and b["dist_m"] <= 50.0]
        geojson_building_note = (
            f"osm.geojson holds only buildings within 50 m of a mapped waterway "
            f"({len(geo_buildings)} of {len(buildings)} within "
            f"{int(OSM_RADIUS_M)} m of the site) to keep the file small; the "
            "counts and areas in this summary cover all of them")
    for b in geo_buildings:
        t = b["tags"]
        feats.append({
            "type": "Feature",
            "properties": {"kind": "building", "id": b["el"]["id"],
                           "building": t.get("building"),
                           "name": t.get("name"),
                           "area_m2": round(b["area_m2"], 1),
                           "dist_to_waterway_m":
                               None if b["dist_m"] is None else round(b["dist_m"], 1)},
            "geometry": geojson_geom(b["geom"], to_lonlat)})
    for kind, lst in (("bridge", bridges), ("construction", constructions)):
        for el in lst:
            tags = el.get("tags", {})
            line = LineString([to_xy(n["lon"], n["lat"])
                               for n in el["geometry"]]).intersection(buf)
            if line.is_empty or line.length < 0.5:
                continue
            feats.append({
                "type": "Feature",
                "properties": {"kind": kind, "id": el.get("id"), "tags": tags},
                "geometry": geojson_geom(line, to_lonlat)})
    fc_props = {"licence": OSM_LICENCE, "radius_m": OSM_RADIUS_M,
                "note": "current OSM data (not historical), clipped to "
                        f"{int(OSM_RADIUS_M)} m around the site geometry"}
    if geojson_building_note:
        fc_props["building_note"] = geojson_building_note
    fc = {"type": "FeatureCollection", "properties": fc_props,
          "features": feats}
    (site_dir / "osm.geojson").write_text(json.dumps(fc, separators=(",", ":")))

    def tag_summaries(lst, cap=30):
        out = [{"name": e.get("tags", {}).get("name"),
                "highway": e.get("tags", {}).get("highway"),
                "bridge": e.get("tags", {}).get("bridge"),
                "construction": e.get("tags", {}).get("construction"),
                "building": e.get("tags", {}).get("building")}
               for e in lst[:cap]]
        if len(lst) > cap:
            out.append({"more": len(lst) - cap})
        return out

    return {
        "source": "OpenStreetMap via Overpass (current data, not historical)",
        "licence": OSM_LICENCE,
        "radius_m": OSM_RADIUS_M,
        "overpass_queries_used": n_queries,
        "n_ways_fetched": len(elements),
        "geojson_building_note": geojson_building_note,
        "drain_length_m": round(drain_len, 1),
        "drain_length_by_type_m": {k: round(v, 1) for k, v in by_type.items()},
        "n_waterway_ways": len(waterways),
        "n_waterway_ways_with_culvert_tag": sum(1 for w in waterways if w["culvert"]),
        "n_other_culvert_tagged_ways": len(culvert_other),
        "buildings": {"n": len(buildings),
                      "area_m2": round(sum(b["area_m2"] for b in buildings), 1)},
        **setbacks,
        "setback_proxy_note": ("Distance of a building footprint to a mapped "
                               "waterway (drain/canal/stream/river/ditch) within "
                               f"{int(OSM_RADIUS_M)} m of the site.  This is a "
                               "setback proxy, NOT the legal setback; drains not "
                               "mapped in OSM are invisible to it."),
        "bridges": tag_summaries(bridges),
        "construction_ways": tag_summaries(constructions),
        "geojson": f"events/drainage_sites/{site['site_id']}/osm.geojson",
    }


# ---------------------------------------------------------------------------
# site loading / processing
# ---------------------------------------------------------------------------

def event_date_for(event_id: str | None) -> date | None:
    """Event day: catalog.json first (canonical), then event.json
    date / focus / window."""
    if not event_id:
        return None
    try:
        cat = json.loads((EVENTS / "catalog.json").read_text())
        for e in cat.get("events", []):
            if e.get("id") == event_id:
                d = parse_date(e.get("date"))
                if d:
                    return d
    except (ValueError, OSError):
        pass
    ev = EVENTS / event_id / "event.json"
    if not ev.exists():
        return None
    try:
        data = json.loads(ev.read_text())
        for key in ("date", "focus", "window"):
            v = (data.get(key) or {}).get("start") if key != "date" else data.get("date")
            d = parse_date(str(v)[:10]) if v else None
            if d:
                return d
    except (ValueError, OSError):
        return None
    return None


def query_point_of(geometry: dict | None):
    if not geometry:
        return None
    if geometry["type"] == "Point":
        c = geometry["coordinates"]
        return float(c[0]), float(c[1])
    line = LineString(geometry["coordinates"])
    p = line.interpolate(0.5, normalized=True)
    return float(p.x), float(p.y)


def load_sites(path_arg: str | None, only: str | None) -> list[dict]:
    raw, src = None, "provisional (Task 18 built-in list)"
    if path_arg:
        raw = json.loads(Path(path_arg).read_text())
        src = path_arg
    elif (EVENTS / "drainage_sites.json").exists():
        raw = json.loads((EVENTS / "drainage_sites.json").read_text())
        src = "events/drainage_sites.json"
    if isinstance(raw, dict) and isinstance(raw.get("sites"), list) and raw["sites"]:
        sites = []
        for r in raw["sites"]:
            if not r.get("site_id"):
                log("  skipping a sites entry without site_id")
                continue
            sites.append({
                "site_id": r["site_id"],
                "source": src,
                "event_id": r.get("event_id"),
                "event_date": event_date_for(r.get("event_id")),
                "geometry": r.get("geometry"),
                "query_point": query_point_of(r.get("geometry")),
                "image_windows": r.get("image_windows"),
                "claim": r.get("claim"),
            })
        log(f"sites: {len(sites)} from {src}")
    else:
        if raw is not None:
            log("sites file has no usable sites array - using provisional list")
        sites = [{
            "site_id": sid, "source": "provisional (Task 18 built-in list)",
            "event_id": ev, "event_date": event_date_for(ev),
            "geometry": {"type": "Point", "coordinates": [lon, lat]},
            "query_point": (lon, lat), "image_windows": None, "claim": None,
        } for sid, lon, lat, ev in PROVISIONAL]
        log(f"sites: {len(sites)} {src}")
    if only:
        keep = {s.strip() for s in only.split(",")}
        sites = [s for s in sites if s["site_id"] in keep]
        log(f"--only: {len(sites)} sites selected")
    return sites


def window_anchor_dates(windows: dict | None) -> list[date]:
    out = []
    for win in (windows or {}).values():
        if isinstance(win, (list, tuple)):
            for v in win[:2]:
                d = parse_date(str(v)[:10])
                if d:
                    out.append(d)
    return out


def process_site(site: dict, releases: list[dict]) -> dict:
    sid = site["site_id"]
    log(f"[{sid}] processing ({site['source']})")
    site_dir = SITES_DIR / sid
    site_dir.mkdir(parents=True, exist_ok=True)

    entry = {
        "site_id": sid,
        "site_source": site["source"],
        "event_id": site.get("event_id"),
        "event_date": site["event_date"].isoformat() if site["event_date"] else None,
        "claim": site.get("claim"),
        "geometry": site.get("geometry"),
        "query_point": ([round(site["query_point"][0], 6),
                         round(site["query_point"][1], 6)]
                        if site.get("query_point") else None),
        "image_windows": site.get("image_windows"),
        "gaps": [],
    }
    if site.get("geometry") is None or site.get("query_point") is None:
        entry["gaps"].append("no geometry for this site - no imagery or OSM "
                             "context produced")
        return entry

    qp = site["query_point"]
    to_xy, to_lonlat = local_proj(qp[0], qp[1])
    gtype = site["geometry"]["type"]
    if gtype == "Point":
        rect = (-POINT_HALF_M, -POINT_HALF_M, POINT_HALF_M, POINT_HALF_M)
        chip_note = f"{2 * POINT_HALF_M:.0f} x {2 * POINT_HALF_M:.0f} m"
    else:
        vs = [to_xy(*c) for c in site["geometry"]["coordinates"]]
        rect = (min(x for x, _ in vs) - LINE_PAD_M, min(y for _, y in vs) - LINE_PAD_M,
                max(x for x, _ in vs) + LINE_PAD_M, max(y for _, y in vs) + LINE_PAD_M)
        chip_note = (f"line bbox + {LINE_PAD_M:.0f} m "
                     f"({rect[2] - rect[0]:.0f} x {rect[3] - rect[1]:.0f} m)")
    entry["chip_window"] = chip_note
    corners = [to_lonlat(rect[0], rect[1]), to_lonlat(rect[2], rect[1]),
               to_lonlat(rect[2], rect[3]), to_lonlat(rect[0], rect[3])]

    stats: Counter = Counter()
    groups = date_groups(qp, releases, stats)
    dates = sorted(groups)
    entry["n_releases_checked"] = len(releases)
    entry["release_metadata_issues"] = dict(stats) or None
    entry["n_distinct_acq_dates"] = len(dates)
    entry["all_acq_dates"] = [{
        "acq_date": d.isoformat(),
        "first_release": min(e["release"]["release"] for e in groups[d]),
        "first_release_date": min(e["release"]["release_date"] or "" for e in groups[d]) or None,
        "n_releases_carrying_it": len(groups[d]),
    } for d in dates]
    if gtype == "Point":
        buf = Point(to_xy(*qp)).buffer(OSM_RADIUS_M)
    else:
        buf = LineString([to_xy(*c) for c in site["geometry"]["coordinates"]]) \
            .buffer(OSM_RADIUS_M)
    if not dates:
        entry["gaps"].append("no dated Wayback imagery found at this site")
        try:
            entry["osm"] = osm_context(site, to_xy, to_lonlat, buf, site_dir)
        except Exception as exc:
            entry["gaps"].append(f"OSM query failed: {exc}")
            entry["osm"] = {"error": str(exc)}
        return entry

    anchors = ([site["event_date"]] if site["event_date"] else []) \
        + window_anchor_dates(site.get("image_windows"))
    selected = select_dates(dates, anchors)
    entry["selected_dates"] = [d.isoformat() for d in selected]
    anchor_dates = set()
    for a in sorted(set(anchors)):
        b_ = [d for d in dates if d <= a]
        f_ = [d for d in dates if d >= a]
        if b_:
            anchor_dates.add(b_[-1])
        if f_:
            anchor_dates.add(f_[0])
    log(f"[{sid}] {len(dates)} distinct acquisition dates "
        f"({dates[0]} .. {dates[-1]}), selected {len(selected)}")

    # whole-corridor chip zoom: highest zoom whose native chip fits the cap
    z_c = ZOOM_FIRST if gtype == "Point" else corridor_zoom(rect, qp[1])
    entry["corridor_zoom"] = z_c if gtype != "Point" else None

    # detail stations for long lines (anchor dates only, native z18)
    stations = []
    if gtype == "LineString" and max(rect[2] - rect[0], rect[3] - rect[1]) > STATION_LINE_M:
        line = LineString(site["geometry"]["coordinates"])
        for i, frac, name in ((1, 0.0, "start"), (2, 0.5, "mid"), (3, 1.0, "end")):
            sp = line.interpolate(frac, normalized=True)
            sx, sy = to_xy(sp.x, sp.y)
            stations.append({
                "i": i, "name": name, "lon": round(sp.x, 6), "lat": round(sp.y, 6),
                "corners": [to_lonlat(sx - POINT_HALF_M, sy - POINT_HALF_M),
                            to_lonlat(sx + POINT_HALF_M, sy - POINT_HALF_M),
                            to_lonlat(sx + POINT_HALF_M, sy + POINT_HALF_M),
                            to_lonlat(sx - POINT_HALF_M, sy + POINT_HALF_M)]})
        entry["stations"] = [{"name": st["name"], "lon": st["lon"],
                              "lat": st["lat"]} for st in stations]
        entry["station_note"] = (
            f"line bbox + pad > {STATION_LINE_M:.0f} m: native-z18 500 x 500 m "
            "detail chips at the start/mid/end stations on the anchor dates "
            "(nearest date either side of the event and of each image_windows "
            "bound), plus the whole-corridor chip per date")

    images = []
    for d in selected:
        got = render_date(d, groups[d], corners, max_zoom=z_c)
        details = []
        if stations and d in anchor_dates:
            for st in stations:
                got_s = render_date(d, groups[d], st["corners"])
                if got_s is None:
                    entry["gaps"].append(
                        f"{d.isoformat()}: no tiles for detail station "
                        f"{st['name']}")
                    continue
                simg, sleft, s_top, sfz, srel, sz = got_s
                sbase = f"{d.isoformat()}_detail{st['i']}.jpg"
                smark = f"{d.isoformat()}_detail{st['i']}_marked.jpg"
                simg.save(site_dir / sbase, "JPEG", quality=JPEG_Q, optimize=True)
                s_px = [(p_[0] - sleft, p_[1] - s_top)
                        for p_ in (lonlat_to_px(c[0], c[1], sz)
                                   for c in site["geometry"]["coordinates"])]
                dimg = draw_marked(simg, s_px, "LineString")
                dd = ImageDraw.Draw(dimg)
                cx, cy = lonlat_to_px(st["lon"], st["lat"], sz)
                cx, cy = cx - sleft, cy - s_top
                r = max(18, min(dimg.size) // 16)
                dd.ellipse([cx - r, cy - r, cx + r, cy + r],
                           outline=(0, 0, 0), width=4)
                dd.ellipse([cx - r, cy - r, cx + r, cy + r],
                           outline=MARK_COLOR, width=2)
                dimg.save(site_dir / smark, "JPEG", quality=JPEG_Q, optimize=True)
                details.append({
                    "station": st["name"], "lon": st["lon"], "lat": st["lat"],
                    "zoom": sz,
                    "gsd_m": round(2 * POINT_HALF_M / simg.width, 2),
                    "size_px": list(simg.size),
                    "file": f"events/drainage_sites/{sid}/{sbase}",
                    "marked_file": f"events/drainage_sites/{sid}/{smark}"})
                log(f"[{sid}]   {sbase} release {srel['release']} z{sz} "
                    f"{simg.size[0]}px (station {st['name']})")
        if got is None:
            if details:
                entry["gaps"].append(
                    f"{d.isoformat()}: no whole-corridor mosaic (the low-zoom "
                    "raster at the site midpoint is a different acquisition; "
                    "long corridors mix imagery blocks at corridor zoom) - "
                    "station detail chips cover the anchor stations")
                images.append({
                    "acq_date": d.isoformat(),
                    "file": None,
                    "marked_file": None,
                    "chip_window": chip_note,
                    "detail_chips": details})
                log(f"[{sid}]   {d.isoformat()}: no corridor chip; "
                    f"{len(details)} station detail chips")
            else:
                entry["gaps"].append(
                    f"no tiles at z{z_c}-z{ZOOM_MIN} for acquisition "
                    f"{d.isoformat()} in any release carrying it")
            continue
        img, left, top, fz, rel, z = got
        native_size = list(img.size)
        scale = 1.0
        if max(img.size) > CORRIDOR_MAX_PX:
            scale = CORRIDOR_MAX_PX / max(img.size)
            img = img.resize((max(1, round(img.width * scale)),
                              max(1, round(img.height * scale))),
                             Image.LANCZOS)
        w_m, h_m = rect[2] - rect[0], rect[3] - rect[1]
        gsd = max(w_m / img.width, h_m / img.height)
        base = f"{d.isoformat()}.jpg"
        marked_name = f"{d.isoformat()}_marked.jpg"
        img.save(site_dir / base, "JPEG", quality=JPEG_Q, optimize=True)
        if gtype == "Point":
            gp = lonlat_to_px(qp[0], qp[1], z)
            geom_px = ((gp[0] - left) * scale, (gp[1] - top) * scale)
        else:
            geom_px = [((p_[0] - left) * scale, (p_[1] - top) * scale)
                       for p_ in (lonlat_to_px(c[0], c[1], z)
                                  for c in site["geometry"]["coordinates"])]
        draw_marked(img, geom_px, gtype).save(
            site_dir / marked_name, "JPEG", quality=JPEG_Q, optimize=True)
        stats_img = brightness_stats(img)
        source = " / ".join(s for s in (fz["sensor"], fz["product"], fz["vendor"]) if s) or None
        kb = (site_dir / base).stat().st_size / 1024
        log(f"[{sid}]   {base} release {rel['release']} ({rel['release_date']}) "
            f"z{z} {img.size[0]}px {kb:.0f}KB")
        if z < z_c:
            entry["gaps"].append(
                f"{d.isoformat()}: tiles missing at z{z_c}; corridor chip "
                f"rendered at z{z} ({gsd:.1f} m/px)")
        if stats_img["bright_frac"] > BRIGHT_FLAG:
            entry["gaps"].append(
                f"{d.isoformat()}: possible cloud/haze (bright pixel fraction "
                f"{stats_img['bright_frac']:.2f})")

        images.append({
            "acq_date": d.isoformat(),
            "release": rel["release"],
            "release_date": rel["release_date"],
            "first_release": min(e["release"]["release"] for e in groups[d]),
            "n_releases_carrying_date": len(groups[d]),
            "source": source,
            "sensor": fz["sensor"] or None,
            "resolution_m": fz["resolution_m"],
            "zoom": z,
            "gsd_m": round(gsd, 2),
            "size_px": list(img.size),
            "downscaled_from_px": native_size if scale != 1.0 else None,
            "chip_window": chip_note,
            "file": f"events/drainage_sites/{sid}/{base}",
            "marked_file": f"events/drainage_sites/{sid}/{marked_name}",
            "brightness": stats_img,
            "detail_chips": details,
            "label": f"{d.isoformat()} z{z} " +
                     (f"{fz['sensor']} " if fz["sensor"] else "") +
                     (f"{fz['resolution_m']:g}m"
                      if fz["resolution_m"] else ""),
        })
    entry["images"] = images
    if images:
        contact_sheet(sid, images, site_dir)
        entry["contact_sheet"] = f"events/drainage_sites/{sid}/contact_sheet.jpg"

    # event-neighbour gaps over ALL distinct dates
    ev = site["event_date"]
    if ev:
        before = [d for d in dates if d <= ev]
        after = [d for d in dates if d >= ev]
        if not before:
            entry["gaps"].append(f"no imagery on or before the event {ev.isoformat()}")
        elif (ev - before[-1]).days > 365:
            entry["gaps"].append(
                f"no imagery within a year before the event "
                f"(nearest {before[-1].isoformat()}, "
                f"{(ev - before[-1]).days} days before)")
        if not after:
            entry["gaps"].append(
                f"no imagery on or after the event {ev.isoformat()} "
                f"(latest acquisition {dates[-1].isoformat()})")
        elif (after[0] - ev).days > 365:
            entry["gaps"].append(
                f"no imagery within a year after the event "
                f"(nearest {after[0].isoformat()}, "
                f"{(after[0] - ev).days} days after)")
    if stats.get("identify_error"):
        entry["gaps"].append(
            f"metadata identify failed for {stats['identify_error']} of "
            f"{len(releases)} releases (retired services or network)")

    try:
        entry["osm"] = osm_context(site, to_xy, to_lonlat, buf, site_dir)
    except Exception as exc:
        entry["gaps"].append(f"OSM query failed: {exc}")
        entry["osm"] = {"error": str(exc)}
    return entry


# ---------------------------------------------------------------------------
# output
# ---------------------------------------------------------------------------

def write_output(entries: list[dict]) -> None:
    merged: dict[str, dict] = {}
    if OUT_JSON.exists():
        try:
            old = json.loads(OUT_JSON.read_text())
            for s in old.get("sites", []):
                if "site_id" in s:
                    merged[s["site_id"]] = s
        except (ValueError, OSError):
            pass
    for e in entries:
        merged[e["site_id"]] = e
    out = {
        "meta": {
            "generated": utc_now(),
            "task": "18 - dated before/after imagery and OSM context for the "
                    "blamed drainage sites",
            "attribution": ATTRIBUTION,
            "imagery": {
                "service": "Esri World Imagery Wayback (public, no login)",
                "releases_config": CONFIG_URL,
                "tile_url_pattern": ("https://wayback.maptiles.arcgis.com/arcgis/rest/"
                                     "services/World_Imagery/WMTS/1.0.0/default028mm/"
                                     "MapServer/tile/{release}/{z}/{y}/{x}"),
                "release_vs_acquisition": ("release date != acquisition date; for "
                                            "every release the release's own metadata "
                                            "layer was queried (identify) at the site "
                                            "point to get the real acquisition date "
                                            "(SRC_DATE), source and resolution of the "
                                            "raster drawn at the chip zoom; releases "
                                            "deduped by acquisition date"),
                "chip": ("point: 500 x 500 m; line: bbox + 150 m; JPEG q85; marked "
                         "copy = site geometry drawn as a thin outline. Point "
                         "chips and station detail chips are native z18 (17 or "
                         "lower when tiles are missing). Whole-corridor chips for "
                         "lines are rendered at the highest zoom that fits "
                         f"{CORRIDOR_MAX_PX} px and downscaled to that cap, so "
                         "long corridors are layout-level overviews; lines whose "
                         f"bbox + pad exceeds {STATION_LINE_M:.0f} m additionally "
                         "get native-z18 500 x 500 m detail chips at their "
                         "start/mid/end stations, on the anchor dates only"),
                "dates_selected": (f"every distinct acquisition date up to "
                                   f"{MAX_DATES} per site: the closest date either "
                                   "side of the event date and of each "
                                   "image_windows bound, then an even spread"),
                "cloud_note": ("'brightness' is a cloud/haze heuristic (fraction of "
                               "near-white pixels), not an interpretation"),
            },
            "osm": {
                "source": "OpenStreetMap via Overpass, current "
                          "data (not historical)",
                "licence": OSM_LICENCE,
                "radius_m": OSM_RADIUS_M,
                "setback_note": ("building count/area within 5/10/20 m of a mapped "
                                 "waterway is a setback proxy, NOT the legal setback"),
            },
        },
        "sites": sorted(merged.values(), key=lambda s: s.get("site_id", "")),
    }
    OUT_JSON.write_text(json.dumps(out, indent=1))
    log(f"wrote {OUT_JSON.relative_to(REPO)} ({len(out['sites'])} sites, "
        f"{len(entries)} in this run)")


def print_table(entries: list[dict]) -> None:
    hdr = (f"{'site':<18} {'n':>2} {'before':>10} {'after':>10} "
           f"{'drains_m':>9} {'bld<=10m':>16}")
    log("")
    log(hdr)
    log("-" * len(hdr))
    for e in entries:
        ev = parse_date(e.get("event_date")) if e.get("event_date") else None
        ds = [parse_date(i["acq_date"]) for i in e.get("images", [])]
        before = after = "-"
        if ev:
            b = [d for d in ds if d < ev]
            a = [d for d in ds if d > ev]
            on = [d for d in ds if d == ev]
            before = b[-1].isoformat() if b else (on[0].isoformat() + "*" if on else "-")
            after = a[0].isoformat() if a else (on[0].isoformat() + "*" if on else "-")
        osm = e.get("osm", {}) or {}
        drains = osm.get("drain_length_m")
        b10 = (osm.get("buildings_within_10m") or {}).get("n", "-")
        a10 = (osm.get("buildings_within_10m") or {}).get("area_m2", "-")
        b10s = f"{b10} / {a10 / 1000:.1f}k m2" if isinstance(a10, (int, float)) else "-"
        log(f"{e['site_id']:<18} {len(ds):>2} {before:>10} {after:>10} "
            f"{drains if drains is not None else '-':>9} {b10s:>16}")
    log("(* = acquisition on the event date itself)")


def du(path: Path) -> int:
    return sum(f.stat().st_size for f in path.rglob("*") if f.is_file()) \
        if path.exists() else 0


# ---------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("sites_file", nargs="?",
                    help="sites JSON file; default: events/drainage_sites.json "
                         "if it exists, else the built-in provisional list")
    ap.add_argument("--only", help="comma-separated site_ids to process")
    ap.add_argument("--smoke", action="store_true",
                    help="test mode: every 20th release only")
    ap.add_argument("--keep-tiles", action="store_true",
                    help="do not delete the tile cache at the end")
    args = ap.parse_args()

    CACHE_TILES.mkdir(parents=True, exist_ok=True)
    CACHE_META.mkdir(parents=True, exist_ok=True)
    SITES_DIR.mkdir(parents=True, exist_ok=True)

    sites = load_sites(args.sites_file, args.only)
    if not sites:
        log("no sites to process")
        return 1
    releases = load_releases()
    log(f"Wayback releases: {len(releases)} "
        f"({releases[0]['release_date']} .. {releases[-1]['release_date']})")
    if args.smoke:
        releases = releases[::20]
        log(f"SMOKE MODE: {len(releases)} releases only")

    t0 = time.time()
    jobs = [(rel, s["query_point"]) for s in sites
            if s.get("query_point") for rel in releases]
    done = 0
    with ThreadPoolExecutor(max_workers=8) as ex:
        futs = [ex.submit(identify, rel, qp[0], qp[1]) for rel, qp in jobs]
        for f in as_completed(futs):
            f.result()          # surface unexpected errors from the sweep
            done += 1
            if done % 250 == 0:
                log(f"  metadata sweep {done}/{len(jobs)} ({time.time() - t0:.0f}s)")
    log(f"metadata sweep: {len(jobs)} identifies in {time.time() - t0:.0f}s")

    entries = []
    for s in sites:
        try:
            entries.append(process_site(s, releases))
        except Exception as exc:
            log(f"[{s['site_id']}] ERROR: {exc}")
            traceback.print_exc()
            entries.append({"site_id": s["site_id"],
                            "gaps": [f"processing error: {exc}"]})

    write_output(entries)
    print_table(entries)

    if not args.keep_tiles:
        shutil.rmtree(CACHE_TILES, ignore_errors=True)
        log("tile cache deleted")
    total = du(SITES_DIR) + (OUT_JSON.stat().st_size if OUT_JSON.exists() else 0)
    log(f"total on disk (events/drainage_sites + imagery json): "
        f"{total / 1e6:.1f} MB (budget {DISK_BUDGET / 1e6:.0f} MB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
