#!/usr/bin/env python3
"""Named OSM features inside the Lagos AOI → events/search_index.json (Task 39).

Queries Overpass once per feature class, caches the raw JSON under
pipeline/cache/osm/, then merges street segments that share a name in the
same neighbourhood. Search itself runs in the browser against this file;
nothing typed in the box is sent anywhere.

Also writes events/osm_facilities.geojson (schools, clinics/hospitals,
markets, bus stations) for Task 41.
"""

from __future__ import annotations

import gzip
import json
import math
import re
import shutil
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

ROOT = Path(__file__).resolve().parents[1]
EVENTS = ROOT / "events"
PUBLIC = ROOT / "public" / "events"
CACHE = Path(__file__).resolve().parent / "cache" / "osm"
OUT_INDEX = EVENTS / "search_index.json"
OUT_FACILITIES = EVENTS / "osm_facilities.geojson"

# west, south, east, north — same AOI as pipeline/geocode.py
BBOX = [2.7, 6.38, 4.35, 6.75]
OVERPASS_URLS = [
    "https://overpass-api.de/api/interpreter",
    "https://lz4.overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
]
USER_AGENT = "FloodTrace/0.1 (research; OSM search index)"
MIN_INTERVAL_S = 10.0
TIMEOUT_S = 180
RETRIES = 6
# Drop kinds in this order if the gzipped index exceeds the budget.
SIZE_BUDGET_GZ = 1.5 * 1024 * 1024
DROP_ORDER = ["worship", "estate", "bridge", "mall"]

PLACE_KINDS = {"suburb", "neighbourhood", "neighborhood", "quarter", "village", "town"}
FACILITY_KINDS = {"school", "hospital", "clinic", "market", "bus_station"}

QUERIES: dict[str, str] = {
    "highways": 'way["highway"]["name"]({bb});',
    "places": 'nwr["place"~"^(suburb|neighbourhood|neighborhood|quarter|village|town)$"]["name"]({bb});',
    "schools": 'nwr["amenity"~"^(school|college|kindergarten|university)$"]["name"]({bb});',
    "health": 'nwr["amenity"~"^(hospital|clinic|doctors)$"]["name"]({bb});',
    "worship": 'nwr["amenity"="place_of_worship"]["name"]({bb});',
    "markets": '(nwr["amenity"="marketplace"]["name"]({bb}); nwr["shop"="supermarket"]["name"]({bb}););',
    "buses": '(nwr["amenity"="bus_station"]["name"]({bb}); nwr["highway"="bus_stop"]["name"]({bb}););',
    "malls": '(nwr["shop"="mall"]["name"]({bb}); nwr["amenity"="mall"]["name"]({bb}););',
    "bridges": '(way["man_made"="bridge"]["name"]({bb}); way["bridge"~"^(yes|viaduct)$"]["name"]["highway"]({bb}););',
    "estates": 'nwr["landuse"="residential"]["name"]({bb});',
}


