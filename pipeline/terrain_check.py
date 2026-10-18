#!/usr/bin/env python3
"""Task 24b - terrain check with fairer controls (docs/tasks/24b-terrain-controls.md).

Task 24 asked whether reported floods sit in terrain lows and flow paths more
than comparable places; its 'pass' verdict was rejected on review because the
controls were matched on built-up level only, so elevation mostly separated
the low coastal city from the Ogun/Epe/Badagry hinterland, and the small
local signals (HAND -0.26 m, depression share +0.025) were uncorrected
p-values next to a ~2 m DEM vertical error.  This rerun keeps the Task 24
numbers as the 'builtup_only' design and adds two control designs:

  matched_water - as builtup_only, plus distance to lagoon/sea within +/- 25%
                  of the point's (minimum +/- 500 m)
  local         - up to 20 random land points in a 1-3 km annulus around each
                  point, built-up 2020 within +/- 0.10 (widened to +/- 0.15
                  only where fewer than 10 candidates exist), never within
                  1 km of any evidence point: within its own neighbourhood,
                  is the flooded spot lower or wetter?

Primary metrics are now the four local ones (hand_min, dep_share_050,
acc_log10_max, tpi_min), Holm-corrected per design x subset; elev_min is
descriptive only (geography-confounded).  Every median difference is also
reported in units of the 2 m DEM vertical error.  The verdict rule is fixed
before the results are seen (meta.verdict_rule in events/terrain_check.json)
and the 'local' design decides.

DEM: FABDEM V1-2 preferred (data.bris; if refused, the verified Hugging Face
mirror links-ads/fabdem-v12, per-tile COGs), Copernicus GLO-30 DSM as the
comparison.  Hydrology, window radii, evidence filtering and the 10,000-
shuffle stratified permutation test (seed 20261018) are unchanged from
Task 24.

Stages (run in the foreground; each stage is resumable):
  fetch   - download + clip the DEM tiles under pipeline/cache/dem/
  hydro   - reproject to UTM 31N 30 m, burn water to a low constant,
            priority-flood fill (depth = filled - dem), D8 flow direction,
            accumulation, HAND (drainage >= 0.25/1/4 km2, water = terminal
            drainage), TPI-500; arrays cached under pipeline/cache/dem/inter/
  analyze - evidence + 3 control designs + tests + PNGs + JSON outputs, then
            delete the intermediate arrays (keep the clipped DEM tiles)

Run:  pipeline/.venv/bin/python pipeline/terrain_check.py fetch
      pipeline/.venv/bin/python pipeline/terrain_check.py hydro glo30
      pipeline/.venv/bin/python pipeline/terrain_check.py hydro fabdem
      pipeline/.venv/bin/python pipeline/terrain_check.py analyze
"""

import argparse
import json
import math
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

# pysheds 0.5 vs numpy 2.x: np.in1d was removed; shim it (identical semantics).
if not hasattr(np, "in1d"):
    np.in1d = np.isin

from affine import Affine  # noqa: E402
import rasterio  # noqa: E402
import rasterio.features  # noqa: E402  (not auto-imported in rasterio 1.5)
import requests  # noqa: E402
from pyproj import Transformer  # noqa: E402
from rasterio.enums import Resampling  # noqa: E402
from rasterio.warp import reproject as rio_reproject  # noqa: E402
import scipy.ndimage as ndi  # noqa: E402
from scipy.signal import fftconvolve  # noqa: E402
from shapely.geometry import LineString, MultiLineString, Point, box, mapping  # noqa: E402
from shapely.ops import polygonize, unary_union  # noqa: E402

REPO = Path(__file__).resolve().parents[1]
PIPE = REPO / "pipeline"
CACHE_DEM = PIPE / "cache" / "dem"
CACHE_OSM = PIPE / "cache" / "osm"
CACHE_WC = PIPE / "cache" / "worldcover"
INTER = CACHE_DEM / "inter"
EVENTS = REPO / "events"
TERRAIN_DIR = EVENTS / "terrain"
sys.path.insert(0, str(PIPE))

AOI = [2.6, 6.28, 4.45, 6.85]          # [min_lon, min_lat, max_lon, max_lat]
AOI_PAD = 0.05                         # degrees, sea polygon / waterways context
METRIC_CRS = "EPSG:32631"              # UTM 31N
RES_M = 30.0

TR_4326_UTM = Transformer.from_crs("EPSG:4326", METRIC_CRS, always_xy=True)
TR_UTM_4326 = Transformer.from_crs(METRIC_CRS, "EPSG:4326", always_xy=True)

# --- data sources -----------------------------------------------------------
GLO30_TILES = ("N06_00_E002_00", "N06_00_E003_00", "N06_00_E004_00")
GLO30_URL = ("https://copernicus-dem-30m.s3.amazonaws.com/"
             "Copernicus_DSM_COG_10_{t}_DEM/Copernicus_DSM_COG_10_{t}_DEM.tif")
GLO30_LICENCE = (
    "Copernicus GLO-30 DSM (Copernicus DEM, Airbus Defence and Space / ESA, "
    "2022_02 release as distributed in the public AWS 'copernicus-dem-30m' "
    "bucket); contains buildings and vegetation."
)
FABDEM_URL = ("https://data.bris.ac.uk/datasets/s5hqmjcdj8yo2ibzi9b4ew3sn/"
              "N00E000-N10E010_FABDEM_V1-2.zip")
FABDEM_LICENCE = (
    "FABDEM V1-2 (Forest And Buildings removed Copernicus DEM; Hawker, Uhe, "
    "Paulo, Sosa, Savage, Sampson, Neal 2022, Environmental Research Letters "
    "https://doi.org/10.1088/1748-9326/ac4d4f), University of Bristol data.bris "
    "repository, CC BY-NC-SA 4.0."
)
FABDEM_INNER = ("N06E002_FABDEM_V1-2.tif", "N06E003_FABDEM_V1-2.tif",
                "N06E004_FABDEM_V1-2.tif")
FABDEM_MAX_ZIP_GB = 3.0
# Task 24b fallback: data.bris refused every request in both runs, so the
# tiles can come from the Hugging Face mirror links-ads/fabdem-v12 (public
# bucket links-ads/fabdem, Fondazione LINKS).  Its README names FABDEM v1.2,
# the University of Bristol and the authors (Hawker et al. 2022), and states
# that the tiles are the Bristol distribution rewritten into COGs with pixel
# values unchanged - see fetch_fabdem_mirror() for the verification recorded
# in pipeline/cache/dem/fabdem_mirror.json.
FABDEM_MIRROR_TILE = ("https://huggingface.co/buckets/links-ads/fabdem/"
                      "resolve/tiles/N00E000-N10E010_FABDEM_V1-2/{tile}")
FABDEM_MIRROR_README = "https://huggingface.co/datasets/links-ads/fabdem-v12"
FABDEM_MIRROR_NOTE = (
    "FABDEM V1-2 fetched from the Hugging Face mirror links-ads/fabdem-v12 "
    "(public bucket links-ads/fabdem, reprocessed and hosted by Fondazione "
    "LINKS) after data.bris refused every request.  The mirror README names "
    "FABDEM v1.2, the University of Bristol and the authors (Hawker, Uhe, "
    "Paulo, Sosa, Savage, Sampson, Neal 2022), and states that tiles are the "
    "Bristol distribution rewritten into COGs with pixel values unchanged.  "
    "The mirror README cites the Non-Commercial Government Licence v2.0 "
    "while data.bris publishes the dataset as CC BY-NC-SA 4.0; both are "
    "non-commercial.  Tile container checks, sha256 hashes and a value "
    "cross-check against GLO-30 are recorded in meta.fabdem_mirror."
)

LAGOON_RELS = {2116203: "Lagos Lagoon", 2116202: "Lekki Lagoon"}
OSM_UA = {"User-Agent": "FloodTrace/0.1 (research)"}
OSM_LICENCE = "ODbL (OpenStreetMap contributors)"
OVERPASS_API = "https://overpass-api.de/api/interpreter"
WATERWAY_TYPES = ("drain", "canal", "stream", "ditch", "river")

GHSL_LICENCE = "CC BY 4.0 (European Union, GHSL R2023A, GHS-BUILT-S)"
WC_LICENCE = "CC BY 4.0 (ESA WorldCover 10 m v200, 2021)"

# --- test constants ---------------------------------------------------------
RADIUS_M = {"street": 150.0, "point": 150.0, "exact": 150.0, "neighbourhood": 750.0}
DEFAULT_RADIUS = 150.0
DEP_THRESHOLDS = (0.25, 0.5, 1.0)       # m
DEP_MIN_CELLS = 3
DRAINAGE_KM2 = (0.25, 1.0, 4.0)         # primary 1.0
CELL_AREA = RES_M * RES_M                # 900 m2
HAND_LOW_M = 2.0
BG_N = 20
BG_TOL = 0.05
MIN_EVIDENCE_DIST_M = 1000.0
FAR_WATER_M = 2000.0
PERM_N = 10000
SEED = 20261018
TPI_RADIUS_M = 500.0

# Task 24b: three control designs; the Task 24 run is kept as 'builtup_only'
DESIGNS = ("builtup_only", "matched_water", "local")
WATER_MATCH_REL_TOL = 0.25              # matched_water: +/- 25% of the point's
WATER_MATCH_MIN_TOL_M = 500.0           # distance to lagoon/sea (minimum)
LOCAL_ANNULUS_M = (1000.0, 3000.0)      # 'local' design ring around each point
LOCAL_BG_TOL = 0.10                     # built-up match, widened only if needed
LOCAL_BG_TOL_WIDE = 0.15
LOCAL_MIN_FOUND = 10                    # fewer than this -> widen the tolerance

# Task 24b: primary metrics are the four LOCAL terrain signals; elevation is
# confounded by geography (low coastal city vs Ogun/Epe/Badagry hinterland)
# and is reported as descriptive only.
PRIMARY_METRICS = ("hand_min", "dep_share_050", "acc_log10_max", "tpi_min")
DESCRIPTIVE_METRICS = ("elev_min",)
SENSITIVITY_METRICS = ("hand_min_025", "hand_min_4", "dep_share_025", "dep_share_100")
ALL_METRICS = PRIMARY_METRICS + DESCRIPTIVE_METRICS + SENSITIVITY_METRICS
DIRECTION = {"hand_min": -1, "tpi_min": -1, "elev_min": -1,
             "dep_share_050": 1, "acc_log10_max": 1,
             # sensitivity variants share their parent's predicted direction
             "hand_min_025": -1, "hand_min_4": -1,
             "dep_share_025": 1, "dep_share_100": 1}
DEM_VERT_ERROR_M = 2.0                  # ~2 m DEM vertical error in cities
ALPHA = 0.05


def log(msg: str) -> None:
    print(msg, flush=True)


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def http_get(url: str, dest: Path, tries: int = 4, timeout: int = 300) -> None:
    last = None
    for attempt in range(1, tries + 1):
        try:
            with requests.get(url, stream=True, timeout=(30, timeout),
                              headers={"User-Agent": "Mozilla/5.0 FloodTrace/0.1"}) as r:
                r.raise_for_status()
                tmp = dest.with_suffix(dest.suffix + ".part")
                with open(tmp, "wb") as f:
                    for chunk in r.iter_content(1 << 20):
                        f.write(chunk)
                tmp.rename(dest)
                return
        except requests.RequestException as exc:
            last = exc
            log(f"  download attempt {attempt} failed ({exc}); retrying ...")
            time.sleep(15 * attempt)
    raise SystemExit(f"could not download {url}: {last}")


# ---------------------------------------------------------------------------
# Stage 1: DEM fetch + clip
# ---------------------------------------------------------------------------

SRC_PAD_DEG = 0.05   # source clips padded so the UTM envelope is fully covered


def clip_bounds() -> tuple:
    return (AOI[0] - SRC_PAD_DEG, AOI[1] - SRC_PAD_DEG,
            AOI[2] + SRC_PAD_DEG, AOI[3] + SRC_PAD_DEG)


def clip_4326(src_path: Path, out_path: Path) -> None:
    """Clip a lon/lat GeoTIFF to the (padded) AOI."""
    b = clip_bounds()
    with rasterio.open(src_path) as src:
        win = rasterio.windows.from_bounds(b[0], b[1], b[2], b[3],
                                           transform=src.transform)
        win = win.round_offsets().round_lengths()
        data = src.read(1, window=win)
        profile = src.profile.copy()
        profile.update(height=win.height, width=win.width,
                       transform=rasterio.windows.transform(win, src.transform),
                       compress="deflate", BIGTIFF="IF_SAFER")
    with rasterio.open(out_path, "w", **profile) as dst:
        dst.write(data, 1)


