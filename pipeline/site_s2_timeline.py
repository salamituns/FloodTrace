#!/usr/bin/env python3
"""Task 20 - Sentinel-2 monthly timelines to date the change at each drainage site.

Sentinel-2 L2A (10-20 m, ~5-day revisit) cannot show a drain, but it can date
vegetation clearing, sand-filling, earthworks and new roofs at site scale.
For every site in events/drainage_sites.json this script builds a 2018-01 ->
today monthly index series over a small AOI using ranged COG reads (windowed,
site bbox only - no full-tile downloads), dates the largest sustained step in
the vegetated fraction / bare-soil index relative to the site's flood date,
and writes true-colour chips around key dates.

AOI: point -> 300 m buffer, line -> 100 m buffer (UTM 31N).  For
alpha-beach-156 an extra AOI covers the south-end cleared area: the southern
600 m of the mapped drain line (measured along the line from the southern,
lowest-latitude endpoint) with a 250 m buffer.

Scenes: Element84 Earth Search STAC (collection sentinel-2-l2a), tile cloud
cover < 60%.  SCL mask keeps classes 4 (vegetation), 5 (not vegetated),
6 (bare soil), 7 (water); a scene is kept for an AOI only if >= 70% of the
AOI pixels are clear.  Indices are computed on 20 m pixels (the 10 m bands
are block-averaged to the B11 grid): median NDVI, median BSI, median NDWI
and the fraction of pixels with NDVI > 0.4, aggregated to monthly medians
with the number of scenes per month recorded.

Change dating: best two-segment piecewise-constant fit (>= 4 clear months on
each side) on the monthly vegetated fraction and BSI.  A step stands out if
it explains >= 25% of the variance, moves >= 0.05 (veg frac) / 0.04 (BSI) and
has |t| >= 2.5; otherwise the verdict is "no clear change".

Chips: true colour B04/B03/B02 at 10 m, 2-98% stretch, AOI + 200 m window,
JPEG q85, for the clearest scene nearest each target date (1 Jan of each
year, 1 month before / after the flood, step month +/- 2 months), saved as
events/drainage_sites/<site_id>/s2_<date>.jpg plus s2_timeline.png per site.

Per-scene metrics are cached under pipeline/cache/s2_sites/ during a run
(merged across runs so chunks can resume) and the cache files are deleted at
the end of a successful run (disk is tight).

Output: events/drainage_sites_s2.json and a printed summary table.
"""

from __future__ import annotations

import argparse
import json
import math
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timezone
from pathlib import Path

import numpy as np
import rasterio
from rasterio import windows
from rasterio.enums import Resampling
from rasterio.features import geometry_mask
from rasterio.warp import transform_geom

import matplotlib
matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
from PIL import Image
from pystac_client import Client
from shapely.geometry import LineString, mapping, shape
from shapely.ops import substring
from dateutil.relativedelta import relativedelta

REPO = Path(__file__).resolve().parents[1]
SITES_JSON = REPO / "events" / "drainage_sites.json"
CATALOG_JSON = REPO / "events" / "catalog.json"
SITES_DIR = REPO / "events" / "drainage_sites"
OUT_JSON = REPO / "events" / "drainage_sites_s2.json"
CACHE = REPO / "pipeline" / "cache" / "s2_sites"

STAC_URL = "https://earth-search.aws.element84.com/v1"
COLLECTION = "sentinel-2-l2a"
LICENCE = "Copernicus Sentinel data 2018-2026"

START_ISO = "2018-01-01T00:00:00Z"
SCL_KEEP = (4, 5, 6, 7)        # vegetation, not vegetated, bare/sand, water
CLEAR_MIN = 0.70               # min fraction of AOI pixels that must be clear
CLOUD_MAX = 60.0                # max tile cloud cover (eo:cloud_cover)
VEG_THRESHOLD = 0.4             # NDVI > this counts as vegetated

POINT_BUF_M = 300.0
LINE_BUF_M = 100.0
SOUTH_BUF_M = 250.0            # alpha-beach south AOI buffer
SOUTH_LEN_M = 600.0             # alpha-beach south AOI: southern part of the line
CHIP_PAD_M = 200.0
CHIP_JPEG_Q = 85
DISK_BUDGET = 25 * 1024 * 1024

STEP_MIN_MONTHS = 4             # min clear months on each side of a step
STEP_MIN_IMPROVEMENT = 0.20     # two-segment fit must explain >= 20% variance
STEP_MIN_T = 2.5                # step significance (Welch-style t)
STEP_MIN_SIZE = {"vegfrac": 0.05, "bsi": 0.04}

