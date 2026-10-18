#!/usr/bin/env python3
"""Sentinel-1 RTC flood map for a FloodTrace event package.

Reads event.json["sar"] item ids from Planetary Computer, windows VV/VH
to the AOI, classifies pre/during/post change, writes sar/ outputs.
"""

from __future__ import annotations

import json
import math
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Patch
import numpy as np
import planetary_computer
import pystac_client
import rasterio
from rasterio.errors import RasterioIOError
from rasterio.crs import CRS
from rasterio.enums import Resampling
from rasterio.env import Env
from rasterio.features import geometry_mask, shapes
from rasterio.transform import from_origin
from rasterio.vrt import WarpedVRT
from rasterio.warp import transform as transform_xy
from rasterio.warp import transform_bounds, transform_geom
from scipy.ndimage import median_filter
from shapely.geometry import Point, mapping, shape
from shapely.ops import unary_union

# Classification thresholds (VV dB unless noted). Recorded in stats.json.
WATER_DB = -16.0
DARKENING_DB = -3.0
WETTING_BRIGHTEN_DB = 3.0
WETTING_PRE_MIN_DB = -8.0
RAIN_BRIGHTEN_DB = 4.0
RAIN_SMOOTH = 9
SPECKLE_SIZE = 5
RESOLUTION_M = 20.0
TARGET_EPSG = 32631
MIN_POLYGON_HA = 0.5
MIN_RAIN_HA = 5.0
SIMPLIFY_M = 20.0
BUFFER_M = 2000.0
PREVIEW_MAX_PX = 2000

CLASS_NONE = 0
CLASS_PERMANENT = 1
CLASS_OPEN_FLOOD = 2
CLASS_RECEDED = 3
CLASS_WETTING = 4
CLASS_RAIN = 5
CLASS_NODATA = 255

CLASS_NAMES = {
    CLASS_NONE: "none",
    CLASS_PERMANENT: "permanent_water",
    CLASS_OPEN_FLOOD: "open_flood",
    CLASS_RECEDED: "receded",
    CLASS_WETTING: "surface_wetting",
    CLASS_RAIN: "rain_cell_on_water",
    CLASS_NODATA: "no_data",
}
CLASS_CONFIDENCE = {
    CLASS_OPEN_FLOOD: "moderate",
    CLASS_RECEDED: "moderate",
    CLASS_WETTING: "low",
    CLASS_RAIN: "moderate",
}
CLASS_COLORS = {
    CLASS_NONE: "#111111",
    CLASS_PERMANENT: "#1d4ed8",
    CLASS_OPEN_FLOOD: "#dc2626",
    CLASS_RECEDED: "#f59e0b",
    CLASS_WETTING: "#4b5563",
    CLASS_RAIN: "#22d3ee",
    CLASS_NODATA: "#6b7280",
}

STAC_API = "https://planetarycomputer.microsoft.com/api/stac/v1"
PIXEL_M2 = RESOLUTION_M * RESOLUTION_M


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace(
        "+00:00", "Z"
    )


def snap_grid(bbox_4326: list[float]) -> dict:
    """Common 20 m grid in UTM 31N covering the AOI bbox."""
    west, south, east, north = bbox_4326
    left, bottom, right, top = transform_bounds(
        "EPSG:4326", f"EPSG:{TARGET_EPSG}", west, south, east, north
    )
    left = math.floor(left / RESOLUTION_M) * RESOLUTION_M
    bottom = math.floor(bottom / RESOLUTION_M) * RESOLUTION_M
    right = math.ceil(right / RESOLUTION_M) * RESOLUTION_M
    top = math.ceil(top / RESOLUTION_M) * RESOLUTION_M
    width = int(round((right - left) / RESOLUTION_M))
    height = int(round((top - bottom) / RESOLUTION_M))
    transform = from_origin(left, top, RESOLUTION_M, RESOLUTION_M)
    return {
        "crs": CRS.from_epsg(TARGET_EPSG),
        "transform": transform,
        "width": width,
        "height": height,
        "bounds": (left, bottom, right, top),
    }


def linear_to_db(arr: np.ndarray, nodata) -> np.ndarray:
    data = arr.astype(np.float32, copy=False)
    invalid = ~np.isfinite(data) | (data <= 0)
    if nodata is not None:
        invalid |= data == np.float32(nodata)
    out = np.full(data.shape, np.nan, dtype=np.float32)
    np.log10(data, out=out, where=~invalid)
    out[~invalid] *= 10.0
    out[invalid] = np.nan
    return out


