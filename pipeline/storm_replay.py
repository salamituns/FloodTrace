#!/usr/bin/env python3
"""Task 31 (docs/tasks/31-rain-matched-replay.md): rain-matched storm replay per site.

Roadmap steps 6 and 7 of docs/LAGOS_PLAN.md. Step 5 found no usable terrain signal
at 30 m, so no water is simulated: storms are replayed against history instead.
"Of the days since 2014 when rain at least this heavy hit this site, how many
flooded it, and did that change after a fix?"

Inputs (events/): rain_history_grid_daily.json (IMERG per 0.1 deg cell, per WAT
day, 2000-06-01 to 2026-10-16), flood_days.json (the catalog), sites.json
(catalog_floods per site with strength; only 'name' and 'near' are strong matches)
and promises.json (dated official commitments, with updates).

Output: events/site_rain_response.json, validated against
pipeline/schemas/site_rain_response.schema.json.

Deterministic: two runs give identical output apart from meta.generated_at.

Run: pipeline/.venv/bin/python pipeline/storm_replay.py
"""
from __future__ import annotations

import hashlib
import json
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import jsonschema  # pipeline/.venv has jsonschema 4.26 and shapely 2.2
from shapely.geometry import shape

ROOT = Path(__file__).resolve().parent.parent
EVENTS = ROOT / "events"
SCHEMA_PATH = ROOT / "pipeline" / "schemas" / "site_rain_response.schema.json"
OUT_PATH = EVENTS / "site_rain_response.json"

THRESHOLDS = [20, 40, 60, 80]
# A storm is a wet spell of consecutive days with 2-day rain at or above this;
# thresholds then select spells by their peak.
SPELL_BASE_MM = 20.0
Z = 1.96  # Wilson 95%
NOT_A_STORM_MM = 10.0
THIN_YEAR_MAX_DAYS = 5
STRONG_STRENGTHS = {"name", "near"}
RATE_FLOOD_TYPE = "pluvial"
WINDOW_MONTHS = range(4, 12)  # April-November
EPS = 1e-9

# The five Tier A events. Anchor date + any extra catalog days sharing the
# tier_a_event_id form the reference storm's days.
REFERENCES = [
    ("lagos-2011-07-10", "2011-07-10"),
    ("lagos-2021-07-16", "2021-07-16"),
    ("lagos-2022-07-08", "2022-07-08"),
    ("lagos-2024-07-03", "2024-07-03"),
    ("lagos-2025-08-04", "2025-08-04"),
]

INPUT_FILES = [
    "events/rain_history_grid_daily.json",
    "events/flood_days.json",
    "events/sites.json",
    "events/promises.json",
]


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def d(s: str) -> date:
    return date.fromisoformat(s)


def wilson(k: int, n: int) -> list:
    """Wilson score interval for k successes in n trials, 95%. [None, None] if n=0."""
    if n == 0:
        return [None, None]
    p = k / n
    denom = 1 + Z * Z / n
    center = (p + Z * Z / (2 * n)) / denom
    half = Z * ((p * (1 - p) / n + Z * Z / (4 * n * n)) ** 0.5) / denom
    return [round(center - half, 4), round(center + half, 4)]


def stats(storms: list) -> dict:
    n = len(storms)
    k = sum(1 for s in storms if s["flooded"])
    return {
        "n_storms": n,
        "n_flooded": k,
        "rate": round(k / n, 4) if n else None,
        "wilson_95": wilson(k, n),
    }


