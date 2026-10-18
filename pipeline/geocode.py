#!/usr/bin/env python3
"""Nominatim geocoder for FloodTrace event packages (stdlib only).

Prefers place results (suburb, neighbourhood, town, …) over same-named
streets, unless the query itself names a road. Optional LGA hint rejects
hits whose address does not contain that LGA. Caches in
pipeline/cache/geocode.json. Max 1 request/second.
"""

from __future__ import annotations

import json
import re
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

USER_AGENT = "FloodTrace/0.1 (research)"
NOMINATIM = "https://nominatim.openstreetmap.org/search"
MIN_INTERVAL_S = 1.05
DEFAULT_CACHE = Path(__file__).resolve().parent / "cache" / "geocode.json"
LAGOS_BBOX = [2.70, 6.38, 4.35, 6.75]
CACHE_VERSION = 3

ROAD_RE = re.compile(
    r"\b(expressway|road|street|bridge|way|avenue|close|"
    r"crescent|drive|lane|highway|link)\b",
    re.I,
)
PLACE_TYPES = {
    "suburb",
    "neighbourhood",
    "neighborhood",
    "quarter",
    "village",
    "town",
    "city",
    "city_district",
    "hamlet",
    "residential",
    "municipality",
    "island",
}

# Prefer settlements over incidental place nodes (e.g. Lekki Foreshore island).
PLACE_RANK = {
    "city": 10,
    "town": 9,
    "suburb": 8,
    "city_district": 8,
    "municipality": 8,
    "neighbourhood": 7,
    "neighborhood": 7,
    "quarter": 7,
    "village": 6,
    "hamlet": 5,
    "residential": 4,
    "island": 2,
}

# Ambiguous short names → a disambiguated query + expected LGA.
ALIASES: dict[str, dict[str, str]] = {
    "lekki": {
        "query": "Lekki, Eti-Osa, Lagos",
        "lga": "Eti-Osa",
        "confidence": "lga",
    },
}


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
_last_request = 0.0


def names_road(text: str) -> bool:
    return ROAD_RE.search(text or "") is not None


def _norm(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (text or "").casefold()).strip()


def primary_name(query: str) -> str:
    return query.split(",")[0].strip()


def alias_for(query: str) -> dict[str, str] | None:
    return ALIASES.get(_norm(primary_name(query)))


def load_cache(path: Path = DEFAULT_CACHE) -> dict[str, Any]:
    if not path.is_file():
        return {"version": CACHE_VERSION, "results": {}}
    raw = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(raw, dict) and raw.get("version") == CACHE_VERSION:
        raw.setdefault("results", {})
        return raw
    # v1 was a flat query → hit map; drop it so street matches are not reused.
    return {"version": CACHE_VERSION, "results": {}}


def save_cache(cache: dict[str, Any], path: Path = DEFAULT_CACHE) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    cache["version"] = CACHE_VERSION
    cache.setdefault("results", {})
    path.write_text(json.dumps(cache, indent=2) + "\n", encoding="utf-8")


def in_bbox(lon: float, lat: float, bbox: list[float]) -> bool:
    west, south, east, north = bbox
    return west <= lon <= east and south <= lat <= north


def _throttle() -> None:
    global _last_request
    wait = MIN_INTERVAL_S - (time.time() - _last_request)
    if wait > 0:
        time.sleep(wait)
    _last_request = time.time()


def cache_key(query: str, lga: str | None) -> str:
    alias = alias_for(query)
    resolved = alias["query"] if alias else query.strip()
    hint = lga or (alias["lga"] if alias else "")
    return f"{resolved}|lga={hint}"


def nominatim_search(query: str, bbox: list[float]) -> list[dict[str, Any]]:
    west, south, east, north = bbox
    params = {
        "q": query,
        "format": "jsonv2",
        "countrycodes": "ng",
        "viewbox": f"{west},{north},{east},{south}",
        "bounded": "1",
        "limit": "8",
        "addressdetails": "1",
    }
    url = f"{NOMINATIM}?{urllib.parse.urlencode(params)}"
    _throttle()
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=30, context=SSL_CONTEXT) as resp:
        return json.loads(resp.read().decode("utf-8"))


