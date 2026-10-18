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

def wayback_list(rec: dict) -> list:
    out = []
    for img in rec.get("images", []):
        if not img.get("file"):
            continue  # selected date whose tiles were missing (e.g. lekki-epe-rehab 2018-12-24)
        res = img.get("resolution_m")
        out.append({
            "acq_date": img["acq_date"],
            "file": img["file"],
            "marked_file": img.get("marked_file"),
            "resolution_m": res,
            "detail_chips": [
                {
                    "station": c.get("station"),
                    "file": c["file"],
                    "marked_file": c.get("marked_file"),
                    # chips are crops of the same acquisition: they inherit its resolution
                    "resolution_m": res,
                }
                for c in (img.get("detail_chips") or [])
            ],
        })
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
            "quote": props.get("cause_quote") or props.get("quote"),
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
        "claims": claims,
        "change": change,
        "promise_ids": sorted(ctx["promises"].get(sid, [])),
        "verdict": None,  # reviewer-written; carried from the previous run below
    }


# ---------------------------------------------------------------- reviewer carry

def computed_view(site: dict) -> str:
    """Everything the builder computes — i.e. the site minus the reviewer fields."""
    s = {k: v for k, v in site.items() if k != "verdict"}
    ch = dict(s.get("change") or {})
    ch.pop("summary", None)
    ch.pop("stale", None)
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
    return 0


if __name__ == "__main__":
    sys.exit(main())