def fetch_glo30() -> None:
    CACHE_DEM.mkdir(parents=True, exist_ok=True)
    merged = CACHE_DEM / "glo30_aoi.tif"
    if merged.exists():
        log("  glo30 AOI clip already present")
        return
    import tempfile
    with tempfile.TemporaryDirectory(prefix="glo30_") as tmp:
        tmp = Path(tmp)
        clips = []
        for t in GLO30_TILES:
            tile = tmp / f"{t}.tif"
            url = GLO30_URL.format(t=t)
            http_get(url, tile)
            clip = CACHE_DEM / f"glo30_{t}_aoi.tif"
            clip_4326(tile, clip)
            clips.append(clip)
            log(f"  {t}: clipped -> {clip.name}")
        from rasterio.merge import merge as rio_merge
        srcs = [rasterio.open(c) for c in clips]
        b = clip_bounds()
        arr, transform = rio_merge(srcs, bounds=b)
        profile = srcs[0].profile.copy()
        for s in srcs:
            s.close()
        profile.update(height=arr.shape[1], width=arr.shape[2],
                       transform=transform, compress="deflate", BIGTIFF="IF_SAFER")
        with rasterio.open(merged, "w", **profile) as dst:
            dst.write(arr[0], 1)
        log(f"  merged {len(clips)} clips -> {merged.name} "
            f"({merged.stat().st_size/1e6:.1f} MB)")


def fabdem_zip_size(url: str) -> int:
    """HEAD, falling back to a 1-byte ranged GET; raises if both fail."""
    try:
        r = requests.head(url, timeout=60, headers={"User-Agent": "Mozilla/5.0 FloodTrace/0.1"},
                          allow_redirects=True)
        r.raise_for_status()
        return int(r.headers.get("Content-Length", 0))
    except requests.RequestException:
        pass
    r = requests.get(url, timeout=120, allow_redirects=True, stream=True,
                     headers={"User-Agent": "Mozilla/5.0 FloodTrace/0.1",
                              "Range": "bytes=0-0"})
    r.raise_for_status()
    cr = r.headers.get("Content-Range", "")
    r.close()
    if "/" in cr:
        return int(cr.rsplit("/", 1)[1])
    return 0


def try_fabdem_vsizip(inner_names) -> bool:
    """First resort: read the inner tiles straight out of the remote zip."""
    import os
    os.environ.setdefault("GDAL_DISABLE_READDIR_ON_OPEN", "EMPTY_DIR")
    candidates = []
    for n in inner_names:
        candidates.append(n)
        candidates.append(f"{n[:-4]}/{n}")       # some archives nest by tile
    got_any = 0
    for n in candidates:
        url = f"/vsizip//vsicurl/{FABDEM_URL}/{n}"
        try:
            with rasterio.Env(CPL_VSIL_CURL_CHUNK_SIZE="16384",
                              CPL_VSIL_CURL_ALLOWED_EXT=".tif",
                              CPL_VSIL_CURL_TIMEOUT="60"):
                with rasterio.open(url) as f:
                    if f.width < 100:
                        continue
                    out = CACHE_DEM / f"fabdem_{n.split('_')[0]}_aoi.tif"
                    if not out.exists():
                        clip_4326_path(url, out)
                    log(f"  vsizip/vsicurl read OK: {n}")
                    got_any += 1
        except Exception as e:
            log(f"  vsizip candidate {n} failed: {str(e)[:120]}")
    return got_any


def clip_4326_path(src_path: str, out_path: Path) -> None:
    b = clip_bounds()
    with rasterio.open(src_path) as src:
        win = rasterio.windows.from_bounds(b[0], b[1], b[2], b[3],
                                           transform=src.transform)
        win = win.round_offsets().round_lengths()
        data = src.read(1, window=win)
        profile = src.profile.copy()
        profile.update(height=win.height, width=win.width,
                       transform=rasterio.windows.transform(win, src.transform),
                       compress="deflate", BIGTIFF="IF_SAFER")
    with rasterio.open(out_path, "w", **profile) as dst:
        dst.write(data, 1)


def fetch_fabdem(attempts: int, wait_s: int) -> bool:
    merged = CACHE_DEM / "fabdem_aoi.tif"
    if merged.exists():
        log("  fabdem AOI clip already present")
        return True
    CACHE_DEM.mkdir(parents=True, exist_ok=True)
    # 1) /vsizip//vsicurl first (no download)
    log("  trying /vsizip//vsicurl direct read of the inner tiles ...")
    try:
        n_ok = try_fabdem_vsizip(FABDEM_INNER)
        if n_ok == len(FABDEM_INNER):
            _merge_fabdem()
            return True
        if n_ok:
            log(f"  vsizip read only {n_ok}/{len(FABDEM_INNER)} tiles; "
                "falling back to a full download")
    except SystemExit:
        raise
    except Exception as e:
        log(f"  vsizip route failed: {str(e)[:120]}")
    # 2) download the 10x10 archive (size-checked)
    import tempfile
    import zipfile
    for attempt in range(1, attempts + 1):
        log(f"  fabdem download attempt {attempt}/{attempts} ...")
        try:
            size = fabdem_zip_size(FABDEM_URL)
        except requests.RequestException as e:
            log(f"    size check failed ({str(e)[:100]})")
            if attempt < attempts:
                time.sleep(wait_s)
            continue
        if not size:
            log("    server did not report a size; treating as unreachable")
            if attempt < attempts:
                time.sleep(wait_s)
            continue
        gb = size / 1e9
        log(f"    zip size: {gb:.2f} GB")
        if gb > FABDEM_MAX_ZIP_GB:
            raise SystemExit(
                f"STOP: FABDEM archive {FABDEM_URL} is {gb:.1f} GB "
                f"(> {FABDEM_MAX_ZIP_GB} GB limit); running on GLO-30 only")
        if size > 8.5e9:                    # disk is tight
            raise SystemExit(
                f"STOP: not enough free disk for a {gb:.1f} GB download; "
                "running on GLO-30 only")
        try:
            with tempfile.TemporaryDirectory(prefix="fabdem_") as tmp:
                tmp = Path(tmp)
                zp = tmp / "fabdem.zip"
                http_get(FABDEM_URL, zp, tries=2, timeout=2400)
                with zipfile.ZipFile(zp) as zf:
                    names = zf.namelist()
                    for want in FABDEM_INNER:
                        hit = [n for n in names if n.endswith(want)]
                        if not hit:
                            raise SystemExit(f"tile {want} not in zip (members: {len(names)})")
                        with zf.open(hit[0]) as m, open(tmp / want, "wb") as out:
                            while True:
                                chunk = m.read(1 << 22)
                                if not chunk:
                                    break
                                out.write(chunk)
                        clip = CACHE_DEM / f"fabdem_{want.split('_')[0]}_aoi.tif"
                        clip_4326(tmp / want, clip)
                        log(f"  {want}: clipped -> {clip.name}")
                _merge_fabdem()
                return True
        except SystemExit:
            raise
        except Exception as e:
            log(f"    download/extract failed: {str(e)[:140]}")
            if attempt < attempts:
                time.sleep(wait_s)
    return False


def _merge_fabdem() -> None:
    clips = sorted(CACHE_DEM.glob("fabdem_N06E*_aoi.tif"))
    if len(clips) < 3:
        raise SystemExit(f"expected 3 fabdem tile clips, found {clips}")
    from rasterio.merge import merge as rio_merge
    srcs = [rasterio.open(c) for c in clips]
    b = clip_bounds()
    arr, transform = rio_merge(srcs, bounds=b)
    profile = srcs[0].profile.copy()
    for s in srcs:
        s.close()
    profile.update(height=arr.shape[1], width=arr.shape[2],
                   transform=transform, compress="deflate", BIGTIFF="IF_SAFER")
    with rasterio.open(CACHE_DEM / "fabdem_aoi.tif", "w", **profile) as dst:
        dst.write(arr[0], 1)
    log(f"  merged {len(clips)} clips -> fabdem_aoi.tif")


# ---------------------------------------------------------------------------
# Stage 1b (Task 24b): FABDEM via the verified Hugging Face mirror
# ---------------------------------------------------------------------------

def fetch_fabdem_mirror() -> bool:
    """Per-tile FABDEM V1-2 from the verified Hugging Face mirror.

    Avoids data.bris's 10x10-degree zip entirely (also over the 3 GB limit
    and the machine's free disk).  Each tile's container is checked against
    the FABDEM tile description (3600x3600 float32, EPSG:4326, 1 arc-second,
    nodata -9999, the tile's own 1-degree extent), its sha256 recorded, and
    the merged clip is value-checked against the GLO-30 clip.  Everything is
    written to pipeline/cache/dem/fabdem_mirror.json for the output meta.
    """
    merged = CACHE_DEM / "fabdem_aoi.tif"
    if merged.exists():
        log("  fabdem AOI clip already present")
        return True
    CACHE_DEM.mkdir(parents=True, exist_ok=True)
    import hashlib
    import tempfile
    info = {"mirror_readme": FABDEM_MIRROR_README,
            "url_pattern": FABDEM_MIRROR_TILE.format(tile="<tile>"),
            "note": FABDEM_MIRROR_NOTE, "tiles": []}
    with tempfile.TemporaryDirectory(prefix="fabdem_mirror_") as tmp:
        tmp = Path(tmp)
        for name in FABDEM_INNER:
            url = FABDEM_MIRROR_TILE.format(tile=name)
            tile = tmp / name
            http_get(url, tile, tries=3)
            h = hashlib.sha256()
            with open(tile, "rb") as f:
                for chunk in iter(lambda: f.read(1 << 22), b""):
                    h.update(chunk)
            sw_lat = int(name[1:3])
            sw_lon = int(name[4:7])
            with rasterio.open(tile) as src:
                checks = {"dtype": src.dtypes[0],
                          "shape": [src.height, src.width],
                          "crs": src.crs.to_string(),
                          "nodata": src.nodata,
                          "res": list(src.res),
                          "bounds": [round(v, 6) for v in src.bounds]}
                problems = []
                if src.dtypes[0] != "float32":
                    problems.append("dtype not float32")
                if (src.height, src.width) != (3600, 3600):
                    problems.append("not 3600x3600")
                if src.crs.to_string() != "EPSG:4326":
                    problems.append("crs not EPSG:4326")
                if src.nodata is None or abs(float(src.nodata) + 9999.0) > 1.0:
                    problems.append("nodata not -9999")
                b = src.bounds
                if (abs(b.left - sw_lon) > 0.01 or abs(b.bottom - sw_lat) > 0.01
                        or abs(b.right - (sw_lon + 1)) > 0.01
                        or abs(b.top - (sw_lat + 1)) > 0.01):
                    problems.append(f"bounds not the 1-degree tile {name}")
                if problems:
                    raise SystemExit(
                        f"mirror tile {name} does not match the FABDEM V1-2 "
                        f"description: {'; '.join(problems)}; {checks}")
            clip = CACHE_DEM / f"fabdem_{name.split('_')[0]}_aoi.tif"
            if not clip.exists():
                clip_4326(tile, clip)
            size = tile.stat().st_size
            log(f"  {name}: {size / 1e6:.1f} MB, sha256 {h.hexdigest()[:16]}..., "
                f"container checks OK -> {clip.name}")
            info["tiles"].append({"tile": name, "url": url,
                                  "sha256": h.hexdigest(), "bytes": size,
                                  "container_checks": checks})
        _merge_fabdem()
    info["value_check_vs_glo30"] = check_fabdem_vs_glo30()
    (CACHE_DEM / "fabdem_mirror.json").write_text(json.dumps(info, indent=1))
    return True


