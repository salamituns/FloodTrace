#!/usr/bin/env python3
"""Task 23 (docs/tasks/23-build-sites.md): merge the drainage-site inputs into events/sites.json.

Inputs (all under events/): drainage_sites.json, drainage_sites_imagery.json,
drainage_sites_s2.json, drainage_sites_buildings.json, */evidence.geojson
(+ meta.citywide_cause_statements, which stay citywide and are never attached to a
site), */dossier.md (the "Cause (preliminary)" section is the source of
evidence_status), catalog.json (event dates), the optional promises.json (Task 22,
may not exist yet) and the previous events/sites.json (reviewer fields only).

Output: events/sites.json, validated against pipeline/schemas/sites.schema.json.

Deterministic: sorted keys and lists, no timestamps. Re-runnable; the reviewer
fields (verdict, change.summary) are carried from the previous run by site_id and
flagged stale when the numbers under them change. Re-run when promises.json appears.

Run: pipeline/.venv/bin/python pipeline/build_sites.py
"""
from __future__ import annotations

import hashlib
import json
import math
import re
import sys
import warnings
from pathlib import Path
from statistics import median

warnings.filterwarnings("ignore", category=DeprecationWarning)

sys.path.insert(0, str(Path(__file__).resolve().parent))
from quotes import clip_quote  # noqa: E402

import jsonschema  # noqa: E402  (pipeline/.venv has jsonschema 4.26 and shapely 2.2)
from shapely.geometry import LineString, Point  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
EVENTS = ROOT / "events"
SCHEMA_PATH = ROOT / "pipeline" / "schemas" / "sites.schema.json"
OUT_PATH = EVENTS / "sites.json"

DEFAULT_RADIUS_M = 400.0
LONG_LINE_RADIUS_M = 600.0
LONG_LINE_M = 2000.0
EARTH_R_M = 6371000.0

# Cause tags that are NOT human acts/omissions; a claim needs at least one other tag.
# canal_overflow is the water's behaviour (like heavy_rain / lagoon_tide), not an action.
NON_HUMAN_CAUSES = {"heavy_rain", "lagoon_tide", "low_lying_terrain", "canal_overflow"}

# Task 23: mark these two; their alignments are town-to-town corridors, not channels.
EXCLUDED_CORRIDOR = {"ikorodu-dammed", "ijede-drain"}
EXCLUDED_CORRIDOR_WHY = "corridor is not a channel"
EXCLUDED_NO_CHANNEL = "no channel line"

EVIDENCE_STATUS_ENUM = [
    "supports", "weak", "inconclusive", "contradicts", "not_checked", "no_imagery_after",
]
# Tokens as they appear in the dossiers' Cause (preliminary) sections.
EVIDENCE_STATUS_TOKENS = {
    "imagery supports": "supports",
    "imagery inconclusive": "inconclusive",
    "not checked": "not_checked",
    "no imagery after event": "no_imagery_after",
    "contradicts": "contradicts",
    "weak support": "weak",
}

# Short human names (task example: "Alpha Beach – System 156").
SITE_NAMES = {
    "alpha-beach-156": "Alpha Beach – System 156",
    "agungi-collector": "Agungi – Collector",
    "olopomeji": "Olopo Meji (Iyana Oworo)",
    "ikorodu-dammed": "Ikorodu – Dammed Waterway",
    "agric-bridge": "Agric – AFA Bridge",
    "ijede-drain": "Ijede – Oko Ope Drain",
    "oko-oba-canal": "Oko-Oba Canal",
    "alapere-ogudu": "Alapere–Ogudu",
    "marina-drainage": "Marina Road",
    "lekki-epe-rehab": "Lekki–Epe Expressway",
    "labora": "Labora (Abijo GRA)",
    "ibeju-lekki-expy": "Ibeju-Lekki Expressway Drains",
    "sangotedo-channel-notices": "Sangotedo – System 63b",
}

# From each site's structure_name (SITES_PLAN enum).
SITE_TYPES = {
    "alpha-beach-156": "channel",
    "agungi-collector": "collector",
    "olopomeji": "road",
    "ikorodu-dammed": "channel",
    "agric-bridge": "bridge",
    "ijede-drain": "channel",
    "oko-oba-canal": "canal",
    "alapere-ogudu": "road",
    "marina-drainage": "road",
    "lekki-epe-rehab": "road",
    "labora": "area",
    "ibeju-lekki-expy": "road",
    "sangotedo-channel-notices": "channel",
}