def haversine_m(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    r = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(min(1.0, math.sqrt(a)))


def norm_name(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (name or "").casefold()).strip()


def overpass_bbox() -> str:
    west, south, east, north = BBOX
    return f"{south},{west},{north},{east}"


_last_request = 0.0


def throttle() -> None:
    global _last_request
    wait = MIN_INTERVAL_S - (time.time() - _last_request)
    if wait > 0:
        time.sleep(wait)
    _last_request = time.time()


def tiles(nx: int = 4, ny: int = 2) -> list[str]:
    west, south, east, north = BBOX
    out = []
    for iy in range(ny):
        s = south + (north - south) * iy / ny
        n = south + (north - south) * (iy + 1) / ny
        for ix in range(nx):
            w = west + (east - west) * ix / nx
            e = west + (east - west) * (ix + 1) / nx
            out.append(f"{s:.5f},{w:.5f},{n:.5f},{e:.5f}")
    return out


def overpass_post(query: str) -> dict[str, Any]:
    last = ""
    headers = {"User-Agent": USER_AGENT, "Content-Type": "text/plain"}
    for attempt in range(RETRIES):
        url = OVERPASS_URLS[attempt % len(OVERPASS_URLS)]
        throttle()
        try:
            resp = requests.post(url, data=query.encode("utf-8"), headers=headers, timeout=TIMEOUT_S + 30)
            if resp.status_code == 200:
                data = resp.json()
                if "elements" in data:
                    return data
                last = f"remark {str(data.get('remark'))[:160]}"
            else:
                last = f"HTTP {resp.status_code} {resp.text[:120]}"
        except (requests.RequestException, ValueError) as exc:
            last = str(exc)[:160]
        sleep = 12 * (attempt + 1)
        print(f"  retry {attempt + 1}/{RETRIES} after {last!r}; sleep {sleep}s")
        time.sleep(sleep)
    raise RuntimeError(f"Overpass failed after {RETRIES} tries ({last})")


def fetch_overpass(name: str, fragment: str, *, tiled: bool = False) -> dict[str, Any]:
    CACHE.mkdir(parents=True, exist_ok=True)
    cache_path = CACHE / f"{name}.json"
    if cache_path.is_file():
        print(f"cache hit {name}")
        return json.loads(cache_path.read_text(encoding="utf-8"))
    bbs = tiles() if tiled else [overpass_bbox()]
    elements: list[dict[str, Any]] = []
    seen: set[tuple[str, int]] = set()
    for i, bb in enumerate(bbs):
        tile_path = CACHE / f"{name}_{i}.json" if tiled else cache_path
        if tile_path.is_file():
            print(f"cache hit {tile_path.name}")
            raw = json.loads(tile_path.read_text(encoding="utf-8"))
        else:
            query = f"[out:json][timeout:{TIMEOUT_S}];({fragment.format(bb=bb)});out tags center;"
            print(f"overpass {name} tile {i + 1}/{len(bbs)} …")
            raw = overpass_post(query)
            tile_path.write_text(json.dumps(raw), encoding="utf-8")
            print(f"  {len(raw.get('elements') or [])} elements")
        for el in raw.get("elements") or []:
            key = (el.get("type"), el.get("id"))
            if key in seen:
                continue
            seen.add(key)
            elements.append(el)
    payload = {"elements": elements}
    cache_path.write_text(json.dumps(payload), encoding="utf-8")
    return payload


def lonlat(el: dict[str, Any]) -> tuple[float, float] | None:
    if "lon" in el and "lat" in el:
        return float(el["lon"]), float(el["lat"])
    c = el.get("center")
    if c and "lon" in c and "lat" in c:
        return float(c["lon"]), float(c["lat"])
    return None


def alt_names(tags: dict[str, str]) -> list[str]:
    seen = {tags.get("name") or ""}
    out: list[str] = []
    for key in ("alt_name", "name:en", "loc_name", "old_name", "short_name"):
        val = tags.get(key)
        if not val:
            continue
        for part in val.split(";"):
            name = part.strip()
            if name and name not in seen:
                seen.add(name)
                out.append(name)
    return out


def kind_of(el: dict[str, Any], query_name: str) -> str | None:
    tags = el.get("tags") or {}
    if query_name == "highways":
        return "street"
    if query_name == "places":
        p = (tags.get("place") or "").casefold()
        return "neighbourhood" if p == "neighborhood" else p if p in PLACE_KINDS else None
    amenity = (tags.get("amenity") or "").casefold()
    shop = (tags.get("shop") or "").casefold()
    highway = (tags.get("highway") or "").casefold()
    if query_name == "schools" or amenity in {"school", "college", "kindergarten", "university"}:
        return "school"
    if amenity == "hospital":
        return "hospital"
    if amenity in {"clinic", "doctors"}:
        return "clinic"
    if query_name == "worship" or amenity == "place_of_worship":
        return "worship"
    if query_name == "markets" or amenity == "marketplace" or shop == "supermarket":
        return "market"
    if amenity == "bus_station" or highway == "bus_stop":
        return "bus_station"
    if query_name == "malls" or shop == "mall" or amenity == "mall":
        return "mall"
    if query_name == "bridges" or tags.get("man_made") == "bridge" or tags.get("bridge") in {"yes", "viaduct"}:
        return "bridge"
    if query_name == "estates" or tags.get("landuse") == "residential":
        return "estate"
    return None


def collect_items() -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for qname, fragment in QUERIES.items():
        try:
            raw = fetch_overpass(qname, fragment, tiled=(qname in {"highways", "estates"}))
        except RuntimeError as err:
            print(f"skip {qname}: {err}")
            continue
        for el in raw.get("elements") or []:
            tags = el.get("tags") or {}
            name = (tags.get("name") or "").strip()
            if not name:
                continue
            pos = lonlat(el)
            if not pos:
                continue
            lon, lat = pos
            if not (BBOX[0] <= lon <= BBOX[2] and BBOX[1] <= lat <= BBOX[3]):
                continue
            kind = kind_of(el, qname)
            if not kind:
                continue
            items.append(
                {
                    "name": name,
                    "alt": alt_names(tags),
                    "kind": kind,
                    "lon": lon,
                    "lat": lat,
                }
            )
    return items


def nearest_area(lon: float, lat: float, areas: list[dict[str, Any]]) -> str | None:
    best: tuple[float, str] | None = None
    for a in areas:
        d = haversine_m(lon, lat, a["lon"], a["lat"])
        if best is None or d < best[0]:
            best = (d, a["name"])
    if best is None or best[0] > 8000:
        return None
    return best[1]


def merge_streets(items: list[dict[str, Any]], areas: list[dict[str, Any]]) -> list[dict[str, Any]]:
    streets = [i for i in items if i["kind"] == "street"]
    others = [i for i in items if i["kind"] != "street"]
    buckets: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for s in streets:
        area = nearest_area(s["lon"], s["lat"], areas) or ""
        buckets[(norm_name(s["name"]), area)].append(s)
    merged: list[dict[str, Any]] = []
    for (_key, area), group in buckets.items():
        # Split groups that are still far apart (same name, same suburb label,
        # but actually two roads). 1.5 km is "same street", not "same name".
        clusters: list[list[dict[str, Any]]] = []
        for s in group:
            placed = False
            for c in clusters:
                if haversine_m(s["lon"], s["lat"], c[0]["lon"], c[0]["lat"]) <= 1500:
                    c.append(s)
                    placed = True
                    break
            if not placed:
                clusters.append([s])
        for c in clusters:
            alts: list[str] = []
            seen = {c[0]["name"]}
            for s in c:
                for a in s["alt"]:
                    if a not in seen:
                        seen.add(a)
                        alts.append(a)
            names = [s["name"] for s in c]
            name = max(set(names), key=names.count)
            merged.append(
                {
                    "name": name,
                    "alt": alts,
                    "kind": "street",
                    "area": area or None,
                    "lon": round(sum(s["lon"] for s in c) / len(c), 6),
                    "lat": round(sum(s["lat"] for s in c) / len(c), 6),
                }
            )
    for o in others:
        area = nearest_area(o["lon"], o["lat"], areas)
        # Dedup identical name+kind+area within 300 m.
        o = {
            "name": o["name"],
            "alt": o["alt"],
            "kind": o["kind"],
            "area": area,
            "lon": round(o["lon"], 6),
            "lat": round(o["lat"], 6),
        }
        merged.append(o)
    return dedup(merged)


def dedup(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    keep: list[dict[str, Any]] = []
    for item in items:
        hit = None
        for i, other in enumerate(keep):
            if other["kind"] != item["kind"]:
                continue
            if norm_name(other["name"]) != norm_name(item["name"]):
                continue
            if (other.get("area") or "") != (item.get("area") or ""):
                continue
            if haversine_m(other["lon"], other["lat"], item["lon"], item["lat"]) <= 300:
                hit = i
                break
        if hit is None:
            keep.append(item)
        else:
            # Prefer the longer alt list; average the point.
            cur = keep[hit]
            alts = list(cur["alt"])
            seen = {cur["name"], *alts}
            for a in item["alt"]:
                if a not in seen:
                    seen.add(a)
                    alts.append(a)
            keep[hit] = {
                **cur,
                "alt": alts,
                "lon": round((cur["lon"] + item["lon"]) / 2, 6),
                "lat": round((cur["lat"] + item["lat"]) / 2, 6),
            }
    return keep


def compact(item: dict[str, Any]) -> dict[str, Any]:
    row: dict[str, Any] = {
        "name": item["name"],
        "kind": item["kind"],
        "area": item.get("area"),
        "lon": item["lon"],
        "lat": item["lat"],
    }
    if item.get("alt"):
        row["alt"] = item["alt"]
    return row


def gzip_size(path: Path) -> int:
    return len(gzip.compress(path.read_bytes(), compresslevel=9))


def drop_kinds(items: list[dict[str, Any]], dropped: list[str]) -> list[dict[str, Any]]:
    remaining = list(items)
    for kind in DROP_ORDER:
        size = len(gzip.compress(json.dumps({"items": [compact(i) for i in remaining]}).encode(), 9))
        if size <= SIZE_BUDGET_GZ:
            break
        remaining = [i for i in remaining if i["kind"] != kind]
        dropped.append(kind)
        print(f"dropped kind {kind} to meet size budget")
    return remaining


def facilities_geojson(items: list[dict[str, Any]]) -> dict[str, Any]:
    feats = []
    for i in items:
        if i["kind"] not in FACILITY_KINDS:
            continue
        feats.append(
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [i["lon"], i["lat"]]},
                "properties": {
                    "name": i["name"],
                    "kind": i["kind"],
                    "area": i.get("area"),
                },
            }
        )
    return {
        "type": "FeatureCollection",
        "features": feats,
        "meta": {
            "licence": "© OpenStreetMap contributors (ODbL)",
            "kinds": sorted(FACILITY_KINDS),
        },
    }