def speckle_median(db: np.ndarray, size: int = SPECKLE_SIZE) -> np.ndarray:
    valid = np.isfinite(db)
    filled = np.where(valid, db, 0.0)
    filtered = median_filter(filled, size=size, mode="nearest")
    return np.where(valid, filtered, np.nan).astype(np.float32)


def read_polarizations(item, grid: dict) -> dict[str, np.ndarray]:
    """Windowed VRT read of VV and VH onto the shared grid, then dB + speckle."""
    out: dict[str, np.ndarray] = {}
    for pol in ("vv", "vh"):
        if pol not in item.assets:
            raise RuntimeError(f"{item.id} missing asset {pol}")
        href = item.assets[pol].href
        nodata = None
        extra = item.assets[pol].extra_fields or {}
        bands = extra.get("raster:bands") or []
        if bands and "nodata" in bands[0]:
            nodata = bands[0]["nodata"]
        raw = None
        last_error: Exception | None = None
        for attempt in range(3):
            try:
                with rasterio.open(href) as src:
                    src_nodata = nodata if nodata is not None else src.nodata
                    with WarpedVRT(
                        src,
                        crs=grid["crs"],
                        transform=grid["transform"],
                        width=grid["width"],
                        height=grid["height"],
                        resampling=Resampling.average,
                        src_nodata=src_nodata,
                        nodata=src_nodata,
                    ) as vrt:
                        raw = vrt.read(1)
                nodata = src_nodata
                break
            except (RasterioIOError, OSError) as exc:
                last_error = exc
                print(f"  retry {attempt + 1}/3 {pol}: {exc}", flush=True)
                time.sleep(2 ** attempt)
        if raw is None:
            raise last_error or RuntimeError(f"failed to read {pol}")
        db = speckle_median(linear_to_db(raw, nodata))
        out[pol] = db
        print(f"  {item.id[:24]}… {pol}: "
              f"{np.isfinite(db).sum():,} valid px", flush=True)
    return out


def classify(pre_vv: np.ndarray, during_vv: np.ndarray, post_vv: np.ndarray) -> np.ndarray:
    during_ok = np.isfinite(during_vv)
    pre_ok = np.isfinite(pre_vv)
    post_ok = np.isfinite(post_vv)
    delta = during_vv - pre_vv
    classes = np.zeros(pre_vv.shape, dtype=np.uint8)

    # Swath edge: west of the AOI is outside the during scene.
    classes[~during_ok] = CLASS_NODATA

    permanent = during_ok & pre_ok & post_ok & (pre_vv < WATER_DB) & (
        post_vv < WATER_DB
    )
    rain = permanent & (delta > RAIN_BRIGHTEN_DB)
    rain = median_filter(rain.astype(np.uint8), size=RAIN_SMOOTH, mode="nearest") == 1

    open_flood = (
        during_ok
        & pre_ok
        & (during_vv < WATER_DB)
        & (delta < DARKENING_DB)
        & (pre_vv >= WATER_DB)
    )
    receded = open_flood & post_ok & (post_vv >= WATER_DB)
    wetting = (
        during_ok
        & pre_ok
        & (delta > WETTING_BRIGHTEN_DB)
        & (pre_vv > WETTING_PRE_MIN_DB)
        & ~permanent
        & ~open_flood
    )

    classes[permanent] = CLASS_PERMANENT
    classes[rain] = CLASS_RAIN
    classes[open_flood] = CLASS_OPEN_FLOOD
    classes[receded] = CLASS_RECEDED
    classes[wetting] = CLASS_WETTING
    return classes


def area_km2(mask: np.ndarray) -> float:
    return float(mask.sum()) * PIXEL_M2 / 1_000_000.0


def point_buffer_mask(
    lon: float,
    lat: float,
    grid: dict,
) -> np.ndarray:
    xs, ys = transform_xy("EPSG:4326", grid["crs"], [lon], [lat])
    buf = Point(xs[0], ys[0]).buffer(BUFFER_M)
    return geometry_mask(
        [mapping(buf)],
        out_shape=(grid["height"], grid["width"]),
        transform=grid["transform"],
        invert=True,
        all_touched=True,
    )