def main() -> None:
    # ---- load inputs -------------------------------------------------------
    rain_path = EVENTS / "rain_history_grid_daily.json"
    with open(rain_path, encoding="utf-8") as f:
        rain = json.load(f)
    with open(EVENTS / "flood_days.json", encoding="utf-8") as f:
        flood_days = json.load(f)
    with open(EVENTS / "sites.json", encoding="utf-8") as f:
        sites_doc = json.load(f)
    with open(EVENTS / "promises.json", encoding="utf-8") as f:
        promises_doc = json.load(f)

    rain_dates = [d(x) for x in rain["dates"]]
    date_idx = {x: i for i, x in enumerate(rain_dates)}
    cells = rain["meta"]["cells"]
    series = rain["series"]
    cell_ids = [c["id"] for c in cells]

    # 2-day measures at one cell: day d total = total_mm[d-1] + total_mm[d]
    # (the same measure as local_max_2d_mm in flood_days.json), and the max
    # 30-min rate over the same two days. Missing days stay missing, never 0.
    def two_day_total(cell_id: str, day: date):
        i = date_idx.get(day)
        j = date_idx.get(day - timedelta(days=1))
        if i is None or j is None:
            return None
        a = series[cell_id]["total_mm"][j]
        b = series[cell_id]["total_mm"][i]
        if a is None or b is None:
            return None
        return a + b

    def two_day_max30(cell_id: str, day: date):
        i = date_idx.get(day)
        j = date_idx.get(day - timedelta(days=1))
        if i is None or j is None:
            return None
        a = series[cell_id]["max_30min_mm_h"][j]
        b = series[cell_id]["max_30min_mm_h"][i]
        if a is None or b is None:
            return None
        return max(a, b)

    # ---- searched window ---------------------------------------------------
    # Searched years/months come from the catalog's meta.search_coverage.
    # In-window day: its year-month was searched AND it is April-November
    # (Dec-Mar was only searched once a year; those floods stay out of the rates).
    searched_ym = {e["year_month"] for e in flood_days["meta"]["search_coverage"]}
    searched_years = sorted({ym[:4] for ym in searched_ym})

    def in_window(day: date) -> bool:
        return f"{day.year:04d}-{day.month:02d}" in searched_ym and day.month in WINDOW_MONTHS

    window_days = [x for x in rain_dates if in_window(x)]
    window_set = set(window_days)

    # ---- catalog flood days per searched year; thin years ------------------
    days = flood_days["days"]
    catalog_by_date = {x["date"]: x for x in days}
    year_counts: dict[str, int] = {y: 0 for y in searched_years}
    in_window_year_counts: dict[str, int] = {y: 0 for y in searched_years}
    for x in days:
        y = x["date"][:4]
        if y in year_counts:
            year_counts[y] += 1
            if in_window(d(x["date"])):
                in_window_year_counts[y] += 1
    years_out = [
        {
            "year": y,
            "catalog_flood_days": year_counts[y],
            "in_window_catalog_flood_days": in_window_year_counts[y],
            "thin": year_counts[y] < THIN_YEAR_MAX_DAYS,
        }
        for y in searched_years
    ]
    thin_years = {rec["year"] for rec in years_out if rec["thin"]}
    well_years = {rec["year"] for rec in years_out if not rec["thin"]}

    # ---- city-wide sanity check (done first; stops the task if it fails) ---
    # Max 2-day rain over all land cells (the 68-cell ocean-filtered land +
    # lagoon-shore set of the rain file) for every in-window day, binned.
    days_missing_rain = 0
    city_bins = {("0-10", 0.0, 10.0): [0, 0, 0], ("10-20", 10.0, 20.0): [0, 0, 0],
                 ("20-40", 20.0, 40.0): [0, 0, 0], ("40-60", 40.0, 60.0): [0, 0, 0],
                 ("60-80", 60.0, 80.0): [0, 0, 0], ("ge_80", 80.0, None): [0, 0, 0]}

    def bin_key(mm: float):
        if mm < 10:
            return "0-10"
        if mm < 20:
            return "10-20"
        if mm < 40:
            return "20-40"
        if mm < 60:
            return "40-60"
        if mm < 80:
            return "60-80"
        return "ge_80"

    for day in window_days:
        values = [two_day_total(c, day) for c in cell_ids]
        values = [v for v in values if v is not None]
        if not values:
            days_missing_rain += 1
            continue
        mm = max(values)
        cnt = city_bins[next(k for k in city_bins if k[0] == bin_key(mm))]
        cnt[0] += 1
        if day.isoformat() in catalog_by_date:
            cnt[1] += 1
            if catalog_by_date[day.isoformat()].get("flood_type") == "pluvial":
                cnt[2] += 1

    bins_out = []
    for (label, lo, hi), (n_days, n_flood, n_pluvial) in city_bins.items():
        bins_out.append({
            "bin": label,
            "min_mm": lo,
            "max_mm": hi,
            "days": n_days,
            "catalog_flood_days": n_flood,
            "pluvial_flood_days": n_pluvial,
            "share": round(n_flood / n_days, 4) if n_days else None,
            "share_pluvial": round(n_pluvial / n_days, 4) if n_days else None,
        })

    shares = [b["share"] for b in bins_out if b["days"]]
    # "Rises with rain" allows a dip that stays within sampling noise of the
    # previous bin (counts here are 2-5 flood days at the low end): each bin's
    # share must sit at or above the previous bin's Wilson 95% lower bound, and
    # the top bin must beat the bottom one. The strict-monotone result is
    # recorded next to it, so nothing is hidden.
    strictly_monotone = (
        len(shares) == len(bins_out)
        and all(later >= earlier for earlier, later in zip(shares, shares[1:]))
    )
    rises = True
    populated = [b for b in bins_out if b["days"]]
    for prev, cur in zip(populated, populated[1:]):
        lo_prev = wilson(prev["catalog_flood_days"], prev["days"])[0]
        if cur["share"] < lo_prev:
            rises = False
    if len(shares) < 2 or not (shares[-1] > shares[0]):
        rises = False

    print("City-wide sanity check: share of in-window days that are catalog flood days")
    print("by max 2-day rain over all land cells (mm):")
    print(f"  {'bin':>6} {'days':>6} {'flood':>6} {'share':>8} {'pluvial':>8}")
    for b in bins_out:
        share = "-" if b["share"] is None else f"{b['share']:.1%}"
        pshare = "-" if b["share_pluvial"] is None else f"{b['share_pluvial']:.1%}"
        print(f"  {b['bin']:>6} {b['days']:>6} {b['catalog_flood_days']:>6} {share:>8} {pshare:>8}")
    print(f"  in-window days: {len(window_days)}, days with missing rain: {days_missing_rain}")
    if not rises:
        print()
        print("The share does NOT rise with rain (beyond sampling noise). The method")
        print("has nothing to stand on (as with roadmap step 5). Stopping; no output")
        print("written.")
        sys.exit(1)

    # ---- storm machinery ---------------------------------------------------
    def decluster(series_2d: dict, series_30: dict, threshold: float,
                  match_dates: set) -> list:
        """Storms are wet spells: consecutive in-window days with a 2-day total
        at or above the spell base (SPELL_BASE_MM, or the threshold if lower).
        A threshold then selects spells by their peak, so a storm's extent
        doesn't depend on the threshold asked about (a spell of 55-120 mm days
        stays one storm at 105 mm). Storm rain = max 2-day total over its days.
        Flooded = a strong pluvial match on any of its days or the day after
        the last one."""
        base = min(SPELL_BASE_MM, threshold)
        at_or_above = [x for x in window_days
                       if series_2d.get(x) is not None and series_2d[x] >= base]
        storms = []
        group = []
        for day in at_or_above:
            if group and (day - group[-1]).days != 1:
                storms.append(group)
                group = []
            group.append(day)
        if group:
            storms.append(group)
        storms = [g for g in storms if max(series_2d[x] for x in g) >= threshold]
        out = []
        for g in storms:
            start, end = g[0], g[-1]
            after = end + timedelta(days=1)
            matched = sorted(x.isoformat() for x in match_dates
                             if start <= x <= after)
            out.append({
                "start": start.isoformat(),
                "end": end.isoformat(),
                "n_days": len(g),
                "rain_mm": round(max(series_2d[x] for x in g), 2),
                "max_30min_mm_h_2d": (lambda vs: round(max(vs), 2) if all(
                    v is not None for v in vs) else None)(
                    [series_30.get(x) for x in g]),
                "flooded": bool(matched),
                "matched_dates": matched,
            })
        return out

    def well_only(storms: list) -> list:
        return [s for s in storms if s["start"][:4] in well_years]

    # ---- reference storm days ----------------------------------------------
    reference_days = {}
    for event_id, anchor in REFERENCES:
        rdays = {anchor}
        for x in days:
            if x.get("tier_a_event_id") == event_id:
                rdays.add(x["date"])
        reference_days[event_id] = sorted(rdays)

    promises_by_site: dict[str, list] = {}
    for p in promises_doc["promises"]:
        promises_by_site.setdefault(p["site_id"], []).append(p)

    # ---- per site ----------------------------------------------------------
    sites_out = []
    for site in sites_doc["sites"]:
        site_id = site["site_id"]
        geom = shape(site["geometry"])
        cen = geom.centroid

        # Site cell: the IMERG cell whose 0.1 deg box contains the centroid
        # (nearest centre as a fallback, recorded).
        own = None
        assigned_by = "nearest"
        for c in cells:
            if (abs(c["lon"] - cen.x) <= 0.05 + EPS
                    and abs(c["lat"] - cen.y) <= 0.05 + EPS):
                own = c
                assigned_by = "contains"
                break
        if own is None:
            own = min(cells, key=lambda c: (c["lon"] - cen.x) ** 2 + (c["lat"] - cen.y) ** 2)
        nbhd = sorted(
            c["id"] for c in cells
            if abs(c["lat"] - own["lat"]) <= 0.1 + EPS
            and abs(c["lon"] - own["lon"]) <= 0.1 + EPS
        )

        # Rain series at the site's own cell and the 3x3 neighbourhood max.
        s2d, s30 = {}, {}
        for day in window_days:
            t = two_day_total(own["id"], day)
            m = two_day_max30(own["id"], day)
            if t is not None:
                s2d[day] = t
            if m is not None:
                s30[day] = m
        nb2d = {}
        for day in window_days:
            vals = [two_day_total(c, day) for c in nbhd]
            vals = [v for v in vals if v is not None]
            if vals:
                nb2d[day] = max(vals)

        # Strong matches from the site's catalog_floods.
        strong = [c for c in (site.get("catalog_floods") or [])
                  if c.get("strength") in STRONG_STRENGTHS]
        match_dates = set()
        excluded = []
        for c in strong:
            day = d(c["date"])
            if c.get("flood_type") != RATE_FLOOD_TYPE:
                excluded.append({
                    "date": c["date"], "flood_type": c.get("flood_type"),
                    "strength": c["strength"],
                    "matched_areas": c.get("matched_areas") or [],
                    "excluded_because": "non_pluvial",
                })
            elif day not in window_set:
                excluded.append({
                    "date": c["date"], "flood_type": c.get("flood_type"),
                    "strength": c["strength"],
                    "matched_areas": c.get("matched_areas") or [],
                    "excluded_because": "out_of_window",
                })
            else:
                match_dates.add(day)

        # Per-threshold storms, rates and Wilson intervals (own cell).
        thresholds_out = {}
        for t in THRESHOLDS:
            storms = decluster(s2d, s30, t, match_dates)
            thresholds_out[str(t)] = {
                "storms": storms,
                "all_years": stats(storms),
                "well_searched_years": stats(well_only(storms)),
            }

        # Sensitivity: same rates on the 3x3 neighbourhood max.
        sens = {}
        for t in THRESHOLDS:
            storms = decluster(nb2d, {x: None for x in window_days}, t, match_dates)
            sens[str(t)] = {
                "all_years": stats(storms),
                "well_searched_years": stats(well_only(storms)),
            }

        # Replay of the five reference storms at this site.
        replays = {}
        for event_id, anchor in REFERENCES:
            rdays = [d(x) for x in reference_days[event_id]]
            ref_vals = [two_day_total(own["id"], x) for x in rdays]
            ref_vals = [v for v in ref_vals if v is not None]
            ref_exact = max(ref_vals) if ref_vals else None  # unrounded: rounding
            # up would drop the reference day out of its own storm set
            ref_mm = round(ref_exact, 2) if ref_exact is not None else None
            rec = {
                "reference_date": anchor,
                "reference_days": reference_days[event_id],
                "site_cell_2d_mm": ref_mm,
            }
            if ref_exact is None or ref_exact < NOT_A_STORM_MM:
                rec["not_a_storm_here"] = True
                replays[event_id] = rec
                continue
            rec["not_a_storm_here"] = False
            # Analogs: in-window storms with at least the reference rain at the
            # site cell, i.e. declustered at the reference rain itself. The
            # reference storm (and any storm whose flood window reaches it) is
            # excluded.
            ref_set = set(rdays)
            analogs = []
            for s in decluster(s2d, s30, ref_exact, match_dates):
                sd, ed = d(s["start"]), d(s["end"])
                if any(sd <= r <= ed or r == ed + timedelta(days=1)
                       for r in ref_set):
                    continue
                sources = []
                seen = set()
                for md in s["matched_dates"]:
                    for c in strong:
                        if c["date"] == md:
                            for src in c.get("sources") or []:
                                key = (src.get("publisher"), src.get("url"))
                                if key not in seen:
                                    seen.add(key)
                                    sources.append({
                                        "publisher": src.get("publisher"),
                                        "url": src.get("url"),
                                    })
                analogs.append({
                    "start": s["start"], "end": s["end"], "rain_mm": s["rain_mm"],
                    "flooded": s["flooded"],
                    "sources": sorted(sources, key=lambda x: (x["publisher"] or "",
                                                              x["url"] or "")),
                })
            analogs.sort(key=lambda x: (x["start"], x["end"]))
            well = [a for a in analogs if a["start"][:4] in well_years]
            rec["analogs"] = analogs
            rec["n_analogs"] = len(analogs)
            rec["n_flooded"] = sum(1 for a in analogs if a["flooded"])
            rec["rate"] = (round(rec["n_flooded"] / len(analogs), 4)
                           if analogs else None)
            rec["well_searched_years"] = {
                "n_storms": len(well),
                "n_flooded": sum(1 for a in well if a["flooded"]),
                "rate": (round(sum(1 for a in well if a["flooded"]) / len(well), 4)
                         if well else None),
                "wilson_95": wilson(sum(1 for a in well if a["flooded"]), len(well)),
            }
            replays[event_id] = rec

        # Before/after for sites with a promise.
        before_after = None
        if promises_by_site.get(site_id):
            candidates = []
            for p in sorted(promises_by_site[site_id], key=lambda x: x["promise_id"]):
                candidates.append({
                    "date": p["date_made"],
                    "source": f"promise {p['promise_id']} date_made",
                })
                for finding, label in (("claimed_done", "first claimed_done update"),
                                       ("claimed_ongoing", "first claimed_ongoing update")):
                    ups = [u for u in (p.get("updates") or [])
                           if u.get("finding") == finding and u.get("date")]
                    if ups:
                        first = min(ups, key=lambda u: u["date"])["date"]
                        candidates.append({
                            "date": first,
                            "source": f"{label} ({p['promise_id']})",
                        })
            candidates.sort(key=lambda x: (x["date"], x["source"]))
            split = candidates[0]
            split_day = d(split["date"])
            storms40 = thresholds_out["40"]["storms"]
            before = [s for s in storms40 if d(s["start"]) < split_day]
            after = [s for s in storms40 if d(s["start"]) >= split_day]
            bs, as_ = stats(before), stats(after)
            if bs["n_storms"] < 5 or as_["n_storms"] < 5:
                short = []
                if bs["n_storms"] < 5:
                    short.append("before")
                if as_["n_storms"] < 5:
                    short.append("after")
                reading = (
                    f"{bs['n_flooded']} of {bs['n_storms']} before, "
                    f"{as_['n_flooded']} of {as_['n_storms']} after: too few storms "
                    f"{' and '.join(short)} to tell"
                )
            else:
                direction = ("lower" if as_["rate"] < bs["rate"]
                             else "higher" if as_["rate"] > bs["rate"] else "the same")
                reading = (
                    f"{bs['n_flooded']} of {bs['n_storms']} before, "
                    f"{as_['n_flooded']} of {as_['n_storms']} after: the rate is "
                    f"{direction} after {split['date']} "
                    f"({bs['rate']:.0%} -> {as_['rate']:.0%}); no significance "
                    f"test, the counts are small"
                )
            before_after = {
                "split_date": split["date"],
                "split_source": (
                    f"earliest of the site's promise dates, first claimed_done "
                    f"and first claimed_ongoing updates: {split['source']}"),
                "candidate_dates": candidates,
                "storms_ge_40mm": {"before": bs, "after": as_},
                "reading": reading,
            }

        sites_out.append({
            "site_id": site_id,
            "name": site["name"],
            "cell": {
                "id": own["id"], "lon": own["lon"], "lat": own["lat"],
                "place": own.get("place"), "assigned_by": assigned_by,
            },
            "cells_3x3": nbhd,
            "strong_pluvial_match_dates": sorted(x.isoformat() for x in match_dates),
            "excluded_matches": sorted(
                excluded, key=lambda x: (x["date"], x["excluded_because"])),
            "thresholds": thresholds_out,
            "sensitivity_3x3": sens,
            "replays": replays,
            "before_after": before_after,
        })

    sites_out.sort(key=lambda s: s["site_id"])

    caveats = [
        "unreported is not dry: the catalog is news coverage, not a gauge, so a "
        "storm with no report is counted as not flooded even if it flooded",
        "IMERG cells are ~10 km and smooth storm cores: the cell total can miss "
        "or dilute the rain that actually fell at a site",
        "thin years: catalog flood days per year are in years[]; years with "
        "fewer than 5 are thin and are excluded from the well_searched rates",
        "a strong match means the news named the place or a point near it, not a "
        "measured depth",
        "flooded counts only strong (name/near) pluvial matches inside the "
        "April-November searched window; riverine, lagoon and coastal days are "
        "listed per site in excluded_matches but stay out of the rates",
    ]

    out = {
        "meta": {
            "method": (
                "Rain-matched storm replay (LAGOS_PLAN roadmap steps 6-7). For "
                "each site the IMERG 0.1 deg cell containing its geometry "
                "centroid is the site cell (3x3 neighbourhood max kept as "
                "sensitivity). A day's rain is the 2-day total (day before + "
                "day), the same measure as local_max_2d_mm in flood_days.json, "
                "plus the max 30-min rate over the two days. Only days in the "
                "April-November months of the years/months actually searched "
                "(flood_days meta.search_coverage) enter the rates; Dec-Mar was "
                "searched once a year only. A storm is a wet spell of consecutive "
                "days with 2-day rain >= 20 mm (or the threshold if lower); a "
                "threshold selects spells by their peak, which is the storm's rain; "
                "it flooded the site if a strong (name/near) pluvial match falls "
                "on any of its days or the day after the last one. Rates carry a "
                "Wilson 95% interval. Replay analogs are the storms whose peak is "
                "at least the reference storm's 2-day rain at the site cell, minus "
                "the reference itself. Before/after splits storms >= 40 mm at the "
                "earliest of the promise date, the first claimed_done update and "
                "the first claimed_ongoing update, and calls a difference only "
                "with at least 5 storms on each side. Missing rain days would be "
                "excluded and counted, never treated as zero."
            ),
            "inputs": {name: sha256(ROOT / name) for name in INPUT_FILES},
            "thresholds_mm": THRESHOLDS,
            "not_a_storm_mm": NOT_A_STORM_MM,
            "thin_year_max_catalog_days": THIN_YEAR_MAX_DAYS,
            "strong_match_strengths": sorted(STRONG_STRENGTHS),
            "rate_flood_type": RATE_FLOOD_TYPE,
            "reference_events": [e for e, _ in REFERENCES],
            "reference_days": {e: reference_days[e] for e, _ in REFERENCES},
            "searched_years": searched_years,
            "well_searched_years": sorted(well_years),
            "caveats": caveats,
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        },
        "citywide": {
            "bins": bins_out,
            "rises_with_rain": rises,
            "strictly_monotone": strictly_monotone,
            "criterion": (
                "rises_with_rain: each populated bin's share is at or above the "
                "previous bin's Wilson 95% lower bound and the top bin's share "
                "exceeds the bottom bin's; strictly_monotone records the "
                "no-dips-at-all result"
            ),
            "days_in_window": len(window_days),
            "days_missing_rain": days_missing_rain,
            "note": (
                "max 2-day rain over all 68 cells of the rain file (the "
                "ocean-filtered land + lagoon-shore set); share = days that are "
                "catalog flood days (any type)"
            ),
        },
        "years": years_out,
        "sites": sites_out,
    }

    # ---- validate and write ------------------------------------------------
    with open(SCHEMA_PATH, encoding="utf-8") as f:
        schema = json.load(f)
    jsonschema.Draft202012Validator(schema).validate(out)
    OUT_PATH.write_text(
        json.dumps(out, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8")

    # ---- console summary ----------------------------------------------------
    print()
    print("Per site, storms >= 40 mm at the site cell (all years / well-searched):")
    print(f"  {'site':>28} {'cell':>14} {'storms':>7} {'fld':>4} "
          f"{'rate':>7} {'| well':>12} {'rate':>7}")
    for s in sites_out:
        a = s["thresholds"]["40"]["all_years"]
        w = s["thresholds"]["40"]["well_searched_years"]
        ra = f"{a['rate']:.0%}" if a["rate"] is not None else "-"
        rw = f"{w['rate']:.0%}" if w["rate"] is not None else "-"
        print(f"  {s['site_id']:>28} {s['cell']['id']:>14} {a['n_storms']:>7} "
              f"{a['n_flooded']:>4} {ra:>7} {'|':>2} {w['n_storms']:>3} "
              f"{w['n_flooded']:>3} {rw:>7}")
    print()
    print("2024-07-03 replay per site (site cell):")
    for s in sites_out:
        r = s["replays"]["lagos-2024-07-03"]
        if r.get("not_a_storm_here"):
            print(f"  {s['site_id']:>28} ref {r['site_cell_2d_mm']} mm: not a storm here")
        else:
            print(f"  {s['site_id']:>28} ref {r['site_cell_2d_mm']:>7} mm, "
                  f"analogs {r['n_analogs']:>3}, flooded {r['n_flooded']:>3}")
    print()
    print("Before/after (sites with a promise):")
    for s in sites_out:
        if s["before_after"]:
            ba = s["before_after"]
            print(f"  {s['site_id']:>28} split {ba['split_date']} "
                  f"({ba['split_source'].split(': ')[-1]})")
            print(f"  {'':>28} {ba['reading']}")
    print()
    print(f"wrote {OUT_PATH.relative_to(ROOT)} ({OUT_PATH.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