def check_fabdem_vs_glo30(n_samples: int = 20000) -> dict:
    """Value cross-check of the mirrored FABDEM clip against GLO-30.

    FABDEM is bare earth carved out of GLO-30, so it should track GLO-30
    closely and sit at or below it, most visibly in built-up cells where the
    DSM still contains the buildings.  Approximated by point sampling land
    cells (GHSL built-up 2020 cell defined).
    """
    import builtup_change as bc
    b2020, _any_land = ghsl_b2020()
    rng = np.random.default_rng(SEED)
    with rasterio.open(CACHE_DEM / "fabdem_aoi.tif") as fab,             rasterio.open(CACHE_DEM / "glo30_aoi.tif") as glo:
        rows = rng.integers(0, fab.height, n_samples)
        cols = rng.integers(0, fab.width, n_samples)
        xs, ys = rasterio.transform.xy(fab.transform, rows, cols)
        fv = np.array([v[0] for v in fab.sample(zip(xs, ys))], dtype=float)
        gv = np.array([v[0] for v in glo.sample(zip(xs, ys))], dtype=float)
    built = np.full(n_samples, np.nan)
    for i, (x, y) in enumerate(zip(xs, ys)):
        ix = int(math.floor((x - bc.LON0) / bc.CELL))
        iy = int(math.floor((y - bc.LAT0) / bc.CELL))
        if 0 <= ix < bc.NX and 0 <= iy < bc.NY:
            built[i] = float(b2020[iy, ix])
    land = (np.isfinite(built) & np.isfinite(fv) & np.isfinite(gv)
            & (fv > -100) & (gv > -100))
    out = {"n_land_samples": int(land.sum()), "note": (
        "point-sampled land cells (GHSL cell defined), FABDEM minus GLO-30; "
        "FABDEM removes buildings/trees, so it should sit at or below GLO-30, "
        "most visibly in built-up cells")}
    if land.sum() >= 100:
        d = fv[land] - gv[land]
        hi = built[land] >= 0.5
        lo = built[land] <= 0.1
        out.update({
            "correlation": round(float(np.corrcoef(fv[land], gv[land])[0, 1]), 4),
            "mean_diff_m": round(float(d.mean()), 3),
            "mean_diff_built_ge_050_m": (round(float(d[hi].mean()), 3)
                                          if hi.sum() > 30 else None),
            "mean_diff_built_le_010_m": (round(float(d[lo].mean()), 3)
                                         if lo.sum() > 30 else None),
            "share_built_cells_fabdem_below_glo30": (round(float((d[hi] <= 0.05).mean()), 4)
                                                     if hi.sum() > 30 else None),
        })
    return out


# ---------------------------------------------------------------------------
# Water: OSM lagoon polygons, sea polygon, waterways
# ---------------------------------------------------------------------------

def overpass(query: str, tries: int = 5) -> dict:
    last = None
    for attempt in range(1, tries + 1):
        try:
            r = requests.post(OVERPASS_API, data={"data": query}, timeout=300,
                               headers=OSM_UA)
            r.raise_for_status()
            return r.json()
        except requests.RequestException as exc:
            last = exc
            time.sleep(20 * attempt)
    raise SystemExit(f"overpass failed: {last}")


def _osm_relation_lines(rid: int):
    """(outer_lines, inner_lines, unassigned_lines) for an OSM relation."""
    url = f"https://api.openstreetmap.org/api/0.6/relation/{rid}/full.json"
    r = requests.get(url, headers=OSM_UA, timeout=180)
    r.raise_for_status()
    els = r.json()["elements"]
    nd = {e["id"]: (e["lon"], e["lat"]) for e in els if e["type"] == "node"}
    ways = {e["id"]: e for e in els if e["type"] == "way"}
    rel = next(e for e in els if e["type"] == "relation" and e["id"] == rid)
    outer, inner, plain = [], [], []
    for m in rel.get("members", []):
        if m.get("type") != "way" or m.get("ref") not in ways:
            continue
        coords = [nd[n] for n in ways[m["ref"]].get("nodes", []) if n in nd]
        if len(coords) < 2:
            continue
        line = LineString(coords)
        role = m.get("role", "")
        if role == "outer":
            outer.append(line)
        elif role == "inner":
            inner.append(line)
        else:
            plain.append(line)
    return outer, inner, plain


def ensure_lagoon_polygons() -> None:
    """Lagos + Lekki lagoon polygons (OSM relations 2116203, 2116202)."""
    CACHE_OSM.mkdir(parents=True, exist_ok=True)
    cache = CACHE_OSM / "lagoon_polygons.geojson"
    log("  fetching OSM lagoon relation polygons ...")
    geoms = {}
    for rid, name in LAGOON_RELS.items():
        outer, inner, plain = _osm_relation_lines(rid)
        lines = outer + plain
        if not lines:
            raise SystemExit(f"relation {rid} has no usable member ways")
        out_poly = unary_union(list(polygonize(lines)))
        if inner:
            holes = unary_union(list(polygonize(inner)))
            out_poly = out_poly.difference(holes)
        if out_poly.is_empty:
            raise SystemExit(f"relation {rid}: polygonization empty")
        geoms[name] = out_poly
        log(f"  {name} ({rid}): {out_poly.geom_type}, "
            f"{out_poly.area * (111 ** 2):.0f} km2 approx")
    feats = [{"type": "Feature",
              "properties": {"name": n, "relation_id": [k for k, v in LAGOON_RELS.items() if v == n][0]},
              "geometry": mapping(g)} for n, g in geoms.items()]
    gj = {"type": "FeatureCollection",
          "meta": {"source": "OpenStreetMap API 0.6 relation geometry (outer/inner roles)",
                   "relations": {str(k): v for k, v in LAGOON_RELS.items()},
                   "licence": OSM_LICENCE, "generated_at": utc_now()},
          "features": feats}
    cache.write_text(json.dumps(gj))
    return [geoms[n] for n in geoms]


def load_lagoon_polygons() -> list:
    CACHE_OSM.mkdir(parents=True, exist_ok=True)
    cache = CACHE_OSM / "lagoon_polygons.geojson"
    if not cache.exists():
        ensure_lagoon_polygons()
    from shapely.geometry import shape
    gj = json.loads(cache.read_text())
    return [shape(f["geometry"]) for f in gj["features"]]


def ensure_sea_polygon():
    """Sea polygon for the padded AOI: polygonize OSM natural=coastline with
    the padded bbox ring; the polygon that does not contain a known land
    point is the sea.  Falls back to Natural Earth 10m coastline."""
    CACHE_OSM.mkdir(parents=True, exist_ok=True)
    cache = CACHE_OSM / "aoi_sea_polygon.geojson"
    if cache.exists():
        from shapely.geometry import shape
        gj = json.loads(cache.read_text())
        return shape(gj["features"][0]["geometry"]), gj["meta"]["source"]

    west, south = AOI[0] - AOI_PAD, AOI[1] - AOI_PAD
    east, north = AOI[2] + AOI_PAD, AOI[3] + AOI_PAD
    pad_box = box(west, south, east, north)
    lines, source = [], "OSM natural=coastline via Overpass"
    try:
        q = (f'[out:json][timeout:180];'
             f'way["natural"="coastline"]({south},{west},{north},{east});'
             f'out geom;')
        data = overpass(q)
        for el in data.get("elements", []):
            geom = el.get("geometry") or []
            coords = [(p["lon"], p["lat"]) for p in geom]
            if len(coords) >= 2:
                lines.append(LineString(coords))
    except SystemExit:
        source = "Natural Earth 10m coastline (ne_10m_coastline.geojson cache)"
        ne = CACHE_OSM.parent / "natural_earth" / "ne_10m_coastline.geojson"
        if not ne.exists():
            raise SystemExit("no coastline source available for the sea polygon")
        gj = json.loads(ne.read_text())
        for f in gj["features"]:
            g = f["geometry"]
            if g["type"] == "LineString":
                lines.append(LineString(g["coordinates"]))
            else:
                lines.extend(LineString(c) for c in g["coordinates"])
        lines = [l.intersection(pad_box) for l in lines]
        lines = [l for l in lines if not l.is_empty and l.geom_type == "LineString"]
    if not lines:
        raise SystemExit("no coastline lines found")
    ring = list(pad_box.exterior.coords)
    merged = unary_union(lines + [LineString(ring)])
    polys = list(polygonize(merged))
    sea = None
    land_probe = Point(3.35, 6.60)      # Ikeja: definitely land
    for p in polys:
        if not p.contains(land_probe):
            sea = p if sea is None or p.area > sea.area else sea
    if sea is None:
        raise SystemExit("could not identify a sea polygon")
    # sanity: sea must extend to the southern bbox edge
    if sea.bounds[1] > south + 0.02:
        raise SystemExit(f"sea polygon looks wrong: bounds {sea.bounds}")
    feats = [{"type": "Feature", "properties": {"name": "sea"},
              "geometry": mapping(sea)}]
    gj = {"type": "FeatureCollection",
          "meta": {"source": source, "licence": OSM_LICENCE if "OSM" in source
                   else "Natural Earth (public domain)", "generated_at": utc_now()},
          "features": feats}
    cache.write_text(json.dumps(gj))
    return sea, source


def load_sea_polygon():
    from shapely.geometry import shape
    CACHE_OSM.mkdir(parents=True, exist_ok=True)
    cache = CACHE_OSM / "aoi_sea_polygon.geojson"
    if not cache.exists():
        return ensure_sea_polygon()
    gj = json.loads(cache.read_text())
    return shape(gj["features"][0]["geometry"]), gj["meta"]["source"]


def ensure_waterways() -> list:
    """OSM waterway lines in the AOI (Task 21's extract types)."""
    CACHE_OSM.mkdir(parents=True, exist_ok=True)
    cache = CACHE_OSM / "waterways_aoi.geojson"
    if cache.exists():
        from shapely.geometry import shape
        gj = json.loads(cache.read_text())
        return [shape(f["geometry"]) for f in gj["features"]], gj["meta"]
    log("  fetching OSM waterways via Overpass ...")
    q = (f'[out:json][timeout:300];'
         f'way["waterway"~"^({"|".join(WATERWAY_TYPES)})$"]'
         f'({AOI[1]},{AOI[0]},{AOI[3]},{AOI[2]});'
         f'out geom;')
    data = overpass(q)
    feats = []
    for el in data.get("elements", []):
        coords = [(p["lon"], p["lat"]) for p in (el.get("geometry") or [])]
        if len(coords) >= 2:
            feats.append({"type": "Feature",
                          "properties": {"id": el["id"],
                                         "waterway": el.get("tags", {}).get("waterway"),
                                         "name": el.get("tags", {}).get("name")},
                          "geometry": mapping(LineString(coords))})
    meta = {"source": f"OSM waterway={'|'.join(WATERWAY_TYPES)} via Overpass",
            "licence": OSM_LICENCE, "generated_at": utc_now(),
            "n_ways": len(feats)}
    gj = {"type": "FeatureCollection", "meta": meta, "features": feats}
    cache.write_text(json.dumps(gj))
    log(f"  {len(feats)} waterway ways")
    from shapely.geometry import shape
    return [shape(f["geometry"]) for f in feats], meta


# ---------------------------------------------------------------------------
# Stage 2: hydrology
# ---------------------------------------------------------------------------

def utm_grid() -> tuple:
    """Fixed UTM 31N / 30 m grid covering the AOI (shared by all DEMs)."""
    n_edge = 60
    lons = np.linspace(AOI[0], AOI[2], n_edge)
    lats = np.linspace(AOI[1], AOI[3], n_edge)
    pts = []
    for lo in list(lons) + [AOI[0]] * n_edge + [AOI[2]] * n_edge:
        pass
    edges = (
        [(lo, AOI[1]) for lo in lons] + [(lo, AOI[3]) for lo in lons] +
        [(AOI[0], la) for la in lats] + [(AOI[2], la) for la in lats] +
        [(AOI[0], AOI[1]), (AOI[0], AOI[3]), (AOI[2], AOI[1]), (AOI[2], AOI[3])]
    )
    xs, ys = TR_4326_UTM.transform([p[0] for p in edges], [p[1] for p in edges])
    xmin = math.floor(min(xs) / RES_M) * RES_M
    ymin = math.floor(min(ys) / RES_M) * RES_M
    xmax = math.ceil(max(xs) / RES_M) * RES_M
    ymax = math.ceil(max(ys) / RES_M) * RES_M
    width = int(round((xmax - xmin) / RES_M))
    height = int(round((ymax - ymin) / RES_M))
    return Affine(RES_M, 0.0, xmin, 0.0, -RES_M, ymax), (height, width)


def ensure_water_mask(affine, shape) -> np.ndarray:
    """Rasterized lagoon + sea polygons on the shared UTM grid (cached)."""
    INTER.mkdir(parents=True, exist_ok=True)
    fp = INTER / "water_mask.npy"
    if fp.exists():
        return np.load(fp)
    lag = load_lagoon_polygons()
    sea, sea_src = load_sea_polygon()
    from shapely import transform as shapely_transform
    geoms = []
    for g in lag + [sea]:
        gg = shapely_transform(g, lambda c: np.column_stack(
            TR_4326_UTM.transform(c[:, 0], c[:, 1])))
        if gg.geom_type == "Polygon":
            geoms.append(gg)
        elif gg.geom_type == "MultiPolygon":
            geoms.extend(gg.geoms)
    mask = rasterio.features.rasterize(
        [(g, 1) for g in geoms], out_shape=shape, transform=affine,
        fill=0, dtype="uint8").astype(bool)
    np.save(fp, mask)
    log(f"  water mask: {int(mask.sum())} cells "
        f"({mask.sum() * CELL_AREA / 1e6:.0f} km2); sea from {sea_src}")
    return mask