def write_cog(path: Path, classes: np.ndarray, grid: dict) -> None:
    colormap = {
        code: tuple(int(CLASS_COLORS[code].lstrip("#")[i : i + 2], 16) for i in (0, 2, 4))
        for code in CLASS_COLORS
    }
    profile = {
        "driver": "COG",
        "dtype": "uint8",
        "count": 1,
        "width": grid["width"],
        "height": grid["height"],
        "crs": grid["crs"],
        "transform": grid["transform"],
        "compress": "deflate",
        "blocksize": 512,
        "overview_resampling": "MODE",
    }
    with rasterio.open(path, "w", **profile) as dst:
        dst.write(classes, 1)
        dst.write_colormap(1, colormap)
        dst.update_tags(
            CLASS_0="none",
            CLASS_1="permanent_water",
            CLASS_2="open_flood",
            CLASS_3="receded",
            CLASS_4="surface_wetting",
            CLASS_5="rain_cell_on_water",
            CLASS_255="no_data",
            CRS=f"EPSG:{TARGET_EPSG}",
        )


def polygonize(
    classes: np.ndarray,
    grid: dict,
    class_ids: tuple[int, ...],
    min_ha: float,
    extra_props: dict | None = None,
) -> dict:
    features = []
    skipped_small = 0
    extra_props = extra_props or {}
    for class_id in class_ids:
        mask = classes == class_id
        if not mask.any():
            continue
        geoms = [
            shape(geom)
            for geom, value in shapes(
                classes, mask=mask, transform=grid["transform"]
            )
            if int(value) == class_id
        ]
        if not geoms:
            continue
        dissolved = unary_union(geoms)
        simplified = dissolved.simplify(SIMPLIFY_M, preserve_topology=True)
        parts = []
        if simplified.geom_type == "Polygon":
            parts = [simplified]
        elif simplified.geom_type == "MultiPolygon":
            parts = list(simplified.geoms)
        elif simplified.geom_type == "GeometryCollection":
            parts = [g for g in simplified.geoms if g.geom_type == "Polygon"]
        for poly in parts:
            area_ha = poly.area / 10_000.0
            if area_ha < min_ha:
                skipped_small += 1
                continue
            gj = transform_geom(
                grid["crs"], "EPSG:4326", mapping(poly), precision=6
            )
            props = {
                "class": CLASS_NAMES[class_id],
                "class_id": class_id,
                "confidence": CLASS_CONFIDENCE[class_id],
                "area_ha": round(area_ha, 3),
            }
            props.update(extra_props)
            features.append(
                {
                    "type": "Feature",
                    "properties": props,
                    "geometry": gj,
                }
            )
    return {
        "type": "FeatureCollection",
        "crs": {"type": "name", "properties": {"name": "EPSG:4326"}},
        "features": features,
        "skipped_small": skipped_small,
    }


def downsample(arr: np.ndarray, max_px: int) -> np.ndarray:
    height, width = arr.shape
    if width <= max_px:
        return arr
    step = int(math.ceil(width / max_px))
    return arr[::step, ::step]


def save_vv_preview(path: Path, db: np.ndarray, title: str) -> None:
    img = downsample(db, PREVIEW_MAX_PX)
    fig, ax = plt.subplots(figsize=(10, 3.2), dpi=160)
    ax.imshow(img, cmap="gray", vmin=-25, vmax=0, interpolation="nearest")
    ax.set_title(title)
    ax.set_axis_off()
    fig.tight_layout()
    fig.savefig(path, bbox_inches="tight", pad_inches=0.08)
    plt.close(fig)


def save_class_preview(path: Path, classes: np.ndarray) -> None:
    img = downsample(classes, PREVIEW_MAX_PX)
    rgb = np.zeros((*img.shape, 3), dtype=np.uint8)
    for code, hex_color in CLASS_COLORS.items():
        r, g, b = (int(hex_color.lstrip("#")[i : i + 2], 16) for i in (0, 2, 4))
        rgb[img == code] = (r, g, b)
    fig, ax = plt.subplots(figsize=(10, 3.6), dpi=160)
    ax.imshow(rgb, interpolation="nearest")
    ax.set_title("SAR classes")
    ax.set_axis_off()
    legend = [
        Patch(facecolor=CLASS_COLORS[c], edgecolor="white", label=CLASS_NAMES[c])
        for c in CLASS_NAMES
    ]
    ax.legend(
        handles=legend,
        loc="lower center",
        ncol=4,
        bbox_to_anchor=(0.5, -0.22),
        frameon=False,
        fontsize=7,
    )
    fig.tight_layout()
    fig.savefig(path, bbox_inches="tight", pad_inches=0.12)
    plt.close(fig)