# Case-insensitive regexes identifying a site's bullet in an event's dossier
# Cause (preliminary) section; first matching bullet (in section order) wins.
# Keywords are chosen so the two Sangotedo bullets and the two 2025 Ijede-corridor
# bullets cannot cross-match.
DOSSIER_KEYWORDS = {
    "alpha-beach-156": [r"system 156"],
    "agungi-collector": [r"agungi"],
    "olopomeji": [r"olopomeji", r"opo meji", r"alapomeji", r"iyana oworo"],
    "ikorodu-dammed": [r"dammed", r"gberigbe"],
    "agric-bridge": [r"afa bridge", r"bridge construction at agric", r"agric[-–]isawo"],
    "ijede-drain": [r"oko ope", r"abule eko", r"abandoned unfinished drainage"],
    "oko-oba-canal": [r"oko[- ]oba"],
    "alapere-ogudu": [r"alapere"],
    "marina-drainage": [r"marina"],
    "lekki-epe-rehab": [r"rehabilitation", r"awoyaya", r"majek", r"abraham adesanya"],
    "labora": [r"labora", r"abijo"],
    "ibeju-lekki-expy": [r"ibeju-lekki expressway", r"blocked drains on the ibeju"],
    "sangotedo-channel-notices": [
        r"buildings on drainage channels", r"system 63b", r"lagos business school",
    ],
}

# Task 29: hand-checked place tokens for catalog-flood name matching. The place
# token, NOT a word from the structure name ("collector", "canal", "expressway"
# would match anything). Tokens are matched against a day's area names with case,
# hyphens, spaces and punctuation removed, so "Olopo Meji" matches "Olopomeji" and
# "Ketu-Alapere" matches "Alapere". Deliberately NOT tokens, after checking every
# hit against the catalog:
#   "Ikorodu"        - Ikorodu Road / Ikorodu city are not the Gberigbe corridor;
#                      its own place, Gberigbe, is never named in the catalog
#   "Oworo" alone   - would match Oworonshoki, a different place
#   "Ibeju-Lekki"    - an LGA suffix on far-away names ("Awoyaya, Ibeju-Lekki")
#   "Lekki-Epe Expressway" / "Ibeju-Lekki Expressway" - structure words; a flood
#                      named for the road can be km from the site's own stretch
#                      (e.g. Igbo-Efon, 2018-02-26, is west of the rehab section)
PLACE_TOKENS = {
    "alpha-beach-156": ["Alpha Beach"],
    "agungi-collector": ["Agungi"],
    # Iyana Oworo is the same junction as Olopo Meji; both spellings appear in
    # the catalog ("Olopo Meji", "Olopomeji", "Iyana-Oworo-Alapomeji").
    "olopomeji": ["Olopo Meji", "Alapomeji", "Iyana Oworo"],
    "ikorodu-dammed": ["Gberigbe"],  # never named in the catalog; near/area still match
    "agric-bridge": ["Agric"],
    "ijede-drain": ["Ijede"],
    "oko-oba-canal": ["Oko Oba"],
    "alapere-ogudu": ["Alapere"],
    "marina-drainage": ["Marina"],
    "lekki-epe-rehab": ["Awoyaya", "Majek", "Abraham Adesanya"],
    "labora": ["Labora"],  # new site; never named in the catalog
    "ibeju-lekki-expy": ["Eleko"],
    "sangotedo-channel-notices": ["Sangotedo"],
}

BULLET_RE = re.compile(r"^- \*\*(?P<title>.+?)\*\*(?P<body>.*)$")
STATUS_RE = re.compile(r"Status:\s*\x60([^\x60]+)\x60")


