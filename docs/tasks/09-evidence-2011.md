# Task 09 — media evidence for the 10 July 2011 Lagos flood

Same job as Task 03 (`docs/tasks/03-media-evidence.md`), for a different event. Read that brief — **its schema and rules apply
unchanged** — plus `events/lagos-2011-07-10/event.json` and the 2011 entry in `events/catalog_review.json` (your Task 08 notes:
13 named areas, Vanguard / Al Jazeera / ReliefWeb sources).

Output: `events/lagos-2011-07-10/evidence.geojson` (new file; ids `ev-001`…).

Specifics for 2011:
- Many 2011 articles are archived or moved; try the Wayback Machine (web.archive.org) for dead links and record the archive URL
  as `source_url` with the original in a new optional `original_url` field.
- Expect named areas from Task 08: Dopemu, Aboru, Agbado-Oke Odo, Ogba, Agege, Orile-Agege, Iyana-Ipaja, Ikoyi, Victoria Island,
  Apapa, Lekki, Ajegunle, Jakande Estate Oke-Afa Isolo — plus whatever else the sources name. One feature per (source, location).
- Casualty figures go in `claim`/`quote` only when a readable source states them for that location. Keep Lagos and non-Lagos
  (e.g. Ibadan, Ogun) figures separate — drop non-Lagos locations.
- Geocode with the fixed `pipeline/geocode.py` (place-type filtering, area hints, aliases). Spot-check each result's district;
  if a name matches a street rather than the place, place manually and lower confidence.
- Run any build script to completion **before** reporting, then confirm the file isn't modified afterwards; no background
  processes left running. Don't touch `src/` or the 2024 event folder. Don't commit.
- Finish with: features, sources (read / headline_only / archive), locations by confidence, anything unresolved.