UTM = "EPSG:32631"              # Lagos is entirely inside UTM zone 31N
CACHE_VERSION = 2               # v2: kept scenes also cache their band hrefs
WORKERS_DEFAULT = 12

# earth-search v1 asset keys are common names; other STAC mirrors use Bxx.
BAND_ALIASES = {
    "B02": ("B02", "blue"),
    "B03": ("B03", "green"),
    "B04": ("B04", "red"),
    "B08": ("B08", "nir"),
    "B11": ("B11", "swir16"),
    "SCL": ("SCL", "scl"),
}

VSI_OPTS = {
    "GDAL_DISABLE_READDIR_ON_OPEN": "EMPTY_DIR",
    "CPL_VSIL_CURL_ALLOWED_EXTENSIONS": ".tif,.TIF,.jp2",
    "GDAL_HTTP_MAX_RETRY": "4",
    "GDAL_HTTP_RETRY_DELAY": "1",
    "GDAL_HTTP_TIMEOUT": "30",
}

STAC: Client | None = None


def log(msg: str) -> None:
    print(msg, flush=True)


def thresholds_dict() -> dict:
    return {
        "cloud_max": CLOUD_MAX,
        "scl_keep": list(SCL_KEEP),
        "clear_min": CLEAR_MIN,
        "veg_ndvi": VEG_THRESHOLD,
        "point_buffer_m": POINT_BUF_M,
        "line_buffer_m": LINE_BUF_M,
        "south_buffer_m": SOUTH_BUF_M,
        "south_len_m": SOUTH_LEN_M,
        "chip_pad_m": CHIP_PAD_M,
    }


# --------------------------------------------------------------------------
# STAC
# --------------------------------------------------------------------------

def asset_href(item, band: str) -> str:
    for key in BAND_ALIASES[band]:
        a = item.assets.get(key)
        if a is not None:
            return a.href
    raise KeyError(f"asset for {band} missing in {item.id} (have {sorted(item.assets)})")


def item_pref(item):
    off = 1 if item.properties.get("earthsearch:boa_offset_applied") is True else 0
    cloud = item.properties.get("eo:cloud_cover")
    cloud = 100.0 if cloud is None else float(cloud)
    return (off, -cloud)


def _search_once(aoi) -> list:
    """One full-text STAC search over the AOI (with retries / fallback)."""
    query = {"eo:cloud_cover": {"lt": CLOUD_MAX}}
    last_err = None
    for attempt in range(3):
        try:
            s = STAC.search(collections=[COLLECTION], intersects=aoi.geo4326,
                            datetime=f"{START_ISO}/{aoi.end_iso}", query=query)
            return list(s.items())
        except Exception as e:  # retry, then fall back to a client-side filter
            last_err = e
            time.sleep(2 + 2 * attempt)
    log(f"{aoi.key}: server-side query failed ({last_err}); filtering client-side")
    s = STAC.search(collections=[COLLECTION], intersects=aoi.geo4326,
                    datetime=f"{START_ISO}/{aoi.end_iso}")
    return [it for it in s.items()
            if (it.properties.get("eo:cloud_cover") or 0.0) < CLOUD_MAX]


def search_scenes(aoi) -> list:
    """Scenes over the AOI, tile cloud < CLOUD_MAX, deduped by datetime.

    earth-search result sets proved flaky between identical requests, so the
    search runs up to 3 times and the union by datetime is used (stops early
    when two consecutive attempts agree)."""
    by_dt = {}
    counts = []
    for attempt in range(3):
        items = _search_once(aoi)
        counts.append(len(items))
        for it in items:
            dt = it.properties.get("datetime")
            if dt is None:
                continue
            cur = by_dt.get(dt)
            if cur is None or item_pref(it) > item_pref(cur):
                by_dt[dt] = it
        if (attempt >= 1 and counts[-1] == counts[-2]
                and len(by_dt) == counts[-1]):
            break
    if len(set(counts)) > 1:
        log(f"{aoi.key}: search counts differed between attempts {counts}; "
            f"using union of {len(by_dt)} distinct dates")
    return [by_dt[k] for k in sorted(by_dt)]


# --------------------------------------------------------------------------
# COG windowed reads
# --------------------------------------------------------------------------

def int_window(src, bounds, pad: int = 0):
    """Integer window covering bounds, clipped to the raster (None if empty)."""
    left, bottom, right, top = bounds
    try:
        w = windows.from_bounds(left, bottom, right, top, transform=src.transform)
    except Exception:
        return None
    c = int(math.floor(w.col_off))
    r = int(math.floor(w.row_off))
    wc = int(math.ceil(w.width)) + pad
    hc = int(math.ceil(w.height)) + pad
    if c < 0:
        wc += c
        c = 0
    if r < 0:
        hc += r
        r = 0
    wc = min(wc, src.width - c)
    hc = min(hc, src.height - r)
    if wc <= 0 or hc <= 0:
        return None
    return windows.Window(c, r, wc, hc)


