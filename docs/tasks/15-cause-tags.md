# Task 15 — tag the causes that sources name, for all five events

Context: rainfall and tide alone don't explain which heavy-rain days flood Lagos (`docs/LAGOS_PLAN.md` → "Flood vs no-flood").
Human factors (blocked drains, building on canal setbacks, construction, waste) are the leading suspects, and many reports
**name a cause**. We want those named causes as structured data, so the app can show "what people and officials blamed" next to
the rain. This is about **attribution claims**: who blamed what. It's not about deciding the true cause.

Events: `lagos-2011-07-10`, `lagos-2021-07-16`, `lagos-2022-07-08`, `lagos-2024-07-03`, `lagos-2025-08-04`.

## A. Tag existing evidence
For each `events/<id>/evidence.geojson` feature, re-read its source (or use the quote if already read) and add:

| field | value |
|---|---|
| `causes` | list of tags (below) the **source explicitly attributes the flooding at this location to**, or `[]` |
| `cause_quote` | ≤ 25-word verbatim excerpt stating the cause, or `null` (may differ from `quote`) |
| `cause_attributed_by` | who makes the claim: `official` (name in `cause_who`) · `journalist` · `resident` · `expert` |
| `cause_who` | e.g. "Tokunbo Wahab, Commissioner for Environment" or `null` |

Cause tags (closed list; add a new one only if nothing fits, and list it in `meta`):
- `heavy_rain`: rain intensity/duration named as the cause
- `blocked_drainage`: drains or canals blocked by waste, refuse, silt or debris
- `drainage_capacity`: drains too small, absent, or not completed
- `setback_encroachment`: buildings or structures on drainage channels, setbacks, floodplains or wetlands
- `construction`: road works, a contractor or a project obstructing flow (e.g. 2025 Ikorodu waterway)
- `canal_overflow`: a named canal, river or stream overflowed
- `lagoon_tide`: tide, high lagoon level or ocean backing up drains
- `ocean_surge`: sea or ocean surge or overtopping on the coast
- `dam_release`: Oyan or other reservoir releases
- `land_reclamation`: sand-filling or reclamation of wetland or lagoon
- `low_lying_terrain`: natural topography or high water table named

**Rules:** tag only what the source states, never what seems likely. "Heavy downpour flooded X" → `heavy_rain` only. A
statement about the city in general ("refuse in drains caused flooding across Lagos") is **not** attributed to a specific street.
Put it in part B. Don't change `id`, coordinates, `quote`, `quote_check` or other existing fields.

## B. Find the cause statements
Search for statements in each event's window **and up to ~4 weeks after** in which officials or outlets attribute **that** flood to
causes: Lagos Ministry of Environment / LASEPA / LAWMA / LASEMA / Drainage Services, NEMA, NIHSA, the Governor, the Commissioner
(e.g. demolitions on drainage setbacks, "drainage blockage", sand-filling, contractors). Add each as a new evidence feature with
`kind: "official_statement"` (or `news_report`). Place it at the named site if there is one, otherwise at the neighbourhood or LGA
it names (`location_confidence` accordingly). A citywide statement with no place goes in `meta.citywide_cause_statements`
(source_id, url, who, date, causes, cause_quote) instead of on the map. Add new sources to `event.json` `sources` only.
Same rules as Task 03 (`docs/tasks/03-media-evidence.md`): verbatim ≤ 25-word quotes, `read_status`, Wayback for dead links,
`pipeline/geocode.py` for places, and all points inside the AOI.

## Output
- Updated `evidence.geojson` per event. Continue numbering after the highest existing `id`; never renumber.
- `meta.cause_summary` per event: counts per tag (features + citywide), split by `cause_attributed_by`.
- Read each file fresh just before writing it. Write once per event. No background processes.
  Don't touch `src/` or anything else. Don't commit.

Finish with a table per event: tag × count (official / journalist / resident / expert), plus new features added and anything
ambiguous.
