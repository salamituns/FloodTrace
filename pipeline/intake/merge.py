#!/usr/bin/env python3
"""Group news-sweep reports into flood days (Tier B catalog).

Usage:
    pipeline/.venv/bin/python pipeline/intake/merge.py \
        [--reports PATH ...] [--out events/flood_days.json]

Input : events/intake/reports_*.json (Task 26 schema). When no pilot
        files exist yet, falls back to pipeline/intake/fixtures/reports_*.json.
Output: events/flood_days.json
Print : flood days per year, and the drainage signal: the share of
        checkable flood days (>= 1 geocoded area and IMERG coverage) with
        local_max_2d_mm below 20 mm. The AOI-mean share is printed as
        context. Days with no geocoded area are excluded from the signal.

Grouping: same date, or dates within +/-1 day when either report's
date_confidence is not "exact" and the areas overlap (same normalized
name, or geocoded points within 2 km). Geocoding uses pipeline/geocode.py
(Nominatim, max 1 request/s, cached); a full name that fails is retried with
its district part (text after the last comma, or a known district inside
the string) at confidence "neighbourhood". Rain signatures come from
events/rain_history_grid_daily.json, including the local block: rain at the
flooded areas' own cells for the flood day and the day before.
Population-weighted rain follows catalog_ranked.json: sum(cell total x cell
pop) / sum(cell pop), GHSL epoch nearest the flood day's year.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from statistics import median

PIPELINE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PIPELINE_DIR))
import geocode  # noqa: E402  (pipeline/geocode.py)

PROJECT_ROOT = PIPELINE_DIR.parent
EVENTS_DIR = PROJECT_ROOT / "events"
FIXTURES_DIR = PIPELINE_DIR / "intake" / "fixtures"
RAIN_HISTORY = EVENTS_DIR / "rain_history_grid_daily.json"
EXPOSURE_CELLS = EVENTS_DIR / "exposure_cells.json"
CATALOG_RANKED = EVENTS_DIR / "catalog_ranked.json"
SEARCH_LOG = EVENTS_DIR / "intake" / "search_log.json"
DEFAULT_OUT = EVENTS_DIR / "flood_days.json"

AREA_OVERLAP_KM = 2.0
DRAINAGE_SIGNAL_MM = 20.0
DATE_CONFIDENCE_ORDER = {"exact": 0, "day": 1, "approx": 2}

# docs/INTAKE_PLAN.md decision 3 (promotion to Tier A)
OFFICIAL_WORDS = re.compile(
    r"\b(NEMA|LASEMA|LASTMA|LASEPA|LAWMA|NIHSA|SEMA|Red Cross|Red Crescent|"
    r"police|fire service|commissioner|commissioner's|ministry|government|"
    r"governor|Nigerian military|army|navy|"
    r"director(?:[- ]general)?|coordinator|general manager|"
    r"spokesman|spokesperson|permanent secretary)\b",
    re.I,
)
# Task 27b fix 4: death words. Any report of the day counts, and the
# official/named attribution may sit in any report of that same day.
DEATH_WORDS = re.compile(
    r"\b(swept away|drowned|drownings?|died|dead|death|deaths|killed|"
    r"bodies|fatalities?|lost (?:their |his |her )?lives?)\b",
    re.I,
)
# Task 27b fix 3: a named structure is a canal, channel, collector, drain
# system number, bridge, culvert, outfall or named road project -- not a
# generic road/street/drain mention.
NAMED_STRUCTURE_RE = re.compile(
    r"\b(canal|channel|collector|culvert|outfall|bridge)\b", re.I)
DRAIN_SYSTEM_NUMBER_RE = re.compile(
    r"\bdrain(?:age)?\s+(?:system|channel)s?\s*(?:no\.?\s*)?\d+\b", re.I)
_ROAD_NAME = r"(?:[A-Z][\w'-]*\s+){1,4}(?:Road|Expressway|Avenue|Boulevard|Way)"
_PROJECT_WORD = r"(?:construction|reconstruction|rehabilitation|expansion|project|abandoned)"
NAMED_ROAD_PROJECT_RE = re.compile(
    rf"{_ROAD_NAME}[^.]{{0,60}}{_PROJECT_WORD}"
    rf"|{_PROJECT_WORD}[^.]{{0,60}}{_ROAD_NAME}"
)
# heavy_rain / lagoon_tide / dam_release are not human cause tags.
NATURAL_CAUSE_TAGS = {"heavy_rain", "lagoon_tide", "dam_release"}
# Task 27b fix 2: a known district immediately followed by one of these is
# part of a route name ("Lagos-Badagry Expressway"), not the district.
ROUTE_AFTER_RE = re.compile(r"^(expressway|road|street|way|avenue|boulevard|link)$", re.I)


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def norm_name(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (text or "").casefold()).strip()


def haversine_km(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    rlat1, rlat2 = math.radians(lat1), math.radians(lat2)
    dlat, dlon = math.radians(lat2 - lat1), math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(rlat1) * math.cos(rlat2) * math.sin(dlon / 2) ** 2
    return 2 * 6371.0 * math.asin(math.sqrt(a))


# ------------------------------------------------------------------ inputs


def load_report_files(paths: list[Path]) -> list[tuple[Path, dict]]:
    files: list[tuple[Path, dict]] = []
    for path in paths:
        data = json.loads(path.read_text(encoding="utf-8"))
        reports = data.get("reports", []) if isinstance(data, dict) else data
        if not isinstance(reports, list):
            raise SystemExit(f"{path}: 'reports' must be a list")
        for report in reports:
            files.append((path, report))
    return files


def read_districts(paths: list[Path]) -> list[str]:
    """Districts the sweep searched (report meta), for the fallback."""
    districts: set[str] = set()
    for path in paths:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            districts.update(data.get("meta", {}).get("districts_searched") or [])
    return sorted(districts)


def report_sources(paths: list[Path]) -> list[dict]:
    out = []
    for path in paths:
        entry = {"path": str(path.relative_to(PROJECT_ROOT))}
        if "fixtures" in path.parts:
            entry["fixture"] = True
        out.append(entry)
    return out


def validate(report: dict, path: Path) -> None:
    problems = [key for key in ("date", "areas", "publisher", "url") if not report.get(key)]
    if problems:
        raise SystemExit(f"{path.name}: report missing {', '.join(problems)}: {report}")
    date.fromisoformat(report["date"])  # raises on bad format


# --------------------------------------------------------------- geocoding


GEOCODE_CONFIDENCE = {
    "suburb": "area", "neighbourhood": "area", "neighborhood": "area",
    "quarter": "area", "village": "area", "hamlet": "area",
    "residential": "area", "island": "area", "town": "area",
    "city_district": "area", "city": "city", "municipality": "city",
}
GEOCODE_CONFIDENCE_ROAD = "street"


def confidence_for(hit: dict | None) -> str | None:
    if hit is None:
        return None
    if str(hit.get("category") or "") == "highway":
        return GEOCODE_CONFIDENCE_ROAD
    kind = str(hit.get("addresstype") or hit.get("type") or "").lower()
    return GEOCODE_CONFIDENCE.get(kind, "area" if kind else None)


def is_neighbourhood_hit(hit: dict | None) -> bool:
    """Task 27b fix 2 gate: a place-level hit. Highways are not places, and
    LGA/boundary hits are excluded (the LGA-level exclusion) -- a fallback
    must land on a neighbourhood, not a whole LGA."""
    if hit is None:
        return False
    category, _kind = geocode.hit_kind(hit)
    if category in ("highway", "boundary"):
        return False
    return geocode.is_place_hit(hit)


def district_fallback_queries(area: str, known_districts: list[str]) -> list[str]:
    """Task 27b fix 2: retry candidates for a failed full name -- first the
    text after the last comma, then known district names inside the string
    (longest first). A district immediately followed by a route word is part
    of a route name ("Badagry Expressway"), not the district, so it is
    skipped."""
    candidates: list[str] = []
    if "," in area:
        tail = area.rsplit(",", 1)[1].strip()
        if tail:
            candidates.append(tail)
    normed = norm_name(area)
    for district in sorted(set(known_districts), key=len, reverse=True):
        nd = norm_name(district)
        if not nd or nd == normed:
            continue  # already tried as the full name
        for m in re.finditer(rf"\b{re.escape(nd)}\b", normed):
            rest = normed[m.end():].strip()
            next_word = rest.split()[0] if rest else ""
            if ROUTE_AFTER_RE.match(next_word):
                continue
            candidates.append(district)
            break
    seen: list[str] = []
    for cand in candidates:
        if cand not in seen:
            seen.append(cand)
    return seen


def geocode_areas(areas: list[str], extra_districts: list[str]) -> tuple[dict[str, dict | None], dict[str, str]]:
    """Full names first; failures are retried with their district part. The
    fallback query is recorded per area in the second dict."""
    cache = geocode.load_cache()
    results: dict[str, dict | None] = {}
    fallbacks: dict[str, str] = {}
    for area in areas:
        hit = geocode.geocode(area, geocode.LAGOS_BBOX, cache=cache)
        results[area] = hit
        where = f"{hit['lon']:.4f},{hit['lat']:.4f}" if hit else "not found"
        print(f"  geocode {area!r} -> {where}", flush=True)
    known = set(extra_districts)
    for area in areas:
        hit = results.get(area)
        if hit is not None and confidence_for(hit) in ("area", "city"):
            known.add(area)
    for area in areas:
        if results.get(area) is not None:
            continue
        for query in district_fallback_queries(area, sorted(known)):
            cand = geocode.geocode(query, geocode.LAGOS_BBOX, cache=cache)
            if cand is not None and is_neighbourhood_hit(cand):
                results[area] = cand
                fallbacks[area] = query
                print(f"  fallback {area!r} via {query!r} -> "
                      f"{cand['lon']:.4f},{cand['lat']:.4f} (neighbourhood)",
                      flush=True)
                break
    geocode.save_cache(cache, geocode.DEFAULT_CACHE)
    return results, fallbacks


# ------------------------------------------------------------------ grouping


def areas_overlap(a: set[str], b: set[str], geocoded: dict[str, dict | None]) -> bool:
    for name_a in a:
        for name_b in b:
            if norm_name(name_a) == norm_name(name_b) and norm_name(name_a):
                return True
            hit_a, hit_b = geocoded.get(name_a), geocoded.get(name_b)
            if hit_a and hit_b:
                if haversine_km(hit_a["lon"], hit_a["lat"], hit_b["lon"], hit_b["lat"]) <= AREA_OVERLAP_KM:
                    return True
    return False


def group_reports(reports: list[dict]) -> list[list[dict]]:
    """Union-find: same date, or +/-1 day with non-exact confidence and
    overlapping areas."""
    parent = list(range(len(reports)))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def union(i: int, j: int) -> None:
        parent[find(i)] = find(j)

    for i in range(len(reports)):
        for j in range(i + 1, len(reports)):
            r1, r2 = reports[i], reports[j]
            d1, d2 = date.fromisoformat(r1["date"]), date.fromisoformat(r2["date"])
            same_day = d1 == d2
            adjacent = abs((d1 - d2).days) <= 1
            non_exact = (r1.get("date_confidence") != "exact"
                         or r2.get("date_confidence") != "exact")
            overlap = areas_overlap(set(r1["areas"]), set(r2["areas"]), r1["_geocode"])
            if same_day or (adjacent and non_exact and overlap):
                union(i, j)

    groups: dict[int, list[dict]] = {}
    for i, report in enumerate(reports):
        groups.setdefault(find(i), []).append(report)
    return sorted(groups.values(), key=lambda g: min(r["date"] for r in g))


def day_date(reports: list[dict]) -> date:
    """Earliest date of the most confident reports in the group."""
    best = min(DATE_CONFIDENCE_ORDER.get(r.get("date_confidence"), 3) for r in reports)
    candidates = [r for r in reports
                  if DATE_CONFIDENCE_ORDER.get(r.get("date_confidence"), 3) == best]
    return min(date.fromisoformat(r["date"]) for r in candidates)


# --------------------------------------------------------------- rain / match


class RainHistory:
    def __init__(self) -> None:
        data = json.loads(RAIN_HISTORY.read_text(encoding="utf-8"))
        self.dates = {d: i for i, d in enumerate(data["dates"])}
        self.series = data["series"]
        self.cells = {c["id"]: c for c in data["meta"]["cells"]}

    def cell_totals(self, day: date) -> dict[str, float | None]:
        i = self.dates.get(day.isoformat())
        if i is None:
            return {}
        return {cell_id: values["total_mm"][i]
                for cell_id, values in self.series.items()}

    def cell_values(self, day: date) -> tuple[dict, dict] | None:
        """Per-cell (daily total, max 30-min rate) for a day, or None."""
        i = self.dates.get(day.isoformat())
        if i is None:
            return None
        return (
            {cell_id: values["total_mm"][i]
             for cell_id, values in self.series.items()},
            {cell_id: values["max_30min_mm_h"][i]
             for cell_id, values in self.series.items()},
        )

    def cell_of(self, lon: float, lat: float) -> dict | None:
        best, best_d = None, None
        for cell in self.cells.values():
            d = (cell["lon"] - lon) ** 2 + (cell["lat"] - lat) ** 2
            if best_d is None or d < best_d:
                best, best_d = cell, d
        return best


def epoch_for(year: int, epochs: list[int]) -> int:
    return min(epochs, key=lambda e: abs(e - year))


def population_weighted_rain(totals: dict[str, float | None], year: int) -> float | None:
    exposure = json.loads(EXPOSURE_CELLS.read_text(encoding="utf-8"))
    epochs = [int(e) for e in exposure["meta"]["epochs"]]
    epoch = epoch_for(year, epochs)
    numerator = denominator = 0.0
    for cell in exposure["cells"]:
        total = totals.get(cell["id"])
        if total is None:
            continue
        pop = float(cell["population"][str(epoch)])
        numerator += float(total) * pop
        denominator += pop
    if denominator == 0:
        return None
    return numerator / denominator


def local_rain(day: date, rain: RainHistory,
                areas: dict[str, dict | None]) -> dict | None:
    """Task 27b fix 1: rain at the flooded areas' own cells, for the flood
    day and the day before (overnight rain lands on the previous calendar
    day). None when the day has no geocoded area or no IMERG coverage."""
    hits = [hit for hit in areas.values() if hit]
    if not hits:
        return None
    cells: dict[str, dict] = {}
    for hit in hits:
        cell = rain.cell_of(hit["lon"], hit["lat"])
        if cell is not None:
            cells[cell["id"]] = cell
    if not cells:
        return None
    today = rain.cell_values(day)
    if today is None:
        return None
    prev = rain.cell_values(day - timedelta(days=1))
    day_totals, day_rates = today
    prev_totals, prev_rates = prev if prev else ({}, {})

    def stats(totals: dict) -> dict:
        values = [totals[c] for c in cells if totals.get(c) is not None]
        if not values:
            return {"max_total_mm": None, "median_total_mm": None}
        return {"max_total_mm": round(max(values), 2),
                "median_total_mm": round(median(values), 2)}

    sums_2d: list[float] = []
    for cell_id in cells:
        parts = [t for t in (day_totals.get(cell_id), prev_totals.get(cell_id))
                 if t is not None]
        if parts:
            sums_2d.append(sum(parts))
    rates = [r for cell_id in cells
             for r in (day_rates.get(cell_id), prev_rates.get(cell_id))
             if r is not None]
    return {
        "n_areas_geocoded": len(hits),
        "n_cells": len(cells),
        "flood_day": {"date": day.isoformat(), **stats(day_totals)},
        "previous_day": {"date": (day - timedelta(days=1)).isoformat(),
                         **stats(prev_totals)},
        "local_max_2d_mm": round(max(sums_2d), 2) if sums_2d else None,
        "max_30min_mm_h_2d": round(max(rates), 2) if rates else None,
    }


def rain_signature(day: date, rain: RainHistory,
                   areas: dict[str, dict | None]) -> dict:
    totals = rain.cell_totals(day)
    values = [v for v in totals.values() if v is not None]
    sig: dict = {"date_covered": bool(totals)}
    if not values:
        sig.update({
            "aoi_mean_mm": None, "wettest_cell": None,
            "cells_ge_50mm": None, "pop_weighted_rain_mm": None,
            "area_cells": {},
            "local": None,
            "note": "no IMERG daily history for this date",
        })
        return sig
    wettest_id = max(totals, key=lambda c: totals[c] or -1.0)
    wettest_cell = rain.cells[wettest_id]
    area_cells = {}
    for name, hit in areas.items():
        if not hit:
            continue
        cell = rain.cell_of(hit["lon"], hit["lat"])
        area_cells[name] = {
            "cell_id": cell["id"] if cell else None,
            "place": cell.get("place") if cell else None,
            "total_mm": totals.get(cell["id"]) if cell else None,
        }
    sig.update({
        "aoi_mean_mm": round(sum(values) / len(values), 2),
        "wettest_cell": {
            "id": wettest_id,
            "mm": totals[wettest_id],
            "place": wettest_cell.get("place"),
        },
        "cells_ge_50mm": sum(1 for v in values if v >= 50.0),
        "pop_weighted_rain_mm": round(population_weighted_rain(totals, day.year), 2),
        "area_cells": area_cells,
        "local": local_rain(day, rain, areas),
    })
    return sig


def match_candidate(day: date) -> dict | None:
    ranked = json.loads(CATALOG_RANKED.read_text(encoding="utf-8"))
    best = None
    for cand in ranked.get("candidates", []):
        start = date.fromisoformat(cand["start"])
        end = date.fromisoformat(cand["end"])
        distance = max((start - day).days, (day - end).days, 0)
        if distance > 1:
            continue
        key = (distance, cand.get("pwr_rank") or 10**9)
        if best is None or key < best[0]:
            best = (key, cand)
    if best is None:
        return None
    cand = best[1]
    return {"candidate_rank": cand.get("pwr_rank"),
            "start": cand["start"], "end": cand["end"]}


def tier_a_event(day: date) -> str | None:
    if not EVENTS_DIR.is_dir():
        return None
    for event_dir in sorted(EVENTS_DIR.iterdir()):
        path = event_dir / "event.json"
        if not path.is_file():
            continue
        try:
            event = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        try:
            window_start = date.fromisoformat(event["window"]["start"][:10])
            window_end = date.fromisoformat(event["window"]["end"][:10])
        except (KeyError, ValueError):
            continue
        # the event folder id carries the flood date; accept the window too
        if event_dir.name == f"lagos-{day.isoformat()}":
            return event.get("id") or event_dir.name
        if window_start <= day <= window_end and event.get("status") != "draft":
            return event.get("id") or event_dir.name
    return None


# --------------------------------------------------------------- promotion


def report_text(report: dict) -> str:
    return " ".join(filter(None, [
        report.get("impacts"), report.get("quote"), report.get("cause_quote"),
        report.get("cause_who"),
    ]))


def find_named_structure(text: str) -> str | None:
    """Task 27b fix 3: the matched named-structure text, or None. A generic
    road/street/drain mention does not count."""
    if not text:
        return None
    for pattern in (NAMED_STRUCTURE_RE, DRAIN_SYSTEM_NUMBER_RE,
                    NAMED_ROAD_PROJECT_RE):
        match = pattern.search(text)
        if match:
            return match.group(0).strip()
    return None


def promote_day(reports: list[dict]) -> tuple[bool, list[str], str | None]:
    """docs/INTAKE_PLAN.md decision 3, with the Task 27b fixes 3 and 4.
    Returns (promote, reasons, deaths_note)."""
    reasons: list[str] = []
    outlets = {r.get("publisher") for r in reports if r.get("publisher")}
    if len(outlets) >= 3:
        reasons.append(f"three_independent_outlets ({len(outlets)})")

    # deaths (fix 4): scan every report of the day; the official/named
    # attribution may sit in the same report or any other of the same day.
    official_report = next((r for r in reports
                            if r.get("cause_attributed_by") == "official"
                            or OFFICIAL_WORDS.search(report_text(r))), None)
    death_hits: list[tuple[dict, str, bool]] = []
    for report in reports:
        text = report_text(report)
        match = DEATH_WORDS.search(text)
        if match:
            same_report_official = (
                report.get("cause_attributed_by") == "official"
                or bool(OFFICIAL_WORDS.search(text)))
            death_hits.append((report, match.group(0), same_report_official))
    deaths_note = None
    if death_hits and (official_report is not None
                       or any(hit[2] for hit in death_hits)):
        reasons.append("deaths_reported_by_official_or_named_source")
        parts = [f"'{word}' in {report.get('publisher')} ({report.get('url')})"
                 for report, word, _ in death_hits]
        if any(hit[2] for hit in death_hits):
            attribution = "official/named source in the same report"
        else:
            attribution = (f"official attribution in "
                          f"{official_report.get('publisher')} "
                          f"({official_report.get('url')})")
        deaths_note = "; ".join(parts) + " -- " + attribution

    # official named structure (fix 3): an official cause attribution with
    # a human cause tag whose cause quote names a physical structure.
    # Each match is listed with its matched text.
    for report in reports:
        if report.get("cause_attributed_by") != "official":
            continue
        human_tags = [c for c in report.get("causes") or []
                      if c not in NATURAL_CAUSE_TAGS]
        if not human_tags:
            continue
        cause_text = " ".join(filter(None, [report.get("cause_quote"),
                                            report.get("cause_who")]))
        structure = find_named_structure(cause_text)
        if structure:
            reasons.append(f"official_named_structure "
                           f"({report.get('publisher')}: '{structure}'; "
                           f"cause tag {human_tags[0]})")

    # dedupe, keep order
    seen: list[str] = []
    for reason in reasons:
        if reason not in seen:
            seen.append(reason)
    return bool(seen), seen, deaths_note


# --------------------------------------------------------------------- main


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--reports", nargs="*", type=Path,
                        help="report files (default: events/intake/reports_*.json, "
                             "else pipeline/intake/fixtures/reports_*.json)")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()

    if args.reports:
        paths = args.reports
    else:
        paths = sorted((EVENTS_DIR / "intake").glob("reports_*.json"))
        if paths:
            print(f"input: {len(paths)} pilot report file(s) from events/intake/")
        else:
            paths = sorted(FIXTURES_DIR.glob("reports_*.json"))
            if not paths:
                raise SystemExit("no events/intake/reports_*.json and no fixtures")
            print("input: no pilot files yet, using fixtures:")
            for path in paths:
                print(f"  {path.relative_to(PROJECT_ROOT)}")

    pairs = load_report_files(paths)
    reports = []
    for path, report in pairs:
        validate(report, path)
        report = dict(report)
        report.setdefault("date_confidence", "approx")
        reports.append(report)
    if not reports:
        raise SystemExit("no reports found")

    areas_all = sorted({a for r in reports for a in r["areas"]})
    print(f"\ngeocoding {len(areas_all)} area(s) (Nominatim, 1 req/s, cached),\n"
          "with a district fallback for full names that fail:")
    geocoded, fallbacks = geocode_areas(areas_all, read_districts(paths))
    for report in reports:
        report["_geocode"] = geocoded

    print("\ngrouping reports into flood days:")
    groups = group_reports(reports)
    rain = RainHistory()

    days = []
    for group in groups:
        day = day_date(group)
        area_names: list[str] = []
        for report in group:
            for area in report["areas"]:
                if area not in area_names:
                    area_names.append(area)
        areas_out = []
        for name in area_names:
            hit = geocoded.get(name)
            areas_out.append({
                "name": name,
                "lon": hit["lon"] if hit else None,
                "lat": hit["lat"] if hit else None,
                "confidence": ("neighbourhood" if name in fallbacks
                               else confidence_for(hit)),
                "geocoded_from": fallbacks.get(name),
                "display_name": hit.get("display_name") if hit else None,
            })
        areas_by_name = {a["name"]: geocoded.get(a["name"]) for a in areas_out}
        candidate = match_candidate(day)
        promote, reasons, deaths_note = promote_day(group)
        days.append({
            "date": day.isoformat(),
            "areas": areas_out,
            "n_sources": len({r.get("url") for r in group}),
            "n_outlets": len({r.get("publisher") for r in group}),
            "impacts": [r.get("impacts") for r in group if r.get("impacts")],
            "causes": sorted({c for r in group for c in r.get("causes") or []}),
            "rain": rain_signature(day, rain, areas_by_name),
            "candidate_rank": candidate["candidate_rank"] if candidate else None,
            "tier_a_event_id": tier_a_event(day),
            "promote": promote,
            "promote_reasons": reasons,
            "deaths_note": deaths_note,
            "reports": [
                {
                    "url": r.get("url"),
                    "publisher": r.get("publisher"),
                    "published_at": r.get("published_at"),
                    "read_status": r.get("read_status"),
                    "date": r.get("date"),
                    "date_confidence": r.get("date_confidence"),
                    "quote": r.get("quote"),
                    "causes": r.get("causes") or [],
                    "cause_attributed_by": r.get("cause_attributed_by"),
                    "cause_who": r.get("cause_who"),
                    "cause_quote": r.get("cause_quote"),
                }
                for r in group
            ],
        })
        print(f"  {day}  {len(group)} report(s), areas: {', '.join(area_names)}")

    search_coverage = None
    if SEARCH_LOG.is_file():
        log_data = json.loads(SEARCH_LOG.read_text(encoding="utf-8"))
        entries = log_data.get("entries", [])
        search_coverage = []
        for entry in entries:
            if not isinstance(entry, dict) or "year_month" not in entry:
                continue
            compact = {k: v for k, v in entry.items() if k != "queries"}
            compact["n_queries"] = len(entry.get("queries") or [])
            search_coverage.append(compact)
        search_coverage.sort(key=lambda e: e["year_month"])
    else:
        print(f"\nnote: {SEARCH_LOG.relative_to(PROJECT_ROOT)} not found; "
              "search coverage per year-month is unknown until Task 26 runs")

    payload = {
        "meta": {
            "method": (
                "Tier B flood-day catalog: reports grouped by date (same day, or "
                "+/-1 day with non-exact date_confidence and overlapping areas); "
                "areas geocoded with pipeline/geocode.py (Nominatim, 1 req/s, "
                "cached), with a district fallback (text after the last comma, "
                "or a known district inside the string) at confidence "
                "'neighbourhood' for full names that fail; rain signature from "
                "events/rain_history_grid_daily.json (IMERG WAT daily totals), "
                "including the local block: rain at the flooded areas' own "
                "cells for the flood day and the day before; population-"
                "weighted rain as in catalog_ranked.json (GHSL epoch nearest "
                "the flood year); candidates matched from catalog_ranked.json "
                "within +/-1 day; promotion per docs/INTAKE_PLAN.md decision 3"
            ),
            "grouping": {
                "same_date": True,
                "adjacent_days": "+/-1 day only when a date_confidence is not 'exact' and areas overlap",
                "area_overlap": f"same normalized name or geocoded points within {AREA_OVERLAP_KM} km",
            },
            "geocoding": {
                "full_name": "pipeline/geocode.py (Nominatim, 1 req/s, cached)",
                "district_fallback": "for a failed full name: retry with the text after the last comma, or a known district name inside the string; a district followed by a route word is part of a route name, not the district",
                "fallback_confidence": "neighbourhood",
                "lga_exclusion": "fallbacks accept place-level hits only; LGA/boundary and highway hits are excluded",
                "geocoded_from": "the fallback query that resolved the area (null for full-name hits)",
            },
            "promotion_rule": {
                "deaths": "a death word (swept away, drowned, died, dead, killed, bodies, ...) in any report of the day, with the official or named attribution in that report or any other report of the same day (NEMA, LASEMA, LASTMA, police, named officials); deaths_note records the sources",
                "outlets": "at least 3 independent outlets (distinct publishers)",
                "structure": "an official cause attribution with a human cause tag (not heavy_rain/lagoon_tide/dam_release) whose cause quote names a physical structure: canal, channel, collector, drain system number, bridge, culvert, outfall or named road project",
            },
            "generated_at": utc_now_iso(),
            "sources": report_sources(paths),
            "search_coverage": search_coverage,
            "rain": {
                "source": str(RAIN_HISTORY.relative_to(PROJECT_ROOT)),
                "units": "mm per WAT calendar day",
                "local": "rain at the geocoded areas' own cells: max and median total_mm for the flood day and the day before; local_max_2d_mm = the largest per-cell day + previous-day sum; max_30min_mm_h_2d = the highest 30-min rate over both days; null when the day has no geocoded area",
                "drainage_signal": f"share of checkable flood days (>= 1 geocoded area and IMERG coverage) with local_max_2d_mm < {DRAINAGE_SIGNAL_MM} mm; the AOI mean is kept as context",
            },
        },
        "days": days,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"\nwrote {args.out} ({len(days)} flood day(s))")

    # --- summary prints
    per_year: dict[int, int] = {}
    low_rain = 0
    for day in days:
        year = int(day["date"][:4])
        per_year[year] = per_year.get(year, 0) + 1
        aoi = day["rain"].get("aoi_mean_mm")
        if aoi is not None and aoi < DRAINAGE_SIGNAL_MM:
            low_rain += 1
    print("\nflood days per year:")
    for year in sorted(per_year):
        print(f"  {year}: {per_year[year]}")
    checkable = [d for d in days
                 if (d["rain"].get("local") or {}).get("local_max_2d_mm") is not None]
    low_local = [d for d in checkable
                 if d["rain"]["local"]["local_max_2d_mm"] < DRAINAGE_SIGNAL_MM]
    share_local = (len(low_local) / len(checkable)) if checkable else None
    print(f"\ndrainage signal: flood days with local_max_2d_mm < "
          f"{DRAINAGE_SIGNAL_MM} mm: {len(low_local)}/{len(checkable)}"
          + (f" ({share_local:.0%})" if share_local is not None else ""))
    print(f"  ({len(days) - len(checkable)} day(s) excluded from the signal: "
          "no geocoded area or no IMERG daily history)")
    share_aoi = (low_rain / len(days)) if days else None
    print(f"context (the old AOI-mean signal): AOI mean rain < "
          f"{DRAINAGE_SIGNAL_MM} mm on {low_rain}/{len(days)} day(s)"
          + (f" ({share_aoi:.0%})" if share_aoi is not None else ""))
    n_promote = sum(1 for d in days if d["promote"])
    print(f"promote to Tier A: {n_promote}/{len(days)}")


if __name__ == "__main__":
    main()