def read_band_window(item, band: str, win):
    href = asset_href(item, band)
    with rasterio.Env(**VSI_OPTS):
        with rasterio.open(href) as src:
            return src.read(1, window=win, boundless=True)


def read_decimated(item, band: str, bounds20, shape20):
    """10 m band read decimated to the 20 m grid (covers bounds20)."""
    href = asset_href(item, band)
    with rasterio.Env(**VSI_OPTS):
        with rasterio.open(href) as src:
            win = int_window(src, bounds20, pad=0)
            if win is None:
                win = windows.Window(0, 0, src.width, src.height)
            return src.read(1, window=win, out_shape=shape20,
                            resampling=Resampling.average, boundless=True)


def dn_to_reflectance(arr: np.ndarray, item) -> np.ndarray:
    """DN -> surface reflectance, harmonised across processing baselines."""
    props = item.properties
    if props.get("earthsearch:boa_offset_applied") is True:
        return arr / 10000.0
    baseline = str(props.get("s2:processing_baseline") or "0")
    try:
        major = int(float(baseline.split("-")[0].split(".")[0]))
    except ValueError:
        major = 0
    if major >= 4:  # BOA offset -1000 applies from baseline 04.00
        return (arr - 1000.0) / 10000.0
    return arr / 10000.0


def nd_index(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """(a-b)/(a+b) with a safe denominator."""
    out = np.full(np.broadcast(a, b).shape, np.nan, dtype=np.float32)
    s = a + b
    np.divide(a - b, s, out=out, where=np.abs(s) > 1e-6)
    return out


def scene_hrefs(item) -> dict:
    """Canonical band name -> COG href, so chips can work without live items."""
    return {band: asset_href(item, band) for band in BAND_ALIASES}


def scene_metrics(item, aoi):
    """Windowed read of one scene over one AOI -> SCL-masked index metrics."""
    base = {
        "scene": item.id,
        "date": (item.properties.get("datetime") or "")[:10],
        "cloud": item.properties.get("eo:cloud_cover"),
    }
    href = asset_href(item, "SCL")
    with rasterio.Env(**VSI_OPTS):
        with rasterio.open(href) as src:
            aoi_g = aoi.geom_in(src.crs)
            win = int_window(src, aoi_g.bounds, pad=1)
            if win is None:
                return None
            tf20 = src.window_transform(win)
            scl = src.read(1, window=win).astype(np.uint8)
            b20 = windows.bounds(win, transform=src.transform)
    inside = geometry_mask([mapping(aoi_g)], out_shape=scl.shape,
                           transform=tf20, invert=True)
    ntot = int(inside.sum())
    if ntot < 20:
        return None
    clear = np.isin(scl, SCL_KEEP)
    clear_frac = float(np.count_nonzero(clear & inside)) / ntot
    if clear_frac < CLEAR_MIN:
        return {**base, "kept": False, "clear_frac": round(clear_frac, 4)}

    arr20 = {}
    for band in ("B02", "B03", "B04", "B08"):
        arr20[band] = read_decimated(item, band, b20, scl.shape)
    arr20["B11"] = read_band_window(item, "B11", win)

    h = min(a.shape[0] for a in arr20.values())
    w = min(a.shape[1] for a in arr20.values())
    h = min(h, scl.shape[0])
    w = min(w, scl.shape[1])
    if h < 3 or w < 3:
        return None
    inside = inside[:h, :w]
    clear = clear[:h, :w]
    mask = inside & clear

    refl = {b: dn_to_reflectance(a[:h, :w].astype(np.float32), item)
            for b, a in arr20.items()}
    ndvi = nd_index(refl["B08"], refl["B04"])
    ndwi = nd_index(refl["B03"], refl["B08"])
    bsi = nd_index(refl["B11"] + refl["B04"], refl["B08"] + refl["B02"])

    def med(arr):
        v = arr[mask & np.isfinite(arr)]
        return round(float(np.median(v)), 4) if v.size else None

    v = ndvi[mask & np.isfinite(ndvi)]
    vegfrac = round(float((v > VEG_THRESHOLD).mean()), 4) if v.size else None
    return {
        **base,
        "kept": True,
        "clear_frac": round(clear_frac, 4),
        "n_pixels": int(mask.sum()),
        "ndvi": med(ndvi),
        "bsi": med(bsi),
        "ndwi": med(ndwi),
        "vegfrac": vegfrac,
        "hrefs": scene_hrefs(item),
    }


def worker(item, aoi):
    last = None
    for attempt in range(3):
        try:
            return scene_metrics(item, aoi)
        except Exception as e:
            last = e
            time.sleep(1 + 2 * attempt)
    raise RuntimeError(f"{item.id}: {last}")


# --------------------------------------------------------------------------
# AOIs
# --------------------------------------------------------------------------

class Aoi:
    def __init__(self, key: str, label: str, aoi_utm, end_iso: str):
        self.key = key
        self.label = label
        self.utm = aoi_utm
        self.geo4326 = transform_geom(UTM, "EPSG:4326", mapping(aoi_utm))
        self.area_m2 = float(aoi_utm.area)
        self.bbox4326 = [round(x, 5) for x in shape(self.geo4326).bounds]
        self.end_iso = end_iso
        self._cache = {}

    def geom_in(self, crs):
        s = crs.to_string() if hasattr(crs, "to_string") else str(crs)
        if s.upper() == UTM.upper():
            return self.utm
        if s not in self._cache:
            self._cache[s] = shape(transform_geom("EPSG:4326", s, self.geo4326))
        return self._cache[s]


def build_aois(site, end_iso) -> list:
    g4326 = shape(site["geometry"])
    gu = shape(transform_geom("EPSG:4326", UTM, mapping(g4326)))
    is_point = site["geometry"]["type"] == "Point"
    buf = POINT_BUF_M if is_point else LINE_BUF_M
    label = f"{site['geometry']['type'].lower()} buffered {int(buf)} m (UTM 31N)"
    aois = [Aoi(site["site_id"], label, gu.buffer(buf), end_iso)]
    if site["site_id"] == "alpha-beach-156":
        # South-end cleared area: the southern 600 m of the mapped drain line
        # (measured along the line from the southern endpoint), 250 m buffer.
        if isinstance(gu, LineString):
            line = gu
            cs = list(line.coords)
            if cs[0][1] > cs[-1][1]:
                line = LineString(cs[::-1])
            south = substring(line, 0, SOUTH_LEN_M).buffer(SOUTH_BUF_M)
            aois.append(Aoi(
                site["site_id"] + "__south",
                f"southern {int(SOUTH_LEN_M)} m of the drain line (from the "
                f"southern endpoint), buffered {int(SOUTH_BUF_M)} m",
                south, end_iso))
    return aois


# --------------------------------------------------------------------------
# per-AOI processing
# --------------------------------------------------------------------------

def load_cache(aoi) -> dict:
    p = CACHE / f"{aoi.key}.json"
    if not p.exists():
        return {}
    try:
        d = json.loads(p.read_text())
        if d.get("version") == CACHE_VERSION and d.get("thresholds") == thresholds_dict():
            return d.get("scenes", {})
    except Exception:
        pass
    return {}


def save_cache(aoi, metrics: dict) -> None:
    p = CACHE / f"{aoi.key}.json"
    p.write_text(json.dumps({"version": CACHE_VERSION,
                             "thresholds": thresholds_dict(),
                             "scenes": metrics}))


def month_range(d0: date, d1: date) -> list:
    out = []
    y, m = d0.year, d0.month
    while (y, m) <= (d1.year, d1.month):
        out.append(f"{y:04d}-{m:02d}")
        m += 1
        if m == 13:
            m = 1
            y += 1
    return out


def monthly_from_metrics(kept: list, today: date) -> list:
    by = {}
    for m in kept:
        by.setdefault(m["date"][:7], []).append(m)
    out = []
    for month in month_range(date(2018, 1, 1), today):
        ms = by.get(month, [])
        e = {"month": month, "n": len(ms)}
        for k in ("ndvi", "bsi", "ndwi", "vegfrac"):
            vals = [x[k] for x in ms if x.get(k) is not None]
            e[k] = round(float(np.median(vals)), 4) if vals else None
        out.append(e)
    return out


def step_fit(months: list, values: list):
    arr = np.asarray(values, dtype=float)
    n = arr.size
    if n < 2 * STEP_MIN_MONTHS:
        return None
    sse1 = float(((arr - arr.mean()) ** 2).sum())
    best = None
    for k in range(STEP_MIN_MONTHS, n - STEP_MIN_MONTHS + 1):
        a, b = arr[:k], arr[k:]
        m1, m2 = float(a.mean()), float(b.mean())
        sse2 = float(((a - m1) ** 2).sum() + ((b - m2) ** 2).sum())
        if best is None or sse2 < best["sse2"]:
            best = {"k": k, "sse2": sse2, "m1": m1, "m2": m2}
    k = best["k"]
    n1, n2 = k, n - k
    improvement = 1.0 - best["sse2"] / sse1 if sse1 > 1e-12 else 0.0
    resid = math.sqrt(best["sse2"] / max(n - 2, 1))
    step = best["m2"] - best["m1"]
    if resid > 1e-9:
        t = abs(step) * math.sqrt(n1 * n2 / (n1 + n2)) / resid
    else:
        t = float("inf") if abs(step) > 1e-9 else 0.0
    return {
        "month": months[k],
        "step": round(step, 4),
        "months_before": n1,
        "months_after": n2,
        "mean_before": round(best["m1"], 4),
        "mean_after": round(best["m2"], 4),
        "improvement": round(improvement, 3),
        "t_stat": round(t, 2),
    }


def months_vs(month: str, flood: date | None):
    if flood is None:
        return None
    sy, sm = int(month[:4]), int(month[5:7])
    d = (flood.year - sy) * 12 + (flood.month - sm)  # months step -> flood
    if d < 0:
        return f"{-d} month(s) after flood"
    if d == 0:
        return "same month as flood"
    return f"{d} month(s) before flood"


def analyse_step(monthly: list, flood: date | None) -> dict:
    fits = {}
    for series in ("vegfrac", "bsi"):
        pts = [(e["month"], e[series]) for e in monthly
               if e["n"] > 0 and e.get(series) is not None]
        fits[series] = step_fit([p[0] for p in pts], [p[1] for p in pts])
    result = {"verdict": "no clear change", "series": None, "fits": fits}
    passing = []
    for series, fit in fits.items():
        if fit and (fit["improvement"] >= STEP_MIN_IMPROVEMENT
                    and fit["t_stat"] >= STEP_MIN_T
                    and abs(fit["step"]) >= STEP_MIN_SIZE[series]):
            passing.append((fit["improvement"], series, fit))
    if passing:
        passing.sort(key=lambda x: x[0], reverse=True)
        _, series, fit = passing[0]
        if series == "vegfrac":
            direction = ("vegetation loss" if fit["step"] < 0
                         else "vegetation gain")
        else:
            direction = ("bare-soil increase" if fit["step"] > 0
                         else "bare-soil decrease")
        result.update({
            "verdict": "clear step",
            "series": series,
            "month": fit["month"],
            "step": fit["step"],
            "direction": direction,
            "months_before": fit["months_before"],
            "months_after": fit["months_after"],
            "improvement": fit["improvement"],
            "t_stat": fit["t_stat"],
            "vs_flood": months_vs(fit["month"], flood),
        })
    return result


def process_aoi(aoi, flood: date | None, today: date, workers: int) -> dict:
    items = search_scenes(aoi)
    log(f"{aoi.key}: {len(items)} scenes with tile cloud < {CLOUD_MAX:.0f}% "
        f"({START_ISO[:10]}..{today.isoformat()})")
    metrics = load_cache(aoi)
    if metrics:
        log(f"{aoi.key}: {len(metrics)} scenes reused from cache")
    todo = [it for it in items if it.id not in metrics]
    fail = 0
    if todo:
        with ThreadPoolExecutor(max_workers=workers) as ex:
            futs = {ex.submit(worker, it, aoi): it for it in todo}
            for i, fut in enumerate(as_completed(futs), 1):
                it = futs[fut]
                try:
                    m = fut.result()
                except Exception as e:
                    fail += 1
                    if fail <= 5 or fail % 25 == 0:
                        log(f"{aoi.key}: scene failed: {e}")
                    continue
                if m is not None:
                    metrics[it.id] = m
                if i % 100 == 0:
                    log(f"{aoi.key}: {i}/{len(todo)} scenes read")
        save_cache(aoi, metrics)
    kept = []
    for m in metrics.values():
        if m.get("kept"):
            kept.append({"scene": m["scene"], "date": m["date"],
                         "d": date.fromisoformat(m["date"]),
                         "clear_frac": m["clear_frac"],
                         "hrefs": m.get("hrefs")})
    kept.sort(key=lambda s: s["date"])
    monthly = monthly_from_metrics(
        [dict(m) for m in metrics.values() if m.get("kept")], today)
    res = {
        "label": aoi.label,
        "aoi_bbox_4326": aoi.bbox4326,
        "aoi_area_m2": int(aoi.area_m2),
        "scenes_searched": len(items),
        "scenes_kept": len(kept),
        "scene_failures": fail,
        "monthly": monthly,
        "step": analyse_step(monthly, flood),
        "_kept": kept,
    }
    clear_months = sum(1 for e in monthly if e["n"] > 0)
    st = res["step"]
    log(f"{aoi.key}: kept {len(kept)} scenes, {clear_months} clear months; "
        f"step: {st.get('verdict')}"
        + (f" {st['series']} {st['step']:+.3f} at {st['month']} "
           f"({st['vs_flood']})" if st["verdict"] == "clear step" else ""))
    return res


# --------------------------------------------------------------------------
# chips
# --------------------------------------------------------------------------

def stretch_band(arr: np.ndarray, valid: np.ndarray) -> np.ndarray:
    lo, hi = np.percentile(arr[valid], (2.0, 98.0))
    if hi - lo < 1e-6:
        return np.zeros_like(arr)
    return np.clip((arr - lo) / (hi - lo), 0.0, 1.0)


def make_chip(hrefs: dict, aoi, out_path: Path) -> bool:
    try:
        bands = []
        for band in ("B04", "B03", "B02"):
            href = hrefs[band]
            with rasterio.Env(**VSI_OPTS):
                with rasterio.open(href) as src:
                    g = aoi.geom_in(src.crs).buffer(CHIP_PAD_M)
                    win = int_window(src, g.bounds, pad=1)
                    if win is None:
                        return False
                    bands.append(src.read(1, window=win, boundless=True)
                                 .astype(np.float32))
        r, g, b = bands
        valid = (r > 0) & (g > 0) & (b > 0)
        if int(valid.sum()) < 200:
            return False
        rgb = np.dstack([stretch_band(x, valid) for x in (r, g, b)])
        Image.fromarray((rgb * 255.0).astype(np.uint8)).save(
            out_path, quality=CHIP_JPEG_Q)
        return True
    except Exception as e:
        log(f"chip failed for {out_path.name}: {e}")
        return False


def build_targets(flood: date | None, step: dict, today: date) -> list:
    targets = []
    for y in range(2018, today.year + 1):
        targets.append((f"jan1-{y}", date(y, 1, 1), 50))
    if flood is not None:
        targets.append(("flood-1mo", flood - relativedelta(months=1), 46))
        targets.append(("flood+1mo", flood + relativedelta(months=1), 46))
    if step.get("verdict") == "clear step":
        d = date(int(step["month"][:4]), int(step["month"][5:7]), 15)
        targets.append((f"step-{step['month']}", d, 75))  # step month +/- 2 mo
    return targets


def make_chips(site_dir: Path, aoi, res: dict, flood: date | None,
               today: date) -> list:
    suffix = "south" if aoi.key.endswith("__south") else ""
    kept = res["_kept"]
    chips = []
    if not kept:
        return chips
    chosen = {}
    for label, tdate, window in build_targets(flood, res["step"], today):
        cands = [s for s in kept if abs((s["d"] - tdate).days) <= window]
        if not cands:
            cands = kept
        best = min(cands, key=lambda s: (round((1 - s["clear_frac"]) * 20),
                                        abs((s["d"] - tdate).days)))
        chosen.setdefault(best["scene"], {"entry": best, "targets": []})
        chosen[best["scene"]]["targets"].append(label)
    for scene_id, info in sorted(chosen.items()):
        name = (f"s2_{info['entry']['date']}"
                + (f"_{suffix}" if suffix else "") + ".jpg")
        out = site_dir / name
        if info["entry"].get("hrefs") and make_chip(
                info["entry"]["hrefs"], aoi, out):
            chips.append({
                "file": out.name,
                "aoi": aoi.key,
                "scene": scene_id,
                "date": info["entry"]["date"],
                "clear_frac": info["entry"]["clear_frac"],
                "targets": info["targets"],
            })
    log(f"{aoi.key}: wrote {len(chips)} chips")
    return chips


# --------------------------------------------------------------------------
# timeline plot
# --------------------------------------------------------------------------

def plot_timeline(site_id: str, aoi_results: dict, flood: date | None,
                  out_png: Path) -> None:
    rows = list(aoi_results.items())
    fig, axes = plt.subplots(len(rows), 2, figsize=(10.5, 3.2 * len(rows)),
                              squeeze=False)
    for i, (key, res) in enumerate(rows):
        months = [datetime.strptime(e["month"], "%Y-%m") for e in res["monthly"]]
        for j, series in enumerate(("vegfrac", "bsi")):
            ax = axes[i][j]
            vals = [np.nan if e[series] is None else e[series]
                    for e in res["monthly"]]
            color = "#2a6fbd" if series == "vegfrac" else "#b0652a"
            ax.plot(months, vals, "-", color=color, lw=1.2)
            ax.plot(months, vals, "o", ms=2.2, color=color)
            if flood is not None:
                ax.axvline(datetime(flood.year, flood.month, flood.day),
                           color="red", ls="--", lw=1.0, label="flood")
            st = res["step"]
            if st.get("verdict") == "clear step":
                d = datetime(int(st["month"][:4]), int(st["month"][5:7]), 1)
                ax.axvline(d, color="darkorange", lw=1.2,
                           label=f"step {st['month']}")
            ax.set_ylabel("vegetated fraction" if series == "vegfrac" else "BSI",
                          fontsize=9)
            ax.set_title(f"{key} - {res['label']}" if j == 0 else "",
                         fontsize=8, loc="left")
            ax.grid(alpha=0.3)
            ax.xaxis.set_major_locator(mdates.YearLocator())
            ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
            if i == 0 and j == 0:
                ax.legend(fontsize=8, loc="best")
    fig.suptitle(f"{site_id}: Sentinel-2 monthly medians "
                 f"(flood {flood.isoformat() if flood else 'n/a'})", fontsize=10)
    fig.tight_layout(rect=(0, 0, 1, 0.96))
    fig.savefig(out_png, dpi=110)
    plt.close(fig)


# --------------------------------------------------------------------------
# output
# --------------------------------------------------------------------------

def build_meta(today: date, end_iso: str) -> dict:
    return {
        "task": "20-sentinel2-site-timelines",
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0)
                                  .isoformat().replace("+00:00", "Z"),
        "source": ("Sentinel-2 L2A COGs via the Element84 Earth Search STAC "
                    "(https://earth-search.aws.element84.com/v1, collection "
                    "sentinel-2-l2a); windowed ranged COG reads over the site "
                    "AOI only, no full-tile downloads"),
        "licence": LICENCE,
        "aoi": {
            "point_buffer_m": POINT_BUF_M,
            "line_buffer_m": LINE_BUF_M,
            "alpha_beach_south": ("extra AOI for alpha-beach-156 over the "
                                  "south-end cleared area: the southern "
                                  "600 m of the mapped drain LineString, "
                                  "measured along the line from the southern "
                                  "(lowest-latitude) endpoint, buffered 250 m "
                                  "(UTM 31N)"),
        },
        "date_range": [START_ISO[:10], today.isoformat()],
        "search": {"end": end_iso},
        "thresholds": {
            "tile_cloud_cover_max": CLOUD_MAX,
            "scl_keep_classes": list(SCL_KEEP),
            "aoi_clear_fraction_min": CLEAR_MIN,
            "veg_ndvi_threshold": VEG_THRESHOLD,
            "index_pixel_size_m": 20,
            "chip": {"pixel_size_m": 10, "stretch": "2-98 percentile",
                     "pad_m": CHIP_PAD_M, "jpeg_quality": CHIP_JPEG_Q},
        },
        "step_method": {
            "description": ("best two-segment piecewise-constant fit on the "
                            "monthly series of each index; step month = first "
                            "month of the second segment; the stronger of "
                            "vegfrac/BSI is reported"),
            "min_clear_months_per_side": STEP_MIN_MONTHS,
            "min_variance_improvement": STEP_MIN_IMPROVEMENT,
            "min_t_stat": STEP_MIN_T,
            "min_step_size": STEP_MIN_SIZE,
        },
        "indices": {
            "ndvi": "(B08-B04)/(B08+B04)",
            "bsi": "((B11+B04)-(B08+B02))/((B11+B04)+(B08+B02))",
            "ndwi": "(B03-B08)/(B03+B08)",
            "vegfrac": "fraction of clear AOI pixels with NDVI > 0.4",
            "aggregation": ("per-scene medians/fractions over clear AOI "
                             "pixels, then monthly medians with scene counts"),
        },
        "reflectance": ("DN/10000; the -1000 BOA offset is subtracted for "
                        "processing baseline >= 04.00 unless "
                        "earthsearch:boa_offset_applied is true (already "
                        "applied by the provider)"),
        "caveats": [
            "10-20 m pixels cannot show drains; steps date site-scale "
            "vegetation clearing, sand-filling, earthworks and new roofs, not "
            "the drain itself.",
            "Monthly medians damp short-lived events (e.g. the 4 Aug 2025 "
            "Ikorodu cofferdam, likely gone within days).",
            "The two-segment constant fit does not model the seasonal cycle; "
            "candidate steps that fail the improvement/t/size thresholds are "
            "reported as no clear change rather than discarded silently.",
            "SCL misclassification over dense urban or dark surfaces can bias "
            "the indices; scenes need >= 70% clear AOI pixels to be kept.",
        ],
    }


