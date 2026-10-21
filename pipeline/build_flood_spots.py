#!/usr/bin/env python3
"""Cluster geocoded flood-day mentions into spots (Task 39).

Reads events/flood_days.json and events/intake/reports_*.json. Writes
events/flood_spots.json (and a copy under public/events/). City-confidence
mentions are dropped: they name a whole city, not a spot. Also writes a
small events/area_rain.json so the area panel can say how often a cell
sees 40 mm in a day, without loading the full IMERG daily grid in the
browser.
"""

from __future__ import annotations

import json
import math
import re
import shutil
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
EVENTS = ROOT / "events"
PUBLIC = ROOT / "public" / "events"
FLOOD_DAYS = EVENTS / "flood_days.json"
RAIN = EVENTS / "rain_history_grid_daily.json"
OUT_SPOTS = EVENTS / "flood_spots.json"
OUT_RAIN = EVENTS / "area_rain.json"

CLUSTER_M = 300.0
NEAR_IDENTICAL_M = 50.0
HEAVY_MM = 40.0

# Word-for-word body phrases → metres. Numbers in feet/inches/metres are
# converted at write time; this table is what the UI quotes in meta.
DEPTH_TABLE_M = {
    "ankle-deep": 0.10,
    "knee-deep": 0.45,
    "knee-high": 0.45,
    "thigh-deep": 0.70,
    "waist-deep": 0.90,
    "waist-high": 0.90,
    "hip-deep": 0.80,
    "chest-deep": 1.20,
    "neck-deep": 1.50,
    "shoulder-deep": 1.40,
    "above the knee": 0.45,
}
WORD_NUM = {
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
}
FT_M = 0.3048
IN_M = 0.0254

# A length of road ("200 metres of Mobil Road") is not a water depth.
LENGTH_OF_RE = re.compile(
    r"\b(\d+(?:\.\d+)?)\s*(?:metres?|meters?|m|feet|ft|inches|inch)\s+of\b",
    re.I,
)
WORD_DEPTH_RE = re.compile(
    r"\b(?:above the knee|(?:ankle|knee|thigh|waist|hip|chest|neck|shoulder)[-\s](?:deep|high)|knee length)\b",
    re.I,
)
NUM_DEPTH_RE = re.compile(
    r"\b(?:up to|about|around|almost|over|nearly)?\s*"
    r"(\d+(?:\.\d+)?|one|two|three|four|five|six|seven|eight|nine|ten)\s*"
    r"(metres?|meters?|m|feet|ft|inches|inch|in)\b"
    r"(?:\s+(?:high|deep|of water|floodwater))?",
    re.I,
)
DEPTH_CONTEXT_RE = re.compile(
    r"\b(deep|wade|waded|waist|knee|flood|water|submerged|high)\b",
    re.I,
)