def warp_dem(dem_name: str, affine, shape) -> np.ndarray:
    src_path = CACHE_DEM / f"{dem_name}_aoi.tif"
    with rasterio.open(src_path) as src:
        dst = np.full(shape, np.nan, dtype=np.float32)
        rio_reproject(
            source=rasterio.band(src, 1), destination=dst,
            src_transform=src.transform, src_crs=src.crs,
            dst_transform=affine, dst_crs=METRIC_CRS,
            dst_nodata=np.nan, resampling=Resampling.bilinear)
    return dst


def stage_hydro(dem_name: str) -> None:
    t0 = time.time()
    affine, shape = utm_grid()
    INTER.mkdir(parents=True, exist_ok=True)
    fp_dem = INTER / f"{dem_name}_dem.npy"
    fp_meta = INTER / f"{dem_name}_meta.json"
    water = ensure_water_mask(affine, shape)

    if not fp_dem.exists():
        log(f"[{dem_name}] warping to UTM 31N @ {RES_M:.0f} m ...")
        dem = warp_dem(dem_name, affine, shape)
        if np.isnan(dem).any():
            raise SystemExit("warp produced nodata holes inside the AOI")
        np.save(fp_dem, dem)
    dem = np.load(fp_dem, mmap_mode="r")
    dem = np.asarray(dem)
    log(f"[{dem_name}] grid {shape[1]}x{shape[0]}, "
        f"elev {float(dem.min()):.1f}..{float(dem.max()):.1f} m")

    C = float(dem[~water].min()) - 10.0
    burned = np.where(water, C, dem).astype(np.float64)
    # rim water cells: guarantee an outlet for border-touching water bodies
    rim = np.zeros(shape, bool)
    rim[0, :] = rim[-1, :] = rim[:, 0] = rim[:, -1] = True
    burned[(water & rim)] = C - 5.0

    # pysheds chain (in-memory Raster viewfinder)
    from pysheds.sview import ViewFinder, Raster
    from pysheds.grid import Grid
    vf = ViewFinder(affine=affine, shape=shape, nodata=np.nan, crs=METRIC_CRS)
    vf_int = ViewFinder(affine=affine, shape=shape, nodata=-1, crs=METRIC_CRS)
    vf_bool = ViewFinder(affine=affine, shape=shape, nodata=False, crs=METRIC_CRS)

    def R(a, dtype=np.float64):
        return Raster(np.asarray(a, dtype=dtype), viewfinder=vf)

    grid = Grid(viewfinder=vf)
    fp_fdir = INTER / f"{dem_name}_fdir.npy"
    fp_depth = INTER / f"{dem_name}_depth.npy"

    if fp_fdir.exists() and fp_depth.exists():
        fdir = np.load(fp_fdir)
        depth = np.load(fp_depth)
    else:
        # a partial previous run would leave inconsistent fill/fdir files
        fp_fdir.unlink(missing_ok=True)
        fp_depth.unlink(missing_ok=True)
        t = time.time()
        pit = grid.fill_pits(R(burned))
        flooded = grid.fill_depressions(pit)
        fl = np.asarray(flooded, dtype=np.float64)
        depth = np.where(water, 0.0, fl - dem)
        np.save(fp_depth, depth.astype(np.float32))
        log(f"[{dem_name}] fill done in {time.time()-t:.0f}s; "
            f"max depth on land {float(depth[~water].max()):.2f} m, "
            f"mean {float(depth[~water].mean()):.3f} m")
        t = time.time()
        inflated = grid.resolve_flats(flooded, eps=1e-5, max_iter=3000)
        fdir_r = grid.flowdir(inflated, routing="d8", flats=-1, pits=-2)
        fdir = np.asarray(fdir_r, dtype=np.int16)
        np.save(fp_fdir, fdir)
        flats_land = int(((fdir == -1) & ~water).sum())
        log(f"[{dem_name}] flowdir done in {time.time()-t:.0f}s; "
            f"unresolved flat cells: {int((fdir == -1).sum())} total, "
            f"{flats_land} on land")
        if flats_land > 0:
            log(f"  WARNING: {flats_land} land cells have no resolved direction")

    fp_acc = INTER / f"{dem_name}_acc.npy"
    if fp_acc.exists():
        acc = np.load(fp_acc)
    else:
        t = time.time()
        fdir_int = Raster(np.asarray(fdir, dtype=np.int64), viewfinder=vf_int)
        acc_r = grid.accumulation(fdir_int, routing="d8")
        acc = np.asarray(acc_r, dtype=np.float32)
        np.save(fp_acc, acc)
        log(f"[{dem_name}] accumulation done in {time.time()-t:.0f}s; "
            f"max {float(acc.max()):.0f} cells")

    # HAND per drainage threshold; water cells count as terminal drainage
    for km2 in DRAINAGE_KM2:
        tag = "025" if km2 == 0.25 else ("4" if km2 == 4.0 else "1")
        fp_hand = INTER / f"{dem_name}_hand_{tag}.npy"
        if fp_hand.exists():
            continue
        t = time.time()
        thr_cells = km2 * 1e6 / CELL_AREA
        mask = ((acc >= thr_cells) | water)
        fdir_int = Raster(np.asarray(fdir, dtype=np.int64), viewfinder=vf_int)
        mask_r = Raster(np.asarray(mask, dtype=np.bool_), viewfinder=vf_bool)
        hand_r = grid.compute_hand(fdir_int, R(dem), mask=mask_r)
        hand = np.asarray(hand_r, dtype=np.float32)
        hand[water] = 0.0
        np.save(fp_hand, hand)
        valid = ~np.isnan(hand) & ~water
        log(f"[{dem_name}] HAND (>= {km2} km2 drainage) in {time.time()-t:.0f}s; "
            f"valid land cells {int(valid.sum())}/{int((~water).sum())}, "
            f"range {float(np.nanmin(hand[valid])):.1f}..{float(np.nanmax(hand[valid])):.1f} m")

    # depression masks
    for thr, tag in zip(DEP_THRESHOLDS, ("025", "050", "100")):
        fp_dep = INTER / f"{dem_name}_depmask_{tag}.npy"
        if fp_dep.exists():
            continue
        raw = depth >= thr
        lab, nlab = ndi.label(raw, structure=np.ones((3, 3), int))
        sizes = np.bincount(lab.ravel())
        keep = np.zeros(sizes.shape, bool)
        keep[1:] = sizes[1:] >= DEP_MIN_CELLS
        dep = keep[lab] & ~water
        np.save(fp_dep, dep)
        log(f"[{dem_name}] depressions >= {thr} m & >= {DEP_MIN_CELLS} cells: "
            f"{int(dep.sum())} cells ({dep.sum()*CELL_AREA/1e6:.1f} km2)")

    # TPI-500 (mean over land cells within 500 m)
    fp_tpi = INTER / f"{dem_name}_tpi.npy"
    if not fp_tpi.exists():
        t = time.time()
        land = ~water
        r_px = int(TPI_RADIUS_M / RES_M)
        yy, xx = np.mgrid[-r_px - 1:r_px + 2, -r_px - 1:r_px + 2]
        kernel = ((yy * RES_M) ** 2 + (xx * RES_M) ** 2) <= TPI_RADIUS_M ** 2
        kernel = kernel.astype(np.float64)
        d = np.asarray(dem, dtype=np.float64)
        m = land.astype(np.float64)
        n = fftconvolve(m, kernel, mode="same")
        s = fftconvolve(d * m, kernel, mode="same")
        with np.errstate(invalid="ignore", divide="ignore"):
            mean = s / n
        tpi = d - mean
        tpi[n < 0.9 * kernel.sum()] = np.nan
        tpi[~land] = np.nan
        np.save(fp_tpi, tpi.astype(np.float32))
        log(f"[{dem_name}] TPI-500 in {time.time()-t:.0f}s")

    # distance to water (m), shared raster
    fp_dist = INTER / "water_dist.npy"
    if not fp_dist.exists():
        t = time.time()
        dist = ndi.distance_transform_edt(~water, sampling=(RES_M, RES_M))
        np.save(fp_dist, dist.astype(np.float32))
        log(f"[{dem_name}] water distance raster in {time.time()-t:.0f}s")

    meta = {"dem": dem_name, "grid": {"affine": [affine.a, affine.b, affine.c,
                                                 affine.d, affine.e, affine.f],
                                      "shape": list(shape), "crs": METRIC_CRS},
            "burn_constant": C, "generated_at": utc_now()}
    fp_meta.write_text(json.dumps(meta))
    log(f"[{dem_name}] hydro stage done in {time.time()-t0:.0f}s")


def available_dems() -> list:
    out = []
    for name in ("fabdem", "glo30"):
        if (INTER / f"{name}_hand_1.npy").exists():
            out.append(name)
    return out


# ---------------------------------------------------------------------------
# Stage 3: analysis
# ---------------------------------------------------------------------------

def load_evidence():
    import builtup_change as bc
    points, stats = bc.collect_evidence2()
    return points, stats


def ghsl_b2020():
    import builtup_change as bc
    clipped = bc.clip_builtup(2020, bc.aoi_mollweide())
    grid = bc.build_grid_arrays({2020: clipped})
    land_mask = bc.ensure_land_mask()
    return grid["built_frac"][2020], land_mask["any_land"]


def window_offsets(radius: float) -> np.ndarray:
    key = int(radius)
    fp = INTER / f"offsets_{key}.npy"
    if fp.exists():
        return np.load(fp)
    r = int(math.ceil(radius / RES_M))
    dy, dx = np.mgrid[-r:r + 1, -r:r + 1]
    dist = np.hypot(dy * RES_M, dx * RES_M)
    sel = dist <= radius
    offs = np.column_stack([dy[sel], dx[sel]]).astype(np.int32)
    np.save(fp, offs)
    return offs


def evaluate_point(row, col, offsets, arrays, land):
    """Window metrics for one point on one DEM."""
    dy, dx = offsets[:, 0], offsets[:, 1]
    rr = row + dy
    cc = col + dx
    H, W = land.shape
    inb = (rr >= 0) & (rr < H) & (cc >= 0) & (cc < W)
    rr, cc = rr[inb], cc[inb]
    valid = land[rr, cc]
    rr, cc = rr[valid], cc[valid]
    out = {"n_land_cells": int(rr.size)}
    if rr.size == 0:
        for k in ALL_METRICS + ("elev_median", "elev_point"):
            out[k] = None
        return out
    hand1 = arrays["hand_1"][rr, cc]
    out["hand_min"] = float(np.nanmin(hand1)) if np.isfinite(hand1).any() else None
    out["hand_min_025"] = (float(np.nanmin(arrays["hand_025"][rr, cc]))
                           if np.isfinite(arrays["hand_025"][rr, cc]).any() else None)
    out["hand_min_4"] = (float(np.nanmin(arrays["hand_4"][rr, cc]))
                         if np.isfinite(arrays["hand_4"][rr, cc]).any() else None)
    for thr, tag in zip(DEP_THRESHOLDS, ("025", "050", "100")):
        key = f"dep_share_{tag}"
        out[key] = float(arrays[f"depmask_{tag}"][rr, cc].mean())
    acc = arrays["acc"][rr, cc]
    accmax = float(acc.max())
    out["acc_log10_max"] = float(math.log10(accmax)) if accmax >= 1 else 0.0
    tpi = arrays["tpi"][rr, cc]
    out["tpi_min"] = float(np.nanmin(tpi)) if np.isfinite(tpi).any() else None
    elev = arrays["dem"][rr, cc]
    out["elev_min"] = float(elev.min())
    out["elev_median"] = float(np.median(elev))
    out["elev_point"] = float(arrays["dem"][row, col]) if land[row, col] else None
    return out


def load_arrays(dem_name: str) -> dict:
    arrs = {
        "dem": np.load(INTER / f"{dem_name}_dem.npy", mmap_mode="r"),
        "acc": np.load(INTER / f"{dem_name}_acc.npy", mmap_mode="r"),
        "tpi": np.load(INTER / f"{dem_name}_tpi.npy", mmap_mode="r"),
    }
    for tag in ("025", "1", "4"):
        arrs[f"hand_{tag}"] = np.load(INTER / f"{dem_name}_hand_{tag}.npy", mmap_mode="r")
    for tag in ("025", "050", "100"):
        arrs[f"depmask_{tag}"] = np.load(INTER / f"{dem_name}_depmask_{tag}.npy", mmap_mode="r")
    return arrs


