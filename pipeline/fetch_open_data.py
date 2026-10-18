#!/usr/bin/env python3
"""Fetch open-data inputs for a FloodTrace event package.

Reads events/<id>/event.json and writes tide, rainfall reanalysis,
satellite catalogue hits, and OSM drainage into the same folder.
Stdlib only: no API keys, one request at a time.
"""

from __future__ import annotations

import json
import re
import ssl
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

USER_AGENT = "FloodTrace/0.1 (research)"
MARINE_API = "https://marine-api.open-meteo.com/v1/marine"
ARCHIVE_API = "https://archive-api.open-meteo.com/v1/archive"
CATALOGUE_API = "https://catalogue.dataspace.copernicus.eu/odata/v1/Products"
OVERPASS_API = "https://overpass-api.de/api/interpreter"
PAGE_SIZE = 100
RETRIES = 3

LICENCE_OPEN_METEO = "CC BY 4.0"
LICENCE_COPERNICUS = "free/open"
LICENCE_OSM = "ODbL"

# python.org macOS builds often have no CA file until certificates are
# installed; load a system bundle so HTTPS works with stdlib only.
def _ssl_context() -> ssl.SSLContext:
    paths = ssl.get_default_verify_paths()
    candidates = (
        paths.cafile,
        paths.openssl_cafile,
        "/etc/ssl/cert.pem",
        "/opt/homebrew/etc/openssl@3/cert.pem",
    )
    for path in candidates:
        if path and Path(path).is_file():
            return ssl.create_default_context(cafile=path)
    return ssl.create_default_context()


SSL_CONTEXT = _ssl_context()


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace(
        "+00:00", "Z"
    )