def publish(path: Path) -> None:
    dest = PUBLIC / path.name
    if dest.resolve() == path.resolve():
        return
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, dest)


def main() -> None:
    raw_items = collect_items()
    areas = [i for i in raw_items if i["kind"] in PLACE_KINDS - {"neighborhood"} or i["kind"] in PLACE_KINDS]
    # Prefer denser place kinds as containers.
    rank = {"neighbourhood": 0, "quarter": 1, "suburb": 2, "village": 3, "town": 4}
    areas.sort(key=lambda a: rank.get(a["kind"], 9))
    items = merge_streets(raw_items, [a for a in areas if a["kind"] in {"suburb", "neighbourhood", "quarter", "village", "town"}])
    dropped: list[str] = []
    items = drop_kinds(items, dropped)
    items.sort(key=lambda i: (i["kind"], i["name"]))

    counts: dict[str, int] = defaultdict(int)
    for i in items:
        counts[i["kind"]] += 1

    payload = {
        "meta": {
            "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "licence": "© OpenStreetMap contributors (ODbL)",
            "bbox": BBOX,
            "n": len(items),
            "by_kind": dict(sorted(counts.items())),
            "dropped_kinds": dropped,
            "privacy": "Search runs in the browser against this file. Typed text never leaves the device.",
        },
        "items": [compact(i) for i in items],
    }
    OUT_INDEX.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    publish(OUT_INDEX)
    gz = gzip_size(OUT_INDEX)
    fac = facilities_geojson(items)
    OUT_FACILITIES.write_text(json.dumps(fac, ensure_ascii=False) + "\n", encoding="utf-8")
    publish(OUT_FACILITIES)
    print(f"search index: {len(items)} items, {OUT_INDEX.stat().st_size} bytes, {gz} gzipped ({gz/1024/1024:.2f} MB)")
    print("by kind:", dict(sorted(counts.items())))
    print(f"facilities: {len(fac['features'])}")
    if dropped:
        print("dropped kinds for size:", dropped)
    if gz > SIZE_BUDGET_GZ:
        raise SystemExit(f"gzipped index {gz} exceeds {SIZE_BUDGET_GZ}")


if __name__ == "__main__":
    main()