def matched_test(rows, metric: str, rng) -> dict:
    """Task 16's stratified permutation test, on one metric."""
    vals = []
    for r in rows:
        if not r.get("_bg") or r.get(metric) is None:
            continue
        bg = [e[metric] for e in r["_bg"] if e.get(metric) is not None]
        if bg:
            vals.append((r[metric], bg))
    n = len(vals)
    if n == 0:
        return {"n_points": 0, "note": "no matched points"}
    m = max(len(bg) for _, bg in vals)
    M = np.full((n, 1 + m), np.nan)
    for i, (x, bg) in enumerate(vals):
        M[i, 0] = x
        M[i, 1:1 + len(bg)] = [b if b is not None else np.nan for b in bg]
    bg_med = np.nanmedian(M[:, 1:], axis=1)
    delta = M[:, 0] - bg_med
    t_obs = float(np.median(delta))
    count = 0
    for _ in range(PERM_N):
        P = rng.permuted(M, axis=1)
        t_star = np.nanmedian(P[:, 0] - np.nanmedian(P[:, 1:], axis=1))
        if abs(t_star) >= abs(t_obs) - 1e-12:
            count += 1
    p = (1 + count) / (PERM_N + 1)
    above = int(np.nansum(M[:, 0] > bg_med))
    below = int(np.nansum(M[:, 0] < bg_med))
    return {
        "n_points": n,
        "n_full_stratum": int(sum(1 for _, bg in vals if len(bg) >= BG_N)),
        "median_point": round(float(np.median(M[:, 0])), 4),
        "median_control": round(float(np.median(bg_med)), 4),
        "median_matched_difference": round(t_obs, 4),
        "mean_matched_difference": round(float(np.mean(delta)), 4),
        "share_above_control_median": round(above / n, 4),
        "share_below_control_median": round(below / n, 4),
        "permutation": {"n_shuffles": PERM_N, "p_two_sided": round(p, 4),
                        "seed": SEED,
                        "statistic": "median over points of (point metric - median of its matched controls)"},
    }


def save_png(fig, path: Path, dpi_try=(130, 100, 80)) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    for dpi in dpi_try:
        fig.savefig(path, dpi=dpi, bbox_inches="tight")
        if path.stat().st_size <= 300_000:
            return
    log(f"  WARNING: {path.name} still > 300 KB at {dpi_try[-1]} dpi "
        f"({path.stat().st_size/1024:.0f} KB)")