def class_areas(classes: np.ndarray, mask: np.ndarray | None = None) -> dict[str, float]:
    region = classes if mask is None else classes[mask]
    return {
        CLASS_NAMES[code]: round(area_km2(region == code), 4)
        for code in CLASS_NAMES
    }


def run(event_dir: Path) -> str:
    event_path = event_dir / "event.json"
    event = json.loads(event_path.read_text(encoding="utf-8"))
    sar = event.get("sar")
    if not sar:
        raise SystemExit("event.json is missing a 'sar' block")
    bbox = event["aoi"]["bbox"]
    out_dir = event_dir / "sar"
    out_dir.mkdir(parents=True, exist_ok=True)

    os_env = Env(
        GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR",
        CPL_VSIL_CURL_USE_HEAD="NO",
        GDAL_HTTP_MAX_RETRY="4",
        GDAL_HTTP_RETRY_DELAY="2",
        GDAL_INGESTED_BYTES_AT_OPEN="32768",
        VSI_CACHE="TRUE",
        VSI_CACHE_SIZE="268435456",
    )

    catalog = pystac_client.Client.open(
        STAC_API,
        modifier=planetary_computer.sign_inplace,
    )
    collection = catalog.get_collection(sar["collection"])
    roles = ("pre", "during", "post")
    items = {role: collection.get_item(sar[role]) for role in roles}
    missing = [role for role, item in items.items() if item is None]
    if missing:
        raise SystemExit(f"STAC items not found: {missing}")

    grid = snap_grid(bbox)
    print(
        f"grid EPSG:{TARGET_EPSG} {grid['width']}x{grid['height']} "
        f"@ {RESOLUTION_M:.0f} m",
        flush=True,
    )

    scenes: dict[str, dict[str, np.ndarray]] = {}
    with os_env:
        for role in roles:
            print(f"reading {role} {items[role].id}", flush=True)
            scenes[role] = read_polarizations(items[role], grid)

    classes = classify(
        scenes["pre"]["vv"], scenes["during"]["vv"], scenes["post"]["vv"]
    )

    classes_path = out_dir / "classes.tif"
    flood_path = out_dir / "flood.geojson"
    wetting_path = out_dir / "wetting.geojson"
    rain_path = out_dir / "rain_cells.geojson"
    stats_path = out_dir / "stats.json"
    preview_pre = out_dir / "preview_pre.png"
    preview_during = out_dir / "preview_during.png"
    preview_classes = out_dir / "preview_classes.png"

    tz = ZoneInfo(event.get("timezone", "Africa/Lagos"))
    during_dt = items["during"].datetime
    if during_dt is None:
        during_dt = datetime.fromisoformat(
            str(items["during"].properties.get("datetime")).replace("Z", "+00:00")
        )
    observed_at = during_dt.astimezone(tz).isoformat()

    write_cog(classes_path, classes, grid)
    flood_fc = polygonize(
        classes, grid, (CLASS_OPEN_FLOOD, CLASS_RECEDED), MIN_POLYGON_HA
    )
    wetting_fc = polygonize(classes, grid, (CLASS_WETTING,), MIN_POLYGON_HA)
    rain_fc = polygonize(
        classes,
        grid,
        (CLASS_RAIN,),
        MIN_RAIN_HA,
        extra_props={"observed_at": observed_at},
    )
    flood_skipped = flood_fc.pop("skipped_small")
    wetting_skipped = wetting_fc.pop("skipped_small")
    rain_skipped = rain_fc.pop("skipped_small")
    flood_path.write_text(json.dumps(flood_fc, indent=2) + "\n", encoding="utf-8")
    wetting_path.write_text(json.dumps(wetting_fc, indent=2) + "\n", encoding="utf-8")
    rain_path.write_text(json.dumps(rain_fc, indent=2) + "\n", encoding="utf-8")

    during_ok = np.isfinite(scenes["during"]["vv"])
    covered_fraction = float(during_ok.mean())
    aoi_areas = class_areas(classes)
    near: dict[str, dict[str, float]] = {}
    for name, coords in event["aoi"]["points"].items():
        lon, lat = coords
        near[name] = class_areas(classes, point_buffer_mask(lon, lat, grid))

    stats = {
        "meta": {
            "source": STAC_API,
            "collection": sar["collection"],
            "licence": (
                "Copernicus Sentinel data, free/open; "
                "processed by Planetary Computer RTC"
            ),
            "retrieved_at": utc_now_iso(),
            "crs": f"EPSG:{TARGET_EPSG}",
            "resolution_m": RESOLUTION_M,
            "grid_width": grid["width"],
            "grid_height": grid["height"],
            "note": (
                "classification uses VV; VH was read and speckle-filtered "
                "but not used in class rules. surface_wetting is wet soil/"
                "surfaces, not flood evidence on its own."
            ),
        },
        "thresholds": {
            "water_db": WATER_DB,
            "darkening_db": DARKENING_DB,
            "wetting_brighten_db": WETTING_BRIGHTEN_DB,
            "wetting_pre_min_db": WETTING_PRE_MIN_DB,
            "rain_brighten_db": RAIN_BRIGHTEN_DB,
            "rain_smooth": RAIN_SMOOTH,
            "speckle_median": SPECKLE_SIZE,
        },
        "coverage": {
            "during_fraction": round(covered_fraction, 4),
            "during_km2": round(area_km2(during_ok), 4),
            "aoi_km2": round(classes.size * PIXEL_M2 / 1_000_000.0, 4),
        },
        "items": {
            role: {
                "id": items[role].id,
                "datetime": items[role].datetime.isoformat()
                if items[role].datetime
                else items[role].properties.get("datetime"),
                "start_datetime": items[role].properties.get("start_datetime"),
                "sat:relative_orbit": items[role].properties.get(
                    "sat:relative_orbit"
                ),
            }
            for role in roles
        },
        "area_km2_aoi": aoi_areas,
        "area_km2_within_2km": near,
        "polygons": {
            "flood": {
                "written": len(flood_fc["features"]),
                "dropped_lt_0_5_ha": flood_skipped,
            },
            "wetting": {
                "written": len(wetting_fc["features"]),
                "dropped_lt_0_5_ha": wetting_skipped,
            },
            "rain_cells": {
                "written": len(rain_fc["features"]),
                "dropped_lt_5_ha": rain_skipped,
            },
        },
    }
    stats_path.write_text(json.dumps(stats, indent=2) + "\n", encoding="utf-8")

    save_vv_preview(preview_pre, scenes["pre"]["vv"], "pre VV (dB)")
    save_vv_preview(preview_during, scenes["during"]["vv"], "during VV (dB)")
    save_class_preview(preview_classes, classes)

    lines = [
        "FloodTrace SAR flood map",
        f"event: {event.get('id', event_dir.name)}",
        f"grid: EPSG:{TARGET_EPSG} {grid['width']}x{grid['height']} @ {RESOLUTION_M:.0f}m",
        f"during coverage: {covered_fraction:.1%} of AOI",
        "areas km² (AOI):",
    ]
    for name, km2 in aoi_areas.items():
        lines.append(f"  {name}: {km2}")
    lines.append("outputs:")
    for path in (
        classes_path,
        flood_path,
        wetting_path,
        rain_path,
        stats_path,
        preview_pre,
        preview_during,
        preview_classes,
    ):
        lines.append(f"  {path} ({path.stat().st_size} bytes)")
    lines.append(
        f"flood polygons: {len(flood_fc['features'])} "
        f"({flood_skipped} < {MIN_POLYGON_HA} ha dropped)"
    )
    lines.append(
        f"wetting polygons: {len(wetting_fc['features'])} "
        f"({wetting_skipped} < {MIN_POLYGON_HA} ha dropped)"
    )
    lines.append(
        f"rain-cell polygons: {len(rain_fc['features'])} "
        f"({rain_skipped} < {MIN_RAIN_HA} ha dropped)"
    )
    lines.append("skipped: none")
    summary = "\n".join(lines)
    print(summary)
    return summary


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit(
            "usage: pipeline/.venv/bin/python pipeline/sar_flood.py events/<id>"
        )
    run(Path(sys.argv[1]))


if __name__ == "__main__":
    main()