def haversine_m(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    r = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(min(1.0, math.sqrt(a)))


def norm_name(name: str) -> str:
    primary = (name or "").split(",")[0]
    return re.sub(r"[^a-z0-9]+", " ", primary.casefold()).strip()


def names_match(a: str, b: str) -> bool:
    na, nb = norm_name(a), norm_name(b)
    if not na or not nb:
        return False
    if na == nb:
        return True
    return na in nb or nb in na


def load_reports() -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for path in sorted((EVENTS / "intake").glob("reports_*.json")):
        raw = json.loads(path.read_text(encoding="utf-8"))
        out.extend(raw.get("reports") or [])
    return out


def extract_depth_phrases(text: str) -> list[tuple[str, float]]:
    """Return (source phrase, metres) pairs; skip road-length 'N metres of …'."""
    if not text:
        return []
    found: list[tuple[str, float]] = []
    skip_spans = [m.span() for m in LENGTH_OF_RE.finditer(text)]

    def covered(span: tuple[int, int]) -> bool:
        return any(s <= span[0] and span[1] <= e for s, e in skip_spans)

    for m in WORD_DEPTH_RE.finditer(text):
        if covered(m.span()):
            continue
        raw = re.sub(r"\s+", "-", m.group(0).casefold()).replace("ankle-to-knee-deep", "knee-deep")
        if "knee-length" in raw or "knee length" in m.group(0).casefold():
            key = "knee-deep"
        elif "above-the-knee" in raw:
            key = "above the knee"
        else:
            key = raw
        metres = DEPTH_TABLE_M.get(key) or DEPTH_TABLE_M.get(key.replace("knee-high", "knee-deep"))
        if metres is None:
            continue
        found.append((m.group(0), metres))
    for m in NUM_DEPTH_RE.finditer(text):
        if covered(m.span()):
            continue
        window = text[max(0, m.start() - 40) : min(len(text), m.end() + 40)]
        if not DEPTH_CONTEXT_RE.search(window):
            continue
        raw_n = m.group(1).casefold()
        n = float(WORD_NUM[raw_n]) if raw_n in WORD_NUM else float(raw_n)
        unit = m.group(2).casefold()
        if unit in {"m", "metre", "metres", "meter", "meters"}:
            metres = n
            if metres > 4:  # standing water in a street is not 5+ m
                continue
        elif unit in {"feet", "ft"}:
            metres = n * FT_M
        else:
            metres = n * IN_M
        found.append((m.group(0).strip(), round(metres, 3)))
    # Unique by lowercase phrase, first wins.
    seen: set[str] = set()
    uniq: list[tuple[str, float]] = []
    for phrase, metres in found:
        k = phrase.casefold()
        if k in seen:
            continue
        seen.add(k)
        uniq.append((phrase, metres))
    return uniq


def split_sentences(text: str) -> list[str]:
    """Split on . ! ? ; without treating a.m. / p.m. as boundaries."""
    if not text:
        return []
    protected = re.sub(
        r"\b([ap])\.(m)\.",
        lambda m: f"{m.group(1)}\0{m.group(2)}.",
        text,
        flags=re.I,
    )
    chunks = re.split(r"(?<=[.!?;])\s+|\n+", protected)
    return [c.replace("\0", ".").strip() for c in chunks if c.strip()]


def name_in_sentence(sentence: str, name: str) -> bool:
    """True when the area name appears, ignoring case and punctuation."""
    needle = re.sub(r"[^a-z0-9]+", " ", (name or "").casefold()).strip()
    hay = re.sub(r"[^a-z0-9]+", " ", (sentence or "").casefold()).strip()
    if not needle or not hay:
        return False
    return re.search(rf"(?<![a-z0-9]){re.escape(needle)}(?![a-z0-9])", hay) is not None


def mention_needles(mention: dict[str, Any]) -> list[str]:
    """Spot name, geocode fallback, and the report's own area string."""
    names: list[str] = []
    for raw in (mention.get("name"), mention.get("geocoded_from"), mention.get("report_area")):
        if not raw:
            continue
        names.append(str(raw))
        primary = str(raw).split(",")[0].strip()
        if primary:
            names.append(primary)
    seen: set[str] = set()
    out: list[str] = []
    for n in names:
        k = n.casefold()
        if k in seen:
            continue
        seen.add(k)
        out.append(n)
    return out


def report_sentences(report: dict[str, Any]) -> list[str]:
    out: list[str] = []
    for field in ("impacts", "quote"):
        out.extend(split_sentences(report.get(field) or ""))
    return out


def attribute_report_depths(
    report: dict[str, Any],
    mentions: list[dict[str, Any]],
) -> tuple[list[list[dict[str, Any]]], list[dict[str, Any]]]:
    """Place each depth phrase on a mention, or return it as unplaced.

    same_sentence wins over single_area. A phrase that names an area which
    never became a geocoded mention stays off the map.
    """
    blob = " ".join(filter(None, [report.get("impacts") or "", report.get("quote") or ""]))
    phrases = extract_depth_phrases(blob)
    sentences = report_sentences(report)
    url = report.get("url") or ""
    publisher = report.get("publisher") or ""
    areas = [a for a in (report.get("areas") or []) if a]
    placed: list[list[dict[str, Any]]] = [[] for _ in mentions]
    unplaced: list[dict[str, Any]] = []

    def area_named_in(hits: list[str]) -> bool:
        for sent in hits:
            for a in areas:
                if name_in_sentence(sent, a) or name_in_sentence(sent, str(a).split(",")[0]):
                    return True
        return False

    for phrase, metres in phrases:
        hits = [s for s in sentences if phrase.casefold() in s.casefold()]
        placed_any = False
        for i, mention in enumerate(mentions):
            needles = mention_needles(mention)
            sent = next((s for s in hits if any(name_in_sentence(s, n) for n in needles)), None)
            if sent is None:
                continue
            placed[i].append(
                {
                    "phrase": phrase,
                    "metres": metres,
                    "url": url,
                    "publisher": publisher,
                    "placed_by": "same_sentence",
                    "sentence": sent,
                }
            )
            placed_any = True
        if placed_any:
            continue
        if len(areas) == 1 and len(mentions) == 1:
            sent = hits[0] if hits else (sentences[0] if sentences else blob)
            placed[0].append(
                {
                    "phrase": phrase,
                    "metres": metres,
                    "url": url,
                    "publisher": publisher,
                    "placed_by": "single_area",
                    "sentence": sent,
                }
            )
            continue
        if area_named_in(hits) or (len(areas) == 1 and not mentions):
            reason = "area_not_geocoded"
        else:
            reason = "no_area_in_sentence"
        unplaced.append({"phrase": phrase, "url": url, "reason": reason})
    return placed, unplaced


def matched_report_area(report: dict[str, Any], area_name: str) -> str | None:
    target = norm_name(area_name)
    if not target:
        return None
    for a in report.get("areas") or []:
        na = norm_name(a)
        if na == target or target in na or na in target:
            return a
    return None


class DSU:
    def __init__(self, n: int) -> None:
        self.p = list(range(n))

    def find(self, i: int) -> int:
        while self.p[i] != i:
            self.p[i] = self.p[self.p[i]]
            i = self.p[i]
        return i

    def union(self, i: int, j: int) -> None:
        a, b = self.find(i), self.find(j)
        if a != b:
            self.p[b] = a


def cluster_mentions(mentions: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    n = len(mentions)
    dsu = DSU(n)
    for i in range(n):
        a = mentions[i]
        for j in range(i + 1, n):
            b = mentions[j]
            d = haversine_m(a["lon"], a["lat"], b["lon"], b["lat"])
            if d <= NEAR_IDENTICAL_M or (d <= CLUSTER_M and names_match(a["name"], b["name"])):
                dsu.union(i, j)
    groups: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for i, m in enumerate(mentions):
        groups[dsu.find(i)].append(m)
    return list(groups.values())


CONF_RANK = {"street": 0, "area": 1, "neighbourhood": 1, "city": 2}


def build_spot(group: list[dict[str, Any]]) -> dict[str, Any]:
    names = Counter(m["name"] for m in group)
    name = names.most_common(1)[0][0]
    lon = sum(m["lon"] for m in group) / len(group)
    lat = sum(m["lat"] for m in group) / len(group)
    conf = min((m["confidence"] for m in group), key=lambda c: CONF_RANK.get(c, 9))
    dates = sorted({m["date"] for m in group})
    reports: list[dict[str, str]] = []
    seen_url: set[str] = set()
    for m in group:
        for r in m["reports"]:
            if r["url"] in seen_url:
                continue
            seen_url.add(r["url"])
            reports.append({"url": r["url"], "publisher": r["publisher"]})
    depths: list[dict[str, Any]] = []
    seen_phrase: set[str] = set()
    for m in group:
        for row in m["depth_rows"]:
            k = row["phrase"].casefold()
            if k in seen_phrase:
                continue
            seen_phrase.add(k)
            depths.append(
                {
                    "phrase": row["phrase"],
                    "metres": row["metres"],
                    "url": row.get("url") or None,
                    "publisher": row.get("publisher") or None,
                    "placed_by": row["placed_by"],
                    "sentence": row["sentence"],
                }
            )
    return {
        "name": name,
        "lon": round(lon, 6),
        "lat": round(lat, 6),
        "confidence": conf,
        "dates": dates,
        "count": len(dates),
        "latest": dates[-1],
        "reports": reports,
        "depths": depths,
    }


def match_reports(
    reports_by_date: dict[str, list[dict[str, Any]]], date: str, area_name: str
) -> list[dict[str, Any]]:
    hits: list[dict[str, Any]] = []
    target = norm_name(area_name)
    for r in reports_by_date.get(date, []):
        areas = r.get("areas") or []
        if any(norm_name(a) == target or target in norm_name(a) or norm_name(a) in target for a in areas):
            hits.append(r)
    return hits


def build_rain() -> dict[str, Any]:
    raw = json.loads(RAIN.read_text(encoding="utf-8"))
    dates: list[str] = raw["dates"]
    y0, y1 = int(dates[0][:4]), int(dates[-1][:4])
    # Inclusive calendar span in years, so a partial last year still counts.
    span_years = (datetime.fromisoformat(dates[-1]).toordinal() - datetime.fromisoformat(dates[0]).toordinal() + 1) / 365.25
    cells = []
    meta_cells = {c["id"]: c for c in raw["meta"]["cells"]}
    for cid, series in raw["series"].items():
        totals = series.get("total_mm") or []
        n_heavy = sum(1 for v in totals if v is not None and v >= HEAVY_MM)
        info = meta_cells.get(cid) or {}
        cells.append(
            {
                "id": cid,
                "lon": info.get("lon"),
                "lat": info.get("lat"),
                "heavy_days": n_heavy,
                "per_year": round(n_heavy / span_years, 2) if span_years else 0.0,
            }
        )
    return {
        "meta": {
            "threshold_mm": HEAVY_MM,
            "dates": [dates[0], dates[-1]],
            "span_years": round(span_years, 2),
            "source": "events/rain_history_grid_daily.json",
            "note": "NASA GPM IMERG daily totals, WAT days. A day counts when the cell total is 40 mm or more.",
        },
        "cells": cells,
    }


def publish(path: Path) -> None:
    dest = PUBLIC / path.name
    if dest.resolve() == path.resolve():
        return
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, dest)


def main() -> None:
    days = json.loads(FLOOD_DAYS.read_text(encoding="utf-8"))["days"]
    reports = load_reports()
    reports_by_date: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in reports:
        reports_by_date[r["date"]].append(r)

    dropped_city = 0
    mentions: list[dict[str, Any]] = []
    for day in days:
        date = day["date"]
        for area in day.get("areas") or []:
            conf = area.get("confidence")
            lon, lat = area.get("lon"), area.get("lat")
            if lon is None or lat is None:
                continue
            if conf == "city":
                dropped_city += 1
                continue
            matched = match_reports(reports_by_date, date, area["name"])
            report_areas: dict[str, str] = {}
            for r in matched:
                url = r.get("url") or ""
                hit = matched_report_area(r, area["name"])
                if url and hit:
                    report_areas[url] = hit
            mentions.append(
                {
                    "name": area["name"],
                    "lon": lon,
                    "lat": lat,
                    "confidence": conf,
                    "geocoded_from": area.get("geocoded_from"),
                    "date": date,
                    "reports": [
                        {"url": r.get("url") or "", "publisher": r.get("publisher") or ""}
                        for r in matched
                    ],
                    "report_areas": report_areas,
                    "depth_rows": [],
                }
            )

    reports_by_url: dict[str, dict[str, Any]] = {}
    for r in reports:
        url = r.get("url") or ""
        if url and url not in reports_by_url:
            reports_by_url[url] = r

    mentions_by_url: dict[str, list[int]] = defaultdict(list)
    for i, m in enumerate(mentions):
        seen_u: set[str] = set()
        for r in m["reports"]:
            u = r["url"]
            if u and u not in seen_u:
                seen_u.add(u)
                mentions_by_url[u].append(i)

    depth_unplaced: list[dict[str, Any]] = []
    seen_unplaced: set[tuple[str, str]] = set()

    def record_unplaced(rows: list[dict[str, Any]]) -> None:
        for row in rows:
            key = (row["phrase"].casefold(), row["url"])
            if key in seen_unplaced:
                continue
            seen_unplaced.add(key)
            depth_unplaced.append(row)

    for url, idxs in mentions_by_url.items():
        report = reports_by_url.get(url)
        if not report:
            continue
        uniq = list(dict.fromkeys(idxs))
        targets = [
            {
                "name": mentions[i]["name"],
                "geocoded_from": mentions[i].get("geocoded_from"),
                "report_area": mentions[i]["report_areas"].get(url),
            }
            for i in uniq
        ]
        placed, unplaced = attribute_report_depths(report, targets)
        for i, rows in zip(uniq, placed):
            mentions[i]["depth_rows"].extend(rows)
        record_unplaced(unplaced)

    for url, report in reports_by_url.items():
        if url in mentions_by_url:
            continue
        blob = " ".join(filter(None, [report.get("impacts") or "", report.get("quote") or ""]))
        if not extract_depth_phrases(blob):
            continue
        _, unplaced = attribute_report_depths(report, [])
        record_unplaced(unplaced)

    groups = cluster_mentions(mentions)
    spots = [build_spot(g) for g in groups]
    spots.sort(key=lambda s: (-s["count"], s["name"]))

    n_with_depth = sum(1 for s in spots if s["depths"])
    phrase_map: dict[str, float] = {}
    for s in spots:
        for d in s["depths"]:
            phrase_map.setdefault(d["phrase"], d["metres"])

    payload = {
        "meta": {
            "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "source": "events/flood_days.json",
            "cluster_m": CLUSTER_M,
            "near_identical_m": NEAR_IDENTICAL_M,
            "mentions_geocoded": sum(
                1
                for day in days
                for a in day.get("areas") or []
                if a.get("lon") is not None
            ),
            "dropped_city": dropped_city,
            "mentions_clustered": len(mentions),
            "n_spots": len(spots),
            "n_clusters": len(groups),
            "n_with_depth": n_with_depth,
            "n_depth_unplaced": len(depth_unplaced),
            "depth_table_m": {
                **DEPTH_TABLE_M,
                "1 foot": FT_M,
                "1 inch": IN_M,
                "1 metre": 1.0,
            },
            "depth_phrases": phrase_map,
            "depth_unplaced": depth_unplaced,
            "licence": "News quotes remain with their publishers. Locations derived from reports geocoded for FloodTrace.",
        },
        "spots": spots,
    }
    OUT_SPOTS.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    publish(OUT_SPOTS)

    rain = build_rain()
    OUT_RAIN.write_text(json.dumps(rain, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    publish(OUT_RAIN)

    print(
        f"flood spots: {len(spots)} (from {len(mentions)} mentions, "
        f"{len(groups)} clusters; dropped {dropped_city} city-level). "
        f"{n_with_depth} with depth phrases; {len(depth_unplaced)} unplaced."
    )
    for s in spots:
        for d in s["depths"]:
            print(
                f"  {s['name']} → {d['phrase']!r} → {d['placed_by']} → {d['sentence']}"
            )


if __name__ == "__main__":
    main()