def hit_kind(hit: dict[str, Any]) -> tuple[str, str]:
    category = str(hit.get("category") or hit.get("class") or "").lower()
    addresstype = str(hit.get("addresstype") or "").lower()
    typ = str(hit.get("type") or "").lower()
    return category, addresstype or typ


def is_place_hit(hit: dict[str, Any]) -> bool:
    category, kind = hit_kind(hit)
    if category == "highway":
        return False
    if category == "place":
        return True
    if category == "boundary" and kind in PLACE_TYPES | {"administrative"}:
        return kind in PLACE_TYPES or kind == "administrative"
    return kind in PLACE_TYPES and category != "highway"


def is_highway_hit(hit: dict[str, Any]) -> bool:
    category, _kind = hit_kind(hit)
    return category == "highway"


def address_blob(hit: dict[str, Any]) -> str:
    parts = [str(hit.get("display_name") or "")]
    addr = hit.get("address") or {}
    if isinstance(addr, dict):
        parts.extend(str(v) for v in addr.values())
    return " ".join(parts)


def address_has_lga(hit: dict[str, Any], lga: str) -> bool:
    blob = _norm(address_blob(hit))
    want = _norm(lga)
    if not want:
        return True
    if want in blob:
        return True
    # "Eti-Osa" vs "Eti Osa"; "Ibeju-Lekki" vs "Ibeju Lekki"
    return want.replace(" ", "") in blob.replace(" ", "")


def summarise_hit(hit: dict[str, Any], extra: dict[str, Any] | None = None) -> dict[str, Any]:
    category, kind = hit_kind(hit)
    out = {
        "lon": float(hit["lon"]),
        "lat": float(hit["lat"]),
        "display_name": hit.get("display_name"),
        "osm_type": hit.get("osm_type"),
        "osm_id": hit.get("osm_id"),
        "category": category or hit.get("category"),
        "type": hit.get("type"),
        "addresstype": hit.get("addresstype"),
        "address": hit.get("address"),
    }
    if extra:
        out.update(extra)
    return out


def pick_hit(
    hits: list[dict[str, Any]],
    bbox: list[float],
    query: str,
    lga: str | None,
) -> dict[str, Any] | None:
    want_road = names_road(query)
    best: tuple[int, dict[str, Any]] | None = None
    for hit in hits:
        try:
            lon = float(hit["lon"])
            lat = float(hit["lat"])
        except (KeyError, TypeError, ValueError):
            continue
        if not in_bbox(lon, lat, bbox):
            continue
        if lga and not address_has_lga(hit, lga):
            continue
        if want_road:
            if not (is_highway_hit(hit) or is_place_hit(hit)):
                continue
        elif not is_place_hit(hit):
            continue
        _category, kind = hit_kind(hit)
        rank = PLACE_RANK.get(kind, 1)
        if best is None or rank > best[0]:
            best = (rank, hit)
    if best is None:
        return None
    extra = {}
    alias = alias_for(query)
    if alias:
        extra["confidence"] = alias.get("confidence", "lga")
        extra["alias"] = alias["query"]
    return summarise_hit(best[1], extra)