def stage_analyze(cleanup: bool) -> None:
    import builtup_change as bc
    t0 = time.time()
    dems = available_dems()
    if not dems:
        raise SystemExit("no DEM has a hydro stage output; run 'hydro <dem>' first")
    log(f"[analyze] DEMs: {dems}")

    affine, shape = utm_grid()
    inv = ~affine
    land_all = ~np.load(INTER / "water_mask.npy", mmap_mode="r")
    water_dist = np.load(INTER / "water_dist.npy", mmap_mode="r")
    waterways, waterways_meta = ensure_waterways()
    from shapely import transform as shapely_transform
    wwm = MultiLineString(waterways) if waterways else MultiLineString()
    wwm_m = shapely_transform(wwm, lambda c: np.column_stack(
        TR_4326_UTM.transform(c[:, 0], c[:, 1]))) if not wwm.is_empty else None

    # evidence
    points, ev_stats = load_evidence()
    log(f"[analyze] evidence: {len(points)} kept points "
        f"({ev_stats['raw']} raw, {ev_stats['lga_excluded']} lga, {ev_stats['dupes_dropped']} dupes)")
    ev_xy = np.array([[p["_x"], p["_y"]] for p in points])
    ev_lonlat = [(p["lon"], p["lat"]) for p in points]

    # GHSL built-up 2020 (Task 16 matching layer)
    b2020, any_land = ghsl_b2020()
    any_built = b2020 > 0
    NXb, NYb = bc.NX, bc.NY
    ev_cells = set()
    for p in points:
        ix = int(math.floor((p["lon"] - bc.LON0) / bc.CELL))
        iy = int(math.floor((p["lat"] - bc.LAT0) / bc.CELL))
        p["_b2020"] = float(b2020[iy, ix])
        ev_cells.add((iy, ix))

    def lonlat_to_rc(lon, lat):
        x, y = TR_4326_UTM.transform(lon, lat)
        col, row = inv * (x, y)
        return int(row), int(col), x, y

    def in_water(lon, lat):
        row, col, _, _ = lonlat_to_rc(lon, lat)
        if not (0 <= row < shape[0] and 0 <= col < shape[1]):
            return True
        return not bool(land_all[row, col])

    # ---- control pools, one per design (shared across DEMs) ----
    def point_dist_water(lon, lat):
        row, col, _, _ = lonlat_to_rc(lon, lat)
        if 0 <= row < shape[0] and 0 <= col < shape[1]:
            return float(water_dist[row, col])
        return 1e9

    def draw_global_pool(p, rng, tree, match_water):
        """Task 24's sampler: candidates uniform over the AOI, GHSL built-up
        2020 matched to +/- BG_TOL; 'matched_water' adds the distance-to-
        lagoon/sea criterion.  The draw order is exactly Task 24's, so the
        builtup_only pool reproduces the Task 24 run."""
        pd = point_dist_water(p["lon"], p["lat"])
        wtol = max(WATER_MATCH_REL_TOL * pd, WATER_MATCH_MIN_TOL_M)
        need = BG_N
        got = []
        tries = 0
        while len(got) < need and tries < 400:
            tries += 1
            batch = max(200, 10 * (need - len(got)))
            lo = rng.uniform(AOI[0], AOI[2], batch)
            la = rng.uniform(AOI[1], AOI[3], batch)
            for lon, lat in zip(lo, la):
                if len(got) >= need:
                    break
                ix = int(math.floor((lon - bc.LON0) / bc.CELL))
                iy = int(math.floor((lat - bc.LAT0) / bc.CELL))
                if not (0 <= ix < NXb and 0 <= iy < NYb):
                    continue
                if not (any_land[iy, ix] or any_built[iy, ix]):
                    continue
                if (iy, ix) in ev_cells:
                    continue
                if abs(float(b2020[iy, ix]) - p["_b2020"]) > BG_TOL:
                    continue
                if in_water(lon, lat):
                    continue
                x, y = TR_4326_UTM.transform(lon, lat)
                if tree.query([x, y])[0] < MIN_EVIDENCE_DIST_M:
                    continue
                if match_water:
                    if abs(point_dist_water(lon, lat) - pd) > wtol:
                        continue
                got.append({"lon": float(lon), "lat": float(lat),
                            "_b2020": float(b2020[iy, ix])})
        return got

    def draw_local_pool(p, rng, tree, tol):
        """'local' design: candidates uniform in a 1-3 km annulus around the
        point; only the built-up tolerance differs from the caller's knob."""
        px, py = p["_x"], p["_y"]
        r1, r2 = LOCAL_ANNULUS_M
        need = BG_N
        got = []
        tries = 0
        while len(got) < need and tries < 400:
            tries += 1
            batch = max(300, 10 * (need - len(got)))
            rad = np.sqrt(rng.uniform(r1 * r1, r2 * r2, batch))
            ang = rng.uniform(0.0, 2.0 * math.pi, batch)
            xs = px + rad * np.cos(ang)
            ys = py + rad * np.sin(ang)
            lons, lats = TR_UTM_4326.transform(xs, ys)
            for lon, lat in zip(lons, lats):
                if len(got) >= need:
                    break
                ix = int(math.floor((lon - bc.LON0) / bc.CELL))
                iy = int(math.floor((lat - bc.LAT0) / bc.CELL))
                if not (0 <= ix < NXb and 0 <= iy < NYb):
                    continue
                if not (any_land[iy, ix] or any_built[iy, ix]):
                    continue
                if abs(float(b2020[iy, ix]) - p["_b2020"]) > tol:
                    continue
                if in_water(lon, lat):
                    continue
                x, y = TR_4326_UTM.transform(lon, lat)
                if tree.query([x, y])[0] < MIN_EVIDENCE_DIST_M:
                    continue
                got.append({"lon": float(lon), "lat": float(lat),
                            "_b2020": float(b2020[iy, ix])})
        return got

    from scipy.spatial import cKDTree
    tree = cKDTree(ev_xy)
    pools = {}
    local_widened = []
    for design in DESIGNS:
        fp = INTER / f"controls_{design}.json"
        if fp.exists():
            pools[design] = json.loads(fp.read_text())
            log(f"[analyze] '{design}' pools loaded from cache "
                f"({sum(len(g) for g in pools[design])} controls)")
            continue
        log(f"[analyze] drawing '{design}' controls ...")
        rng = np.random.default_rng(SEED)
        got_pools = []
        for pi, p in enumerate(points):
            if design == "local":
                got = draw_local_pool(p, rng, tree, LOCAL_BG_TOL)
                if len(got) < LOCAL_MIN_FOUND:
                    got = draw_local_pool(p, rng, tree, LOCAL_BG_TOL_WIDE)
                    local_widened.append(pi)
            else:
                got = draw_global_pool(p, rng, tree,
                                       design == "matched_water")
            got_pools.append(got)
            if (pi + 1) % 50 == 0:
                log(f"  {design}: point {pi + 1}/{len(points)} "
                    f"(median pool {np.median([len(g) for g in got_pools]):.0f})")
        pools[design] = got_pools
        fp.write_text(json.dumps(got_pools))
        if design == "local":
            (INTER / "controls_local_widened.json").write_text(
                json.dumps(local_widened))
        full = sum(1 for g in got_pools if len(g) == BG_N)
        extra = ""
        if design == "local":
            extra = (f"; built-up tolerance widened to +/- {LOCAL_BG_TOL_WIDE} "
                     f"for {len(local_widened)} points")
        log(f"[analyze] '{design}' pools drawn: {full}/{len(points)} points with "
            f"the full {BG_N}; median pool "
            f"{np.median([len(g) for g in got_pools]):.0f}{extra}")
    fp_local_widen = INTER / "controls_local_widened.json"
    if fp_local_widen.exists():
        local_widened = json.loads(fp_local_widen.read_text())

    # ---- per-DEM evaluation (points + every design's pools) ----
    per_dem = {}
    for dem_name in dems:
        t = time.time()
        arrs = load_arrays(dem_name)
        land = np.asarray(land_all)
        evals = []
        for p in points:
            row, col, x, y = lonlat_to_rc(p["lon"], p["lat"])
            radius = RADIUS_M.get(p["location_confidence"], DEFAULT_RADIUS)
            offs = window_offsets(radius)
            e = evaluate_point(row, col, offs, arrs, land)
            e["radius_m"] = radius
            e["row"], e["col"] = row, col
            evals.append(e)
        ctrl_evals = {design: [] for design in DESIGNS}
        for design in DESIGNS:
            for gi, got in enumerate(pools[design]):
                radius = RADIUS_M.get(points[gi]["location_confidence"], DEFAULT_RADIUS)
                offs = window_offsets(radius)
                ce = []
                for c in got:
                    row, col, _, _ = lonlat_to_rc(c["lon"], c["lat"])
                    e = evaluate_point(row, col, offs, arrs, land)
                    e["row"], e["col"] = row, col
                    ce.append(e)
                ctrl_evals[design].append(ce)
        per_dem[dem_name] = (evals, ctrl_evals)
        n_ctrl = sum(len(x) for design in DESIGNS for c in ctrl_evals[design] for x in c)
        log(f"[analyze] {dem_name}: evaluated {len(evals)} points and "
            f"{n_ctrl} control windows across {len(DESIGNS)} designs "
            f"in {time.time()-t:.0f}s")

    # ---- assemble per-point records and run tests ----
    results = {d: {design: {} for design in DESIGNS} for d in dems}
    point_table = []
    for pi, p in enumerate(points):
        rec = {
            "event_id": p["event"], "id": p["id"],
            "location_name": p.get("location_name"),
            "location_confidence": p["location_confidence"],
            "lon": round(p["lon"], 5), "lat": round(p["lat"], 5),
            "b2020": round(p["_b2020"], 3),
            "radius_m": RADIUS_M.get(p["location_confidence"], DEFAULT_RADIUS),
            "dist_lagoon_sea_m": None, "dist_waterway_m": None,
            "metrics": {d: {} for d in dems},
        }
        row, col, x, y = lonlat_to_rc(p["lon"], p["lat"])
        if 0 <= row < shape[0] and 0 <= col < shape[1]:
            rec["dist_lagoon_sea_m"] = round(float(water_dist[row, col]), 0)
        if wwm_m is not None:
            rec["dist_waterway_m"] = round(float(wwm_m.distance(Point(x, y))), 0)
        for d in dems:
            e = per_dem[d][0][pi]
            for k in ALL_METRICS + ("elev_median", "elev_point", "n_land_cells"):
                rec["metrics"][d][k] = (round(e[k], 3)
                                        if isinstance(e[k], float) else e[k])
        point_table.append(rec)

    def holm_adjust(rawp):
        """Holm-Bonferroni over the metrics present in rawp (metric -> p)."""
        order = sorted(rawp.items(), key=lambda kv: kv[1])
        m = len(order)
        adj = {}
        running = 0.0
        for rank, (met, p) in enumerate(order):
            running = max(running, (m - rank) * p)
            adj[met] = min(1.0, running)
        return adj

    def finish_metric(r, metric):
        """Role label + median difference in 2 m DEM-error units."""
        if metric in PRIMARY_METRICS:
            r["role"] = "primary"
        elif metric in DESCRIPTIVE_METRICS:
            r["role"] = "descriptive"
        else:
            r["role"] = "sensitivity"
        if isinstance(r.get("median_matched_difference"), float):
            r["diff_over_2m"] = round(
                r["median_matched_difference"] / DEM_VERT_ERROR_M, 4)
        return r

    def add_holm(res_s):
        rawp = {mx: (res_s[mx]["permutation"]["p_two_sided"]
                     if isinstance(res_s.get(mx, {}).get("permutation"), dict) else None)
                for mx in PRIMARY_METRICS if mx in res_s}
        rawp = {k: v for k, v in rawp.items() if v is not None}
        adj = holm_adjust(rawp)
        for mx in PRIMARY_METRICS:
            if mx in res_s:
                res_s[mx]["holm_p"] = round(adj[mx], 4) if mx in adj else None

    # ---- tests: results[dem][design][subset][metric] ----
    for d in dems:
        evals, ctrl_evals = per_dem[d]
        for design in DESIGNS:
            rows = []
            for pi in range(len(points)):
                r = dict(evals[pi])
                r["_bg"] = ctrl_evals[design][pi]
                rows.append(r)
            subsets = {
                "all": rows,
                "precise_street_point": [r for r, p in zip(rows, points)
                                         if p["location_confidence"] in ("street", "point", "exact")],
                "far_from_water_gt2km": [r for r, p in zip(rows, points)
                                         if lonlat_dist_water(p) > FAR_WATER_M],
            }
            for sname, srows in subsets.items():
                res_s = {}
                for metric in ALL_METRICS:
                    res_s[metric] = finish_metric(
                        matched_test(srows, metric, np.random.default_rng(SEED)),
                        metric)
                add_holm(res_s)
                results[d][design][sname] = res_s

    # ---- keep the Task 24 run as the 'builtup_only' design ----
    repro = {}
    as_run = {}
    old_file = EVENTS / "terrain_check.json"
    if old_file.exists():
        try:
            old_doc = json.loads(old_file.read_text())
        except Exception:
            old_doc = None
        old_res = (old_doc or {}).get("results") or {}
        for d, sub in old_res.items():
            if d not in dems or not isinstance(sub, dict):
                continue
            if "builtup_only" in sub:
                # 24b schema: the stored builtup_only numbers are the
                # preserved Task 24 run (or, for DEMs Task 24 never ran, the
                # preserved 24b recomputation) - keep using them verbatim
                stored = sub["builtup_only"]
                prev = ((old_doc or {}).get("meta") or {}).get(
                    "designs_meta", {}).get("builtup_only", {}).get("as_run")
                as_run[d] = (prev.get(d) if isinstance(prev, dict) else
                             "task 24b run (numbers preserved from the previous "
                             "events/terrain_check.json)")
            elif "all" in sub:
                stored = sub          # Task 24 schema (dem -> subset -> metric)
                as_run[d] = ("task 24 run, preserved verbatim from the previous "
                             "events/terrain_check.json (role labels, Holm p and "
                             "diff_over_2m recomputed for the 24b scheme)")
            else:
                continue
            migrated = {}
            for sname, metrics in stored.items():
                mm = {}
                for metric, r in metrics.items():
                    mm[metric] = finish_metric(dict(r), metric)
                add_holm(mm)
                migrated[sname] = mm
            dp = dmed = 0.0
            for sname, metrics in migrated.items():
                for metric, r_old in metrics.items():
                    r_new = results[d]["builtup_only"].get(sname, {}).get(metric, {})
                    if isinstance(r_old.get("permutation"), dict) and \
                            isinstance(r_new.get("permutation"), dict):
                        dp = max(dp, abs(r_old["permutation"]["p_two_sided"]
                                         - r_new["permutation"]["p_two_sided"]))
                        dmed = max(dmed, abs(r_old.get("median_matched_difference", 0.0)
                                             - r_new.get("median_matched_difference", 0.0)))
            ok = dp <= 0.005 and dmed <= 0.05
            repro[d] = {"max_delta_p": round(dp, 4),
                        "max_delta_median_diff": round(dmed, 4),
                        "reproduces_stored_run": ok}
            log(f"[analyze] {d}/builtup_only recomputed vs the stored run: "
                f"max delta p {dp:.4f}, max delta median diff {dmed:.4f} -> "
                + ("reproduced; keeping the stored numbers" if ok else
                   "DRIFTED; keeping the stored numbers verbatim anyway"))
            results[d]["builtup_only"] = migrated

    # ---- verdict: rule fixed before results (written to meta.verdict_rule) ----
    def sig_metrics(res_design, sname):
        sub = res_design.get(sname, {})
        return [m for m in PRIMARY_METRICS
                if sub.get(m, {}).get("n_points")
                and sub[m].get("holm_p") is not None
                and sub[m]["holm_p"] < ALPHA
                and np.sign(sub[m]["median_matched_difference"]) == DIRECTION[m]]

    def design_verdict(res_design):
        sig_all = sig_metrics(res_design, "all")
        sig_far = sig_metrics(res_design, "far_from_water_gt2km")
        if not sig_all:
            word = "fail"
        elif len(sig_all) >= 2 and any(m in sig_far for m in sig_all):
            word = "pass"
        else:
            word = "mixed"
        return word, sig_all, sig_far

    deciding_dem = "fabdem" if "fabdem" in dems else dems[0]
    verdicts = {(d, design): design_verdict(results[d][design])
                for d in dems for design in DESIGNS}
    verdict_word = verdicts[(deciding_dem, "local")][0]

    # ---- secondary honest check: low land share ----
    secondary = {}
    for d in dems:
        hand = np.load(INTER / f"{d}_hand_1.npy", mmap_mode="r")
        land = np.asarray(land_all)
        hv = np.asarray(hand)[land]
        hv = hv[np.isfinite(hv)]
        land_low = float((hv < HAND_LOW_M).mean())
        depmask = np.load(INTER / f"{d}_depmask_050.npy", mmap_mode="r")
        land_dep = float(np.asarray(depmask)[land].mean())
        pts_low = [r for r in point_table
                   if r["metrics"][d].get("hand_min") is not None
                   and r["metrics"][d]["hand_min"] < HAND_LOW_M]
        pts_dep = [r for r in point_table
                   if (r["metrics"][d].get("dep_share_050") or 0) > 0]
        ctrl_low = 0
        ctrl_n = 0
        for ce in per_dem[d][1]["builtup_only"]:
            for e in ce:
                ctrl_n += 1
                if e.get("hand_min") is not None and e["hand_min"] < HAND_LOW_M:
                    ctrl_low += 1
        secondary[d] = {
            "aoi_land_share_hand_lt_2m": round(land_low, 4),
            "aoi_land_share_depression_ge_050": round(land_dep, 4),
            "points_share_hand_lt_2m": round(len(pts_low) / len(points), 4),
            "points_share_in_depression": round(len(pts_dep) / len(points), 4),
            "controls_share_hand_lt_2m": round(ctrl_low / ctrl_n, 4) if ctrl_n else None,
            "n_land_cells": int(hv.size),
            "n_control_cells": int(ctrl_n),
            "note": ("points/controls use the min HAND within their radius window; "
                      "AOI share is cell-level over land"),
        }

    # ---- drainage sites ----
    sites_out = []
    if (EVENTS / "drainage_sites.json").exists():
        ds = json.loads((EVENTS / "drainage_sites.json").read_text())
        from shapely.geometry import shape as shp_shape
        pool = {d: {design: [e for ce in per_dem[d][1][design] for e in ce]
                    for design in DESIGNS} for d in dems}
        for site in ds.get("sites", []):
            g = shp_shape(site["geometry"])
            cx, cy = g.centroid.x, g.centroid.y
            conf = site.get("location_confidence", "street")
            radius = RADIUS_M.get(conf, DEFAULT_RADIUS)
            row, col, x, y = lonlat_to_rc(cx, cy)
            offs = window_offsets(radius)
            rec = {
                "site_id": site["site_id"],
                "structure_name": site.get("structure_name"),
                "location_confidence": conf,
                "radius_m": radius,
                "centroid": [round(cx, 5), round(cy, 5)],
                "dist_lagoon_sea_m": (round(float(water_dist[row, col]), 0)
                                      if 0 <= row < shape[0] and 0 <= col < shape[1] else None),
                "metrics": {},
            }
            for d in dems:
                e = evaluate_point(row, col, offs, load_arrays(d), np.asarray(land_all))
                mets = {}
                for k in ALL_METRICS + ("elev_median", "elev_point"):
                    if isinstance(e.get(k), float):
                        v = e[k]

                        def pct_among(pool_key, _v=v, _k=k):
                            cv = [c[_k] for c in pool[d][pool_key]
                                  if c.get(_k) is not None and isinstance(c[_k], float)]
                            return (round(float((np.array(cv) < _v).mean()), 4)
                                    if cv else None)

                        mets[k] = {"value": round(v, 3),
                                   "control_percentile": pct_among("builtup_only"),
                                   "percentile_local": pct_among("local")}
                    else:
                        mets[k] = {"value": e.get(k), "control_percentile": None,
                                   "percentile_local": None}
                rec["metrics"][d] = mets
            sites_out.append(rec)

    # ---- maps and plots ----
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    TERRAIN_DIR.mkdir(parents=True, exist_ok=True)
    pts_rc = np.array([[r["lat"], r["lon"]] for r in point_table])
    xs, ys = TR_4326_UTM.transform(pts_rc[:, 1], pts_rc[:, 0])
    extent = [affine.c, affine.c + shape[1] * RES_M,
              affine.f - shape[0] * RES_M, affine.f]

    for d in dems:
        hand = np.load(INTER / f"{d}_hand_1.npy", mmap_mode="r")
        wmask = ~np.asarray(land_all)
        h = np.asarray(hand, dtype=np.float64)
        h = np.ma.masked_array(h, mask=wmask | ~np.isfinite(h))
        fig, ax = plt.subplots(figsize=(11, 4.2))
        im = ax.imshow(h[::2, ::2], extent=extent, cmap="viridis", vmin=0, vmax=15,
                       interpolation="nearest")
        ax.scatter(xs, ys, s=9, c="red", edgecolors="white", linewidths=0.3, zorder=3)
        ax.set_title(f"{'FABDEM' if d == 'fabdem' else 'Copernicus GLO-30'} - "
                     f"HAND (drainage >= 1 km2; water = terminal drainage)\n"
                     f"Lagos AOI; red = {len(point_table)} kept flood-evidence points")
        ax.set_xlabel("UTM 31N easting (m)")
        ax.set_ylabel("northing (m)")
        fig.colorbar(im, ax=ax, label="m above nearest drainage", shrink=0.9)
        save_png(fig, TERRAIN_DIR / f"hand_map_{d}.png")
        plt.close(fig)

        depth = np.asarray(np.load(INTER / f"{d}_depth.npy", mmap_mode="r"),
                           dtype=np.float64)
        dep = np.ma.masked_array(depth, mask=wmask)
        dep = np.clip(dep, 0, 2)
        fig, ax = plt.subplots(figsize=(11, 4.2))
        im = ax.imshow(dep[::2, ::2], extent=extent, cmap="magma", vmin=0, vmax=2,
                       interpolation="nearest")
        ax.scatter(xs, ys, s=9, c="cyan", edgecolors="black", linewidths=0.3, zorder=3)
        ax.set_title(f"{'FABDEM' if d == 'fabdem' else 'Copernicus GLO-30'} - "
                     f"fill depth (filled - DEM), clipped at 2 m\n"
                     f"cyan = flood-evidence points; depressions = depth >= 0.5 m and >= 3 cells")
        ax.set_xlabel("UTM 31N easting (m)")
        ax.set_ylabel("northing (m)")
        fig.colorbar(im, ax=ax, label="m of fill", shrink=0.9)
        save_png(fig, TERRAIN_DIR / f"depression_map_{d}.png")
        plt.close(fig)

    metric_labels = {
        "hand_min": "min HAND within radius (m)",
        "dep_share_050": "share of window in depression >= 0.5 m",
        "acc_log10_max": "max log10 flow accumulation",
        "tpi_min": "min TPI-500 (m)",
        "elev_min": "min elevation in window (m)",
    }
    for metric in PRIMARY_METRICS + DESCRIPTIVE_METRICS:
        fig, axes = plt.subplots(len(dems), len(DESIGNS),
                                 figsize=(4.4 * len(DESIGNS), 4.0 * len(dems)),
                                 squeeze=False)
        for di, d in enumerate(dems):
            pv = [r["metrics"][d][metric] for r in point_table
                  if r["metrics"][d].get(metric) is not None]
            for gi, design in enumerate(DESIGNS):
                ax = axes[di][gi]
                cv = []
                for ce in per_dem[d][1][design]:
                    cv.extend(e[metric] for e in ce if e.get(metric) is not None)
                data = [pv, cv]
                ax.boxplot(data, showfliers=False, widths=0.5)
                ax.set_xticks([1, 2])
                ax.set_xticklabels(["flood points", "controls"], fontsize=8)
                rng2 = np.random.default_rng(1)
                for i, vals in enumerate(data, start=1):
                    j = rng2.uniform(-0.13, 0.13, len(vals))
                    ax.scatter(np.full(len(vals), i) + j, vals, s=2.5, alpha=0.25,
                               color="#666666", zorder=1)
                res = results[d][design]["all"][metric]
                pv_p = (res.get("permutation") or {}).get("p_two_sided")
                holm_p = res.get("holm_p")
                title = (f"{'FABDEM' if d == 'fabdem' else 'GLO-30'} / {design}  "
                         f"(n={res.get('n_points', 0)})\n")
                if isinstance(res.get("median_matched_difference"), float):
                    title += (f"median diff {res['median_matched_difference']:+.3f}"
                              f" ({res['diff_over_2m']:+.2f} DEM errors), ")
                if pv_p is not None:
                    title += f"p = {pv_p:.3f}"
                if holm_p is not None:
                    title += f", Holm p = {holm_p:.3f}"
                ax.set_title(title, fontsize=8)
                if gi == 0:
                    ax.set_ylabel(metric_labels[metric], fontsize=8)
        fig.suptitle(f"{metric_labels[metric]} - flood points vs controls, "
                     "one panel per design", fontsize=10)
        fig.tight_layout()
        save_png(fig, TERRAIN_DIR / f"box_{metric}.png")
        plt.close(fig)

    # ---- write JSON outputs ----
    sea_geom, sea_src = load_sea_polygon()
    fab_ok = "fabdem" in dems
    fp_mirror = CACHE_DEM / "fabdem_mirror.json"
    mirror_used = fab_ok and fp_mirror.exists()
    mirror_info = json.loads(fp_mirror.read_text()) if mirror_used else None
    meta = {
        "task": "24b-terrain-controls (extends 24-terrain-check, roadmap step 5)",
        "question": ("do reported flood locations sit in terrain lows and modelled "
                     "flow paths more than comparable places? - now asked against "
                     "geography-controlled and neighbourhood-matched controls"),
        "sources": {
            "dem_primary": FABDEM_LICENCE,
            "dem_comparison": GLO30_LICENCE,
            "dem_urls": {"fabdem": FABDEM_URL,
                         "fabdem_mirror": FABDEM_MIRROR_TILE.format(tile="<tile>"),
                         "glo30": GLO30_URL.format(t="<tile>")},
            "water_lagoon_sea": {
                "lagoon": f"OSM relations {sorted(LAGOON_RELS)}, {OSM_LICENCE}",
                "sea": f"{sea_src}, rasterized with the lagoon polygons",
            },
            "waterways": waterways_meta,
            "builtup_2020_matching": f"GHS-BUILT-S R2023A E2020, {GHSL_LICENCE}",
            "land_mask": f"ESA WorldCover 10 m v200 (2021), {WC_LICENCE}",
            "evidence": "events/*/evidence.geojson (five events)",
        },
        "fabdem_available": fab_ok,
        "fabdem_note": (("FABDEM V1-2 fetched from the University of Bristol "
                         "data.bris repository.") if fab_ok and not mirror_used else
                        (FABDEM_MIRROR_NOTE if mirror_used else
                         "FABDEM V1-2 was NOT reachable from data.bris during this run "
                         "(connection resets on every request, retried) and no verified "
                         "mirror could be used; results are GLO-30 only. FABDEM adds a "
                         "bare-earth comparison; re-run 'fetch' + 'hydro fabdem' + "
                         "'analyze' when a source recovers.")),
        "fabdem_mirror": mirror_info,
        "method": {
            "grid": f"UTM 31N (EPSG:32631), {RES_M:.0f} m, bilinear reprojection",
            "outlet_burning": ("lagoon/sea rasterized from OSM polygons and set to "
                               f"(min land elevation - 10) m; rim water cells set 5 m "
                               "lower so border-touching water bodies drain"),
            "depressions": ("priority-flood fill (pysheds 0.5 fill_pits + "
                            "fill_depressions); depth = filled - DEM on land; "
                            f"depression mask = depth >= {{0.25, 0.5, 1.0}} m and >= "
                            f"{DEP_MIN_CELLS} connected cells (8-neighbourhood); "
                            "FABDEM vertical error is ~2 m in cities, so 0.25 m is "
                            "optimistic and 1.0 m is conservative"),
            "routing": ("D8 on the flat-resolved conditioned surface "
                        "(pysheds resolve_flats, Barnes et al. 2015); "
                        "flow accumulation in cells"),
            "hand": ("HAND via pysheds compute_hand (Nobre-style: elevation minus the "
                     "elevation of the drainage cell at the end of the D8 flow path); "
                     "drainage = accumulation >= 0.25/1/4 km2 (primary 1 km2), and "
                     "lagoon/sea cells are terminal drainage so that cells draining "
                     "straight into water are defined; mapped waterways were NOT burned "
                     "in (kept only for distance-to-water)"),
            "tpi_500": "elevation minus mean land elevation within 500 m (FFT disk mean)",
            "metrics_window": ("per point, metrics computed within a radius matched to "
                               "location confidence: street/point/exact 150 m, "
                               "neighbourhood 750 m, over land cells only"),
            "designs": {
                "builtup_only": ("Task 24's controls: up to 20 random land points "
                                 "anywhere in the AOI, GHSL built-up 2020 within "
                                 f"+/- {BG_TOL} of the point's 1 km cell; numbers kept "
                                 "from the Task 24 run itself"),
                "matched_water": ("as builtup_only, plus distance to lagoon/sea "
                                  f"within +/- {WATER_MATCH_REL_TOL:.0%} of the point's "
                                  f"(minimum +/- {WATER_MATCH_MIN_TOL_M:.0f} m)"),
                "local": (f"up to {BG_N} random land points in a "
                          f"{LOCAL_ANNULUS_M[0] / 1000:.0f}-{LOCAL_ANNULUS_M[1] / 1000:.0f} km "
                          "annulus around each point, GHSL built-up 2020 within "
                          f"+/- {LOCAL_BG_TOL} (widened to +/- {LOCAL_BG_TOL_WIDE} only "
                          f"where fewer than {LOCAL_MIN_FOUND} candidates existed; "
                          "widened points in meta.designs_meta.local.widened_points)"),
                "shared_rules": ("all designs: land candidates only (not water), "
                                 f"never within {MIN_EVIDENCE_DIST_M:.0f} m of any "
                                 "kept evidence point, evaluated at the same window "
                                 "radius as their point"),
            },
            "test": (f"stratified permutation (within-stratum label exchange), "
                     f"{PERM_N:,} shuffles, seed {SEED}; statistic = median over points "
                     "of (point metric - median of its matched controls); raw and "
                     "Holm-corrected p-values reported for the 4 primary metrics per "
                     "DEM x design x subset"),
            "subsets": {"all": "every kept point",
                        "precise_street_point": "street/point/exact confidence only",
                        "far_from_water_gt2km": (f"points > {FAR_WATER_M:.0f} m from "
                                                 "lagoon/sea (tide cannot be the explanation)")},
        },
        "primary_metrics": {
            "metrics": list(PRIMARY_METRICS),
            "elevation_demoted": ("elev_min is descriptive only: the AOI reaches Ogun "
                                  "State and the Epe/Badagry hinterland, so AOI-wide "
                                  "elevation differences mostly separate the low "
                                  "coastal city from the interior, not local lows "
                                  "within a neighbourhood"),
            "effect_scale": ("every median difference is also reported as diff_over_2m, "
                             f"in units of the ~{DEM_VERT_ERROR_M:.0f} m DEM vertical "
                             "error, so local signals can be read against DEM noise"),
            "multiple_testing": ("Holm correction across the 4 primary metrics, per "
                                 "DEM x design x subset"),
        },
        "designs_meta": {
            "builtup_only": {
                "as_run": (as_run or {"note": "task 24b run; no previous run found"}),
                "reproduction_check": repro,
            },
            "matched_water": {
                "relative_tolerance": WATER_MATCH_REL_TOL,
                "minimum_tolerance_m": WATER_MATCH_MIN_TOL_M,
            },
            "local": {
                "annulus_m": list(LOCAL_ANNULUS_M),
                "builtup_tolerance": LOCAL_BG_TOL,
                "builtup_tolerance_widened": LOCAL_BG_TOL_WIDE,
                "n_points_widened": len(local_widened),
                "widened_points": local_widened,
            },
        },
        "verdict_rule": {
            "fixed_before_results": True,
            "decided_by": {"design": "local", "dem": deciding_dem},
            "primary_metrics": list(PRIMARY_METRICS),
            "predicted_direction": {m: ("lower" if DIRECTION[m] < 0 else "higher")
                                    for m in PRIMARY_METRICS},
            "alpha": ALPHA,
            "pass": ("in the local design, at least 2 of the 4 primary metrics are "
                     "significant after Holm (p < 0.05) in the predicted direction "
                     "for the all-points subset, and at least one of those is also "
                     "significant in the far_from_water_gt2km subset"),
            "fail": ("none of the 4 primary metrics significant after Holm in the "
                     "local design"),
            "mixed": "anything else",
            "note": ("the verdict is written for every design, but the local design "
                     "decides; with both DEMs, the primary DEM (FABDEM) decides"),
        },
        "verdict": verdict_word,
        "verdicts": {f"{d}|{design}": {
            "verdict": verdicts[(d, design)][0],
            "significant_all_points": verdicts[(d, design)][1],
            "significant_far_from_water_gt2km": verdicts[(d, design)][2],
        } for d in dems for design in DESIGNS},
        "evidence_filtering": {
            "raw": ev_stats["raw"], "lga_excluded": ev_stats["lga_excluded"],
            "dupes_dropped": ev_stats["dupes_dropped"],
            "kept": len(points),
            "rule": "Task 16: location_confidence 'lga' dropped; duplicates within "
                    "200 m in the same event removed (first kept)",
        },
        "seed": SEED,
        "caveats": [
            "Lagos is extremely flat and 30 m DEM vertical error is ~2 m, so HAND and "
            "depression values are relative indicators, not depth predictions",
            "HAND can be negative where a cell drains into a drainage cell that sits "
            "higher in the raw DEM - i.e. inside a filled depression below its outlet; "
            "the more negative, the deeper the modelled depression, so min HAND and "
            "the depression-share metrics partly measure the same thing",
            "GLO-30 contains interpolation artifacts over the open lagoon (values up "
            "to ~58 m over water); those cells are masked as water and burned to the "
            "outlet constant, so they never enter land metrics",
            "GLO-30 is a DSM: buildings add spurious relief; FABDEM removes buildings "
            "and trees but its own bare-earth surface is smoothed",
            "evidence points are mostly neighbourhood centroids, not the flooded spot",
            "builtup_only controls are matched on built-up level only; matched_water "
            "adds distance to lagoon/sea and 'local' restricts to the point's own "
            "1-3 km neighbourhood; population density and drainage investment remain "
            "unmeasured confounders in every design",
            "elevation is confounded by geography: the AOI includes Ogun State and "
            "the Epe/Badagry hinterland, so elev_min is descriptive only and the Task "
            "24 17 m elevation gap says 'low coastal city', not 'local low'",
            "the local signals are small next to the ~2 m DEM vertical error: read "
            "diff_over_2m next to every p-value, not just the p-value",
            "p-values are Holm-corrected across the 4 primary metrics per design x "
            "subset; uncorrected scanning of 9 metrics x 3 subsets x 3 designs would "
            "overstate significance",
            "HAND treats lagoon/sea as terminal drainage; near-shore HAND is height "
            "above the water body rather than above a modelled stream",
            "a positive result earns the right to model forward, it does not identify "
            "which human action caused any individual flood",
        ],
        "generated_at": utc_now(),
    }

    out = {"meta": meta, "results": results, "secondary_low_land": secondary,
           "points": point_table}
    (EVENTS / "terrain_check.json").write_text(json.dumps(out, indent=1))

    sites_doc = {
        "meta": {
            "task": "24b-terrain-controls (drainage sites)",
            "note": ("same terrain metrics at each site's centroid, radius from "
                     "its location_confidence; control_percentile = percentile "
                     "among the builtup_only design's control windows, "
                     "percentile_local = percentile among the 'local' design's "
                     "1-3 km neighbourhood control windows (mixed radii), both "
                     "for that DEM"),
            "seed": SEED,
            "generated_at": utc_now(),
            "sources": meta["sources"],
        },
        "sites": sites_out,
    }
    (EVENTS / "drainage_sites_terrain.json").write_text(json.dumps(sites_doc, indent=1))

    # ---- summary table ----
    log("\n=== summary: median difference = points - controls, per design; "
        "diff/2m = difference in units of the ~2 m DEM vertical error; "
        "negative HAND/TPI/elevation and positive dep-share/accumulation "
        "favour the terrain hypothesis ===")
    hdr = (f"{'dem':<8}{'design':<15}{'subset':<24}{'metric':<16}{'role':<12}"
           f"{'n':>4}{'point':>10}{'ctrl':>10}{'diff':>9}{'diff/2m':>9}"
           f"{'p':>8}{'Holm p':>8}{'sig':>4}")
    log(hdr)
    for d in dems:
        for design in DESIGNS:
            for s in ("all", "precise_street_point", "far_from_water_gt2km"):
                for metric in ALL_METRICS:
                    r = results[d][design][s][metric]
                    if not r.get("n_points"):
                        continue
                    pv_p = (r.get("permutation") or {}).get("p_two_sided")
                    hp = r.get("holm_p")
                    diff = r.get("median_matched_difference")
                    d2 = r.get("diff_over_2m")
                    d2s = f"{d2:+.2f}" if d2 is not None else "-"
                    ps = f"{pv_p:.4f}" if pv_p is not None else "-"
                    hs = f"{hp:.4f}" if hp is not None else "-"
                    if r.get("role") == "primary":
                        sig = ("*" if (hp is not None and hp < ALPHA
                                       and np.sign(diff) == DIRECTION[metric])
                               else " ")
                    else:
                        sig = ("~" if (pv_p is not None and pv_p < ALPHA
                                       and np.sign(diff) == DIRECTION.get(metric, 1))
                               else " ")
                    log(f"{d:<8}{design:<15}{s:<24}{metric:<16}{r['role']:<12}"
                        f"{r['n_points']:>4}"
                        f"{r['median_point']:>10.3f}{r['median_control']:>10.3f}"
                        f"{diff:>9.3f}{d2s:>9}{ps:>8}{hs:>8}{sig:>4}")
    log("(sig: * = primary metric significant after Holm (p < 0.05) in the "
        "predicted direction; ~ = descriptive/sensitivity metric significant "
        "at raw p < 0.05)")
    log("\n--- secondary check (builtup_only controls): is it just 'most of Lagos is low'? ---")
    for d in dems:
        s = secondary[d]
        log(f"{d}: land with HAND<2 m {s['aoi_land_share_hand_lt_2m']*100:.1f}% | "
            f"points {s['points_share_hand_lt_2m']*100:.1f}% | "
            f"controls {s['controls_share_hand_lt_2m']*100:.1f}% | "
            f"land in depression(>=0.5m) {s['aoi_land_share_depression_ge_050']*100:.1f}% | "
            f"points {s['points_share_in_depression']*100:.1f}%")

    # ---- verdict lines per design (rule fixed before results) ----
    label = {"hand_min": "min HAND", "dep_share_050": "depression share",
             "acc_log10_max": "flow accumulation", "tpi_min": "TPI",
             "elev_min": "min elevation"}
    lines = ["per-design verdicts (rule fixed before results; "
             "meta.verdict_rule in events/terrain_check.json):"]
    for design in DESIGNS:
        for d in dems:
            word, sig_all, sig_far = verdicts[(d, design)]
            tag = "  <- DECIDES" if (design == "local" and d == deciding_dem) else ""
            extra = ""
            if sig_all:
                extra += f" [all: {', '.join(sig_all)}"
                if sig_far:
                    extra += f"; >2 km: {', '.join(sig_far)}"
                extra += "]"
            lines.append(f"  {design:<14} {'FABDEM' if d == 'fabdem' else 'GLO-30'}: "
                         f"{word}{tag} - {len(sig_all)}/4 primary metrics significant "
                         f"after Holm in the all-points subset, {len(sig_far)}/4 in the "
                         f">2 km subset{extra}")
    log("\n".join(lines))

    # ---- plain-language verdict (printed + verdict.txt) ----
    dl = deciding_dem
    word, sig_all, sig_far = verdicts[(dl, "local")]
    r_all = results[dl]["local"]["all"]
    sent = []
    if sig_all:
        pretty = ", ".join(
            f"{label[m]} (Holm p={r_all[m]['holm_p']:.3f}, "
            f"diff {r_all[m]['median_matched_difference']:+.3f})" for m in sig_all)
        sent.append(f"Verdict: {verdict_word} (decided by the 'local' design on "
                    f"{'FABDEM' if dl == 'fabdem' else 'GLO-30'}). Asked directly - within "
                    f"its own 1-3 km neighbourhood, is the flooded spot lower or wetter "
                    f"than equally built-up places - {len(sig_all)} of the 4 primary "
                    f"metrics are significant after Holm correction: {pretty}.")
    else:
        sent.append(f"Verdict: {verdict_word} (decided by the 'local' design on "
                    f"{'FABDEM' if dl == 'fabdem' else 'GLO-30'}). Asked directly - within "
                    f"its own 1-3 km neighbourhood, is the flooded spot lower or wetter "
                    f"than equally built-up places - none of the 4 primary metrics "
                    f"separate flooded spots from their neighbours after Holm "
                    f"correction.")
    hm, tm = r_all["hand_min"], r_all["tpi_min"]
    sent.append(f"In DEM terms the neighbourhood gaps are small: min HAND differs by "
                f"{hm['median_matched_difference']:+.2f} m and min TPI by "
                f"{tm['median_matched_difference']:+.2f} m - only {hm['diff_over_2m']:+.2f} "
                f"and {tm['diff_over_2m']:+.2f} times the ~2 m DEM vertical error - while "
                f"depression share is "
                f"{r_all['dep_share_050']['median_matched_difference']:+.3f} and flow "
                f"accumulation "
                f"{r_all['acc_log10_max']['median_matched_difference']:+.2f} log10 cells "
                f"higher; elevation is no longer a primary metric because AOI-wide "
                f"elevation mostly separates the low coastal city from the "
                f"Ogun/Epe/Badagry hinterland rather than local lows.")
    comp = "; ".join(f"{design} {verdicts[(dl, design)][0]} "
                     f"({len(verdicts[(dl, design)][1])}/4 significant)"
                     for design in DESIGNS)
    sent.append(f"Design comparison on {'FABDEM' if dl == 'fabdem' else 'GLO-30'}: "
                f"{comp} - so the Task 24 'pass' {'survives' if verdict_word == 'pass' else 'does not survive'} "
                f"controls that also match distance to water and the point's own "
                f"neighbourhood.")
    far_r = results[dl]["local"]["far_from_water_gt2km"]
    n_far = far_r[PRIMARY_METRICS[0]].get("n_points", 0)
    sent.append(f"The >2 km-from-water subset (n={n_far}) has {len(sig_far)} of those "
                f"significant after Holm, so tide "
                f"{'cannot be the whole explanation' if sig_far else 'remains a possible explanation'}; "
                f"every per-design verdict is recorded in meta.verdicts.")
    if "fabdem" not in dems:
        sent.append("FABDEM (bare earth) stayed unavailable - data.bris refused every "
                    "request and no verified mirror could be used - so this is the "
                    "GLO-30 DSM, which still includes buildings.")
    elif mirror_used:
        other = "glo30" if dl == "fabdem" else "fabdem"
        tail = ""
        if other in dems:
            agree = verdicts[(other, "local")][0] == word
            tail = ("; the GLO-30 comparison agrees on the local-design verdict "
                    f"({verdicts[(other, 'local')][0]})" if agree else
                    f"; the GLO-30 comparison disagrees "
                    f"(its local-design verdict is {verdicts[(other, 'local')][0]})")
        sent.append("FABDEM V1-2 (bare earth) came from the verified Hugging Face "
                    "mirror links-ads/fabdem-v12 after data.bris refused every request"
                    + tail + ".")
    else:
        sent.append("FABDEM V1-2 (bare earth) came from data.bris this run.")
    log("\n".join(sent))
    (TERRAIN_DIR / "verdict.txt").write_text(
        "\n".join([f"task 24b terrain check (fairer controls) - verdict: {verdict_word} "
                   f"(decided by the 'local' design on "
                   f"{'FABDEM' if dl == 'fabdem' else 'GLO-30'})"] + lines + [""] + sent) + "\n")
    log(f"[analyze] done in {time.time()-t0:.0f}s")

    if cleanup:
        import subprocess
        n_before = sum(1 for f in INTER.iterdir() if f.is_file())
        subprocess.run(["find", str(INTER), "-type", "f", "-delete"], check=True)
        log(f"[cleanup] deleted {n_before} intermediate files under {INTER} "
            f"(clipped DEM tiles kept under {CACHE_DEM})")