def public_view(res: dict) -> dict:
    return {k: v for k, v in res.items() if not k.startswith("_")}


def print_table(rows: list) -> None:
    print()
    print(f"{'site':36} {'clear mo':>8} {'step month':>10} "
          f"{'step':>34} {'vs flood':>28}")
    print("-" * 120)
    for name, clear_months, st in rows:
        if st.get("verdict") == "clear step":
            sm = st["month"]
            desc = f"{st['series']} {st['step']:+.3f} ({st['direction']})"
            vs = st["vs_flood"] or "-"
        else:
            sm, desc, vs = "-", "no clear change", "-"
        print(f"{name:36} {clear_months:>8} {sm:>10} {desc:>34} {vs:>28}")
    print()


def disk_usage_of_outputs(site_ids: list) -> int:
    total = 0
    for sid in site_ids:
        d = SITES_DIR / sid
        if d.exists():
            for f in d.iterdir():
                if f.is_file() and (f.name.startswith("s2_")):
                    total += f.stat().st_size
    return total


def cleanup_cache() -> None:
    n = 0
    if CACHE.exists():
        for f in sorted(CACHE.rglob("*")):
            if f.is_file():
                f.unlink()
                n += 1
    log(f"cache: deleted {n} file(s) under {CACHE}")


# --------------------------------------------------------------------------
# main
# --------------------------------------------------------------------------

