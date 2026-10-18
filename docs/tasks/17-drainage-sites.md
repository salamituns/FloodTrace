# Task 17 — pin down the drains, canals and works that sources blamed

Context: `docs/LAGOS_PLAN.md` → "Reported causes" and "Built-up change". 1 km built-up change doesn't explain where Lagos floods.
The human causes that sources name are street-scale (a blocked collector, buildings on a drainage channel, a dammed waterway).
We will check each one on dated before/after imagery (Task 18, Droid). Your job is to say **exactly what and where** to look at,
and **when** the alleged change happened. Research only: no imagery and no interpretation of images.

## Sites (from `events/*/evidence.geojson`, features with human `causes`)
| site_id | event · evidence ids | claim |
|---|---|---|
| `alpha-beach-156` | 2024 ev-003 | buildings/developers blocked "System 156" on the Alpha Beach Road corridor (Wahab) |
| `agungi-collector` | 2024 ev-001, ev-064 | collector too small; Agungi road development outgrew the drainage |
| `olopomeji` | 2024 ev-061 | water paths blocked by refuse (which Olopomeji: Ebute Metta/Yaba?) |
| `ikorodu-dammed` | 2025 ev-005 | a contractor dammed the downstream of a waterway for construction: which waterway, which project, which contractor |
| `agric-bridge` | 2025 ev-001 | bridge construction at Agric, Ikorodu |
| `ijede-drain` | 2025 ev-002 | abandoned drainage system at Ijede |
| `oko-oba-canal` | 2022 ev-014 | canal by old Oko-Oba Road (Agege) overflowed; was it under works? |
| `alapere-ogudu` | 2021 ev-023 | construction at Alapere inwards Ogudu Car Wash |
| `marina-drainage` | 2021 ev-018 | Marina has "no drainage system" |
| `lekki-epe-rehab` | 2024 ev-027–030 | road rehabilitation works at Sangotedo, Awoyaya, Majek, Abraham Adesanya |
| `labora` | 2024 ev-021, ev-053 | new site with no drainage |
| `ibeju-lekki-expy` | 2024 ev-022 | blocked drains on the Ibeju-Lekki Expressway |

## For each site, find (open sources only, as in Task 03)
1. **The structure:** the drain, channel, canal, bridge or road segment the claim refers to, and its official name or number if any
   (Lagos drainage channels are numbered "System N"). Give a point or a short line (2–6 vertices) in lon/lat, from OSM
   (`waterway=*`, `bridge`, `highway`), from `pipeline/geocode.py`, or from a description in the source ("from X junction to Y").
   Say how you located it and give a `location_confidence` (`exact` / `street` / `neighbourhood`).
2. **The alleged change and its dates:** when the buildings went up, the works started or ended, the dam was placed or removed,
   and any official follow-up (demolition notices, removal orders, contractor sanctions, channel dredging) **before or after** the
   flood. Quote ≤ 25 words verbatim, with url, outlet, date and `read_status`, same rules as Task 03.
3. **Image dates to request:** a `before` window (ideally before the change) and an `after` window (around or after the flood).
   If nothing dates the change, say so and use before = 2-3 years earlier, after = flood ±6 months.
4. Anything that would make imagery useless (e.g. an underground culvert, or a drain under a road).

## Output
`events/drainage_sites.json`: `{meta:{...}, sites:[{site_id, event_id, evidence_ids, claim, cause_tags, structure_name,
geometry (GeoJSON Point or LineString), location_confidence, located_how, change_dates:[{what, date or range, source_id}],
followups:[{what, date, source_id, quote}], image_windows:{before:[start,end], after:[start,end]}, notes, sources:[...]}]}`.
Add sites if a source names another specific structure; never drop one, mark it `not_found` instead.
Don't touch `src/`, event folders or other files. No background processes. Don't commit.
Finish with a table: site_id, structure, confidence, dated change (y/n), windows.