def geocode(
    query: str,
    bbox: list[float],
    cache: dict[str, Any] | None = None,
    cache_path: Path = DEFAULT_CACHE,
    lga: str | None = None,
) -> dict[str, Any] | None:
    """Return a place (or road, if named) inside bbox, or None."""
    own_cache = cache is None
    if cache is None:
        cache = load_cache(cache_path)
    results = cache.setdefault("results", {})
    alias = alias_for(query)
    search_q = alias["query"] if alias else query.strip()
    hint = lga or (alias["lga"] if alias else None)
    key = cache_key(query, lga)
    if key in results:
        cached = results[key]
        if cached is None:
            return None
        if (
            in_bbox(cached["lon"], cached["lat"], bbox)
            and (not hint or address_has_lga(cached, hint))
        ):
            # Re-check type so a v2 cache cannot serve a street to a place query.
            fake = {
                "category": cached.get("category"),
                "type": cached.get("type"),
                "addresstype": cached.get("addresstype"),
                "lon": cached["lon"],
                "lat": cached["lat"],
                "display_name": cached.get("display_name"),
                "address": cached.get("address"),
            }
            want_road = names_road(query) or names_road(search_q)
            ok = is_highway_hit(fake) if want_road and is_highway_hit(fake) else is_place_hit(fake)
            if want_road:
                ok = is_highway_hit(fake) or is_place_hit(fake)
            if ok:
                return cached
    try:
        hits = nominatim_search(search_q, bbox)
        result = pick_hit(hits, bbox, query if not alias else search_q, hint)
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError):
        result = None
    results[key] = result
    if own_cache:
        save_cache(cache, cache_path)
    return result


def geocode_many(
    queries: list[str],
    bbox: list[float],
    cache_path: Path = DEFAULT_CACHE,
    lga: str | None = None,
) -> dict[str, dict[str, Any] | None]:
    cache = load_cache(cache_path)
    out: dict[str, dict[str, Any] | None] = {}
    for query in queries:
        out[query] = geocode(
            query, bbox, cache=cache, cache_path=cache_path, lga=lga
        )
        print(f"{query!r} -> {out[query]}", flush=True)
    save_cache(cache, cache_path)
    return out


def _fail_if(cond: bool, message: str, failures: list[str]) -> None:
    if cond:
        failures.append(message)
        print(f"FAIL  {message}")
    else:
        print(f"ok    {message.replace('must not', 'did not').replace('must ', '')}")


def selftest() -> int:
    bbox = LAGOS_BBOX
    print("geocode self-test (place filter + LGA hint + Lekki alias)")
    majek = geocode("Majek", bbox, lga="Ibeju-Lekki")
    abijo = geocode("Abijo", bbox, lga="Ibeju-Lekki")
    lekki = geocode("Lekki", bbox)
    print(f"  Majek  -> {majek}")
    print(f"  Abijo  -> {abijo}")
    print(f"  Lekki  -> {lekki}")
    failures: list[str] = []
    majek_txt = _norm(address_blob(majek or {}))
    abijo_txt = _norm(address_blob(abijo or {}))
    lekki_txt = _norm(address_blob(lekki or {}))
    _fail_if(
        majek is not None and ("ifako" in majek_txt or "ijaiye" in majek_txt or "fagba" in majek_txt),
        "Majek must not land in Ifako-Ijaiye / Fagba",
        failures,
    )
    _fail_if(
        abijo is not None and "ikoyi" in abijo_txt,
        "Abijo must not land in Ikoyi",
        failures,
    )
    _fail_if(
        lekki is not None and (lekki["lon"] > 3.70 or "ibeju" in lekki_txt),
        "Lekki must not resolve to Ibeju-Lekki / Free Trade Zone",
        failures,
    )
    if lekki is not None:
        _fail_if(
            "eti" not in lekki_txt and "peninsula" not in lekki_txt,
            "Lekki alias should land in Eti-Osa / peninsula",
            failures,
        )
    if failures:
        print(f"selftest: {len(failures)} failed")
        return 1
    print("selftest: pass")
    return 0


def main() -> None:
    if len(sys.argv) == 2 and sys.argv[1] == "--selftest":
        raise SystemExit(selftest())
    if len(sys.argv) < 2:
        raise SystemExit(
            "usage: python3 pipeline/geocode.py <query> [<query>...]\n"
            "       python3 pipeline/geocode.py --selftest"
        )
    geocode_many(sys.argv[1:], LAGOS_BBOX)


if __name__ == "__main__":
    main()