def load(path: Path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def rel(path: Path) -> str:
    return str(path.relative_to(ROOT))


# ---------------------------------------------------------------- geodesy (local)

def site_metric(geom: dict):
    """Site geometry in a local equirectangular metric frame (Lagos is small and flat)."""
    pts = [geom["coordinates"]] if geom["type"] == "Point" else list(geom["coordinates"])
    lat0 = sum(p[1] for p in pts) / len(pts)
    lon0 = sum(p[0] for p in pts) / len(pts)
    k = math.cos(math.radians(lat0)) * EARTH_R_M * math.radians(1.0)
    xy = [((lon - lon0) * k, (lat - lat0) * EARTH_R_M * math.radians(1.0)) for lon, lat in pts]
    g = Point(xy[0]) if geom["type"] == "Point" else LineString(xy)
    radius = LONG_LINE_RADIUS_M if (geom["type"] == "LineString" and g.length > LONG_LINE_M) else DEFAULT_RADIUS_M
    return g, radius, lat0, lon0


def point_dist_m(g, lon, lat, lat0, lon0) -> float:
    k = math.cos(math.radians(lat0)) * EARTH_R_M * math.radians(1.0)
    p = Point((lon - lon0) * k, (lat - lat0) * EARTH_R_M * math.radians(1.0))
    return g.distance(p)


# ------------------------------------------------------- catalog (Tier B) matching

# Task 29: match events/flood_days.json days to a site. Strength is the strongest
# of name > near > area. city/lga/unknown confidence never match; fallback
# geocodes (geocoded_from set) count as 'area' at best.
CATALOG_NEAR_CONF = {"exact", "street"}
CATALOG_AREA_CONF = {"neighbourhood", "area"}
CATALOG_AREA_RADIUS_M = 1500.0
CATALOG_NOTE = "counts reported floods; a year with no report is not proof of no flood"


def squash(s: str) -> str:
    """Case-, hyphen-, space- and punctuation-insensitive form ("Olopo Meji" == "Olopomeji")."""
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


def _nearest_m(g, areas, lat0, lon0):
    ds = [point_dist_m(g, a["lon"], a["lat"], lat0, lon0)
          for a in areas if a.get("lon") is not None and a.get("lat") is not None]
    return round(min(ds), 1) if ds else None


def match_catalog_day(day: dict, site_id: str, g, radius: float, lat0: float, lon0: float):
    """One catalog flood day vs one site -> (strength, [matched area names], distance_m) | None."""
    tokens = [squash(t) for t in PLACE_TOKENS.get(site_id, [])]
    named = []
    for a in day["areas"]:
        nm = squash(a.get("name"))
        if nm and any(t and t in nm for t in tokens):
            named.append(a)
    if named:
        return "name", sorted({a["name"] for a in named}), _nearest_m(g, named, lat0, lon0)
    near, area = [], []
    for a in day["areas"]:
        conf = a.get("confidence")
        if a.get("lon") is None or a.get("lat") is None or conf not in (CATALOG_NEAR_CONF | CATALOG_AREA_CONF):
            continue
        d = point_dist_m(g, a["lon"], a["lat"], lat0, lon0)
        if conf in CATALOG_NEAR_CONF and not a.get("geocoded_from") and d <= radius + 200:
            near.append((d, a))
        elif conf in CATALOG_AREA_CONF and d <= CATALOG_AREA_RADIUS_M:
            area.append((d, a))
    if near:
        return "near", sorted({a["name"] for _, a in near}), round(min(d for d, _ in near), 1)
    if area:
        return "area", sorted({a["name"] for _, a in area}), round(min(d for d, _ in area), 1)
    return None


def catalog_sources(day: dict, matched_names: list) -> list:
    """Up to 3 reports naming a matched area (in quote or cause_quote); else the first ones."""
    names = [squash(n) for n in matched_names]
    naming = []
    for rp in day["reports"]:
        text = squash((rp.get("quote") or "") + " " + (rp.get("cause_quote") or ""))
        if any(n and n in text for n in names):
            naming.append(rp)
    chosen = naming or day["reports"]
    return [{"url": rp.get("url"), "publisher": rp.get("publisher"), "quote": clip_quote(rp.get("quote"))} for rp in chosen[:3]]


def catalog_floods_for_site(site_id: str, g, radius: float, lat0: float, lon0: float, catalog: dict):
    """Task 29: the site's dated, sourced catalog flood days (newest first) + honest counts."""
    entries = []
    for day in catalog["days"]:
        m = match_catalog_day(day, site_id, g, radius, lat0, lon0)
        if m is None:
            continue
        strength, names, dist = m
        entries.append({
            "date": day["date"],
            "flood_type": day["flood_type"],
            "episode_id": day.get("episode_id"),
            "strength": strength,
            "matched_areas": names,
            "distance_m": dist,
            "n_outlets": day["n_outlets"],
            "promote": day["promote"],
            "tier_a_event_id": day.get("tier_a_event_id"),
            "sources": catalog_sources(day, names),
        })
    entries.sort(key=lambda e: e["date"], reverse=True)
    n_strong = sum(e["strength"] in ("name", "near") for e in entries)
    years_searched = catalog["years_searched"]
    summary = {
        "n_days": len(entries),
        "n_days_strong": n_strong,
        "years_with_flood": sorted({int(e["date"][:4]) for e in entries}),
        "years_searched": years_searched,
        "per_searched_year": round(n_strong / len(years_searched), 2) if years_searched else 0,
        "riverine_days": sum(e["flood_type"] == "riverine" for e in entries),
        "note": CATALOG_NOTE,
    }
    return entries, summary


# ---------------------------------------------------------------- dossier parsing

def parse_dossier_causes(path: Path):
    """Bullets of the Cause (preliminary) section: text, status token, parenthetical note."""
    bullets = []
    lines = path.read_text(encoding="utf-8").splitlines()
    start = next((i for i, l in enumerate(lines) if re.match(r"^#+\s.*[Cc]ause", l)), None)
    if start is None:
        return bullets
    for line in lines[start + 1:]:
        if re.match(r"^#+\s", line):
            break
        m = BULLET_RE.match(line)
        if not m:
            continue
        sm = STATUS_RE.search(m.group("body"))
        status_raw = sm.group(1) if sm else None
        note = None
        if sm:
            rest = m.group("body")[sm.end():]
            a = rest.find("(")
            if a != -1:
                b = rest.find(")", a)
                if b != -1:
                    note = rest[a + 1:b].strip()
        bullets.append({"text": line, "status_raw": status_raw, "status_note": note})
    return bullets


def map_status(raw):
    if raw is None:
        return None
    key = raw.strip().lower()
    if key in EVIDENCE_STATUS_TOKENS:
        return EVIDENCE_STATUS_TOKENS[key]
    if key in EVIDENCE_STATUS_ENUM:
        return key
    return None


def dossier_site_status(bullets, site_id):
    """evidence_status + status_note for a site in one event's dossier."""
    for b in bullets:
        low = b["text"].lower()
        if any(re.search(k, low) for k in DOSSIER_KEYWORDS.get(site_id, [])):
            return map_status(b["status_raw"]) or "not_checked", b["status_note"]
    return "not_checked", None


# ---------------------------------------------------------------- change blocks

def wayback_live_chip(c: dict, res) -> dict | None:
    """Browser fields for one Wayback chip. Skip dates that never got a live view."""
    if not c.get("tile_url") or not c.get("bounds") or c.get("zoom") is None:
        return None
    if c.get("release") is None:
        return None
    out = {
        "release": c["release"],
        "zoom": c["zoom"],
        "tile_url": c["tile_url"],
        "bounds": c["bounds"],
        "resolution_m": res,
    }
    if c.get("station"):
        out["station"] = c["station"]
        if c.get("lon") is not None:
            out["lon"] = c["lon"]
            out["lat"] = c["lat"]
    return out


def wayback_list(rec: dict) -> list:
    out = []
    for img in rec.get("images", []):
        res = img.get("resolution_m")
        live = wayback_live_chip(img, res)
        if live is None:
            continue  # selected date whose tiles were missing (e.g. lekki-epe-rehab 2018-12-24)
        live["acq_date"] = img["acq_date"]
        live["detail_chips"] = []
        for c in (img.get("detail_chips") or []):
            d = wayback_live_chip(c, res)
            if d:
                live["detail_chips"].append(d)
        out.append(live)
    out.sort(key=lambda e: e["acq_date"])
    return out


def s2_wet_season(rec: dict, site_id: str) -> dict:
    aois = rec.get("aois", {})
    aoi = site_id
    if site_id == "alpha-beach-156" and "alpha-beach-156__south" in aois:
        aoi = "alpha-beach-156__south"
    by_month = {}
    for m in aois.get(aoi, {}).get("monthly", []):
        if m.get("n", 0) and m.get("vegfrac") is not None:
            y, mo = m["month"].split("-")
            if "05" <= mo <= "10":  # May–Oct wet season, same-season medians only
                by_month.setdefault(y, []).append(m["vegfrac"])
    return {
        "aoi": aoi,
        "by_year": {y: round(median(v), 4) for y, v in sorted(by_month.items())},
    }


def buildings_block(rec: dict, baseline_segs: list) -> dict:
    """Built fraction 0–10 m by year + the matched-baseline re-rank (Task 21 method).

    Matched baseline: segments whose 2016 20–50 m built fraction is within
    ±max(0.05, 0.5 × the site's). matched_pct = percent of matched segments whose
    2016→2023 0–10 m change is below the site's change (reproduces the reviewed
    88/21/71/73 percentiles for Alpha Beach, Oko-Oba, Agungi, Olopomeji).
    """
    out = {"by_year": {}, "matched_pct": None, "matched_n": None, "excluded": None}
    if rec is None:
        out["excluded"] = EXCLUDED_NO_CHANNEL
        return out
    if rec.get("site_id") in EXCLUDED_CORRIDOR:
        out["excluded"] = EXCLUDED_CORRIDOR_WHY
    bands = rec.get("bands") or {}
    bf = (bands.get("0-10") or {}).get("built_fraction")
    if not bf:
        out["excluded"] = out["excluded"] or EXCLUDED_NO_CHANNEL
        return out
    out["by_year"] = {y: bf[y] for y in sorted(bf)}
    try:
        v16, v23 = bf["2016"], bf["2023"]
        w16 = bands["20-50"]["built_fraction"]["2016"]
    except (KeyError, TypeError):
        return out
    if v16 is None or v23 is None or w16 is None:
        return out
    tol = max(0.05, 0.5 * w16)
    site_change = v23 - v16
    matched = []
    for seg in baseline_segs:
        try:
            sw = seg["built_fraction"]["20-50"]["2016"]
            s0 = seg["built_fraction"]["0-10"]["2016"]
            s1 = seg["built_fraction"]["0-10"]["2023"]
        except (KeyError, TypeError):
            continue
        if sw is None or s0 is None or s1 is None:
            continue
        if abs(sw - w16) <= tol:
            matched.append(s1 - s0)
    if not matched:
        return out
    out["matched_n"] = len(matched)
    out["matched_pct"] = int(round(100 * sum(1 for c in matched if c < site_change) / len(matched)))
    return out


# ---------------------------------------------------------------- site assembly

def guess_type(structure_name: str) -> str:
    s = structure_name.lower()
    if "collector" in s:
        return "collector"
    if "canal" in s:
        return "canal"
    if "bridge" in s:
        return "bridge"
    if "channel" in s or "drain" in s:
        return "channel"
    if "road" in s or "expressway" in s or "highway" in s:
        return "road"
    return "area"


def claim_date(props: dict):
    for key in ("published_at", "observed_at"):
        v = props.get(key)
        if v:
            return str(v)[:10]
    return None


def build_site(src, ctx) -> dict:
    sid = src["site_id"]
    g, radius, lat0, lon0 = site_metric(src["geometry"])

    # Per event: matched evidence features (within radius, excluding LGA-level points).
    matched = {}  # event_id -> list of (dist, feature)
    for ev_id, feats in ctx["evidence"].items():
        ms = []
        for f in feats:
            props = f["properties"]
            if props.get("location_confidence") == "lga":
                continue
            try:
                lon, lat = f["geometry"]["coordinates"][:2]
            except (KeyError, TypeError, ValueError):
                continue
            d = point_dist_m(g, lon, lat, lat0, lon0)
            if d <= radius:
                ms.append((d, f))
        if ms:
            matched[ev_id] = ms

    floods = [
        {
            "event_id": ev_id,
            "date": ctx["dates"].get(ev_id),
            "evidence_ids": sorted(f["properties"]["id"] for _, f in ms),
            "n_reports": len(ms),
            "nearest_m": round(min(d for d, _ in ms), 1),
        }
        for ev_id, ms in sorted(matched.items())
    ]

    # Claims: the site's own evidence_ids (its own event) + matched features with
    # human causes (any event — recurring places get claims from later events too).
    claim_feats = {}
    own_ids = set(src.get("evidence_ids") or [])
    if own_ids:
        for f in ctx["evidence"].get(src["event_id"], []):
            if f["properties"].get("id") in own_ids:
                claim_feats[(src["event_id"], f["properties"]["id"])] = f
        missing = own_ids - {f["properties"]["id"] for f in ctx["evidence"].get(src["event_id"], [])}
        if missing:
            print(f"  warning: {sid}: evidence_ids not found in {src['event_id']}: {sorted(missing)}", file=sys.stderr)
    for ev_id, ms in matched.items():
        for _, f in ms:
            causes = f["properties"].get("causes") or []
            if any(c not in NON_HUMAN_CAUSES for c in causes):
                claim_feats[(ev_id, f["properties"]["id"])] = f

    claims = []
    for (ev_id, evid) in sorted(claim_feats):
        props = claim_feats[(ev_id, evid)]["properties"]
        causes = props.get("causes") or []
        human = [c for c in causes if c not in NON_HUMAN_CAUSES]
        status, note = ctx["status_by_event"][(ev_id, sid)]
        claims.append({
            "claim_id": f"{sid}-{ev_id}-{evid}",
            "event_id": ev_id,
            "cause": (human or causes or [None])[0],
            "attributed_by": props.get("cause_attributed_by"),
            "who": props.get("cause_who"),
            "quote": clip_quote(props.get("cause_quote") or props.get("quote")),
            "source_id": props.get("source_id"),
            "url": props.get("source_url"),
            "date": claim_date(props),
            "evidence_status": status,
            "status_note": note,
        })

    aliases = set()
    for f in claim_feats.values():
        if f["properties"].get("location_name"):
            aliases.add(f["properties"]["location_name"])
    for ms in matched.values():
        for _, f in ms:
            if f["properties"].get("location_name"):
                aliases.add(f["properties"]["location_name"])

    # Task 29: the site's catalog (Tier B) flood days and honest per-year counts.
    catalog_floods, catalog_summary = catalog_floods_for_site(
        sid, g, radius, lat0, lon0, ctx["catalog"])

    change = {
        "wayback": wayback_list(ctx["imagery"].get(sid, {})),
        "s2_wet_season": s2_wet_season(ctx["s2"].get(sid, {}), sid),
        "buildings_0_10m": buildings_block(ctx["buildings"].get(sid), ctx["baseline_segs"]),
        "summary": None,   # reviewer-written; carried from the previous run below
        "stale": None,
    }

    return {
        "site_id": sid,
        "name": SITE_NAMES.get(sid, sid.replace("-", " ").title()),
        "aliases": sorted(aliases),
        "structure_name": src["structure_name"],
        "structure_type": SITE_TYPES.get(sid) or guess_type(src["structure_name"]),
        "geometry": src["geometry"],
        "location_confidence": src["location_confidence"],
        "located_how": src["located_how"],
        "flood_radius_m": radius,
        "floods": floods,
        "catalog_floods": catalog_floods,
        "catalog_summary": catalog_summary,
        "claims": claims,
        "change": change,
        "promise_ids": sorted(ctx["promises"].get(sid, [])),
        "verdict": None,  # reviewer-written; carried from the previous run below
    }


# ---------------------------------------------------------------- reviewer carry

def computed_view(site: dict) -> str:
    """Everything the builder computes — i.e. the site minus the reviewer fields
    and the Task 29 catalog counts (a reported-flood tally doesn't invalidate a
    verdict written on the evidence chain; it's shown alongside it)."""
    s = {k: v for k, v in site.items() if k not in ("verdict", "catalog_floods", "catalog_summary")}
    ch = dict(s.get("change") or {})
    ch.pop("summary", None)
    ch.pop("stale", None)
    # Live tile fields vs stored JPG paths are the same pictures; don't stale a review on that.
    ch["wayback"] = [
        {
            "acq_date": w.get("acq_date"),
            "resolution_m": w.get("resolution_m"),
            "n_detail": len(w.get("detail_chips") or []),
        }
        for w in (ch.get("wayback") or [])
    ]
    s["change"] = ch
    return json.dumps(s, sort_keys=True, ensure_ascii=False)


def carry_reviewer_fields(site: dict, prev_site) -> None:
    changed = prev_site is not None and computed_view(prev_site) != computed_view(site)

    verdict = None
    if prev_site and isinstance(prev_site.get("verdict"), dict):
        pv = prev_site["verdict"]
        verdict = {k: pv.get(k) for k in ("text", "confidence", "reviewed_by", "reviewed_at")}
        # stale stays true until the reviewer clears it and the numbers hold steady
        verdict["stale"] = bool(pv.get("stale") or changed)
    site["verdict"] = verdict

    summary, summary_stale = None, None
    if prev_site:
        pc = prev_site.get("change") or {}
        summary = pc.get("summary")
        if summary is not None:
            summary_stale = bool(pc.get("stale") or changed)
    site["change"]["summary"] = summary
    site["change"]["stale"] = summary_stale


# ---------------------------------------------------------------- main

def main() -> int:
    sites_src = load(EVENTS / "drainage_sites.json")["sites"]
    imagery = {s["site_id"]: s for s in load(EVENTS / "drainage_sites_imagery.json")["sites"]}
    s2 = load(EVENTS / "drainage_sites_s2.json")["sites"]
    buildings_doc = load(EVENTS / "drainage_sites_buildings.json")
    buildings = {s["site_id"]: s for s in buildings_doc["sites"]}
    baseline_segs = buildings_doc.get("baseline", {}).get("per_segment", [])
    catalog = load(EVENTS / "catalog.json")
    dates = {e["id"]: e.get("date") for e in catalog["events"]}

    tier_b = load(EVENTS / "flood_days.json")
    # Task 29: years searched = years with an April-November month in the catalog's
    # frozen meta.search_coverage, not the live search log, so a year Cursor
    # hasn't finished sweeping doesn't count as searched.
    years_searched = sorted({
        int(e["year_month"][:4]) for e in tier_b["meta"].get("search_coverage", [])
        if "04" <= e["year_month"][5:7] <= "11"
    })

    promises_path = EVENTS / "promises.json"
    promises_by_site = {}
    if promises_path.exists():
        for p in load(promises_path).get("promises", []):
            promises_by_site.setdefault(p.get("site_id"), []).append(p["promise_id"])

    event_dirs = sorted(d for d in EVENTS.iterdir() if (d / "evidence.geojson").exists())
    evidence, dossiers = {}, {}
    for d in event_dirs:
        gj = load(d / "evidence.geojson")
        evidence[d.name] = [f for f in gj["features"] if f.get("geometry", {}).get("coordinates")]
        dossiers[d.name] = parse_dossier_causes(d / "dossier.md")
    event_ids = sorted(evidence)

    status_by_event = {
        (ev_id, src["site_id"]): dossier_site_status(dossiers[ev_id], src["site_id"])
        for ev_id in event_ids
        for src in sites_src
    }

    prev = load(OUT_PATH) if OUT_PATH.exists() else None
    prev_by_id = {s.get("site_id"): s for s in prev.get("sites", [])} if prev else {}

    ctx = {
        "evidence": evidence,
        "dates": dates,
        "status_by_event": status_by_event,
        "imagery": imagery,
        "s2": s2,
        "buildings": buildings,
        "baseline_segs": baseline_segs,
        "promises": promises_by_site,
        "catalog": {"days": tier_b["days"], "years_searched": years_searched},
    }

    sites = []
    for src in sorted(sites_src, key=lambda s: s["site_id"]):
        site = build_site(src, ctx)
        carry_reviewer_fields(site, prev_by_id.get(src["site_id"]))
        sites.append(site)

    input_files = [
        EVENTS / "drainage_sites.json",
        EVENTS / "drainage_sites_imagery.json",
        EVENTS / "drainage_sites_s2.json",
        EVENTS / "drainage_sites_buildings.json",
        EVENTS / "catalog.json",
    ] + [d / "evidence.geojson" for d in event_dirs] + [d / "dossier.md" for d in event_dirs]
    if promises_path.exists():
        input_files.append(promises_path)

    data = {
        "meta": {
            "task": "23-build-sites (docs/tasks/23-build-sites.md)",
            "generated_by": "pipeline/build_sites.py",
            "schema": "pipeline/schemas/sites.schema.json",
            "site_count": len(sites),
            "event_ids": event_ids,
            "event_dates_from": "events/catalog.json",
            "promises_present": promises_path.exists(),
            "catalog_floods": {
                "task": "29-site-flood-counts (docs/tasks/29-site-flood-counts.md)",
                "method": "each Tier B flood day (events/flood_days.json) matched to the site; "
                          "strength is the strongest of name > near > area; catalog days are "
                          "reported floods, so a year with no report is not proof of no flood",
                "flood_days_sha256": sha256(EVENTS / "flood_days.json"),
                "years_searched": years_searched,
                "rules": {
                    "name": "a hand-checked place token (PLACE_TOKENS in pipeline/build_sites.py) "
                            "appears in a day's area name, compared with case, hyphens, spaces and "
                            "punctuation removed",
                    "near": "an area with confidence exact or street (not a fallback geocode) within "
                            "flood_radius_m + 200 m of the site geometry",
                    "area": "an area with confidence neighbourhood or area within 1,500 m; fallback "
                            "geocodes (geocoded_from set) count as area at best",
                    "never": "confidence city, lga or unknown, and un-geocoded areas, never match",
                    "sources": "up to 3 of the day's reports naming a matched area, else the first "
                               "reports; url, publisher, quote",
                    "years_searched": "years with an April-November entry in flood_days.json "
                                      "meta.search_coverage (not the live search log)",
                    "per_searched_year": "n_days_strong / len(years_searched), rounded to 2 decimals",
                    "riverine_days": "matched days whose flood_type is riverine",
                },
            },
            "inputs": {rel(p): sha256(p) for p in sorted(input_files)},
            "rules": {
                "floods": "per event, evidence features within flood_radius_m of the site geometry "
                          "(400 m; 600 m for LineStrings longer than 2 km), excluding location_confidence "
                          "'lga'; includes events other than the site's own",
                "human_causes": "all cause tags except: " + ", ".join(sorted(NON_HUMAN_CAUSES)),
                "claims": "the site's evidence_ids plus matched features with human causes; "
                          "evidence_status parsed from the event dossier's Cause (preliminary) section",
                "evidence_status_tokens": EVIDENCE_STATUS_TOKENS,
                "s2_wet_season": "per-year median of May–Oct monthly vegfrac for the recorded AOI "
                                 "(step-detector output not used)",
                "buildings_match": "baseline segments whose 2016 20–50 m built fraction is within "
                                   "±max(0.05, 0.5 × the site's); matched_pct = percent of matched segments "
                                   "whose 2016→2023 0–10 m change is below the site's",
            },
            "notes": [
                "Deterministic: sorted keys and lists, no timestamps; identical inputs give identical bytes.",
                "Reviewer fields (verdict, change.summary) are carried from the previous events/sites.json "
                "by site_id; verdict.stale / change.stale flag a run whose underlying numbers changed. "
                "stale stays true until the reviewer clears it and the numbers hold steady.",
                "meta.citywide_cause_statements are citywide and are never attached to a site.",
                "Wayback detail chips inherit their acquisition's resolution_m (crops of the same image); "
                "the app hides coarse fallbacks (e.g. 15 m).",
                "When events/promises.json appears (Task 22), re-run this script to fill promise_ids.",
            ],
        },
        "sites": sites,
    }

    schema = load(SCHEMA_PATH)
    jsonschema.Draft202012Validator(schema).validate(data)
    print(f"schema OK: pipeline/schemas/sites.schema.json ({len(sites)} sites)")

    OUT_PATH.write_text(json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {rel(OUT_PATH)}")

    hdr = ("site", "floods", "claims", "statuses", "s2 years", "ob pct", "promises")
    print()
    print(f"{hdr[0]:28s} {hdr[1]:>6s} {hdr[2]:>6s}  {hdr[3]:<44s} {hdr[4]:<14s} {hdr[5]:>6s} {hdr[6]:>8s}")
    for s in sites:
        statuses = ",".join(sorted({c["evidence_status"] for c in s["claims"]})) or "-"
        years = list(s["change"]["s2_wet_season"]["by_year"])
        yrs = f"{years[0]}–{years[-1]} ({len(years)})" if years else "-"
        ob = s["change"]["buildings_0_10m"]["matched_pct"]
        ob_s = "-" if ob is None else (f"{ob}" + ("*" if s["change"]["buildings_0_10m"]["excluded"] else ""))
        print(f"{s['site_id']:28s} {len(s['floods']):>6d} {len(s['claims']):>6d}  {statuses:<44s} {yrs:<14s} {ob_s:>6s} {len(s['promise_ids']):>8d}")
    print()
    tot_f = sum(len(s["floods"]) for s in sites)
    tot_c = sum(len(s["claims"]) for s in sites)
    print(f"totals: {len(sites)} sites, {tot_f} site-floods, {tot_c} claims, promises_present={promises_path.exists()}")
    print("* = buildings block excluded (corridor is not a channel / no channel line)")

    # Task 29: per-site catalog flood counts and the area-strength matches to review.
    print()
    hdr = ("site", "days", "strong", "years with flood", "per yr", "river", "newest dates")
    print(f"{hdr[0]:28s} {hdr[1]:>5s} {hdr[2]:>6s}  {hdr[3]:<34s} {hdr[4]:>6s} {hdr[5]:>5s}  {hdr[6]}")
    for s in sites:
        cs = s["catalog_summary"]
        yrs = ",".join(str(y) for y in cs["years_with_flood"]) or "-"
        dates = ", ".join(e["date"] for e in s["catalog_floods"][:3]) or "-"
        print(f"{s['site_id']:28s} {cs['n_days']:>5d} {cs['n_days_strong']:>6d}  {yrs:<34s} "
              f"{cs['per_searched_year']:>6.2f} {cs['riverine_days']:>5d}  {dates}")
    print(f"years searched (Apr-Nov entry in flood_days.json meta.search_coverage): {years_searched}")

    print()
    print("area-strength catalog matches (check these on the map):")
    n_area = 0
    for s in sites:
        for e in s["catalog_floods"]:
            if e["strength"] == "area":
                n_area += 1
                dm = "-" if e["distance_m"] is None else f"{e['distance_m']:.1f}"
                print(f"  {s['site_id']:28s} {e['date']}  {dm:>8s} m  {', '.join(e['matched_areas'])}")
    if not n_area:
        print("  (none)")
    print(f"  ({n_area} area-strength matches)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
