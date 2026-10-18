# Task 03 — media evidence for the 3 July 2024 Lagos flood

Context: `events/lagos-2024-07-03/dossier.md` (§1 timeline, locations) and `event.json` (`sources`).
For a flash flood, geolocated, timestamped media reports are the main ground truth for *where streets flooded and when*.

## Output: `events/lagos-2024-07-03/evidence.geojson`
A GeoJSON FeatureCollection with a top-level `"meta"` (compiled_at UTC, method, notes). Each Feature is a Point (EPSG:4326)
for **one location named in one source**. Properties:

| field | value |
|---|---|
| `id` | `ev-001`, `ev-002`, … |
| `kind` | `news_report` · `news_photo` · `video` · `official_statement` · `social_post` |
| `source_id` | key in `event.json` `sources` (add new sources there, same key style `publisher-YYYY-MM-DD`) |
| `source_url`, `publisher`, `published_at` | as found (ISO 8601 with offset, WAT = +01:00) |
| `observed_at` | when the flooding at this location was observed, if the source says; else `null` |
| `time_confidence` | `exact` · `approx` (e.g. "around 3am") · `day` · `unknown` |
| `location_name` | as written in the source, e.g. "Alapomeji, Iyana-Oworo" |
| `location_confidence` | `point` (specific landmark/junction) · `street` · `neighbourhood` · `lga` |
| `geocode_method` | e.g. `nominatim:"Iyana Oworo, Lagos"` or `manual: Third Mainland Bridge Oworonshoki ramp` |
| `claim` | ≤ 20 words, what the source says happened here (e.g. "road submerged, commuters stranded") |
| `depth_note` | any depth wording ("knee-deep", "cars submerged") or `null` |
| `quote` | ≤ 25-word verbatim excerpt supporting the claim, or `null` if the source couldn't be read |
| `verified` | `false` for all (human review comes later) |
| `read_status` | `read` (you read the article) · `headline_only` (blocked/paywalled; based on title/snippet) |

## Steps
1. Start with every source in `event.json` `sources`. Then search the web for more coverage of **2–4 July 2024** Lagos flooding
   (e.g. Premium Times, Channels TV, The Guardian NG, Vanguard, Nairametrics, Pulse, LASEMA / Lagos State Ministry of Environment
   statements, Nigerian Meteorological Agency). Aim for breadth of *locations*, not volume of articles.
2. One Feature per (source, location). Many ThisDay locations → many Features from one source; that's expected.
3. Geocode with Nominatim (https://nominatim.openstreetmap.org/search, `format=jsonv2`, `countrycodes=ng`, viewbox = AOI bbox,
   `bounded=1`), **max 1 request/second**, User-Agent `FloodTrace/0.1 (research)`. Cache results in `pipeline/cache/geocode.json`.
   If Nominatim can't resolve a name or returns something implausible, place it manually at the neighbourhood centre and say so in
   `geocode_method`, with `location_confidence` lowered accordingly. Every point must fall inside the AOI bbox.
4. Save the reusable bits as `pipeline/geocode.py` (stdlib only) so later events can use it.

## Rules — this is evidence, so accuracy beats coverage
- **Never invent** a location, time, depth or quote. If a source can't be read, use `read_status: headline_only` and only what the
  headline/snippet says.
- Keep quotes short (≤ 25 words) and verbatim.
- Events on other dates (e.g. 27 June Agungi, 7 July Punch) are fine to include — set `observed_at`/`published_at` honestly.
- Don't touch `src/`. Don't commit.
- Finish with a summary: number of features, number of sources (read vs headline_only), locations by confidence, and anything you
  couldn't resolve.