def main(argv=None) -> int:
    global STAC
    ap = argparse.ArgumentParser(
        description="Sentinel-2 monthly timelines for the drainage sites")
    ap.add_argument("--sites", help="comma-separated site_ids (default: all)")
    ap.add_argument("--workers", type=int, default=WORKERS_DEFAULT)
    ap.add_argument("--keep-cache", action="store_true",
                    help="do not delete the per-scene cache at the end")
    args = ap.parse_args(argv)

    today = date.today()
    end_iso = (datetime.now(timezone.utc).replace(microsecond=0)
               .isoformat().replace("+00:00", "Z"))

    sites = json.loads(SITES_JSON.read_text())["sites"]
    if args.sites:
        want = {s.strip() for s in args.sites.split(",") if s.strip()}
        sites = [s for s in sites if s["site_id"] in want]
        missing = want - {s["site_id"] for s in sites}
        if missing:
            log(f"unknown site ids ignored: {sorted(missing)}")
    if not sites:
        log("no sites to process")
        return 1

    floods = {e["id"]: e["date"]
              for e in json.loads(CATALOG_JSON.read_text())["events"]}

    out_doc = {"meta": build_meta(today, end_iso), "sites": {}}
    if OUT_JSON.exists():
        try:
            old = json.loads(OUT_JSON.read_text())
            out_doc["sites"] = old.get("sites", {})
        except Exception:
            pass

    CACHE.mkdir(parents=True, exist_ok=True)
    STAC = Client.open(STAC_URL)

    rows = []
    for site in sites:
        sid = site["site_id"]
        flood = (date.fromisoformat(floods[site["event_id"]])
                 if site.get("event_id") in floods else None)
        site_dir = SITES_DIR / sid
        site_dir.mkdir(parents=True, exist_ok=True)
        log(f"=== {sid} (flood {flood})")

        aois = build_aois(site, end_iso)
        aoi_results = {}
        chips = []
        for aoi in aois:
            aoi_results[aoi.key] = process_aoi(aoi, flood, today, args.workers)
        for aoi in aois:
            chips += make_chips(site_dir, aoi, aoi_results[aoi.key],
                                flood, today)
        plot_timeline(sid, aoi_results, flood, site_dir / "s2_timeline.png")
        log(f"{sid}: timeline png written")

        out_doc["sites"][sid] = {
            "site_id": sid,
            "event_id": site.get("event_id"),
            "flood_date": flood.isoformat() if flood else None,
            "aois": {k: public_view(v) for k, v in aoi_results.items()},
            "chips": chips,
            "timeline_png": "s2_timeline.png",
        }
        OUT_JSON.write_text(json.dumps(out_doc, indent=1))
        for key, res in aoi_results.items():
            clear_months = sum(1 for e in res["monthly"] if e["n"] > 0)
            rows.append((sid if key == sid else f"{sid}/{key.split('__')[-1]}",
                         clear_months, res["step"]))

    all_site_ids = list(out_doc["sites"])
    total = disk_usage_of_outputs(all_site_ids)
    log(f"chips + timelines on disk: {total / 1e6:.1f} MB "
        f"(budget {DISK_BUDGET / 1e6:.0f} MB)")

    print_table(rows)

    if not args.keep_cache:
        cleanup_cache()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