def parse_iso(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def iso_z(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def to_utc_and_local(value: str, tz: ZoneInfo) -> tuple[str, str]:
    dt = parse_iso(value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    utc = dt.astimezone(timezone.utc).replace(microsecond=0)
    local = dt.astimezone(tz).replace(microsecond=0)
    return (
        utc.isoformat().replace("+00:00", "Z"),
        local.isoformat(),
    )


def http_get_json(
    url: str,
    *,
    data: bytes | None = None,
    timeout: int = 90,
) -> Any:
    """GET or POST JSON. Retry 3x with exponential backoff on 429/5xx."""
    last_error: Exception | None = None
    for attempt in range(RETRIES):
        request = Request(url, data=data, headers={"User-Agent": USER_AGENT})
        try:
            with urlopen(request, timeout=timeout, context=SSL_CONTEXT) as response:
                body = response.read()
            return json.loads(body.decode("utf-8"))
        except HTTPError as exc:
            last_error = exc
            retryable = exc.code == 429 or exc.code >= 500
            if not retryable or attempt == RETRIES - 1:
                raise
        except (URLError, TimeoutError, json.JSONDecodeError) as exc:
            last_error = exc
            if attempt == RETRIES - 1:
                raise
        time.sleep(2**attempt)
    raise last_error or RuntimeError("request failed")


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def bbox_polygon_wkt(bbox: list[float]) -> str:
    west, south, east, north = bbox
    return (
        f"POLYGON(({west} {south},{east} {south},"
        f"{east} {north},{west} {north},{west} {south}))"
    )


def attr_lookup(product: dict[str, Any], *names: str) -> Any:
    wanted = {name.lower() for name in names}
    for item in product.get("Attributes") or []:
        name = str(item.get("Name") or "").lower()
        if name in wanted:
            return item.get("Value")
    return None


def parse_relative_orbit(name: str, product: dict[str, Any]) -> int | None:
    # S2 names encode relative orbit as _R122_; do not use absolute orbitNumber.
    match = re.search(r"_R(\d{3})_", name)
    if match:
        return int(match.group(1))
    raw = attr_lookup(
        product,
        "relativeOrbitNumber",
        "relOrbit",
        "relorbit",
    )
    if raw is not None and str(raw).strip() != "":
        try:
            return int(float(raw))
        except (TypeError, ValueError):
            return None
    return None


def fetch_tide(event: dict[str, Any], tz: ZoneInfo) -> dict[str, Any]:
    lon, lat = event["aoi"]["points"]["offshore_tide"]
    start = parse_iso(event["window"]["start"]).astimezone(tz).date().isoformat()
    end = parse_iso(event["window"]["end"]).astimezone(tz).date().isoformat()
    query = urlencode(
        {
            "latitude": lat,
            "longitude": lon,
            "hourly": "sea_level_height_msl",
            "start_date": start,
            "end_date": end,
            "timezone": event["timezone"],
        }
    )
    url = f"{MARINE_API}?{query}"
    payload = http_get_json(url)
    hourly = payload.get("hourly") or {}
    times = hourly.get("time") or []
    payload["meta"] = {
        "source_url": url,
        "retrieved_at": utc_now_iso(),
        "units": payload.get("hourly_units")
        or {"sea_level_height_msl": "m"},
        "licence": LICENCE_OPEN_METEO,
        "point": "offshore_tide",
        "coordinates": {"longitude": lon, "latitude": lat},
        "record_count": len(times),
    }
    return payload


def fetch_rainfall(event: dict[str, Any], tz: ZoneInfo) -> dict[str, Any]:
    start = parse_iso(event["window"]["start"]).astimezone(tz).date().isoformat()
    end = parse_iso(event["window"]["end"]).astimezone(tz).date().isoformat()
    points: dict[str, Any] = {}
    source_urls: list[str] = []
    for name, coords in event["aoi"]["points"].items():
        if name == "offshore_tide":
            continue
        lon, lat = coords
        query = urlencode(
            {
                "latitude": lat,
                "longitude": lon,
                "hourly": "precipitation",
                "start_date": start,
                "end_date": end,
                "timezone": event["timezone"],
            }
        )
        url = f"{ARCHIVE_API}?{query}"
        source_urls.append(url)
        payload = http_get_json(url)
        hourly = payload.get("hourly") or {}
        points[name] = {
            "longitude": lon,
            "latitude": lat,
            "hourly": hourly,
            "hourly_units": payload.get("hourly_units")
            or {"precipitation": "mm"},
        }
    hour_count = 0
    if points:
        first = next(iter(points.values()))
        hour_count = len((first.get("hourly") or {}).get("time") or [])
    return {
        "product": "ERA5 reanalysis via Open-Meteo",
        "note": (
            "smooths convective bursts; context only, not event intensity"
        ),
        "meta": {
            "source_url": source_urls,
            "retrieved_at": utc_now_iso(),
            "units": {"precipitation": "mm"},
            "licence": LICENCE_OPEN_METEO,
            "point_count": len(points),
            "hours_per_point": hour_count,
        },
        "points": points,
    }


def catalogue_page(filter_expr: str, skip: int) -> tuple[str, dict[str, Any]]:
    query = (
        f"$filter={quote(filter_expr)}"
        f"&$expand=Attributes"
        f"&$orderby=ContentDate/Start"
        f"&$top={PAGE_SIZE}"
        f"&$skip={skip}"
    )
    url = f"{CATALOGUE_API}?{query}"
    return url, http_get_json(url, timeout=120)


def fetch_catalogue_collection(
    collection: str,
    name_contains: str,
    polygon: str,
    start_z: str,
    end_z: str,
) -> tuple[list[str], list[dict[str, Any]]]:
    filter_expr = (
        f"Collection/Name eq '{collection}' and contains(Name,'{name_contains}')"
        f" and OData.CSC.Intersects(area=geography'SRID=4326;{polygon}')"
        f" and ContentDate/Start ge {start_z}"
        f" and ContentDate/Start le {end_z}"
    )
    skip = 0
    urls: list[str] = []
    products: list[dict[str, Any]] = []
    while True:
        url, payload = catalogue_page(filter_expr, skip)
        urls.append(url)
        page = payload.get("value") or []
        products.extend(page)
        if len(page) < PAGE_SIZE:
            break
        skip += PAGE_SIZE
    return urls, products


def record_from_product(
    product: dict[str, Any],
    tz: ZoneInfo,
) -> dict[str, Any] | None:
    name = product.get("Name") or ""
    if name.endswith("_COG.SAFE"):
        return None
    start_raw = (product.get("ContentDate") or {}).get("Start") or ""
    utc, local = to_utc_and_local(start_raw, tz) if start_raw else (None, None)
    cloud = attr_lookup(product, "cloudCover", "CloudCover")
    if cloud is not None:
        try:
            cloud = float(cloud)
        except (TypeError, ValueError):
            pass
    platform = name.split("_", 1)[0] if name else None
    record: dict[str, Any] = {
        "name": name,
        "acquisition_start_utc": utc,
        "acquisition_start_local": local,
        "platform": platform,
        "relative_orbit": parse_relative_orbit(name, product),
    }
    if "MSIL2A" in name or "L2A" in name:
        record["cloud_cover"] = cloud
        record["collection"] = "SENTINEL-2"
    else:
        record["collection"] = "SENTINEL-1"
    return record


def fetch_satellite_passes(
    event: dict[str, Any],
    tz: ZoneInfo,
) -> dict[str, Any]:
    window_start = parse_iso(event["window"]["start"])
    window_end = parse_iso(event["window"]["end"])
    start_z = iso_z(window_start - timedelta(days=14))
    end_z = iso_z(window_end + timedelta(days=14))
    polygon = bbox_polygon_wkt(event["aoi"]["bbox"])
    urls_s1, raw_s1 = fetch_catalogue_collection(
        "SENTINEL-1", "GRDH", polygon, start_z, end_z
    )
    urls_s2, raw_s2 = fetch_catalogue_collection(
        "SENTINEL-2", "L2A", polygon, start_z, end_z
    )
    products: list[dict[str, Any]] = []
    for raw in raw_s1 + raw_s2:
        record = record_from_product(raw, tz)
        if record is not None:
            products.append(record)
    products.sort(key=lambda item: item.get("acquisition_start_utc") or "")
    return {
        "meta": {
            "source_url": urls_s1 + urls_s2,
            "retrieved_at": utc_now_iso(),
            "units": {"cloud_cover": "percent"},
            "licence": LICENCE_COPERNICUS,
            "window_extended": {"start": start_z, "end": end_z},
            "record_count": len(products),
        },
        "products": products,
    }


def overpass_element_to_feature(element: dict[str, Any]) -> dict[str, Any] | None:
    geom = element.get("geometry") or []
    if len(geom) < 2:
        return None
    coords = [[pt["lon"], pt["lat"]] for pt in geom if "lon" in pt and "lat" in pt]
    if len(coords) < 2:
        return None
    tags = element.get("tags") or {}
    closed = coords[0] == coords[-1] and len(coords) >= 4
    is_water_body = tags.get("natural") == "water"
    if closed and is_water_body:
        geometry = {"type": "Polygon", "coordinates": [coords]}
    else:
        geometry = {"type": "LineString", "coordinates": coords}
    return {
        "type": "Feature",
        "properties": {
            "waterway": tags.get("waterway"),
            "name": tags.get("name"),
            "osm_id": element.get("id"),
        },
        "geometry": geometry,
    }


def fetch_drainage(event: dict[str, Any]) -> dict[str, Any]:
    west, south, east, north = event["aoi"]["bbox"]
    query = (
        f"[out:json][timeout:180];\n"
        f"(\n"
        f'  way["waterway"~"canal|drain|ditch|stream|river"]'
        f"({south},{west},{north},{east});\n"
        f'  way["natural"="water"]["water"~"lagoon|canal"]'
        f"({south},{west},{north},{east});\n"
        f");\n"
        f"out geom;\n"
    )
    body = urlencode({"data": query}).encode("utf-8")
    url = OVERPASS_API
    payload = http_get_json(url, data=body, timeout=200)
    features: list[dict[str, Any]] = []
    for element in payload.get("elements") or []:
        if element.get("type") != "way":
            continue
        feature = overpass_element_to_feature(element)
        if feature is not None:
            features.append(feature)
    return {
        "type": "FeatureCollection",
        "meta": {
            "source_url": url,
            "query": query,
            "retrieved_at": utc_now_iso(),
            "units": {"coordinates": "EPSG:4326 lon,lat"},
            "licence": LICENCE_OSM,
            "record_count": len(features),
        },
        "features": features,
    }


def run(event_dir: Path) -> str:
    event_path = event_dir / "event.json"
    if not event_path.is_file():
        raise SystemExit(f"missing {event_path}")
    event = json.loads(event_path.read_text(encoding="utf-8"))
    tz = ZoneInfo(event["timezone"])
    written: list[tuple[str, int]] = []
    failures: list[str] = []

    jobs = (
        ("tide.json", lambda: fetch_tide(event, tz), "hourly"),
        ("rainfall_reanalysis.json", lambda: fetch_rainfall(event, tz), "points"),
        ("satellite_passes.json", lambda: fetch_satellite_passes(event, tz), "products"),
        ("drainage_osm.geojson", lambda: fetch_drainage(event), "features"),
    )

    for filename, fetcher, count_key in jobs:
        try:
            payload = fetcher()
            write_json(event_dir / filename, payload)
            if count_key == "hourly":
                count = len((payload.get("hourly") or {}).get("time") or [])
            else:
                count = len(payload.get(count_key) or [])
            written.append((filename, count))
        except Exception as exc:
            failures.append(f"{filename}: {exc}")

    lines = [
        "FloodTrace open-data fetch",
        f"event: {event.get('id', event_dir.name)}",
        f"dir: {event_dir}",
    ]
    for filename, count in written:
        lines.append(f"wrote {filename} ({count} records)")
    if failures:
        lines.append("failures:")
        lines.extend(f"  {item}" for item in failures)
    else:
        lines.append("failures: none")
    summary = "\n".join(lines)
    print(summary)
    return summary


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit(
            "usage: python3 pipeline/fetch_open_data.py events/<event-id>"
        )
    run(Path(sys.argv[1]))


if __name__ == "__main__":
    main()