def lonlat_dist_water(p):
    """Distance (m) from an evidence point to the rasterized water, via the
    shared distance raster (analyzed points are inside the grid)."""
    global _WATER_DIST_CACHE
    if _WATER_DIST_CACHE is None:
        _WATER_DIST_CACHE = np.load(INTER / "water_dist.npy", mmap_mode="r")
    affine, shape = _GRID_CACHE
    x, y = TR_4326_UTM.transform(p["lon"], p["lat"])
    inv = ~affine
    col, row = inv * (x, y)
    row, col = int(row), int(col)
    if 0 <= row < shape[0] and 0 <= col < shape[1]:
        return float(_WATER_DIST_CACHE[row, col])
    return 1e9


_GRID_CACHE = None
_WATER_DIST_CACHE = None


def stage_analyze_wrapper(cleanup=True):
    global _GRID_CACHE
    _GRID_CACHE = utm_grid()
    stage_analyze(cleanup)


# ---------------------------------------------------------------------------

def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("stage", choices=("fetch", "hydro", "analyze", "all"))
    ap.add_argument("dem", nargs="?", default=None,
                    help="dem name for the hydro stage: fabdem | glo30")
    ap.add_argument("--fabdem-attempts", type=int, default=2)
    ap.add_argument("--fabdem-wait", type=int, default=60)
    ap.add_argument("--keep-intermediates", action="store_true")
    args = ap.parse_args()

    if args.stage in ("fetch", "all"):
        log("[fetch] GLO-30 ...")
        fetch_glo30()
        log("[fetch] FABDEM V1-2 (data.bris retry) ...")
        ok = fetch_fabdem(args.fabdem_attempts, args.fabdem_wait)
        if not ok:
            log("[fetch] data.bris refused - trying the verified Hugging Face "
                "mirror links-ads/fabdem-v12 (per-tile COGs) ...")
            ok = fetch_fabdem_mirror()
        if not ok:
            log("[fetch] FABDEM UNAVAILABLE - continuing with GLO-30 only "
                "(results will say so prominently)")
    if args.stage in ("hydro", "all"):
        if args.dem:
            targets = [args.dem]
        else:
            targets = [n for n in ("fabdem", "glo30")
                       if (CACHE_DEM / f"{n}_aoi.tif").exists()]
        if not targets:
            raise SystemExit("no DEMs fetched yet")
        for d in targets:
            stage_hydro(d)
    if args.stage in ("analyze", "all"):
        stage_analyze_wrapper(cleanup=not args.keep_intermediates)


if __name__ == "__main__":
    main()
